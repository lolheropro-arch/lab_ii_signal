/*
 * Task 2 — Real-Time Audio Sampling: ESP32 + INMP441 (I2S)
 *
 * Wiring (ESP32 DevKit V1):
 *   INMP441 VDD -> 3.3V
 *   INMP441 GND -> GND
 *   INMP441 L/R -> GND   (left channel)
 *   INMP441 SCK -> GPIO 18 (BCLK)
 *   INMP441 WS  -> GPIO 19 (LRCLK)
 *   INMP441 SD  -> GPIO 21 (DIN)
 *
 * Design:
 *   - Sampling timing comes from the I2S peripheral clock + DMA (hardware),
 *     never from the CPU or from Serial.
 *   - acqTask (high priority) reads I2S blocks and converts them into one of
 *     two ping-pong buffers. loop() sends completed buffers over Serial.
 *   - If Serial is too slow, a block is dropped (counted), but I2S sampling
 *     keeps running at a constant rate.
 *
 * Frame format sent to the host (little-endian):
 *   [0xAA 0x55 0xAA 0x55] [uint32 seq] [uint32 drops] [N x int16 samples]
 *   = 12 + 2*N bytes per block
 *
 * IMPORTANT: Do not use Serial.print() anywhere — it would corrupt the binary stream.
 *            Close the Arduino Serial Monitor before running MATLAB.
 */

#include <Arduino.h>
#include <driver/i2s.h>

// ---------------- Pins ----------------
#define PIN_SCK     18
#define PIN_WS      19
#define PIN_SD      21
#define PIN_TIMING  4      // toggles once per block -> square wave, period = N/FS = 64 ms

// ---------------- Settings ----------------
#define I2S_PORT    I2S_NUM_0
#define FS          16000  // sample rate (S/s)
#define N           1024   // samples per block
#define BAUD        921600
#define SHIFT       14     // 32-bit I2S word -> int16. Larger = quieter, smaller = louder (risk of clipping)

// If every sample is 0 (flat line), change this to I2S_CHANNEL_FMT_ONLY_RIGHT
#define CHANNEL_FMT I2S_CHANNEL_FMT_ONLY_LEFT

// ---------------- Buffers ----------------
static int32_t  rawBuf[N];            // used only by acqTask
static int16_t  pingPong[2][N];       // double buffer
static uint32_t blockSeq[2];          // sequence number of each buffer
static QueueHandle_t freeQ;           // indices of buffers that are free to fill
static QueueHandle_t readyQ;          // indices of buffers that are ready to send
static volatile uint32_t dropCount = 0;

static void i2sInit() {
  i2s_config_t cfg = {};
  cfg.mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate          = FS;
  cfg.bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT;   // INMP441: 24-bit data in a 32-bit slot
  cfg.channel_format       = CHANNEL_FMT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count        = 8;
  cfg.dma_buf_len          = 256;
  cfg.use_apll             = false;
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);

  i2s_pin_config_t pins = {};
  pins.mck_io_num   = I2S_PIN_NO_CHANGE;
  pins.bck_io_num   = PIN_SCK;
  pins.ws_io_num    = PIN_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num  = PIN_SD;
  i2s_set_pin(I2S_PORT, &pins);

  i2s_zero_dma_buffer(I2S_PORT);
}

// Acquisition: always keeps reading I2S, independent of Serial
static void acqTask(void *arg) {
  uint32_t seq = 0;
  bool level = false;

  for (;;) {
    // 1) Read exactly N samples (blocks until the DMA delivers them)
    size_t got = 0;
    const size_t want = sizeof(rawBuf);
    uint8_t *p = (uint8_t *)rawBuf;
    while (got < want) {
      size_t n = 0;
      i2s_read(I2S_PORT, p + got, want - got, &n, portMAX_DELAY);
      got += n;
    }

    level = !level;
    digitalWrite(PIN_TIMING, level);   // block timing marker for the oscilloscope

    // 2) Get a free ping-pong buffer; if none, drop this block (sampling continues)
    uint8_t idx;
    if (xQueueReceive(freeQ, &idx, 0) != pdTRUE) {
      dropCount++;
      seq++;
      continue;
    }

    // 3) Convert 32-bit words to int16 with saturation
    for (int i = 0; i < N; i++) {
      int32_t v = rawBuf[i] >> SHIFT;
      if (v >  32767) v =  32767;
      if (v < -32768) v = -32768;
      pingPong[idx][i] = (int16_t)v;
    }
    blockSeq[idx] = seq++;

    // 4) Hand the buffer to the transmitter
    xQueueSend(readyQ, &idx, portMAX_DELAY);
  }
}

void setup() {
  Serial.setTxBufferSize(8192);
  Serial.begin(BAUD);

  pinMode(PIN_TIMING, OUTPUT);

  freeQ  = xQueueCreate(2, sizeof(uint8_t));
  readyQ = xQueueCreate(2, sizeof(uint8_t));
  uint8_t b0 = 0, b1 = 1;
  xQueueSend(freeQ, &b0, 0);
  xQueueSend(freeQ, &b1, 0);

  i2sInit();

  // High-priority acquisition task on core 0; loop() (transmission) runs on core 1
  xTaskCreatePinnedToCore(acqTask, "acq", 4096, NULL, configMAX_PRIORITIES - 1, NULL, 0);
}

// Transmission: send completed blocks, then return the buffer to freeQ
void loop() {
  uint8_t idx;
  if (xQueueReceive(readyQ, &idx, portMAX_DELAY) == pdTRUE) {
    uint8_t hdr[12] = {0xAA, 0x55, 0xAA, 0x55};
    uint32_t s = blockSeq[idx];
    uint32_t d = dropCount;
    memcpy(&hdr[4], &s, 4);
    memcpy(&hdr[8], &d, 4);

    Serial.write(hdr, sizeof(hdr));
    Serial.write((uint8_t *)pingPong[idx], N * sizeof(int16_t));

    xQueueSend(freeQ, &idx, portMAX_DELAY);
  }
}
