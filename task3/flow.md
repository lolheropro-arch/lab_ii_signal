# Task 3 — ขั้นตอนทำในแล็บแบบละเอียด (ทำตามทีละข้อ)

> อุปกรณ์ชุดนี้: **DE10-Lite + ESP32-S3 UNO (บอร์ดม่วง) + MCP3201 + ไมค์ MAX4466**
> ทำตามลำดับ ติ๊ก `[x]` ทีละข้อ. ข้อที่มี 📷 = ต้องเก็บรูป (ชื่อไฟล์ตามรหัส F..)
> ถ้าขั้นไหน "ผลที่ต้องเห็น" ไม่ตรง → ดูกล่อง ❗ ใต้ขั้นนั้นก่อน ไม่ต้องข้าม

---

## ขั้น 0 — เตรียมไฟล์และโปรแกรม (5–10 นาที)

- [ ] แตก `task3_fpga_audio.zip` ไว้ที่ **`C:\task3`** (path ต้องไม่มีภาษาไทยหรือช่องว่าง ไม่งั้น Quartus error)
  - ต้องได้โฟลเดอร์ `C:\task3\fpga`, `C:\task3\esp32`, `C:\task3\host`
- [ ] สร้างโฟลเดอร์เก็บรูป `C:\task3\pics` (ทุกรูปเซฟลงที่นี่ ตั้งชื่อ `F06.jpg`, `F08.png` …)
- [ ] เปิด **Command Prompt** (กด Win แล้วพิมพ์ `cmd`) แล้วพิมพ์:
  ```
  pip install pyserial numpy matplotlib
  ```
  - ผลที่ต้องเห็น: `Successfully installed …` หรือ `Requirement already satisfied`
- [ ] ลองโปรแกรม host โดยไม่ต้องมีฮาร์ดแวร์:
  ```
  cd C:\task3\host
  python task3_host.py --demo
  ```
  - ผลที่ต้องเห็น: หน้าต่างกราฟ 3 ช่อง + ปุ่มด้านล่าง → ปิดหน้าต่างได้เลย
- [ ] เปิดตารางจดค่า (กระดาษหรือ Notepad) หัวตาราง: `รูป | ตั้งค่าอะไร | ค่าที่อ่านได้ | สังเกตอะไร`

---

## ขั้น 1 — อัปโหลดโปรแกรมลง ESP32-S3 UNO (5 นาที)

- [ ] เสียบ ESP32-S3 UNO เข้าคอมด้วยสาย USB-C (**ยังไม่ต่อสายอื่นใด ๆ**)
- [ ] เปิด Arduino IDE → **File → Open** → `C:\task3\esp32\task3_esp32_bridge\task3_esp32_bridge.ino`
- [ ] **Tools → Board → esp32 → ESP32S3 Dev Module**
  - ❗ ถ้าไม่มีเมนู esp32: Tools → Board → Boards Manager → ค้น `esp32` → Install "esp32 by Espressif"
- [ ] **Tools → Port** → เลือก COM ที่เพิ่งโผล่ (จด COM นี้ไว้ เช่น `COM7`)
- [ ] กด **Upload** (ลูกศร →)
  - ผลที่ต้องเห็น: ล่างสุดขึ้น `Hard resetting via RTS pin...` = สำเร็จ
  - ❗ ถ้าขึ้น `Failed to connect`: กดปุ่ม **BOOT ค้าง** → กด **RST** 1 ครั้ง → ปล่อย BOOT → กด Upload ใหม่
- [ ] **ห้ามเปิด Serial Monitor** (ถ้าเปิดอยู่ให้ปิด) — พอร์ตใช้ได้ทีละโปรแกรม
- [ ] ถอดสาย USB-C ของ ESP32 ออกก่อน (จะต่อสายไฟ)

---

## ขั้น 2 — ต่อสาย ESP32-S3 ↔ DE10-Lite (10 นาที)

> **ถอด USB ทั้งสองบอร์ดก่อนต่อสายเสมอ**
> ขา JP1 ของ DE10-Lite นับ: pin 1 คือมุมที่มีเลข 1 พิมพ์ไว้บนบอร์ด, แถวบนเป็นเลขคี่ 1,3,5…, แถวล่างเป็นเลขคู่ 2,4,6…
> ใช้สาย **ผู้–เมีย**: ฝั่งเมียเสียบขา JP1, ฝั่งผู้เสียบ header ของ S3

| ✔ | สาย | DE10-Lite JP1 | ESP32-S3 UNO (ดูป้ายบนบอร์ด) |
|---|---|---|---|
| [ ] | SCLK | pin **1** | **IO12** |
| [ ] | MOSI | pin **2** | **IO11** |
| [ ] | MISO | pin **3** | **IO13** |
| [ ] | CS | pin **4** | **IO10** |
| [ ] | DRDY | pin **5** | **IO14** |
| [ ] | GND | pin **12** | **GND** (ช่องข้าง IO12) |

- [ ] ตรวจซ้ำอีกรอบ: นับขาใหม่ทีละเส้น โดยเฉพาะ GND (ไม่มี GND = ข้อมูลมั่วทั้งหมด)
- [ ] 📷 **F06** ถ่ายภาพชุดทดลองทั้งหมดจากด้านบน
- [ ] 📷 **F07** ถ่ายใกล้ ๆ ที่ JP1 ให้เห็นสายแต่ละเส้นชัด

---

## ขั้น 3 — สร้างและโปรแกรม FPGA แบบ "test tone" (15 นาที, compile ~3 นาที)

> **ทางลัด:** ดับเบิลคลิก `fpga\build.bat` ทำข้อ 3.1, 3.3, 3.4 ให้ครบในครั้งเดียว (ขั้น 6 ใช้ `build.bat 0 3201`) และเปิดกราฟด้วย `host\run_host.bat` · ผังต่อสายแบบมีรูปอยู่ใน `docs/wiring.html`

### 3.1 สร้างโปรเจกต์
- [ ] เสียบ DE10-Lite เข้าคอม (สาย USB-B) — ไฟบอร์ดติด
- [ ] ใน cmd พิมพ์ (แก้เลขเวอร์ชัน `20.1` ให้ตรงกับที่ติดตั้งในเครื่อง — ดูใน `C:\intelFPGA_lite\`):
  ```
  cd C:\task3\fpga
  C:\intelFPGA_lite\20.1\quartus\bin64\quartus_sh -t create_project.tcl 2
  ```
  - ผลที่ต้องเห็น: `Project task3_audio created (ADC_SELECT = 2, MCP_PART = 3202)`
  - ❗ ถ้าหา quartus_sh ไม่เจอ ใช้วิธีสำรอง: เปิดไฟล์ `create_project.tcl` ด้วย Notepad → แก้บรรทัด `set adc_select 0` เป็น `set adc_select 2` → Save → เปิด Quartus (ถ้ามีโปรเจกต์เปิดอยู่ให้ **File → Close Project** ก่อน) → **View → Utility Windows → Tcl Console** → พิมพ์ `cd C:/task3/fpga` Enter แล้ว `source create_project.tcl` Enter

### 3.2 ตรวจพิน (2 นาที, กันพังและกันเสียเวลา)
- [ ] เปิด `C:\task3\fpga\de10lite_pins.tcl` ด้วย Notepad เทียบกับคู่มือ DE10-Lite (หรือไฟล์ .qsf จากแล็บเก่าที่ใช้ได้):
  - `MAX10_CLK1_50 = PIN_P11`, `KEY[0] = PIN_B8`, `GPIO[0] = PIN_V10`, `GPIO[1] = PIN_W10`, `GPIO[2] = PIN_V9`, `GPIO[3] = PIN_W9`
  - ❗ ถ้าไม่ตรง: แก้เลขในไฟล์ให้ตรงคู่มือ แล้วรันข้อ 3.1 ใหม่

### 3.3 Compile
- [ ] เปิด Quartus → **File → Open Project** → `C:\task3\fpga\task3_audio.qpf`
- [ ] **Processing → Start Compilation** (หรือปุ่ม ▶ สีม่วง) รอ ~3 นาที
  - ผลที่ต้องเห็น: `Full Compilation was successful` (warning เยอะได้ ไม่เป็นไร)
  - ❗ ถ้า error: ถ่ายหน้าจอข้อความ error สีแดงส่งมาถาม
- [ ] 📷 **F04** หน้าต่าง **Compilation Report → Flow Summary** (เห็นจำนวน Logic elements, Memory bits)
- [ ] 📷 **F05** (ไม่บังคับ) **Tools → Netlist Viewers → RTL Viewer**

### 3.4 โปรแกรมลงบอร์ด
- [ ] **Tools → Programmer**
- [ ] ถ้าช่อง Hardware ขึ้น `No Hardware` → กด **Hardware Setup** → เลือก **USB-Blaster** → Close
- [ ] Mode = **JTAG**. ถ้าในรายการยังไม่มีไฟล์ → **Add File** → `output_files\task3_audio.sof`
- [ ] ติ๊กช่อง **Program/Configure** → กด **Start** → แถบ Progress = **100% (Successful)**
- [ ] ผลที่ต้องเห็นบนบอร์ด: **LEDR0 กะพริบ** ช้า ๆ (~1 ครั้ง/วินาที) = sampling ทำงาน
  - LEDR4–9 บางดวงติด (ระดับสัญญาณ test tone)

---

## ขั้น 4 — ทดสอบลิงก์ข้อมูล FPGA → ESP32 → คอม (10 นาที)

- [ ] เสียบ ESP32-S3 กลับเข้าคอม
- [ ] ตั้งสวิตช์ DE10-Lite: **SW6 ขึ้น** ตัวอื่นลงหมด (= เลข 64 = โทน 1000 Hz)
- [ ] ใน cmd:
  ```
  cd C:\task3\host
  python task3_host.py --port COM7
  ```
  (ใช้ COM ที่จดไว้ในขั้น 1)
  - ผลที่ต้องเห็น: กราฟขยับ, บรรทัดบนสุดเขียน `src=FPGA test tone`, `Fs_est=` ใกล้ **16000**, `spi_err=0`
  - ❗ กราฟไม่ขยับเลย: ปิดหน้าต่าง → Arduino IDE → **Tools → USB CDC On Boot** สลับค่า (Enabled↔Disabled) → Upload ใหม่ → ลองใหม่
  - ❗ `spi_err` เพิ่มขึ้นเรื่อย ๆ: เช็กสาย MISO (pin 3 ↔ IO13) และ GND; ถ้ายังไม่หาย แก้ `SPI_HZ = 2000000` ใน sketch แล้ว Upload ใหม่
  - ❗ ขึ้นว่าเปิด port ไม่ได้ (Access denied): ปิด Serial Monitor / โปรแกรมอื่นที่ใช้ COM นั้น
- [ ] คลิกที่หน้าต่างกราฟ 1 ครั้ง แล้วกดคีย์ **`t`**
  - ผลที่ต้องเห็น: ขึ้น **`TEST RAMP: OK`** (กราฟเป็นเส้นเฉียงขึ้น)
  - [ ] 📷 **F08** (หน้าจอทั้งหน้าต่าง ให้เห็นบรรทัดข้อความด้านบน)
- [ ] กด **`n`** กลับโหมดปกติ
- [ ] ปุ่ม **Window** ให้เป็น `Rect`
  - ผลที่ต้องเห็น: peak แหลมที่ **1000 Hz**
  - [ ] 📷 **F09** (กด Pause ก่อนถ่าย แล้วกด Resume ต่อ — ทำแบบนี้ทุกรูป)
- [ ] ปุ่ม **Window** → `Hann` → 📷 **F10**
- [ ] **กด KEY1 ค้างไว้** (โทนเลื่อนเป็น 1007.8 Hz)
  - [ ] Window `Rect` → 📷 **F11** (ฐาน peak จะกว้าง = spectral leakage)
  - [ ] Window `Hann` → 📷 **F12** (leakage ลดลง)
  - ปล่อย KEY1
- [ ] ยก **SW9 ขึ้น** (เพิ่มโทน 3000 Hz) → 📷 **F13** (เห็น 2 peak: 1000 กับ 3000 Hz) → เอา SW9 ลง
- [ ] จดลงตาราง: ความถี่ peak ที่อ่านได้ของแต่ละรูป

---

## ขั้น 5 — พิสูจน์ sampling rate ด้วยออสซิลโลสโคป (10 นาที)

> โพรบ: ปลายเข็มจิ้มขาบน JP1 (หรือใช้สายจัมเปอร์เมียต่อออกมา), ปากคีบ GND หนีบ JP1 pin 12 หรือ 30

- [ ] CH1 → **JP1 pin 6** (`fs_tick`). กด **Auto/Autoset**
- [ ] เปิด Measure → **Frequency** และ **Period**
  - ผลที่ต้องเห็น: **8.000 kHz**, period **125 µs** (= 2/Fs → Fs = 16 kHz)
  - [ ] 📷 **F14** (ให้เห็นค่าที่วัดบนจอ)
- [ ] CH2 → **JP1 pin 4** (CS ของ ESP32). Trigger source = CH2, falling edge. Time/div ≈ **1 ms**
  - ผลที่ต้องเห็น: ช่วง CS ต่ำ (~4 ms) แต่ CH1 ยังเป็นสี่เหลี่ยมสม่ำเสมอไม่สะดุด
  - [ ] 📷 **F15**
- [ ] รันในหน้าต่าง cmd ใหม่ (ปิดหน้าต่างกราฟก่อน):
  ```
  python task3_host.py --port COM7 --check 20
  ```
  - ผลที่ต้องเห็นบรรทัดสุดท้าย: `RESULT: Fs_est = 16000.xx S/s … OK; lost blocks = 0`
  - [ ] 📷 **F17** (หน้าจอ cmd)

---

## ขั้น 6 — ต่อ MCP3201 และเปลี่ยน FPGA เป็นโหมด ADC จริง (20 นาที)

### 6.1 ต่อวงจรบน breadboard (ถอด USB ของ DE10-Lite ก่อน)
> หา **ขา 1** ของ MCP3201: มุมที่มีจุดกลม/รอยบากครึ่งวงกลม. ขา 1–4 ด้านซ้าย (บนลงล่าง), ขา 5–8 ด้านขวา (ล่างขึ้นบน)

| ✔ | ขา MCP3201 | ต่อไปที่ |
|---|---|---|
| [ ] | 1 VREF | 3.3 V (JP1 pin **29**) |
| [ ] | 2 IN+ | ตัวต้านทาน 1 kΩ → (ปลายอีกข้างปล่อยไว้ก่อน เดี๋ยวต่อ generator) |
| [ ] | 3 IN− | GND |
| [ ] | 4 VSS | GND (JP1 pin **30**) |
| [ ] | 5 CS | JP1 pin **7** |
| [ ] | 6 DOUT | JP1 pin **10** |
| [ ] | 7 CLK | JP1 pin **8** |
| [ ] | 8 VDD | 3.3 V |
| [ ] | ตัวเก็บประจุ 100 nF | คร่อมระหว่างขา 8 กับ GND (ให้ใกล้ชิปที่สุด) |

- [ ] **ไม่ต้องต่อ** JP1 pin 9
- [ ] ใช้ราง + ของ breadboard เป็น 3.3 V และราง − เป็น GND จะต่อง่ายกว่า
- [ ] 📷 **F06b** ถ่ายวงจร breadboard ใกล้ ๆ

### 6.2 สร้างโปรเจกต์ใหม่สำหรับ MCP3201
- [ ] ใน cmd:
  ```
  cd C:\task3\fpga
  C:\intelFPGA_lite\20.1\quartus\bin64\quartus_sh -t create_project.tcl 0 3201
  ```
  - ผลที่ต้องเห็น: `ADC_SELECT = 0, MCP_PART = 3201`
  - (วิธีสำรอง Tcl Console: แก้ไฟล์เป็น `set adc_select 0` และ `set mcp_part 3201` แล้ว `source create_project.tcl`)
- [ ] Quartus: ถ้าถามว่าไฟล์เปลี่ยน → Yes/Reload. **Start Compilation** → **Programmer → Start** (เหมือนขั้น 3.3–3.4)

### 6.3 ดูสัญญาณ MCP3201 บนสโคป
- [ ] CH1 → JP1 pin **7** (CS ของ MCP), CH2 → JP1 pin **8** (CLK). Trigger CH1 falling. Time/div ≈ **5 µs**
  - ผลที่ต้องเห็น: CS ต่ำช่วงสั้น ๆ มี CLK **16 ลูก** และ CS เกิดซ้ำทุก **62.5 µs** (Frequency CH1 = **16.00 kHz**)
  - [ ] 📷 **F16a** ซูมให้เห็น 16 clock
  - [ ] 📷 **F16b** time/div 20 µs ให้เห็นค่า frequency 16 kHz

---

## ขั้น 7 — ทดลองกับ function generator (20 นาที)

### 7.1 ตั้ง generator (**ห้ามต่อเข้าวงจรก่อนเช็ก**)
- [ ] ตั้ง: **Sine, 1 kHz, Amplitude 1.5 Vpp, Offset 1.65 V**
- [ ] ตั้ง Output load = **High-Z** (มักอยู่ใน Utility / Output Setup / Load)
- [ ] เปิด Output แล้ววัดด้วยสโคปก่อน (ยังไม่ต่อ MCP):
  - ต้องได้ **min ≈ 0.9 V, max ≈ 2.4 V** (อยู่ใน 0–3.3 V)
  - ❗ ถ้า max เกิน 3.3 V หรือ min ต่ำกว่า 0 V → **ห้ามต่อ** แก้ค่าก่อน (มักเป็นเพราะ load ไม่ใช่ High-Z)
  - [ ] 📷 **F18**
- [ ] ต่อ: สายแดง generator → ปลายว่างของตัวต้านทาน 1 kΩ (เข้า IN+), สายดำ → GND

### 7.2 วัดผล
- [ ] เปิด host: `python task3_host.py --port COM7`
  - ผลที่ต้องเห็น: บรรทัดบน `src=MCP320x ADC`, waveform เป็นไซน์ ~0.9–2.4 V
- [ ] 1000 Hz, Window Hann → 📷 **F19** (peak ≈ 1000 Hz)
- [ ] เปลี่ยน generator เป็น **1007.8125 Hz** (ถ้าใส่ทศนิยมไม่ได้ ใช้ 1007.8)
  - [ ] Window Rect → 📷 **F20**
  - [ ] Window Hann → 📷 **F21**
- [ ] **7000 Hz** → 📷 **F22** (peak ≈ 7000 Hz ถูกต้อง)
- [ ] **9000 Hz** → 📷 **F23** (peak ไปโผล่ที่ **≈ 7000 Hz** = aliasing เพราะเกิน Fs/2 = 8 kHz)
- [ ] (เสริม) ลอง 15 kHz → peak จะอยู่ที่ ≈ 1 kHz (16 − 15)
- [ ] จดลงตาราง: ความถี่ที่ตั้ง vs ความถี่ peak ที่อ่านได้
- [ ] ปิด output generator แล้วถอดสาย generator ออก

---

## ขั้น 8 — ทดลองกับไมค์ + ทริกเกอร์ (20 นาที)

### 8.1 ต่อไมค์
- [ ] MAX4466: **VCC → 3.3 V, GND → GND, OUT → ตัวต้านทาน 1 kΩ** (ที่เดิมที่ generator เคยต่อ)
- [ ] เปิด host. ห้องเงียบ → 📷 **F25** (noise floor; สังเกตหนามที่ 50 Hz ถ้ามี)
  - ❗ waveform ชนขอบบน/ล่างตลอด: หมุนตัวต้านทานปรับ gain ด้านหลังไมค์ลง (ทวนเข็ม)

### 8.2 เสียงต่อเนื่อง (ไม่ต้องใช้ทริกเกอร์, ใช้ Pause ก่อนถ่าย)
- [ ] พูด "อาาาา" ยาว ๆ ใกล้ไมค์ → Pause → 📷 **F26** → Resume
- [ ] เปิดแอปโทนในมือถือ 1000 Hz ใกล้ไมค์ → 📷 **F28** (เทียบกับ F19)
- [ ] ผิวปาก / เปิดเพลงที่มีเครื่องดนตรี → 📷 **F29** (เห็น harmonic เป็นเส้นซ้อนใน spectrogram)
- [ ] ตะโกนใกล้ไมค์จน LEDR3 ติด / waveform ยอดแบน → 📷 **F30** (clipping)

### 8.3 เหตุการณ์ฉับพลัน (ใช้ทริกเกอร์)
- [ ] ตั้งปุ่ม: **Trigger: SINGLE**, **Detect: level**, **Edge: rise**, Threshold 12 dB
- [ ] ตบมือ 1 ครั้ง
  - ผลที่ต้องเห็น: ภาพหยุดเอง, หัวกราฟสีแดง `CAPTURED EVENT #…`, เส้นประแดงที่ 0 ms, กราฟ FFT มีเส้นเทา (ก่อน) กับน้ำเงิน (หลัง)
  - ❗ ไม่จับ: เลื่อน Threshold ลงเหลือ ~8 dB / จับเองทั้งที่ไม่ได้ตบ: เลื่อนขึ้น ~18 dB
  - [ ] 📷 **F27** แล้วกด **Save** (ได้ PNG + .wav ของเหตุการณ์ในโฟลเดอร์ host)
- [ ] กด **Re-arm** → **Edge: fall** → เปิดโทนมือถือค้างไว้ 3 วินาทีแล้วหยุด → 📷 **F27b** (จับตอนเสียงหยุด)
- [ ] กด **Re-arm** → **Detect: spectrum** → เปิดโทน 1000 Hz ค้าง แล้วเปลี่ยนเป็น 2000 Hz ในแอป → 📷 **F27c** (จับการเปลี่ยนความถี่ทั้งที่ดังเท่าเดิม)
- [ ] จดลงตาราง: ค่า `score` และ `level change` (dB) ที่หัวกราฟแต่ละรูป

---

## ขั้น 9 — (ไม่บังคับ ถ้ามีเวลา) MAX 10 ADC ในชิป

ข้ามได้ถ้าเวลาไม่พอ ต้องสร้าง IP 2 ตัวก่อน (ทำตาม README ข้อ 3.2) แล้ว:
- [ ] ต่อ OUT ไมค์/generator เข้า **Arduino A0** ของ DE10-Lite
- [ ] `quartus_sh -t create_project.tcl 1` → compile → program
- [ ] generator 1 kHz → 📷 **F24** (เทียบกับ F19)

---

## ขั้น 10 — ก่อนเก็บของ (5 นาที)

- [ ] เช็กว่ามีรูปครบ: F04 F06 F06b F07 F08–F23 F25–F30 F27b F27c (F05 F24 ไม่บังคับ)
- [ ] ก๊อปไฟล์ `task3_*.png`, `task3_event*.wav` จาก `C:\task3\host` ไปไว้ใน `C:\task3\pics`
- [ ] ก๊อปทั้งโฟลเดอร์ `C:\task3` ลงแฟลชไดรฟ์ / ส่งเข้าอีเมลตัวเอง (รวม `output_files\*.sof`)
- [ ] ถ่ายรูปตารางจดค่า
- [ ] ปิด generator, ถอดสาย, คืนอุปกรณ์

---

## ทำที่บ้านทีหลัง (ไม่ต้องใช้แล็บ)

- [ ] Simulation (รูป F01–F03): ตามคำสั่งใน README ข้อ 3.4 (ModelSim หรือ GHDL)
  - 📷 **F01** ข้อความ `TB PASSED`
  - 📷 **F02** waveform ช่วง SPI ส่งเฟรม (cs_n, sclk, miso, drdy)
  - 📷 **F03** waveform ช่วงอ่าน MCP (adc_cs_n, adc_sclk, adc_dout) — ใช้ `-gPART=3201 -gMSCLK=800000`
- [ ] รูปวาด block diagram / timing diagram / โครงสร้างเฟรม (ให้ Claude วาดให้)
- [ ] เขียนรายงานตามโครงในข้อความก่อนหน้า (ช่วง 6) และตารางเปรียบเทียบ Task 1 ใน README ข้อ 7

---

### สรุปผลที่ "ต้องได้" (ใช้เช็กเร็ว)

| สิ่งที่วัด | ค่าที่ต้องได้ |
|---|---|
| fs_tick (JP1 pin 6) | 8.000 kHz |
| CS ของ MCP (JP1 pin 7) | 16.00 kHz, 16 clock ต่อครั้ง |
| `--check` Fs_est | ≈ 16000 S/s, lost = 0 |
| test ramp | `TEST RAMP: OK`, spi_err = 0 |
| generator 1 kHz | peak ≈ 1000 Hz |
| generator 9 kHz | peak ≈ 7000 Hz (alias) |
| ความละเอียดความถี่ | Δf = 16000/1024 = 15.625 Hz |
