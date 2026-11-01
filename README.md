# lab_ii_signal

Source code and results for the **Signals & Systems / DSP Practical Labs — Assignment II** (Group 7).

![MATLAB real-time audio scope](docs/matlab_gui_screenshot.png)

## โครงสร้าง repository

```
matlab/realtime_audio_scope.m        สคริปต์ MATLAB ตัวเดียว ใช้ร่วมกัน Task 1 และ Task 2
task1/  firmware/task1_adc_mic/      ESP32-S3 + MAX4466 (ADC, hardware timer, ping-pong buffer)
        results/                     ภาพ oscilloscope, กราฟ MATLAB, เทียบ window vs no window
task2/  firmware/task2_i2s_mic/      ESP32-S3 + INMP441 (I2S + DMA, ping-pong buffer)
        results/                     กราฟ MATLAB
task3/  fpga/                        VHDL (DE10-Lite MAX 10), testbench, Quartus TCL
        esp32/task3_esp32_bridge/    ESP32 = SPI master ดึง block จาก FPGA ส่งต่อ USB
        host/                        task3_host.m / task3_host.py
        README.md                    คู่มือ Task 3 แบบละเอียด
mini_project/                        Mini Shazam (Python GUI) ดู mini_project/README.md
docs/                                รูปวงจรและ screenshot
```

| Task | ฮาร์ดแวร์ | Fs | ใครคุมจังหวะ sampling | DMA | Ping-pong | โปรแกรมฝั่ง PC |
|---|---|---|---|---|---|---|
| 1 | ESP32-S3 + MAX4466 (analog) | 10 kS/s | hardware timer | ไม่ใช้ | `sampleBuf[2][1024]` ใน ESP32 | `matlab/realtime_audio_scope.m` |
| 2 | ESP32-S3 + INMP441 (I²S) | 16 kS/s | clock ของ I²S peripheral | ใช้ (I²S RX DMA) | `sampleBuf[2][1024]` ใน ESP32 | `matlab/realtime_audio_scope.m` |
| 3 | DE10-Lite + MCP3202 / MAX 10 ADC → ESP32 | 16 kS/s | counter บน FPGA 50 MHz | ไม่ใช้ (FPGA เขียน BRAM เอง) | BRAM 2 bank ใน FPGA + pool 6 buffer ใน ESP32 | `task3/host/task3_host.m` / `.py` |

---

## วิธีใช้งาน Task 1 และ Task 2

### 1. ต่อวงจร

**Task 1 — MAX4466** ([รูปวงจร](docs/circuit/task1_circuit.jpg))

| MAX4466 | ESP32-S3 |
|---|---|
| VCC | 3V3 (ห้ามใช้ 5 V) |
| GND | GND |
| OUT | GPIO4 (ADC1_CH3) |
| — | GPIO5 → oscilloscope (toggle ทุก sample ใช้ตอบคำถามข้อ 1) |

**Task 2 — INMP441** ([รูปวงจร](docs/circuit/task2_circuit.jpg))

| INMP441 | ESP32-S3 |
|---|---|
| VDD | 3V3 |
| GND | GND |
| SCK (BCLK) | GPIO18 |
| WS (LRCLK) | GPIO17 |
| SD | GPIO21 |
| L/R | GND (ช่องซ้าย) ห้ามปล่อยลอย |
| — | GPIO5 → oscilloscope (toggle ทุก block) |

### 2. อัปโหลด firmware (Arduino IDE)

1. ติดตั้ง board package **esp32 by Espressif** เวอร์ชัน 3.x (Task 2 ต้องเป็น 3.x, Task 1 ใช้ได้ทั้ง 2.x และ 3.x)
2. เปิด `task1/firmware/task1_adc_mic/task1_adc_mic.ino` หรือ `task2/firmware/task2_i2s_mic/task2_i2s_mic.ino`
3. `Tools > Board` = **ESP32S3 Dev Module**, `Tools > USB CDC On Boot` = **Disabled**
4. เสียบสาย USB ที่ช่อง **UART/COM** ของบอร์ด แล้วกด Upload
5. ค่าที่ปรับได้อยู่ในส่วน `ส่วนตั้งค่า (แก้ตรงนี้)` ด้านบนของแต่ละไฟล์ เช่น `SAMPLE_RATE_HZ`, `BLOCK_SIZE`, ขา GPIO, `SERIAL_BAUD`
6. ถ้าอยากเช็กวงจรก่อน ให้ตั้ง `TEXT_DEBUG 1` แล้วเปิด Serial Monitor (1000000 baud) จะเห็น min/max/mean ของแต่ละ block

หรือใช้ `arduino-cli`:

```bash
arduino-cli compile -b esp32:esp32:esp32s3 --upload -p /dev/ttyUSB0 task1/firmware/task1_adc_mic
```

### 3. รัน MATLAB (สคริปต์เดียวกันทั้ง 2 task)

**ปิด Serial Monitor ของ Arduino IDE ก่อน** (เปิด port ได้ทีละโปรแกรม) แล้วใน MATLAB:

```matlab
cd matlab
realtime_audio_scope                          % เลือก port ให้อัตโนมัติ
realtime_audio_scope('port', 'COM5')          % Windows
realtime_audio_scope('port', '/dev/ttyUSB0')  % Linux
realtime_audio_scope('demo', true)            % ลองหน้าจอโดยไม่ต้องต่อบอร์ด
```

สคริปต์ไม่ต้องแก้เมื่อสลับ Task 1 ↔ Task 2 เพราะค่า `fs`, `n`, ชนิดข้อมูล (uint16/int16) และจำนวนบิต
ถูกส่งมาใน header ของทุก frame (Task 1 = 10 kHz, uint16, 12 บิต / Task 2 = 16 kHz, int16, 16 บิต)

หน้าจอประกอบด้วย waveform, FFT (เลือก window ได้: Rectangular / Hann / Hamming / Blackman / Flat-top และติ๊ก
*Overlay FFT without window* เพื่อเทียบ spectral leakage), spectrogram ย้อนหลัง 5 วินาที, ป้ายบอกความถี่เด่น 3 ยอด
และแถบสถานะที่บอก `df = Fs/N`, จำนวน *missed samples*, *dropped blocks* และ *bad frames*
(ถ้าระบบทำงานถูกต้องทั้ง 3 ตัวต้องเป็น 0) ปุ่ม **Stop/Play** ใช้หยุดภาพไว้จับภาพหน้าจอ

ต้องใช้ MATLAB R2019b ขึ้นไป ไม่ต้องใช้ toolbox เพิ่ม
(Linux: ถ้าเปิด port ไม่ได้ให้รัน `sudo usermod -aG dialout $USER` แล้ว logout/login)

### รูปแบบ frame (Task 1 และ 2 ใช้รูปแบบเดียวกัน, little-endian)

| offset | ขนาด | field | ความหมาย |
|---|---|---|---|
| 0 | 4 | sync | `A5 5A C3 3C` |
| 4 | uint32 | seq | ลำดับ block (เลขกระโดด = มี block หาย) |
| 8 | uint32 | fs | sampling rate (Hz) |
| 12 | uint16 | n | จำนวน sample (1024) |
| 14 | uint16 | missed | sample ที่หายฝั่ง ESP32 (Task 1 = timer tick ที่อ่าน ADC ไม่ทัน, Task 2 = DMA ล้น) |
| 16 | uint8 | format | 0 = uint16, 1 = int16 |
| 17 | uint8 | bits | 12 (Task 1) / 16 (Task 2) |
| 18 | uint16 | reserved | 0 |
| 20 | 2·n | samples | ข้อมูลเสียง |
| 20+2n | uint16 | checksum | ผลรวม sample mod 65536 |

1 frame = 2070 byte. ที่ 1 Mbaud ส่ง 1 frame ใช้ ~21 ms ขณะที่ 1 block กินเวลา 102.4 ms (Task 1) / 64 ms (Task 2)
จึงเหลือเวลาว่างมาก ข้อมูลส่งเป็น binary ไม่ใช่ ASCII ตาม Hint 3.2

---

## DMA และ Ping-pong buffering ทำงานอย่างไร

หลักการที่โจทย์ต้องการ (Hint 1.3, 2.1, 3.3) คือ **แยกการเก็บข้อมูลออกจากการส่งข้อมูล**
ให้จังหวะ sampling มาจาก hardware เท่านั้น และการส่ง serial จะช้าหรือเร็วก็ไม่มีผลกับ Fs
ทั้ง Task 1 และ 2 ใช้โครงสร้างเดียวกันคือมี 2 งานที่วิ่งขนานกันบนคนละ core

```
          core 0 (priority สูงสุด)                         core 1
 ┌───────────────────────────────────┐          ┌───────────────────────────┐
 │ ผู้ผลิต (producer)                   │  queue   │ ผู้บริโภค (consumer) = loop() │
 │ Task 1: samplerTask  (timer → ADC) │ ───────► │ เขียน header + sampleBuf[i] │
 │ Task 2: readerTask   (I2S DMA)     │ BlockInfo│ + checksum ออก Serial       │
 │ เขียนลง sampleBuf[fill]             │  ยาว 1   │ เสร็จแล้ว txBusy = false     │
 └───────────────────────────────────┘          └───────────────────────────┘
```

### Ping-pong buffer (ใช้ทั้ง Task 1 และ 2)

ใน firmware มี buffer 2 ชุด `sampleBuf[2][BLOCK_SIZE]` และตัวแปร 3 ตัวที่คุมการสลับ

| ตัวแปร | หน้าที่ |
|---|---|
| `fill` (0 หรือ 1) | buffer ที่ producer กำลังเติม |
| `blockQueue` (FreeRTOS queue ยาว 1) | ส่ง `BlockInfo {index, seq, missed}` ของ buffer ที่เต็มแล้วไปให้ `loop()` |
| `txBusy` | `true` = `loop()` ยังส่ง buffer อีกชุดไม่เสร็จ ห้ามสลับไปเขียนทับ |

ลำดับการทำงาน

1. producer เติม `sampleBuf[fill]` จนครบ 1024 sample
2. ถ้า `txBusy == false` → ตั้ง `txBusy = true`, ส่ง `index = fill` เข้า queue แล้ว **สลับ** `fill ^= 1` ไปเติมอีกชุดทันที
3. `loop()` ที่รออยู่ใน `xQueueReceive()` ตื่นขึ้นมา ส่ง `sampleBuf[index]` ออก Serial แล้วตั้ง `txBusy = false` เพื่อคืน buffer
4. ระหว่างที่ `loop()` ส่ง buffer A อยู่ producer ก็เติม buffer B ไปพร้อมกัน — ไม่มีใครรอใคร

```
เวลา →     block 0        block 1        block 2        block 3
producer   [เติม A ]      [เติม B ]      [เติม A ]      [เติม B ]
loop()                    [ส่ง A]        [ส่ง B]        [ส่ง A]
```

ถ้า Serial ช้าจนส่งไม่ทันจริง ๆ (`txBusy` ยังเป็น `true` ตอน block ถัดไปเต็ม) producer จะ **ทิ้ง block นั้น**
แล้วเติมทับ buffer เดิมต่อ แต่ `seq` ยังนับเพิ่ม MATLAB จึงเห็นเลข seq กระโดดและนับเป็น *dropped blocks* —
สิ่งสำคัญคือ sampling ไม่เคยหยุดหรือช้าลง (Hint 3.3)

### Task 1: hardware timer + ping-pong (ไม่ใช้ DMA)

```
hardware timer (4 MHz, alarm ทุก 400 tick = 100 µs)
   └─► ISR onSampleTimer()  : แค่ vTaskNotifyGiveFromISR() ปลุก samplerTask แล้วออก
          └─► samplerTask  : toggle GPIO5 → analogRead(GPIO4) → sampleBuf[fill][wr++]
                               ครบ 1024 → ping-pong swap
```

- จังหวะมาจาก **hardware timer** ตาม Hint 1.1 ไม่มีการเช็ก `micros()`/`millis()` ใน `loop()` (Hint 1.2)
- ไม่เรียก `analogRead()` ใน ISR โดยตรง เพราะใน core 3.x ฟังก์ชันนี้เรียก `adc_oneshot_read()` ซึ่ง Espressif ห้ามใช้ใน ISR
  จึงให้ ISR ปลุก task ที่ priority สูงสุดซึ่งอยู่ core เดียวกับ ISR แทน
- `ulTaskNotifyTake()` คืนจำนวน tick ที่ค้าง ถ้ามากกว่า 1 แปลว่าอ่าน ADC ไม่ทัน → นับใส่ `missed` ใน header
- **Task 1 ไม่ได้ใช้ DMA** — โจทย์ข้อ 1.1 ให้เลือกได้ระหว่าง hardware timer หรือ ADC continuous/DMA
  กลุ่มเลือกแบบ timer เพราะวัดจังหวะ sampling ได้ทุก sample ด้วย GPIO5 (คำถามข้อ 1) และเห็นค่า `missed` ได้ชัด
  (ทางเลือกถ้าจะใช้ DMA: `analogContinuous()` ของ Arduino-ESP32 3.x ซึ่งให้ ADC + DMA เติม buffer เองโดยไม่ใช้ CPU ต่อ sample)

### Task 2: I²S + DMA + ping-pong

ไมค์ INMP441 มี ADC ในตัว ESP32 แค่สร้าง clock ให้ (SCK = 64 × 16 kHz = 1.024 MHz, WS = 16 kHz)
แล้วรับข้อมูล digital กลับมาทาง SD ข้อมูลไหลผ่าน 2 ชั้น:

```
INMP441 ──SD──► I2S RX FIFO ──GDMA──► DMA ring buffer (8 descriptor × 256 sample × 4 byte = 8 KB ≈ 128 ms)
                                              │  i2s_channel_read() รอจนได้ 1024 sample
                                              ▼
                                       rawBuf[1024] (int32, 24 บิตชิดซ้าย)
                                              │  toInt16(): >> 16 (+GAIN_SHIFT, clamp)
                                              ▼
                                       sampleBuf[fill]  ── ping-pong ──►  loop() ──► Serial
```

**DMA ทำอะไร**
- ตั้งค่าใน `startI2S()`: `chanCfg.dma_desc_num = 8`, `chanCfg.dma_frame_num = 256`
- เมื่อ `i2s_channel_enable()` แล้ว hardware I²S + GDMA จะเขียน sample ลง DMA buffer **เอง ไม่ใช้ CPU ต่อ sample**
  เมื่อ descriptor หนึ่งเต็ม (256 sample = 16 ms) driver จะได้ interrupt และนำ buffer นั้นเข้าคิว
- `readerTask` เรียก `i2s_channel_read(..., portMAX_DELAY)` ซึ่งจะ block รอจน DMA เติมครบ 1024 sample (4 descriptor)
  จากนั้นคัดลอกออกมา จังหวะ sampling จึงถูกกำหนดโดย clock ของ I²S ทั้งหมด
- DMA ring 8 ชุดทำหน้าที่เป็น buffer สำรองรอบแรก: ถ้า `readerTask` ถูกขัดจังหวะ ข้อมูลรอได้ถึง ~128 ms
  ถ้าเกินนั้น driver เรียก callback `onRxOverflow()` → `dmaOverflows++` → นับเป็น `missed = 256` sample ต่อครั้งใน header
- ช่วง 300 ms แรกหลังเริ่ม clock ไมค์ยังส่งค่าขยะ (datasheet: 2¹⁸ SCK cycles) จึงอ่านทิ้งก่อน

**Ping-pong ทำอะไร** — เหมือน Task 1 ทุกอย่าง ต่างแค่ producer คือ `readerTask` ที่ได้ข้อมูลจาก DMA
และเมื่อ `loop()` ยังส่งไม่เสร็จ `readerTask` ยัง **อ่าน DMA ต่อเสมอ** (แค่ทิ้ง block) ทำให้ DMA ไม่ล้น

สรุปคือ Task 2 มี buffer 2 ชั้น: **DMA ring** (hardware → RAM, กัน CPU ช้า) และ **ping-pong** (แยก acquisition ออกจาก USB, กัน Serial ช้า)

### Task 3 (ดูรายละเอียดใน [`task3/README.md`](task3/README.md))

- **Ping-pong ใน FPGA**: `fpga/audio_block_buffer.vhd` เป็น Block RAM 2 bank × 1024 × 12 บิต
  ฝั่ง ADC เขียน bank หนึ่งที่ 16 kS/s ไม่หยุด ฝั่ง SPI อ่าน bank ที่เต็มแล้ว (lock ตอน CS ลง, ปล่อยตอน CS ขึ้น)
  ถ้า ESP32 อ่านไม่ทันจะทิ้ง block และนับ `drop_cnt` แต่ไม่เคยหยุดการเขียน
- **ฝั่ง ESP32** (`esp32/task3_esp32_bridge`): ใช้ pool 6 buffer กับ queue `freeQ`/`fullQ` (เป็น ping-pong แบบหลายช่อง)
  `spiTask` ดึง block เมื่อ DRDY ขึ้น ส่วน `loop()` ส่งออก USB
- **DMA**: Task 3 ไม่ได้ใช้ DMA — FPGA เขียนลง BRAM ด้วย logic เองโดยตรง และฝั่ง ESP32 ใช้ `SPI.transferBytes()`
  ของ Arduino (CPU เติม FIFO) ซึ่งเร็วพอ: 2060 byte ที่ 4 MHz ≈ 4 ms ต่อ block 64 ms
- Task 3 ใช้ frame คนละรูปแบบ (`AA 55 33 CC`) จึงใช้ `task3/host/task3_host.m` หรือ `task3_host.py` แทนสคริปต์ของ Task 1/2

---

## ผลการตรวจโค้ด

- คอมไพล์ผ่านทั้ง 3 sketch ด้วย `arduino-cli` + esp32 core 3.3.12 บอร์ด ESP32S3 Dev Module
- ตรวจ header/checksum ของ firmware Task 1, Task 2 กับ `parseFrames()` ใน MATLAB แล้วตรงกัน (format 0/1, checksum นับแบบ uint16 เหมือนกัน)
- ผ่านข้อกำหนดของโจทย์: sampling คุมด้วย hardware (timer / I²S clock / FPGA counter), ไม่ใช้ `micros()` ใน `loop()`,
  แยก acquisition กับ transmission, ใช้ double buffer, ส่ง binary ที่ 1 Mbaud, ใส่ Hann window และเทียบกับไม่ใส่ window
- แก้ไขใน commit นี้:
  - ย้าย `task1_adc_mic.ino` เข้าโฟลเดอร์ชื่อเดียวกัน (Arduino IDE บังคับ ไม่อย่างนั้นจะถามย้ายไฟล์ตอนเปิด)
  - ย้ายสคริปต์ MATLAB ไปไว้ที่ `matlab/` ให้ Task 1 และ 2 ใช้ร่วมกัน
  - ลบ `inmp441_stream.ino` / `inmp441_viewer.m` ซึ่งเป็นเวอร์ชันเก่าที่ใช้ frame คนละรูปแบบ (`AA 55 AA 55`) และ I²S driver แบบเก่า
  - แก้คำอธิบาย frame ใน README ที่เคยเขียนผิดเป็น `AA 55 AA 55`

## Mini project

**Mini Shazam** — Python GUI ระบุเพลงจากเสียง 5–10 วินาทีที่สตรีมจาก FPGA/ESP32 ด้วย audio fingerprinting
ดู [`mini_project/README.md`](mini_project/README.md)

```bash
cd mini_project && pip install -r requirements.txt && python app.py
```
