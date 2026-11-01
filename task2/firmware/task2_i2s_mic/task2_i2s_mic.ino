/*
 * ============================================================================
 *  Signals & Systems Lab - Task 2
 *  Real-Time Audio Sampling : ESP32-S3 + INMP441 (I2S MEMS microphone)
 *
 *  วิธีทำงาน
 *    1) I2S peripheral ของ ESP32 สร้าง clock (SCK, WS) ให้ไมค์ ไมค์ทำ ADC เองแล้วส่งข้อมูล
 *       แบบ digital กลับมาทางขา SD  จังหวะ sampling จึงมาจาก hardware clock ทั้งหมด
 *       (WS = 1 คาบต่อ 1 sample = 16 kHz)  ไม่มี timer หรือ micros()/millis() ใน loop()
 *    2) DMA ของ I2S เขียนข้อมูลลง buffer ในหน่วยความจำเอง (ไม่ต้องใช้ CPU ต่อ sample)
 *    3) "reader task" (core 0, priority สูง) ดึงข้อมูลจาก DMA ครั้งละ 1 block
 *       แปลงจาก 24 บิต (อยู่ในคำ 32 บิต) เป็น int16 แล้วเก็บลง ping-pong buffer
 *    4) loop() ส่ง block ที่เต็มแล้วออก serial เป็น binary frame  (เหมือน Task 1)
 *
 *  ใช้สคริปต์ MATLAB ตัวเดียวกับ Task 1 ได้เลย (matlab/realtime_audio_scope.m)
 *  frame บอก fs = 16000, format = 1 (int16), bits = 16  MATLAB ปรับตามเอง
 *  ฝั่ง MATLAB ให้ดูแกน FFT เป็น dBFS และ waveform เป็น counts
 *  (หน่วย dBV / V ไม่มีความหมายกับไมค์ digital)
 *
 * ----------------------------------------------------------------------------
 *  การต่อวงจร INMP441  (ใช้ไฟ 3.3 V เท่านั้น และต้องต่อ GND ร่วม)
 *      INMP441 VDD  ->  3V3
 *      INMP441 GND  ->  GND
 *      INMP441 SCK  ->  I2S_SCK_PIN   (ค่าเริ่มต้น GPIO18)   bit clock (BCLK)
 *      INMP441 WS   ->  I2S_WS_PIN    (ค่าเริ่มต้น GPIO17)   word select (LRCLK)
 *      INMP441 SD   ->  I2S_SD_PIN    (ค่าเริ่มต้น GPIO21)   ข้อมูลจากไมค์
 *      INMP441 L/R  ->  GND           = ช่องซ้าย  (ถ้าต่อ 3V3 ให้ตั้ง MIC_ON_RIGHT 1)
 *    ห้ามปล่อย L/R ลอย  ไมค์จะสุ่มช่อง หรือไม่ส่งข้อมูลเลย
 *
 *  วัดด้วย oscilloscope
 *      ขา WS  : square wave 16 kHz  = sampling rate จริง
 *      ขา SCK : 64 x 16 kHz = 1.024 MHz  (2 ช่อง x 32 บิต ต่อ 1 sample)
 *      BLOCK_PIN : toggle 1 ครั้งต่อ 1 block  ->  คาบครึ่งลูก = N / Fs = 64 ms
 *
 * ----------------------------------------------------------------------------
 *  การตั้งค่า Arduino IDE  (เหมือนกันทั้ง Windows และ Linux)
 *      Tools > Board            : "ESP32S3 Dev Module"
 *      Tools > USB CDC On Boot  : "Disabled"
 *      เสียบสาย USB ที่ช่องที่เขียนว่า "UART" หรือ "COM" บนบอร์ด
 *    ต้องใช้ Arduino-ESP32 core 3.x ขึ้นไป  (Tools > Board > Boards Manager > esp32)
 *
 *  ชื่อ serial port
 *      Windows : COM3, COM5, ...       ดูใน Device Manager > Ports (COM & LPT)
 *      Linux   : /dev/ttyUSB0 หรือ /dev/ttyACM0     ดูด้วยคำสั่ง  ls /dev/ttyUSB* /dev/ttyACM*
 *                ถ้าเปิด port ไม่ได้ (permission denied) ให้รัน
 *                    sudo usermod -aG dialout $USER      แล้ว logout/login ใหม่
 *
 * ----------------------------------------------------------------------------
 *  รูปแบบ frame (เหมือน Task 1 ทุกอย่าง ต่างแค่ค่าใน header)
 *        0     4 byte      sync word  = A5 5A C3 3C
 *        4     uint32      seq
 *        8     uint32      fs         = SAMPLE_RATE_HZ
 *       12     uint16      n          = BLOCK_SIZE
 *       14     uint16      missed     : จำนวน sample ที่หายเพราะ DMA ล้น (ควรเป็น 0)
 *       16     uint8       format     = 1  (int16 signed)
 *       17     uint8       bits       = 16
 *       18     uint16      reserved   = 0
 *       20     int16 x n   samples
 *     20+2n    uint16      checksum   : ผลรวมของ sample (มองเป็น uint16) mod 65536
 * ============================================================================
 */

#include <Arduino.h>

#if !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR < 3
#error "ต้องใช้ Arduino-ESP32 core 3.x ขึ้นไป  อัปเดตใน Boards Manager"
#endif

#include "driver/i2s_std.h"

// ============================================================================
//  >>>>>>>>>>>>>>>>>>>>>>>>   ส่วนตั้งค่า (แก้ตรงนี้)   <<<<<<<<<<<<<<<<<<<<<<<<
// ============================================================================

// Sampling rate (Hz)  โจทย์กำหนดค่าเริ่มต้น 16 kS/s   INMP441 รองรับประมาณ 7.8 - 50 kHz
#define SAMPLE_RATE_HZ   16000

// จำนวน sample ต่อ 1 block (= ขนาด FFT ฝั่ง MATLAB)
#define BLOCK_SIZE       1024

// ขา I2S  (ESP32-S3 เลือกขาไหนก็ได้ผ่าน GPIO matrix  เลี่ยง GPIO0, 3, 45, 46 ที่เป็น strapping pin,
// GPIO19-20 ที่เป็น USB และ GPIO26-37 ที่โมดูลบางรุ่นใช้กับ flash/PSRAM)
// ห้ามใช้ GPIO19 / GPIO20 บน ESP32-S3 เพราะเป็นขา USB D- / D+ ของชิป
#define I2S_SCK_PIN      18
#define I2S_WS_PIN       17
#define I2S_SD_PIN       21

// 0 = ขา L/R ของไมค์ต่อ GND (ช่องซ้าย)    1 = ขา L/R ต่อ 3V3 (ช่องขวา)
#define MIC_ON_RIGHT     0

// ขยายสัญญาณแบบ digital ก่อนตัดเป็น 16 บิต  (0 = ไม่ขยาย, ค่า dBFS ตรงตาม datasheet)
// แต่ละ 1 ขั้น = x2 = +6.02 dB    ถ้าเสียงพูดเบามากในกราฟ ลอง 2 ถึง 4
// ถ้าตั้งมากกว่า 0 ค่า dBFS ใน MATLAB จะสูงกว่าจริง GAIN_SHIFT x 6.02 dB (จดไว้ตอนตอบคำถาม)
#define GAIN_SHIFT       0

// ขา GPIO ที่ toggle 1 ครั้งต่อ 1 block  ตั้งเป็น -1 ถ้าไม่ใช้
#define BLOCK_PIN        5

// Baud rate ของ serial  (ต้องตรงกับสคริปต์ MATLAB)
// ต้องการอย่างน้อยประมาณ 16000 x 2 byte x 10 bit = 320000 bit/s
#define SERIAL_BAUD      1000000

// 0 = ส่ง binary frame ให้ MATLAB (โหมดใช้งานจริง)
// 1 = พิมพ์สถิติของแต่ละ block เป็นข้อความ ไว้ดูใน Serial Monitor เพื่อเช็กวงจร
#define TEXT_DEBUG       0

// ---- ปกติไม่ต้องแก้ส่วนข้างล่างนี้ ------------------------------------------

#define STREAM           Serial

// ขนาด DMA buffer : DMA_DESC_NUM ชุด x DMA_FRAME_NUM sample  = 8 x 256 = 2048 sample (128 ms)
// เป็นพื้นที่สำรองถ้า reader task ถูกขัดจังหวะ
#define DMA_DESC_NUM     8
#define DMA_FRAME_NUM    256

// INMP441 ต้องใช้เวลาเริ่มทำงานหลังได้ clock (datasheet ~ 2^18 SCK cycles ~ 256 ms ที่ 1.024 MHz)
// ข้อมูลช่วงนี้เป็นค่าขยะ จึงอ่านทิ้งก่อน
#define STARTUP_DISCARD_MS  300

#define READER_CORE      0

// ============================================================================
//  จบส่วนตั้งค่า
// ============================================================================

static_assert(BLOCK_SIZE >= 2 && BLOCK_SIZE <= 65535, "BLOCK_SIZE must fit in uint16");
static_assert(GAIN_SHIFT >= 0 && GAIN_SHIFT <= 8, "GAIN_SHIFT must be 0..8");

// ---- frame header (เหมือน Task 1) ------------------------------------------
struct __attribute__((packed)) FrameHeader {
  uint8_t  sync[4];
  uint32_t seq;
  uint32_t fs;
  uint16_t n;
  uint16_t missed;
  uint8_t  format;     // 0 = uint16, 1 = int16
  uint8_t  bits;
  uint16_t reserved;
};
static_assert(sizeof(FrameHeader) == 20, "unexpected header size");

struct BlockInfo {
  uint8_t  index;
  uint32_t seq;
  uint16_t missed;
};

// ---- buffers ---------------------------------------------------------------
static int32_t rawBuf[BLOCK_SIZE];            // ข้อมูล 32 บิตจาก I2S (24 บิตชิดซ้าย)
static int16_t sampleBuf[2][BLOCK_SIZE];      // ping-pong buffer ที่จะส่งออก

static volatile bool     txBusy        = false;
static volatile uint32_t droppedBlocks = 0;
static volatile uint32_t dmaOverflows  = 0;   // นับครั้งที่ DMA ล้น (เขียนจาก ISR)

static i2s_chan_handle_t rxChan     = NULL;
static QueueHandle_t     blockQueue = NULL;

// ----------------------------------------------------------------------------
//  ISR callback : DMA ล้น (reader task อ่านไม่ทัน ข้อมูล 1 DMA buffer หายไป)
// ----------------------------------------------------------------------------
static bool IRAM_ATTR onRxOverflow(i2s_chan_handle_t handle, i2s_event_data_t *event, void *ctx) {
  (void)handle; (void)event; (void)ctx;
  dmaOverflows = dmaOverflows + 1;
  return false;
}

// ----------------------------------------------------------------------------
//  ตั้งค่า I2S : master, รับอย่างเดียว, Philips format, slot 32 บิต, mono
// ----------------------------------------------------------------------------
static bool startI2S() {
  i2s_chan_config_t chanCfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  chanCfg.dma_desc_num  = DMA_DESC_NUM;
  chanCfg.dma_frame_num = DMA_FRAME_NUM;
  if (i2s_new_channel(&chanCfg, NULL, &rxChan) != ESP_OK) return false;

  // INMP441 ส่ง 24 บิต ในช่อง 32 บิต (ต้องใช้ 64 SCK ต่อ 1 WS) -> ใช้ slot 32 บิต
  i2s_std_clk_config_t  clkCfg  = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE_HZ);
  i2s_std_slot_config_t slotCfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,
                                                                       I2S_SLOT_MODE_MONO);
  slotCfg.slot_mask = MIC_ON_RIGHT ? I2S_STD_SLOT_RIGHT : I2S_STD_SLOT_LEFT;

  i2s_std_config_t stdCfg = {};
  stdCfg.clk_cfg  = clkCfg;
  stdCfg.slot_cfg = slotCfg;
  stdCfg.gpio_cfg.mclk = I2S_GPIO_UNUSED;               // INMP441 ไม่ใช้ MCLK
  stdCfg.gpio_cfg.bclk = (gpio_num_t)I2S_SCK_PIN;
  stdCfg.gpio_cfg.ws   = (gpio_num_t)I2S_WS_PIN;
  stdCfg.gpio_cfg.dout = I2S_GPIO_UNUSED;
  stdCfg.gpio_cfg.din  = (gpio_num_t)I2S_SD_PIN;
  stdCfg.gpio_cfg.invert_flags.mclk_inv = false;
  stdCfg.gpio_cfg.invert_flags.bclk_inv = false;
  stdCfg.gpio_cfg.invert_flags.ws_inv   = false;
  if (i2s_channel_init_std_mode(rxChan, &stdCfg) != ESP_OK) return false;

  i2s_event_callbacks_t cbs = {};
  cbs.on_recv_q_ovf = onRxOverflow;
  i2s_channel_register_event_callback(rxChan, &cbs, NULL);

  return i2s_channel_enable(rxChan) == ESP_OK;
}

// อ่าน 1 block เต็ม ๆ จาก DMA (รอจนครบ)
static bool readRawBlock() {
  size_t got = 0;
  esp_err_t err = i2s_channel_read(rxChan, rawBuf, sizeof(rawBuf), &got, portMAX_DELAY);
  return err == ESP_OK && got == sizeof(rawBuf);
}

// 24 บิตชิดซ้ายในคำ 32 บิต -> int16
//   raw >> 16 = เอา 16 บิตบนสุด  (full scale ของไมค์ = full scale ของ int16  ค่า dBFS จึงตรง)
//   GAIN_SHIFT > 0 = เลื่อนน้อยลง (ขยาย) แล้วตัดไม่ให้เกินช่วง int16
static inline int16_t toInt16(int32_t raw) {
  int32_t v = raw >> (16 - GAIN_SHIFT);
  if (v >  32767) v =  32767;
  if (v < -32768) v = -32768;
  return (int16_t)v;
}

// ----------------------------------------------------------------------------
//  Reader task : รอ DMA ครบ 1 block -> แปลง -> ใส่ ping-pong buffer -> แจ้ง loop()
// ----------------------------------------------------------------------------
static void readerTask(void *arg) {
  (void)arg;

  uint8_t  fill        = 0;
  uint32_t seq         = 0;
  uint32_t lastOvf     = 0;
#if BLOCK_PIN >= 0
  bool pinLevel = false;
#endif

  // ทิ้งข้อมูลช่วงไมค์เพิ่งเริ่มทำงาน
  const uint32_t discardBlocks =
      (uint32_t)((uint64_t)STARTUP_DISCARD_MS * SAMPLE_RATE_HZ / 1000 / BLOCK_SIZE) + 1;
  for (uint32_t i = 0; i < discardBlocks; i++) readRawBlock();
  lastOvf = dmaOverflows;

  for (;;) {
    if (!readRawBlock()) continue;

#if BLOCK_PIN >= 0
    pinLevel = !pinLevel;
    digitalWrite(BLOCK_PIN, pinLevel);
#endif

    // นับ sample ที่หายระหว่าง block นี้ (1 ครั้งที่ล้น = 1 DMA buffer = DMA_FRAME_NUM sample)
    uint32_t ovf    = dmaOverflows;
    uint32_t missed = (ovf - lastOvf) * DMA_FRAME_NUM;
    lastOvf = ovf;

    if (!txBusy) {
      int16_t *dst = sampleBuf[fill];
      for (uint32_t i = 0; i < BLOCK_SIZE; i++) dst[i] = toInt16(rawBuf[i]);

      BlockInfo info;
      info.index  = fill;
      info.seq    = seq;
      info.missed = (missed > 65535u) ? 65535u : (uint16_t)missed;
      txBusy = true;
      xQueueSend(blockQueue, &info, 0);
      fill ^= 1;
    } else {
      // loop() ยังส่ง block ก่อนหน้าไม่เสร็จ -> ทิ้ง block นี้ แต่ยังอ่าน DMA ต่อ (DMA จึงไม่ล้น)
      droppedBlocks = droppedBlocks + 1;
    }
    seq++;
  }
}

// ----------------------------------------------------------------------------
void setup() {
  STREAM.begin(SERIAL_BAUD);

#if BLOCK_PIN >= 0
  pinMode(BLOCK_PIN, OUTPUT);
  digitalWrite(BLOCK_PIN, LOW);
#endif

  blockQueue = xQueueCreate(1, sizeof(BlockInfo));

  if (!startI2S()) {
    // ส่งเป็นข้อความเสมอ (MATLAB จะข้ามไปเพราะไม่มี sync word)  เปิด Serial Monitor เพื่อดู
    for (;;) {
      STREAM.println("I2S init failed - check pin numbers / board settings");
      delay(1000);
    }
  }

  xTaskCreatePinnedToCore(readerTask, "i2s_reader", 4096, NULL,
                          configMAX_PRIORITIES - 1, NULL, READER_CORE);
}

// ----------------------------------------------------------------------------
//  loop() : รอ block ที่เต็มแล้ว แล้วส่งออก serial
// ----------------------------------------------------------------------------
void loop() {
  BlockInfo info;
  if (xQueueReceive(blockQueue, &info, portMAX_DELAY) != pdTRUE) return;

  const int16_t *data = sampleBuf[info.index];

#if TEXT_DEBUG
  // ถ้า min = max = 0 หรือ -1 ตลอด : ไม่มีข้อมูลจากไมค์  เช็ก SD, L/R, VDD
  int16_t vmin = 32767, vmax = -32768;
  int64_t sum = 0;
  double  sq  = 0.0;
  for (uint32_t i = 0; i < BLOCK_SIZE; i++) {
    if (data[i] < vmin) vmin = data[i];
    if (data[i] > vmax) vmax = data[i];
    sum += data[i];
  }
  double mean = (double)sum / BLOCK_SIZE;
  for (uint32_t i = 0; i < BLOCK_SIZE; i++) {
    double d = data[i] - mean;
    sq += d * d;
  }
  double rms    = sqrt(sq / BLOCK_SIZE);
  double rmsDb  = 20.0 * log10((rms > 1e-3 ? rms : 1e-3) / 32768.0);
  STREAM.printf("seq=%lu  min=%d  max=%d  mean=%.1f  rms=%.1f (%.1f dBFS)  missed=%u  dropped=%lu\n",
                (unsigned long)info.seq, vmin, vmax, mean, rms, rmsDb,
                (unsigned)info.missed, (unsigned long)droppedBlocks);
#else
  FrameHeader hdr;
  hdr.sync[0] = 0xA5; hdr.sync[1] = 0x5A; hdr.sync[2] = 0xC3; hdr.sync[3] = 0x3C;
  hdr.seq      = info.seq;
  hdr.fs       = SAMPLE_RATE_HZ;
  hdr.n        = BLOCK_SIZE;
  hdr.missed   = info.missed;
  hdr.format   = 1;                  // int16 (signed)
  hdr.bits     = 16;
  hdr.reserved = 0;

  uint16_t checksum = 0;
  for (uint32_t i = 0; i < BLOCK_SIZE; i++) checksum += (uint16_t)data[i];

  STREAM.write((const uint8_t *)&hdr, sizeof(hdr));
  STREAM.write((const uint8_t *)data, BLOCK_SIZE * sizeof(int16_t));
  STREAM.write((const uint8_t *)&checksum, sizeof(checksum));
#endif

  txBusy = false;
}
