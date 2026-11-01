/* =============================================================================
 * task3_esp32_bridge.ino
 * Task 3 : ESP32 = SPI master that pulls audio blocks from the DE10-Lite FPGA
 *          and forwards them to the host PC over USB serial (binary frames).
 *
 *   FPGA (sampling @16 kS/s, BRAM ping-pong) --SPI--> ESP32 --USB--> PC
 *
 * The ESP32 does NOT sample anything: Fs is set by the FPGA clock. The ESP32
 * only moves finished blocks, so its timing can never disturb the sampling.
 *
 * Board : ESP32-S3 UNO (purple, Arduino-UNO form factor)  -- default
 *         Arduino IDE: board "ESP32S3 Dev Module", core 2.x or 3.x
 *         (a plain ESP32 dev board also works: set BOARD_ESP32_S3 to 0)
 *
 * Wiring ESP32-S3 UNO (3.3 V logic on both sides, COMMON GND is mandatory):
 *   UNO pin   S3 GPIO          DE10-Lite JP1
 *   D13  ->   IO12 (SCK)  ->   GPIO[0]  pin 1   spi_sclk
 *   D11  ->   IO11 (MOSI) ->   GPIO[1]  pin 2   spi_mosi
 *   D12  <-   IO13 (MISO) <-   GPIO[2]  pin 3   spi_miso
 *   D10  ->   IO10 (CS)   ->   GPIO[3]  pin 4   spi_cs_n
 *   D7   <-   IO14 (DRDY) <-   GPIO[4]  pin 5   drdy
 *   GND  --   GND         --   pin 12 or 30
 *   IO10..IO13 are the S3's native FSPI pins. Do NOT use D4/D5 (IO19/IO20 =
 *   USB D-/D+) or D6/D9 (IO3/IO46 = strapping pins) for this link.
 *
 * Plain ESP32 dev board: SCK 18, MOSI 23, MISO 19, CS 5, DRDY 4.
 *
 * ---------------------------------------------------------------- FPGA SPI
 *   mode 0, MSB first, 16-bit big-endian words, N + 6 words per transaction
 *   w0 : 0xC3 | STATUS(bit0 ready)    (MOSI byte0 = command)
 *   w1 : 0xA55A   w2 : SEQ   w3 : FLAGS<<8 | DROPS   w4 : N
 *   w5..w(N+4) : samples (12-bit)     w(N+5) : checksum = sum(samples) mod 2^16
 *   CMD 0x01 = READ_BLOCK, 0x02 = READ_TEST (ramp 0..N-1, link test)
 *
 * ---------------------------------------------------------------- HOST USB
 *   All little-endian, one frame per block:
 *   off size field
 *    0   4   sync      AA 55 33 CC
 *    4   2   seq       FPGA block counter (gaps = dropped blocks)
 *    6   2   n         samples in this frame (1024)
 *    8   1   fpga_flags  b0 valid, b1 test ramp, b3..2 source (0 MCP,1 MAX10,2 tone)
 *    9   1   fpga_drops  blocks dropped inside the FPGA since last read
 *   10   2   spi_errs  ESP32: frames rejected (sync/checksum), cumulative
 *   12   2   esp_drops ESP32: blocks lost because the USB queue was full
 *   14   4   t_us      ESP32 micros() when DRDY was served
 *   18   2   fs        nominal sample rate (16000)
 *   20  2n   samples   uint16 (12-bit ADC code)
 *  20+2n 2   checksum  sum of samples mod 2^16
 *
 * Host -> ESP32 single-character commands:  't' = test ramp, 'n' = normal
 * =============================================================================
 */
#include <Arduino.h>
#include <SPI.h>

// ============================== USER SETTINGS ================================
#define BOARD_ESP32_S3 1                         // 1 = ESP32-S3 UNO, 0 = ESP32 dev board
#if BOARD_ESP32_S3
static const int      PIN_SCK      = 12;        // UNO D13
static const int      PIN_MISO     = 13;        // UNO D12
static const int      PIN_MOSI     = 11;        // UNO D11
static const int      PIN_CS       = 10;        // UNO D10
static const int      PIN_DRDY     = 14;        // UNO D7
#else
static const int      PIN_SCK      = 18;
static const int      PIN_MISO     = 19;
static const int      PIN_MOSI     = 23;
static const int      PIN_CS       = 5;
static const int      PIN_DRDY     = 4;
#endif

static const uint32_t SPI_HZ       = 4000000;   // 1..8 MHz (jumper wires: <= 4 MHz)
static const uint32_t SERIAL_BAUD  = 921600;    // 921600 or 2000000 (must match host)
static const uint16_t N            = 1024;      // must match FPGA ADDR_W (2^10)
static const uint16_t FS_NOMINAL   = 16000;
static const int      NUM_BUFS     = 6;         // ESP32-side block queue depth
// ============================================================================

static const uint8_t  CMD_READ_BLOCK = 0x01;
static const uint8_t  CMD_READ_TEST  = 0x02;
static const size_t   SPI_WORDS      = N + 6;
static const size_t   SPI_BYTES      = SPI_WORDS * 2;
static const size_t   HDR_BYTES      = 20;
static const size_t   FRAME_BYTES    = HDR_BYTES + 2 * N + 2;

struct Block {
  uint16_t seq;
  uint8_t  flags;
  uint8_t  drops;
  uint32_t t_us;
  uint16_t checksum;
  uint16_t samples[N];
};

static Block          pool[NUM_BUFS];
static QueueHandle_t  freeQ, fullQ;
static SemaphoreHandle_t drdySem;
static uint8_t        spiTx[SPI_BYTES];
static uint8_t        spiRx[SPI_BYTES];
static uint8_t        frame[FRAME_BYTES];

static volatile uint8_t  readCmd   = CMD_READ_BLOCK;
static volatile uint16_t spiErrs   = 0;
static volatile uint16_t espDrops  = 0;

// --------------------------------------------------------------- DRDY ISR
void IRAM_ATTR onDrdy() {
  BaseType_t woken = pdFALSE;
  xSemaphoreGiveFromISR(drdySem, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static inline uint16_t be16(const uint8_t *p) { return (uint16_t(p[0]) << 8) | p[1]; }
static inline void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static inline void put32(uint8_t *p, uint32_t v) {
  p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}

// ------------------------------------------------ one SPI transaction (frame)
static bool readFpgaBlock(uint8_t cmd, Block *b) {
  memset(spiTx, 0, sizeof(spiTx));
  spiTx[0] = cmd;

  SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(PIN_CS, LOW);
  delayMicroseconds(2);              // FPGA needs ~60 ns to see CS (2-FF sync)
  SPI.transferBytes(spiTx, spiRx, SPI_BYTES);
  delayMicroseconds(1);
  digitalWrite(PIN_CS, HIGH);        // FPGA releases the bank on this edge
  SPI.endTransaction();

  // ---- validate
  if (spiRx[0] != 0xC3)                 return false;   // MISO not connected?
  if (be16(&spiRx[2]) != 0xA55A)        return false;   // sync
  if (be16(&spiRx[8]) != N)             return false;   // block size
  uint16_t flagsDrop = be16(&spiRx[6]);
  b->seq   = be16(&spiRx[4]);
  b->flags = flagsDrop >> 8;
  b->drops = flagsDrop & 0xFF;
  if ((b->flags & 0x01) == 0)           return false;   // no valid block locked

  uint16_t sum = 0;
  const uint8_t *p = &spiRx[10];
  for (uint16_t k = 0; k < N; k++, p += 2) {
    uint16_t s = be16(p);
    b->samples[k] = s;
    sum += s;
  }
  b->checksum = be16(p);
  return sum == b->checksum;
}

// ------------------------------------------- SPI task (core 0, high priority)
static void spiTask(void *) {
  for (;;) {
    xSemaphoreTake(drdySem, pdMS_TO_TICKS(20));  // edge, or poll every 20 ms
    while (digitalRead(PIN_DRDY) == HIGH) {
      uint32_t t = micros();
      int idx;
      if (xQueueReceive(freeQ, &idx, 0) != pdTRUE) {
        // USB is too slow: leave the block in the FPGA (it will count a drop)
        espDrops++;
        vTaskDelay(1);
        break;
      }
      uint8_t cmd = readCmd;
      bool ok = readFpgaBlock(cmd, &pool[idx]);
      pool[idx].t_us = t;
      if (ok) {
        xQueueSend(fullQ, &idx, portMAX_DELAY);
      } else {
        spiErrs++;
        xQueueSend(freeQ, &idx, portMAX_DELAY);
        vTaskDelay(1);
      }
      if (cmd == CMD_READ_TEST) {     // test read does not release the bank
        vTaskDelay(pdMS_TO_TICKS(60)); // ~1 block period, then read again
        break;
      }
    }
  }
}

// ----------------------------------------------------------------- setup
void setup() {
  Serial.setTxBufferSize(8192);
  Serial.begin(SERIAL_BAUD);

  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_DRDY, INPUT_PULLDOWN);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);   // CS driven manually

  freeQ   = xQueueCreate(NUM_BUFS, sizeof(int));
  fullQ   = xQueueCreate(NUM_BUFS, sizeof(int));
  drdySem = xSemaphoreCreateBinary();
  for (int i = 0; i < NUM_BUFS; i++) xQueueSend(freeQ, &i, 0);

  attachInterrupt(digitalPinToInterrupt(PIN_DRDY), onDrdy, RISING);
  xTaskCreatePinnedToCore(spiTask, "spi", 4096, nullptr, 5, nullptr, 0);
}

// ------------------------------------------- loop = USB sender (core 1)
void loop() {
  // host commands
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 't') readCmd = CMD_READ_TEST;
    if (c == 'n') readCmd = CMD_READ_BLOCK;
  }

  int idx;
  if (xQueueReceive(fullQ, &idx, pdMS_TO_TICKS(50)) != pdTRUE) return;
  Block *b = &pool[idx];

  frame[0] = 0xAA; frame[1] = 0x55; frame[2] = 0x33; frame[3] = 0xCC;
  put16(&frame[4],  b->seq);
  put16(&frame[6],  N);
  frame[8] = b->flags;
  frame[9] = b->drops;
  put16(&frame[10], spiErrs);
  put16(&frame[12], espDrops);
  put32(&frame[14], b->t_us);
  put16(&frame[18], FS_NOMINAL);
  uint8_t *p = &frame[HDR_BYTES];
  for (uint16_t k = 0; k < N; k++, p += 2) put16(p, b->samples[k]);
  put16(p, b->checksum);

  xQueueSend(freeQ, &idx, 0);         // buffer copied into 'frame' -> recycle
  Serial.write(frame, FRAME_BYTES);   // 2070 bytes / 64 ms = 32 kB/s
}
