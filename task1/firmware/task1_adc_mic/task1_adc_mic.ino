/*
 * ============================================================================
 *  Signals & Systems Lab - Task 1
 *  Real-Time Audio Sampling : ESP32-S3 + MAX4466 (analog electret microphone)
 *
 *  วิธีทำงาน (ตามข้อ Hints 1.1 - 3.3 ของโจทย์)
 *    1) Hardware timer สร้าง interrupt ทุก ๆ 1/Fs วินาที  -> เป็นตัวกำหนดจังหวะ sampling
 *       (ไม่ได้ใช้ micros()/millis() ใน loop() เลย)
 *    2) Timer ISR ปลุก "sampler task" (priority สูงสุด, อยู่คนละ core กับ loop())
 *       task นี้อ่าน ADC 1 ค่า แล้วเก็บลง buffer
 *    3) Ping-pong (double) buffer : มี buffer 2 ชุด ชุดหนึ่งกำลังถูกเติม
 *       อีกชุดหนึ่งถูก loop() ส่งออก serial  เมื่อเต็มก็สลับกัน
 *    4) loop() ทำหน้าที่ "ส่งข้อมูลอย่างเดียว" เป็น binary frame
 *       การส่ง serial ช้า/เร็วจึงไม่มีผลต่อจังหวะ sampling
 *
 *  ทำไมไม่เรียก analogRead() ใน ISR ตรง ๆ :
 *    ใน Arduino-ESP32 core 3.x analogRead() เรียก adc_oneshot_read() ซึ่งเอกสารของ
 *    Espressif ระบุว่าไม่ควรใช้ใน ISR และใช้เวลาหลายสิบ us  จึงให้ ISR ทำแค่ปลุก task
 *
 * ----------------------------------------------------------------------------
 *  การต่อวงจร MAX4466
 *      MAX4466 VCC  ->  3V3   (ห้ามใช้ 5V เพราะ output จะเกินช่วงของ ADC)
 *      MAX4466 GND  ->  GND
 *      MAX4466 OUT  ->  MIC_PIN    (ค่าเริ่มต้น GPIO4 = ADC1_CH3)
 *      TIMING_PIN   ->  oscilloscope (ค่าเริ่มต้น GPIO5) ใช้ตอบ Question 1
 *    ตอนเงียบ OUT ของ MAX4466 จะอยู่ราว VCC/2 ~ 1.65 V  (ค่า ADC ประมาณ 2000)
 *    ปรับ gain ด้วย trimpot ด้านหลังโมดูล
 *
 * ----------------------------------------------------------------------------
 *  การตั้งค่า Arduino IDE  (เหมือนกันทั้ง Windows และ Linux)
 *      Tools > Board            : "ESP32S3 Dev Module"
 *      Tools > USB CDC On Boot  : "Disabled"
 *      เสียบสาย USB ที่ช่องที่เขียนว่า "UART" หรือ "COM" บนบอร์ด (ช่องที่ผ่านชิป USB-to-serial)
 *    รองรับ Arduino-ESP32 core ทั้ง 2.x และ 3.x (โค้ดเลือก timer API ให้อัตโนมัติ)
 *
 *  ชื่อ serial port (ใช้ตอนเลือก port ใน IDE และในสคริปต์ MATLAB)
 *      Windows : COM3, COM5, ...       ดูใน Device Manager > Ports (COM & LPT)
 *      Linux   : /dev/ttyUSB0 หรือ /dev/ttyACM0     ดูด้วยคำสั่ง  ls /dev/ttyUSB* /dev/ttyACM*
 *                ถ้าเปิด port ไม่ได้ (permission denied) ให้รัน
 *                    sudo usermod -aG dialout $USER      แล้ว logout/login ใหม่
 *
 * ----------------------------------------------------------------------------
 *  รูปแบบ frame ที่ส่งออก (binary, little-endian)  ->  1 frame ต่อ 1 block
 *      offset  ขนาด        ความหมาย
 *        0     4 byte      sync word  = A5 5A C3 3C
 *        4     uint32      seq        : ลำดับ block (ถ้าเลขกระโดด = มี block ถูกทิ้ง)
 *        8     uint32      fs         : sampling rate (Hz)
 *       12     uint16      n          : จำนวน sample ใน block นี้
 *       14     uint16      missed     : จำนวน timer tick ที่อ่าน ADC ไม่ทัน (ควรเป็น 0)
 *       16     uint8       format     : ชนิดของ sample  0 = uint16 (unsigned), 1 = int16 (signed)
 *       17     uint8       bits       : จำนวนบิตที่ใช้จริงของ sample (Task 1 = 12)
 *       18     uint16      reserved   : ยังไม่ใช้ (0)
 *       20     uint16 x n  samples    : ค่า ADC ดิบ 0..4095
 *     20+2n    uint16      checksum   : ผลรวมของ sample ทั้งหมด (มองเป็น uint16) mod 65536
 *    ขนาดรวม = 22 + 2n byte  (n = 1024 -> 2070 byte)
 *    fs, n, format, bits ถูกส่งไปใน header ดังนั้นเปลี่ยนค่าที่นี่ที่เดียว ฝั่ง MATLAB อ่านตามได้เอง
 *    (Task 2 ใช้ frame รูปแบบเดียวกันนี้ จึงใช้สคริปต์ MATLAB ตัวเดียวกัน: matlab/realtime_audio_scope.m)
 * ============================================================================
 */

#include <Arduino.h>

// ============================================================================
//  >>>>>>>>>>>>>>>>>>>>>>>>   ส่วนตั้งค่า (แก้ตรงนี้)   <<<<<<<<<<<<<<<<<<<<<<<<
// ============================================================================

// Sampling rate (Hz)  โจทย์กำหนดค่าเริ่มต้น 10 kS/s
// ต้องหาร TIMER_TICK_HZ ลงตัว เช่น 8000, 10000, 16000, 20000
#define SAMPLE_RATE_HZ   10000

// จำนวน sample ต่อ 1 block (= ขนาด FFT ฝั่ง MATLAB)  โจทย์ยกตัวอย่าง N = 1024
#define BLOCK_SIZE       1024

// ขา ADC ที่ต่อกับ OUT ของ MAX4466
// ESP32-S3 ให้ใช้ ADC1 เท่านั้น = GPIO1 ถึง GPIO10  (เลี่ยง GPIO3 เพราะเป็น strapping pin)
#define MIC_PIN          4

// ขา GPIO สำหรับวัดจังหวะ sampling ด้วย oscilloscope (Question 1)
// ขานี้จะ toggle 1 ครั้งต่อ 1 sample  ->  ได้ square wave ความถี่ = SAMPLE_RATE_HZ / 2
// เช่น 10 kS/s จะเห็น 5 kHz และระยะห่างระหว่างขอบสัญญาณ = 100 us
// ตั้งเป็น -1 ถ้าไม่ใช้
#define TIMING_PIN       5

// Baud rate ของ serial  (ต้องตรงกับสคริปต์ MATLAB)
// 1000000 ใช้ได้ทั้ง Windows และ Linux   ถ้าข้อมูลเพี้ยนให้ลองลดเป็น 921600 หรือ 500000
// ต้องการอย่างน้อยประมาณ SAMPLE_RATE_HZ x 2 byte x 10 bit = 200000 bit/s ที่ 10 kS/s
#define SERIAL_BAUD      1000000

// 0 = ส่ง binary frame ให้ MATLAB (โหมดใช้งานจริง)
// 1 = พิมพ์สถิติของแต่ละ block เป็นข้อความ ไว้ดูใน Serial Monitor เพื่อเช็กวงจร/ระดับสัญญาณ
//     (ตั้ง baud ของ Serial Monitor ให้เท่ากับ SERIAL_BAUD)
#define TEXT_DEBUG       0

// ช่วงแรงดันของ ADC :  ADC_11db ~ 0 ถึง 3.1 V  เหมาะกับ MAX4466 ที่จ่ายไฟ 3.3 V
// ตัวเลือกอื่น : ADC_0db (~0-0.95 V), ADC_2_5db (~0-1.25 V), ADC_6db (~0-1.75 V)
#define ADC_ATTENUATION  ADC_11db

// ความละเอียดของ ADC (bit)  ESP32-S3 ใช้ได้สูงสุด 12 บิต  ->  ค่า 0..4095
#define ADC_BITS         12

// ---- ปกติไม่ต้องแก้ส่วนข้างล่างนี้ ------------------------------------------

// Port ที่ใช้ส่งข้อมูล  (Serial = UART0 ผ่านชิป USB-to-serial เมื่อ USB CDC On Boot = Disabled)
#define STREAM           Serial

// ความถี่นับของ hardware timer   คาบ sampling = TIMER_TICK_HZ / SAMPLE_RATE_HZ tick
#define TIMER_TICK_HZ    4000000

// Core ที่ใช้รัน sampler task + timer ISR   (loop() ของ Arduino อยู่ที่ core 1)
#define SAMPLER_CORE     0

// ============================================================================
//  จบส่วนตั้งค่า
// ============================================================================

static_assert(TIMER_TICK_HZ % SAMPLE_RATE_HZ == 0,
              "SAMPLE_RATE_HZ must divide TIMER_TICK_HZ exactly");
static_assert(BLOCK_SIZE >= 2 && BLOCK_SIZE <= 65535, "BLOCK_SIZE must fit in uint16");

#define TIMER_ALARM_TICKS  (TIMER_TICK_HZ / SAMPLE_RATE_HZ)

// ---- frame header ----------------------------------------------------------
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

// ---- ข้อมูลของ block ที่เต็มแล้ว ส่งจาก sampler task ไปให้ loop() ----------------
struct BlockInfo {
  uint8_t  index;    // buffer ชุดไหน (0 หรือ 1)
  uint32_t seq;
  uint16_t missed;
};

// ---- ping-pong buffer ------------------------------------------------------
static uint16_t sampleBuf[2][BLOCK_SIZE];

// true = loop() ยังส่ง buffer อีกชุดไม่เสร็จ  ห้ามสลับไปเขียนทับ
static volatile bool txBusy = false;
static volatile uint32_t droppedBlocks = 0;

static hw_timer_t   *sampleTimer   = NULL;
static TaskHandle_t  samplerHandle = NULL;
static QueueHandle_t blockQueue    = NULL;

// ----------------------------------------------------------------------------
//  Timer ISR : เกิดทุก 1/Fs วินาที  ทำแค่ปลุก sampler task แล้วออกทันที
// ----------------------------------------------------------------------------
static void IRAM_ATTR onSampleTimer() {
  BaseType_t higherPriorityTaskWoken = pdFALSE;
  vTaskNotifyGiveFromISR(samplerHandle, &higherPriorityTaskWoken);
  if (higherPriorityTaskWoken) {
    portYIELD_FROM_ISR();
  }
}

static bool startSampleTimer() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  sampleTimer = timerBegin(TIMER_TICK_HZ);
  if (sampleTimer == NULL) return false;
  timerAttachInterrupt(sampleTimer, &onSampleTimer);
  timerAlarm(sampleTimer, TIMER_ALARM_TICKS, true, 0);   // auto-reload, ทำซ้ำไม่จำกัด
#else
  sampleTimer = timerBegin(0, 80000000UL / TIMER_TICK_HZ, true);   // APB clock 80 MHz
  if (sampleTimer == NULL) return false;
  timerAttachInterrupt(sampleTimer, &onSampleTimer, true);
  timerAlarmWrite(sampleTimer, TIMER_ALARM_TICKS, true);
  timerAlarmEnable(sampleTimer);
#endif
  return true;
}

// ----------------------------------------------------------------------------
//  Sampler task : รอ timer -> อ่าน ADC 1 ค่า -> เก็บลง buffer -> เต็มแล้วสลับ buffer
// ----------------------------------------------------------------------------
static void samplerTask(void *arg) {
  (void)arg;

  uint8_t  fill   = 0;      // buffer ที่กำลังเติม
  uint32_t wr     = 0;      // ตำแหน่งเขียนใน buffer
  uint32_t seq    = 0;
  uint32_t missed = 0;
#if TIMING_PIN >= 0
  bool pinLevel = false;
#endif

  // เริ่ม timer จากใน task นี้ เพื่อให้ ISR อยู่ core เดียวกับ task (ปลุกได้เร็วและคงที่)
  samplerHandle = xTaskGetCurrentTaskHandle();
  if (!startSampleTimer()) {
    vTaskDelete(NULL);
  }

  for (;;) {
    // ค่าที่คืนมา = จำนวน tick ที่เกิดขึ้นตั้งแต่รอบก่อน  ถ้า > 1 แปลว่าอ่าน ADC ไม่ทัน
    uint32_t ticks = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (ticks > 1) missed += ticks - 1;

#if TIMING_PIN >= 0
    pinLevel = !pinLevel;
    digitalWrite(TIMING_PIN, pinLevel);     // ขอบสัญญาณ = จังหวะที่เริ่มแปลง ADC จริง
#endif

    sampleBuf[fill][wr++] = (uint16_t)analogRead(MIC_PIN);

    if (wr >= BLOCK_SIZE) {
      wr = 0;
      if (!txBusy) {
        // buffer อีกชุดว่างแล้ว -> ส่งชุดนี้ให้ loop() แล้วสลับไปเติมอีกชุด
        BlockInfo info;
        info.index  = fill;
        info.seq    = seq;
        info.missed = (missed > 65535u) ? 65535u : (uint16_t)missed;
        txBusy = true;
        xQueueSend(blockQueue, &info, 0);
        fill ^= 1;
      } else {
        // loop() ยังส่งไม่เสร็จ -> ทิ้ง block นี้ (เติมทับชุดเดิม)  sampling ยังเดินต่อตามปกติ
        droppedBlocks = droppedBlocks + 1;
      }
      seq++;
      missed = 0;
    }
  }
}

// ----------------------------------------------------------------------------
void setup() {
  STREAM.begin(SERIAL_BAUD);

  analogReadResolution(ADC_BITS);
  analogSetPinAttenuation(MIC_PIN, ADC_ATTENUATION);
  analogRead(MIC_PIN);                     // อ่านทิ้ง 1 ครั้งให้ ADC ตั้งค่าเสร็จก่อนเริ่ม timer

#if TIMING_PIN >= 0
  pinMode(TIMING_PIN, OUTPUT);
  digitalWrite(TIMING_PIN, LOW);
#endif

  blockQueue = xQueueCreate(1, sizeof(BlockInfo));

  xTaskCreatePinnedToCore(samplerTask, "sampler", 4096, NULL,
                          configMAX_PRIORITIES - 1, NULL, SAMPLER_CORE);
}

// ----------------------------------------------------------------------------
//  loop() : รอ block ที่เต็มแล้ว แล้วส่งออก serial  (ไม่ยุ่งกับจังหวะ sampling)
// ----------------------------------------------------------------------------
void loop() {
  BlockInfo info;
  if (xQueueReceive(blockQueue, &info, portMAX_DELAY) != pdTRUE) return;

  const uint16_t *data = sampleBuf[info.index];

#if TEXT_DEBUG
  uint16_t vmin = 65535, vmax = 0;
  uint32_t sum = 0;
  for (uint32_t i = 0; i < BLOCK_SIZE; i++) {
    if (data[i] < vmin) vmin = data[i];
    if (data[i] > vmax) vmax = data[i];
    sum += data[i];
  }
  STREAM.printf("seq=%lu  min=%u  max=%u  mean=%lu  p-p=%u  missed=%u  dropped=%lu\n",
                (unsigned long)info.seq, vmin, vmax, (unsigned long)(sum / BLOCK_SIZE),
                (unsigned)(vmax - vmin), (unsigned)info.missed,
                (unsigned long)droppedBlocks);
#else
  FrameHeader hdr;
  hdr.sync[0] = 0xA5; hdr.sync[1] = 0x5A; hdr.sync[2] = 0xC3; hdr.sync[3] = 0x3C;
  hdr.seq    = info.seq;
  hdr.fs     = SAMPLE_RATE_HZ;
  hdr.n      = BLOCK_SIZE;
  hdr.missed = info.missed;
  hdr.format   = 0;                  // uint16 (unsigned)
  hdr.bits     = ADC_BITS;
  hdr.reserved = 0;

  uint16_t checksum = 0;
  for (uint32_t i = 0; i < BLOCK_SIZE; i++) checksum += data[i];

  STREAM.write((const uint8_t *)&hdr, sizeof(hdr));
  STREAM.write((const uint8_t *)data, BLOCK_SIZE * sizeof(uint16_t));
  STREAM.write((const uint8_t *)&checksum, sizeof(checksum));
#endif

  txBusy = false;      // คืน buffer ให้ sampler task ใช้รอบถัดไป
}
