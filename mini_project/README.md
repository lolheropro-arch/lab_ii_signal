# Mini Shazam — ระบบจำเพลงจากเสียง (ESP32 + FPGA + Python)

ฟังเสียงเพลงจากไมค์ 5–10 วินาที แล้วบอกว่าเป็นเพลงอะไร และกำลังเล่นอยู่ที่นาทีไหนของเพลง
ใช้หลัก **Audio Fingerprinting** ตามเปเปอร์ของ Avery Wang (ผู้ร่วมก่อตั้ง Shazam), ISMIR 2003

```
ไมค์ ─► FPGA (สุ่ม 16 kS/s) ─► ESP32 ─USB─► Python: fingerprint ─► ค้นในฐานข้อมูล ─► ชื่อเพลง
```

---

## โครงสร้างไฟล์

| ไฟล์ | ทำหน้าที่ |
|---|---|
| `config.py` | **ค่าตั้งทั้งหมด** (พอร์ต, baud rate, sample rate, พารามิเตอร์อัลกอริทึม) แก้ที่นี่ที่เดียว |
| `fingerprint.py` | หัวใจ DSP: เตรียมสัญญาณ → Spectrogram → หาจุดยอด → สร้าง hash |
| `database.py` | เก็บ hash ลง SQLite และค้นหาเพลงด้วย offset histogram |
| `audio_input.py` | รับเสียง 2 แบบ: ไมค์ผ่าน FPGA + ESP32 (Serial), ไฟล์ทดสอบ |
| `app.py` | **โปรแกรมหลัก (GUI)** |
| `experiment.py` | ทดลองวัดความแม่นยำอัตโนมัติ ได้ตาราง CSV + กราฟไว้ใส่รายงาน |
| `songs/` | ใส่ไฟล์เพลงที่นี่ |
| `fingerprints.db` | ฐานข้อมูล (สร้างให้อัตโนมัติ ลบทิ้งได้ถ้าอยากเริ่มใหม่) |

---

## ติดตั้ง (ทำครั้งเดียว)

ต้องมี Python 3.9 ขึ้นไป

```bash
pip install -r requirements.txt
```

- **Windows:** tkinter มากับ Python อยู่แล้ว
- **Linux:** ถ้าเจอ `No module named tkinter` ให้ติดตั้งเพิ่ม `sudo apt install python3-tk`
- ไฟล์ `.m4a` ต้องมี [ffmpeg](https://ffmpeg.org/) ในเครื่อง (mp3/wav/flac ไม่ต้อง)

## วิธีใช้

1. คัดลอกไฟล์เพลงลงโฟลเดอร์ `songs/` (ชื่อไฟล์ = ชื่อเพลงที่จะแสดง)
2. รัน `python app.py`
3. กด **"เพิ่มเพลงทั้งหมดในโฟลเดอร์ songs/"** (ครั้งแรกใช้เวลาเพลงละไม่กี่วินาที)
4. เลือกแหล่งเสียง แล้วกด **"ฟังและค้นหาเพลง"**

| แหล่งเสียง | ใช้เมื่อ |
|---|---|
| ไฟล์ทดสอบ | ทดสอบอัลกอริทึมโดยไม่ต้องต่ออะไร — สุ่มตัดช่วงจากไฟล์ และใส่ noise ได้ (ช่อง SNR, เว้นว่าง = ไม่ใส่) |
| ESP32 (USB-Serial) | ใช้งานจริง: ไมค์ → FPGA → ESP32 → คอม — เลือกพอร์ตจาก dropdown (กด ↻ เพื่อรีเฟรช) |

### อ่านกราฟใน GUI
1. **Waveform** — เสียงที่อัดได้ (ถ้าแบนติดขอบ = clip → ลด gain ไมค์)
2. **Spectrogram + จุดฟ้า** — จุดยอดที่ใช้เป็นลายนิ้วมือ เส้นประ = ช่วงความถี่ที่ใช้ (300–3800 Hz)
3. **Offset histogram** — ถ้าเจอเพลง จะมี **แท่งเดียวสูงโด่ง** ตรงตำแหน่งในเพลง ถ้าไม่เจอจะกระจายเตี้ย ๆ

---

## รูปแบบข้อมูลที่ ESP32 ต้องส่ง

ส่งเป็น **binary** ต่อเนื่องเป็นบล็อก แต่ละบล็อกมี header นำหน้า:

```
[0xAA 0x55][sample 0][sample 1] ... [sample 1023][0xAA 0x55][sample 0] ...
             int16 little-endian (2 ไบต์ต่อ sample)
```

ฝั่ง Arduino ทำได้ง่าย ๆ เมื่อบล็อกเต็ม:
```cpp
const uint8_t SYNC[2] = {0xAA, 0x55};
Serial.write(SYNC, 2);
Serial.write((uint8_t*)block, 1024 * sizeof(int16_t));
```

ถ้า sketch เดิมส่งรูปแบบอื่น **ไม่ต้องแก้ sketch** ให้แก้ใน `config.py` แทน:

| ค่า | ความหมาย |
|---|---|
| `INPUT_FS` | sample rate ที่บอร์ดส่งมา (16000 สำหรับ INMP441, 10000 สำหรับ Task 1, 8000 ถ้า FPGA decimate แล้ว) |
| `BLOCK_SIZE` | จำนวน sample ต่อบล็อก |
| `SYNC_BYTES` | header (`b""` ถ้าไม่มี) |
| `SAMPLE_DTYPE` | `"<i2"` = int16, `"<u2"` = uint16 (ADC 12-bit) — DC offset จะถูกลบให้อัตโนมัติ |
| `BAUD_RATE` | ต้องตรงกับ `Serial.begin()` |

> ⚠️ อัตรา 16 kS/s × 2 ไบต์ = 32 kB/s ต้องใช้ baud ≥ 460800 (แนะนำ 921600 หรือ 2 Mbaud)

---

## ทดลองสำหรับรายงาน

```bash
python experiment.py                                         # ค่าเริ่มต้น
python experiment.py --lengths 2 5 10 --snr none 10 5 0 -5 --trials 30
python experiment.py --negatives other_songs/                # ทดสอบเพลงที่ "ไม่มี" ในฐานข้อมูล
```

ได้ไฟล์ `results/experiment_<เวลา>.csv` และกราฟ `.png` (Accuracy vs SNR แยกตามความยาวคลิป)

**ไอเดียการทดลองเพิ่มเติม** (ทำผ่าน GUI)
- เปิดเพลงจากลำโพงมือถือ vs ลำโพงคอม
- ระยะห่างลำโพง–ไมค์ 0.5 / 1 / 2 เมตร
- มีคนพูดแทรก / เปิดพัดลม
- เทียบไมค์ MAX4466 (analog) กับ INMP441 (I²S)

---

## ปรับจูนพารามิเตอร์ (`config.py`)

> ⚠️ แก้ค่าในหมวด "Fingerprint" แล้ว **ต้องกดล้างฐานข้อมูลและเพิ่มเพลงใหม่** เพราะ hash จะเปลี่ยน

| อาการ | ลองปรับ |
|---|---|
| เพลงที่ไม่มีในฐานข้อมูล แต่ระบบตอบว่าเจอ | เพิ่ม `MIN_RATIO` (เช่น 3–4) |
| เพลงที่มีอยู่ แต่หาไม่เจอเมื่อเสียงรบกวนเยอะ | ลด `MIN_RATIO` (เช่น 2), เพิ่ม `RECORD_SECONDS` |
| จุดยอดน้อยเกินไป (เห็นจุดฟ้าน้อย) | ลด `PEAK_MIN_DB` หรือลด `PEAK_NEIGHBORHOOD` |
| ฐานข้อมูลใหญ่/ช้า | เพิ่ม `PEAK_MIN_DB`, ลด `FAN_OUT` |

## แก้ปัญหาที่พบบ่อย

| ปัญหา | สาเหตุ / วิธีแก้ |
|---|---|
| `ไม่พบ header ของบล็อก` | baud rate ไม่ตรง, `SYNC_BYTES` ไม่ตรงกับ sketch, หรือ Serial Monitor ของ Arduino IDE เปิดค้างอยู่ (ต้องปิด) |
| `Permission denied: /dev/ttyUSB0` (Linux) | `sudo usermod -a -G dialout $USER` แล้ว logout/login |
| Waveform มีแต่สัญญาณรบกวน / เสียงเพี้ยน | `SAMPLE_DTYPE` หรือ `INPUT_FS` ไม่ตรงกับที่บอร์ดส่ง |
| Waveform แบนติดขอบ | เสียงดังเกิน → ลด gain ไมค์ หรือลดเสียงลำโพง |

---

## หลักการโดยย่อ (สำหรับอธิบายตอนนำเสนอ)

1. **Spectrogram** — STFT ด้วย Hann window, N = 1024 ที่ 8 kHz → ความละเอียด 7.8 Hz, 1 เฟรม = 32 ms
2. **Constellation map** — เก็บเฉพาะจุดที่ดังที่สุดในพื้นที่รอบตัว จุดพวกนี้ทนต่อ noise
3. **Combinatorial hashing** — จับคู่จุดยอด: `hash = (f1, f2, Δt)` → ไม่ขึ้นกับความดังและตำแหน่งเวลา
4. **Offset voting** — hash ที่ตรงกันของเพลงที่ถูกจะมี `t_เพลง − t_คลิป` เท่ากันหมด → histogram มีแท่งเดียวสูงโด่ง
5. **ตัดสินผล** — ต้องได้คะแนน ≥ `MIN_MATCHES` และมากกว่าคู่แข่ง ≥ `MIN_RATIO` เท่า

อ้างอิง: A. Wang, "An Industrial-Strength Audio Search Algorithm," *Proc. ISMIR*, 2003.
