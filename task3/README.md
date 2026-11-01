# Task 3 — Audio Sampling ด้วย MAX 10 FPGA (DE10-Lite) + ESP32-S3 UNO

## 0. รายการอุปกรณ์ที่ต้องเตรียม

| อุปกรณ์ | จำนวน | หมายเหตุ |
|---|---|---|
| DE10-Lite + สาย USB-B (USB-Blaster) | 1 | |
| ESP32-S3 UNO (บอร์ดสีม่วง) + สาย USB-C (ต้องเป็นสายที่ส่งข้อมูลได้) | 1 | sketch ตั้งค่าไว้สำหรับบอร์ดนี้แล้ว |
| **MCP3202** (DIP-8) | 1 | ถ้าไม่มี ใช้ MCP3201 / MCP3204 / MCP3208 / MCP3008 แทนได้ (ดูข้อ 1.2) |
| ตัวเก็บประจุ 100 nF (เซรามิก) | 1 | decouple ที่ VDD ของ MCP |
| ตัวต้านทาน 1 kΩ | 1 | ต่ออนุกรมเข้า CH0 เพื่อกันกระแสเกิน |
| ไมค์ MAX4466 | 1 | |
| Breadboard | 1 | |
| สายจัมเปอร์ **ผู้–เมีย** | ~12 เส้น | ฝั่งเมียเสียบขา JP1 ของ DE10-Lite (เป็นขาตัวผู้), ฝั่งผู้เสียบ header ของ S3 UNO หรือ breadboard |
| สายจัมเปอร์ ผู้–ผู้ | ~6 เส้น | ใช้บน breadboard |
| Oscilloscope 2 ช่อง + โพรบ 2 เส้น | 1 | |
| Function generator + สาย BNC–ปากคีบ | 1 | |
| คอมพิวเตอร์ที่มี Quartus Prime Lite, Arduino IDE (ESP32 core), Python (pyserial numpy matplotlib) | 1 | |
| มือถือที่มีแอปสร้างโทนเสียง | 1 | ใช้ในการทดลองกับไมค์ |

```
 Mic (MAX4466) ──► ADC ──► FPGA: BRAM ping-pong ──SPI──► ESP32 ──USB──► Python / MATLAB
                   │        (Fs = 16 kS/s จาก clock 50 MHz)   (master)      waveform + FFT
                   ├─ MCP3202 (SPI ADC ภายนอก)      ADC_SELECT = 0  (ค่าเริ่มต้น)
                   ├─ MAX 10 on-chip ADC (A0)       ADC_SELECT = 1
                   └─ DDS test tone ใน FPGA          ADC_SELECT = 2
```

| โฟลเดอร์ / ไฟล์ | หน้าที่ (ข้อในใบงาน) |
|---|---|
| `fpga/sample_tick_gen.vhd` | สร้าง sampling tick 16 kHz จาก 50 MHz (÷3125) — Hint 1.3, ข้อ 6 |
| `fpga/mcp3202_reader.vhd` | SPI master อ่าน MCP3202 (หรือ MCP3204/3208/3008) ทีละ sample ตาม tick — Hint 2.1–2.3 |
| `fpga/max10_adc_sampler.vhd` | ห่อ Modular ADC Core ของ MAX 10 (สั่ง convert ทุก tick) — Hint 1.1–1.2 |
| `fpga/test_tone_gen.vhd` | แหล่งสัญญาณทดสอบ sine ความถี่แม่นยำ (ตรง bin / ครึ่ง bin / 2 โทน) |
| `fpga/audio_block_buffer.vhd` | Dual-port Block RAM 2×1024 แบบ ping-pong + ตรวจ overrun — ข้อ 2, Hint 1.4/2.4 |
| `fpga/spi_slave_block.vhd` | SPI slave + โปรโตคอลส่ง block ให้ ESP32 — ข้อ 3 |
| `fpga/de10lite_audio_top.vhd` | Top-level, LED แสดงระดับเสียง/clipping/overrun |
| `fpga/de10lite_pins.tcl`, `de10lite_audio.sdc`, `create_project.tcl` | pin, timing, สร้างโปรเจกต์ Quartus |
| `fpga/tb/tb_audio_system.vhd` | testbench ตรวจอัตโนมัติ (มีโมเดล MCP3202 + master แบบ ESP32) |
| `esp32/task3_esp32_bridge/task3_esp32_bridge.ino` | ESP32-S3 UNO: SPI master → USB serial (binary) — ข้อ 4 |
| `host/task3_host.py` | Python: waveform + FFT + spectrogram + ปุ่ม Pause + ทริกเกอร์จับเหตุการณ์ + สถิติ/วัด Fs — ข้อ 5 |
| `host/task3_host.m` | MATLAB เวอร์ชันเต็ม ความสามารถเท่า Python: waveform + FFT + spectrogram, Pause, ทริกเกอร์, Save, โหมด check/demo/selftest |

---

## 1. การต่อสาย

### 1.1 DE10-Lite ↔ ESP32-S3 UNO (ลอจิก 3.3 V ทั้งคู่ ต่อตรงได้)

| สัญญาณ | DE10-Lite (JP1) | ESP32-S3 UNO (ป้ายบนบอร์ด) | ทิศทาง |
|---|---|---|---|
| SCLK | GPIO[0] pin 1 | **IO12** (D13) | S3 → FPGA |
| MOSI | GPIO[1] pin 2 | **IO11** (D11) | S3 → FPGA |
| MISO | GPIO[2] pin 3 | **IO13** (D12) | FPGA → S3 |
| CS_N | GPIO[3] pin 4 | **IO10** (D10) | S3 → FPGA |
| DRDY | GPIO[4] pin 5 | **IO14** (D7) | FPGA → S3 |
| **GND** | pin 12 หรือ 30 | GND (ข้าง IO12) | **ต้องต่อ common ground** |

ทั้งหมดอยู่บน header แถว DIGITAL (ช่วงที่มีป้าย SPI) ของ S3 UNO. ห้ามใช้ IO19/IO20 (เป็นสาย USB D−/D+) และ IO3/IO46 (strapping pin)
ถ้าใช้ ESP32 dev board ธรรมดาแทน: ตั้ง `BOARD_ESP32_S3 0` ใน sketch แล้วใช้ SCK 18, MOSI 23, MISO 19, CS 5, DRDY 4

สายจัมเปอร์ควรสั้น (< 20 cm) ถ้าข้อมูลเพี้ยนให้ลด `SPI_HZ` ใน sketch เป็น 2 MHz

### 1.2 MCP3202 (ADC_SELECT = 0)

| MCP3202 | ต่อกับ |
|---|---|
| 1 CS/SHDN | JP1 GPIO[6] pin 7 |
| 2 CH0 | OUT ของ MAX4466 (หรือ function generator ผ่านวงจร 1.4) |
| 3 CH1 | GND (ไม่ใช้) |
| 4 VSS | GND |
| 5 DIN | JP1 GPIO[8] pin 9 |
| 6 DOUT | JP1 GPIO[9] pin 10 |
| 7 CLK | JP1 GPIO[7] pin 8 |
| 8 VDD/VREF | 3.3 V (JP1 pin 29) + ตัวเก็บประจุ 100 nF ลง GND |

VREF = VDD = 3.3 V ⇒ 1 LSB = 3.3/4096 ≈ 0.81 mV และไมค์ที่จ่าย 3.3 V ให้ DC ≈ 1.65 V กลางช่วงพอดี
ไมค์ MAX4466: VCC → 3.3 V, GND → GND, OUT → 1 kΩ → CH0

**ถ้าในแล็บไม่มี MCP3202** ใช้ตัวอื่นได้ โดยสร้างโปรเจกต์ด้วย `quartus_sh -t create_project.tcl 0 <part>` (ใน testbench ผ่านทั้ง 3 แบบ):

| ชิป | part | ขาที่ต่อ (DIP) | ความละเอียด |
|---|---|---|---|
| MCP3202 | 3202 | ตามตารางข้างบน (8 ขา) | 12 bit |
| **MCP3201** (-B/-C) | 3201 | ดูตาราง MCP3201 ด้านล่าง (ไม่มีขา DIN) | 12 bit, 1 ช่อง, SCLK 800 kHz อัตโนมัติ |
| MCP3204 / MCP3208 | 3204 / 3208 | CH0 = pin 1, VDD = 14 (MCP3204) / 16 (MCP3208), VREF = ขาถัดลงมา (ต่อ 3.3 V), AGND/DGND → GND, CLK, DOUT, DIN, CS ตามป้ายใน datasheet | 12 bit |
| MCP3004 / MCP3008 | 3004 / 3008 | เหมือน MCP3204/3208 | 10 bit (FPGA เลื่อนเป็นสเกล 12 bit ให้) |

ชิปตระกูล 32xx/300x ทุกตัวขา CLK/DOUT/DIN/CS ต่อเข้า JP1 pin 8/10/9/7 เหมือนกันหมด

#### MCP3201 (ใช้ `quartus_sh -t create_project.tcl 0 3201`)

| MCP3201 | ต่อกับ |
|---|---|
| 1 VREF | 3.3 V (JP1 pin 29) |
| 2 IN+ | OUT ของไมค์ / function generator ผ่าน 1 kΩ |
| 3 IN− | GND |
| 4 VSS | GND |
| 5 CS/SHDN | JP1 pin 7 |
| 6 DOUT | JP1 pin 10 |
| 7 CLK | JP1 pin 8 |
| 8 VDD | 3.3 V + 100 nF ลง GND |

JP1 pin 9 (DIN) ไม่ต้องต่อ. เกรด -B (INL ±1 LSB) กับ -C (±2 LSB) ใช้โค้ดเดียวกัน

### 1.3 MAX 10 on-chip ADC (ADC_SELECT = 1)

ต่อ OUT ของไมค์เข้า **Arduino header A0** (ADC1 channel 1). ขาบนบอร์ดผ่าน buffer + divider ทำให้ช่วงภายนอกคือ 0–5 V → code = Vin/5 V × 4096 (ไมค์ 3.3 V จะใช้ช่วงได้ ~66 %)

### 1.4 Function generator แทนไมค์ (ข้อ 6 / Question 3 ของ Task 1)

ตั้งเครื่องกำเนิดสัญญาณ: Sine, **Offset = 1.65 V**, **Amplitude ≤ 2.0 Vpp** (ไม่เกินช่วงที่ไมค์ปล่อยจริง) และ **ตั้ง output load = High-Z** (ถ้าเครื่องตั้งไว้ 50 Ω ค่าที่ปล่อยจริงจะเป็น 2 เท่าของที่แสดง). ตรวจด้วย oscilloscope ก่อนเสียบเข้า ADC ว่า min ≥ 0 V และ max ≤ 3.3 V. ใส่ตัวต้านทาน 1 kΩ อนุกรมเข้า CH0 เพื่อจำกัดกระแสถ้าเผลอเกินช่วง

---

## 2. โปรโตคอล

### 2.1 FPGA ↔ ESP32 (SPI mode 0, MSB first, word 16 bit big-endian)

DRDY = '1' เมื่อมี block ที่เต็มแล้วรออ่าน (handshake line) → ESP32 ดึง CS_N ลง แล้ว clock ทั้งเฟรม **N + 6 = 1030 word (2060 byte)**:

| word | MOSI (ESP32) | MISO (FPGA) |
|---|---|---|
| 0 | `CMD`, 0x00 | `0xC3` \| STATUS (bit0 = ready, bit7..4 = version 1) |
| 1 | 0 | `0xA55A` SYNC |
| 2 | 0 | SEQ — หมายเลข block (นับทุก block รวมที่ถูก drop) |
| 3 | 0 | FLAGS<<8 \| DROPS — FLAGS: b0 valid, b1 test ramp, b3..2 source |
| 4 | 0 | N = 1024 |
| 5 … N+4 | 0 | sample[0…N−1] = `0000` & ADC 12 bit |
| N+5 | 0 | CHECKSUM = Σ sample mod 65536 |

| CMD | ความหมาย |
|---|---|
| `0x01` READ_BLOCK | ส่ง sample จริง; เมื่ออ่านครบทั้งเฟรมแล้วยก CS_N ขึ้น FPGA จะปล่อย bank (DRDY → 0) |
| `0x02` READ_TEST | แทน sample ด้วย ramp 0,1,…,N−1 เพื่อทดสอบสาย/บิตสลับ; ไม่ปล่อย bank |
| อื่น ๆ | status poll (อ่านแค่ word 0 ก็พอ) |

กลไกในฝั่ง FPGA:
* SCLK/MOSI/CS ผ่าน synchronizer 2 FF ใน domain 50 MHz; FPGA เปลี่ยน MISO ~60 ns **หลัง** ขอบขาขึ้นของ SCLK (master sample ไปแล้ว) จึงนิ่งเกือบเต็มคาบก่อนขอบถัดไป — ใช้ได้ถึง ~8 MHz
* ขณะ CS_N ต่ำ bank ที่กำลังส่งถูก **lock**; ฝั่ง ADC เขียนอีก bank ต่อไปโดย **ไม่หยุดรอ** ⇒ Fs ไม่ถูกกระทบจากการโอนข้อมูล
* ถ้า ESP32 อ่านไม่ทัน: block ใหม่แทนที่ block ที่ยังไม่ถูกอ่าน หรือถ้ากำลังอ่านอยู่ block ที่เพิ่งเต็มจะถูกทิ้ง → DROPS เพิ่ม, SEQ กระโดด, LEDR2 ติดค้าง

ปริมาณข้อมูล: 16 000 × 2 B = 32 kB/s; ที่ SPI 4 MHz หนึ่ง block ใช้ ~4.2 ms จากคาบ block 64 ms (ใช้บัสแค่ ~7 %)

### 2.2 ESP32 → PC (USB serial 921 600 baud, binary little-endian)

| offset | ขนาด | field |
|---|---|---|
| 0 | 4 | sync `AA 55 33 CC` |
| 4 | 2 | seq (จาก FPGA) |
| 6 | 2 | n = 1024 |
| 8 | 1 | fpga_flags |
| 9 | 1 | fpga_drops |
| 10 | 2 | spi_errs (สะสม: เฟรม SPI ที่ sync/checksum ผิด) |
| 12 | 2 | esp_drops (สะสม: queue ฝั่ง USB เต็ม) |
| 14 | 4 | t_us = micros() ของ ESP32 ตอนรับ DRDY |
| 18 | 2 | fs nominal = 16000 |
| 20 | 2n | samples uint16 |
| 20+2n | 2 | checksum |

รวม 2070 byte/เฟรม (≈ 32.3 kB/s; 921 600 baud รับได้ ~92 kB/s). PC ส่งตัวอักษร `t` / `n` เพื่อสลับโหมด test ramp / ปกติ

ใน ESP32 มีสอง task: `spiTask` (core 0) รอ DRDY แล้วอ่าน SPI ลง buffer pool 6 ช่อง, `loop()` (core 1) ส่งออก USB — แยกการรับกับการส่งออกจากกัน

---

## 3. สร้างโปรเจกต์ Quartus

### 3.1 แบบ MCP3202 หรือ test tone (ไม่ต้องใช้ IP)
```
cd fpga
quartus_sh -t create_project.tcl 0     # 0 = MCP3202, 2 = test tone
quartus_sh --flow compile task3_audio
quartus_pgm -m jtag -o "p;output_files/task3_audio.sof"
```
(หรือเปิด `task3_audio.qpf` ใน GUI แล้วกด Compile / Programmer)

> ⚠ ตรวจหมายเลขพิน GPIO/LED/SW ใน `de10lite_pins.tcl` กับคู่มือ DE10-Lite หรือ DE10-Lite System Builder อีกครั้งก่อนโปรแกรม

### 3.2 แบบ MAX 10 on-chip ADC (ADC_SELECT = 1)
1. **IP Catalog → ALTPLL** ตั้งชื่อ `adc_pll` (VHDL): inclk0 = 50 MHz, c0 = 10 MHz, เปิด output `locked`
2. **IP Catalog → Modular ADC core** ตั้งชื่อ `adc_core`:
   Core variant = **ADC control core only**, ADC input clock = 10 MHz, Reference = Internal 2.5 V, เปิด **CH1** (Arduino A0)
3. Generate HDL แล้วรัน `quartus_sh -t create_project.tcl 1` (สคริปต์จะเพิ่ม `adc_pll.qip` และ `adc_core/synthesis/adc_core.qip` — ถ้า path ต่างให้ Add File เอง)
4. ถ้าชื่อพอร์ตที่ generate ได้ไม่ตรง ให้แก้เฉพาะ component declaration ใน `max10_adc_sampler.vhd`

ADC ของ MAX 10 ต้องใช้ clock จาก PLL1/PLL3 c0 — Quartus จะเลือก PLL ให้เอง

### 3.3 ตัวเลือก (generic ใน top หรือ `set_parameter`)
`FS_HZ` (16000), `ADDR_W` (10 → N = 1024), `MCP_SCLK_HZ` (1 MHz; ถ้า VDD 2.7 V ใช้ 500 kHz), `MCP_CHANNEL`, `MAX10_CH`
ถ้าเปลี่ยน N ต้องแก้ `N` ใน sketch ESP32 และ host ให้ตรงกัน

### 3.4 Simulation (GHDL หรือ ModelSim/Questa)
```
cd fpga
ghdl -a --std=93c sample_tick_gen.vhd mcp3202_reader.vhd test_tone_gen.vhd \
     audio_block_buffer.vhd spi_slave_block.vhd de10lite_audio_top.vhd tb/tb_audio_system.vhd
ghdl -r --std=93c tb_audio_system --stop-time=500ms                     # N=64, MCP3202 model
ghdl -r --std=93c tb_audio_system -gSRC=2 --stop-time=500ms             # test tone
ghdl -r --std=93c tb_audio_system -gADDR_W=10 -gNBLK=2 --stop-time=2000ms   # N=1024 เต็ม
```
testbench ตรวจ: Fs = 16 000 จากขา fs_tick, บิตคำสั่งที่ส่งให้ MCP3202, SYNC/N/checksum, ความต่อเนื่องของ sample ทั้งในและข้าม block, SEQ เรียงต่อกัน, ramp ของ READ_TEST, และการนับ drop เมื่อหยุดอ่าน 3 คาบ — ทั้ง 3 config ผ่านแล้ว (`==== TB PASSED ====`)

---

## 4. ESP32-S3 UNO
1. Arduino IDE → Boards Manager → ติดตั้ง **esp32 by Espressif** (2.x หรือ 3.x)
2. เปิด `esp32/task3_esp32_bridge/task3_esp32_bridge.ino` แล้วเลือกบอร์ด **ESP32S3 Dev Module** และเลือก Port ที่ขึ้นเมื่อเสียบ USB-C
3. Upload (ถ้าอัปโหลดไม่เข้า ให้กดปุ่ม BOOT/IO0 ค้างแล้วกด RST หนึ่งครั้ง จากนั้นปล่อย)
4. ถ้า upload สำเร็จแต่ host ไม่ได้ข้อมูลเลย ให้สลับ Tools → **USB CDC On Boot** (Enabled ↔ Disabled) แล้วอัปโหลดใหม่ เพราะขึ้นกับว่าพอร์ต USB-C ของบอร์ดผ่านชิป USB-UART หรือเป็น USB ของ S3 โดยตรง
5. ค่าที่ปรับได้อยู่ส่วน USER SETTINGS ด้านบนไฟล์ (ขา, `SPI_HZ`, `SERIAL_BAUD`, `N`)

ปิด Serial Monitor ของ Arduino IDE ก่อนรัน host ทุกครั้ง (พอร์ตใช้ได้ทีละโปรแกรม)

## 5. Host
```
pip install pyserial numpy matplotlib
python task3_host.py                      # หา port อัตโนมัติ (Windows: --port COM5, Linux: --port /dev/ttyUSB0)
python task3_host.py --demo               # ลองโปรแกรมโดยไม่มีฮาร์ดแวร์
python task3_host.py --check 20           # โหมดข้อความ: วัด Fs และนับ block หาย 20 s
```
### ปุ่มด้านล่างหน้าต่างกราฟ (ในวงเล็บคือคีย์ลัด)

| ปุ่ม | หน้าที่ |
|---|---|
| **Pause / Resume** (`p`) | หยุดภาพทั้งหมดเพื่อดูหรือถ่ายรูป; ข้อมูลยังรับต่อเบื้องหลัง (สถิติ/ทริกเกอร์ไม่หาย) |
| **Trigger: OFF → NORMAL → SINGLE** (`g`) | OFF = แสดงสด; NORMAL = แสดงเหตุการณ์ล่าสุดที่จับได้; SINGLE = จับเหตุการณ์เดียวแล้ว**หยุดภาพทั้งหน้าจออัตโนมัติ** |
| **Re-arm** (`r`) | รอจับเหตุการณ์ถัดไป (ใช้กับ SINGLE) และปล่อย Pause |
| **Detect: level / spectrum** (`d`) | level = ความดังเปลี่ยนฉับพลัน (ตบมือ, เริ่มพูด, เสียงเปิด/ปิด); spectrum = ส่วนประกอบความถี่เปลี่ยน แม้ความดังเท่าเดิม (เช่น โทน 1 kHz เปลี่ยนเป็น 1.5 kHz) |
| **Edge: rise / fall / both** (`e`) | (เฉพาะ level) ดังขึ้น / เบาลง (เสียงหยุด) / ทั้งสองแบบ |
| **Window: Hann / Rect** (`w`) | หน้าต่างของ FFT |
| **Save** (`s`) | บันทึก PNG ของทั้งหน้าจอ + ข้อมูลเหตุการณ์ที่จับได้เป็น .npz/.wav (ถ้าไม่มี จะบันทึก 10 s ล่าสุด) |
| **Threshold [dB]** (slider) | ความไวของทริกเกอร์ ค่าเริ่มต้น 12 dB (ลดลงถ้าจับไม่ติด, เพิ่มถ้าทริกเกอร์มั่ว) |

คีย์อื่น: `t` test ramp, `n` ปกติ, `l` สลับ dB/linear

### หลักการทริกเกอร์ (ใส่ในรายงานได้)
* แบ่งสัญญาณต่อเนื่องเป็นเฟรม 256 sample (16 ms) เทียบกับ **ระดับพื้นหลัง** ที่ปรับตัวช้า ๆ (~0.5 s)
* level: score = 20·log10(RMS เฟรม / RMS พื้นหลัง); spectrum: ค่าเฉลี่ยถ่วงน้ำหนักด้วยกำลังของ |ผลต่าง dB| ในแต่ละ bin
* ยิงเมื่อ score > threshold และสัญญาณดังกว่า 4 mV rms; จะยิงครั้งต่อไปได้เมื่อ score ลดลงต่ำกว่า threshold − 6 dB (hysteresis) ⇒ **1 เหตุการณ์ = 1 ทริกเกอร์**
* ตรวจในเธรดที่รับข้อมูลและเก็บ ring buffer 12 s จึงไม่พลาดเหตุการณ์ระหว่างการวาดจอ
* ภาพที่จับได้: waveform −64…+192 ms รอบจุดทริกเกอร์ (เส้นประแดง = t = 0) และกราฟ FFT เทียบ **ก่อน** (เทา) กับ **หลัง** (น้ำเงิน) ทริกเกอร์ 1024 sample; บน spectrogram มีลูกศรแดงชี้ทุกเหตุการณ์ และ console พิมพ์ค่า score/การเปลี่ยนระดับ (dB)

ทดลองได้ทันทีด้วย `python task3_host.py --demo` (มีเสียงตบมือจำลองทุก 3 s และโทนเปลี่ยนความถี่ทุก 6 s)
Linux: ถ้าเปิด port ไม่ได้ให้ `sudo usermod -aG dialout $USER` แล้ว log in ใหม่

### MATLAB (R2019b ขึ้นไป ไม่ต้องใช้ toolbox เพิ่ม)
ใน MATLAB เปลี่ยน Current Folder เป็น `host` แล้วพิมพ์ใน Command Window:
```
task3_host                     % หา COM เอง แล้วเปิดกราฟ
task3_host('COM7')             % ระบุพอร์ตเอง
task3_host('demo')             % ไม่มีฮาร์ดแวร์ ใช้ข้อมูลจำลอง
task3_host('check', 20)        % ไม่เปิดกราฟ วัด Fs และนับ block หาย 20 วินาที
task3_host('COM7', 15)         % เปิดกราฟ 15 วินาที แล้วบันทึก PNG + .mat + .wav อัตโนมัติ
task3_host('selftest')         % ทดสอบ parser / FFT / ทริกเกอร์ โดยไม่ต้องมีบอร์ด
```
ปุ่มด้านล่างหน้าต่างเหมือนเวอร์ชัน Python: Pause/Resume, Trigger OFF/NORMAL/SINGLE, Re-arm, Detect, Edge, Window, Scale dB/Linear, Save, Test ramp, Normal และแถบ Threshold
ปิดหน้าต่างเพื่อหยุด (พอร์ตจะถูกปล่อยให้อัตโนมัติ) · ใช้พร้อมกับโปรแกรม Python ไม่ได้ เพราะพอร์ตเปิดได้ทีละโปรแกรม

---

## 6. ขั้นตอนตรวจสอบ (ข้อ 6–7 ของใบงาน)

1. **ทดสอบลิงก์ก่อน**: สร้างด้วย `ADC_SELECT = 2`, เปิด host แล้วกด `t` → ต้องขึ้น `TEST RAMP: OK` และ `spi_err = 0`; กด `n` กลับโหมดปกติ
2. **ความถี่ที่แม่นยำ (test tone)**: SW = 64 → 1000 Hz ตรง bin 64 พอดี, peak แหลมทั้ง Rect/Hann. กด KEY1 ค้าง → 1007.8 Hz (ครึ่ง bin) เห็น spectral leakage ชัดในโหมด Rect และลดลงเมื่อใช้ Hann. SW9 = 1 เพิ่มโทน 3 kHz (ทดสอบ 2 โทน)
3. **Fs ด้วยฮาร์ดแวร์**: oscilloscope ที่ JP1 pin 6 (`fs_tick`) ต้องเป็นสี่เหลี่ยม **8.000 kHz** (คาบ 125 µs = 2/Fs) นิ่งตลอด แม้ขณะ ESP32 กำลังอ่าน SPI — trigger ที่ CS_N (pin 4) เทียบกันได้ว่าไม่มี jitter. pin 13 (`blk_tick`) สลับทุก 64 ms. ใช้โพรบอีกช่องที่ MCP3202 CS (pin 7) จะเห็น conversion ทุก 62.5 µs
4. **Fs จากข้อมูล**: `--check` แสดง `Fs_est` (คำนวณจาก SEQ ของ FPGA และเวลาของ ESP32) ควรได้ 16 000 ± crystal tolerance (~±0.005 %)
5. **ฟังก์ชันเจนเนอเรเตอร์ + MCP3202/MAX10**: sine 1 kHz, 1.5 Vpp, offset 1.65 V → peak ที่ ~1000 Hz; ลอง 1007.8125 Hz (ไม่เต็มรอบใน 1024 sample) เทียบ Rect vs Hann. ความละเอียดความถี่ Δf = Fs/N = 16000/1024 = **15.625 Hz**
6. **สัญญาณจริง**: เงียบ, พูด, ตบมือ, โน้ตดนตรี, โทนจากลำโพง; LEDR9..4 แสดงระดับ, LEDR3 ติดเมื่อ clipping (เสียงดังเกิน → ยอดสัญญาณแบน → เกิด harmonic ใน FFT)

---

## 7. เปรียบเทียบกับ Task 1 (ข้อ 8)

| ประเด็น | Task 1: ESP32 ADC | Task 3: FPGA |
|---|---|---|
| ผู้กำหนดเวลา sample | hardware timer/ISR ของ ESP32 — มี latency/jitter ของ interrupt (ระดับ µs) และถูกรบกวนได้จาก Wi-Fi/flash/ISR อื่น | ตัวนับจาก clock 50 MHz ใน logic ล้วน — jitter ระดับ ps ของ oscillator, ไม่มีซอฟต์แวร์เกี่ยวข้อง |
| ADC | SAR 12 bit ในชิป ESP32 — nonlinear, offset มาก, ต้อง calibrate | MCP3202 12 bit แยก (linear ดีกว่า, VREF ชัดเจน) หรือ MAX 10 ADC 12 bit 1 MSPS |
| การแยก acquisition / transfer | ทำด้วย ISR + double buffer ในซอฟต์แวร์บน CPU เดียวกัน | แยกทางกายภาพ: ADC path กับ SPI path เป็นวงจรขนาน, BRAM dual-port |
| เส้นทางข้อมูล | ADC → RAM ESP32 → USB | ADC → BRAM FPGA → SPI → ESP32 → USB (มีลิงก์เพิ่มหนึ่งชั้น ต้องมีโปรโตคอล/checksum) |
| การประมวลผล | CPU 240 MHz ทำ FFT ได้แต่แย่งเวลากับงานอื่น | ทำ filter/FFT แบบขนานได้ใน hardware แบบ deterministic (แต่ออกแบบยากกว่า) |
| ความยืดหยุ่น/ความง่าย | เขียนโค้ด C ง่าย แก้เร็ว | ต้องออกแบบ HDL, timing, simulation |
| ขยายช่อง/อัตรา | จำกัดด้วย CPU และ ADC ESP32 | เพิ่มช่อง/Fs ได้ง่ายเพียงเปลี่ยน logic (ข้อจำกัดอยู่ที่ ADC) |

---

## 8. Troubleshooting

| อาการ | สาเหตุที่เป็นไปได้ |
|---|---|
| `spi_err` เพิ่มเรื่อย ๆ, status ≠ 0xC3 | MISO ไม่ได้ต่อ/ต่อผิดขา, ไม่มี common GND, ไม่ได้โปรแกรม FPGA |
| ramp ผิดบางค่า | SCLK เร็วไป/สายยาว → ลด `SPI_HZ` เป็น 2 MHz |
| DRDY ไม่ขึ้นเลย | FPGA ค้าง reset (KEY0), ADC_SELECT=1 แต่ PLL ไม่ lock |
| ค่า MCP3202 คงที่ 0 หรือ 4095 | DIN/DOUT สลับกัน, CH0 ลอย, VDD ไม่ได้ต่อ |
| `lost` เพิ่ม, LEDR2 ติด | host อ่านไม่ทัน (ปิดโปรแกรมอื่นที่เปิด port), baud ไม่ตรงกัน |
| FFT มีหนามที่ 50 Hz และ harmonic | สัญญาณรบกวนจากไฟบ้านผ่านสายยาว — ใช้สายสั้น, ต่อ GND จุดเดียว |

---

## 9. แนวคิด Mini-Project (ต่อยอดจากระบบนี้)
* **Guitar/voice tuner + pitch tracker**: autocorrelation/YIN บน stream ต่อเนื่อง แสดงโน้ต ±cents และกราฟ pitch ตามเวลา
* **DTMF / tone-command decoder**: ใช้ Goertzel ถอดรหัสปุ่มโทรศัพท์จากลำโพงแล้วสั่งงาน (เช่นเปิด LED บน FPGA ผ่านคำสั่ง SPI ใหม่)
* **Acoustic event detector**: ตรวจจับเสียงตบมือ/กระจกแตก/เสียงนกหวีดด้วย spectral flux + threshold แล้ว log เหตุการณ์พร้อมเวลา
* **Sound-level meter แบบ A-weighting**: กรอง A-weight, คำนวณ Leq/Lmax เป็น dB(A) พร้อม calibrate กับแอปวัดเสียงอ้างอิง
