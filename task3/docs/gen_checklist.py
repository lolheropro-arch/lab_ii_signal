#!/usr/bin/env python3
"""Generates checklist.html -- Task 3 report evidence checklist (tick boxes, value
fields, example pictures from img/).  Run gen_examples.py first."""
import html
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "checklist.html"


def e(s):
    return html.escape(s, quote=True)


# Each item: id, title, how (html), expect (html), fields [(id,label,hint)], imgs [(file, caption)], opt
SECTIONS = [
    ("hw", "1", "รูปฮาร์ดแวร์และซอฟต์แวร์", "ถ่ายตอนต่อเสร็จและ compile ผ่านแล้ว", [
        dict(id="hw1", t="รูปวงจรจริงทั้งชุด",
             how="ถ่ายจากด้านบนให้เห็น DE10-Lite, breadboard กับ MCP3201 และไมค์, ESP32-S3 UNO และสายทุกเส้น โดยเฉพาะสาย <b>GND ร่วม</b> (JP1 ขา 12 → GND ของ S3)",
             exp="เทียบกับผังภาพรวมใน Wiring Manual ได้ทีละเส้น"),
        dict(id="hw2", t="รูปใกล้ JP1 และ breadboard",
             how="ซูมให้อ่านสีสายและตำแหน่งขาได้ 2 รูป: ปลาย JP1 ที่เสียบสาย และ MCP3201 บน breadboard (เห็นรอยบากชิป)",
             exp="ใช้คู่กับตารางต่อขาในรายงาน"),
        dict(id="hw3", t="ตารางต่อขา",
             how="คัดจาก Wiring Manual ส่วนที่ 1 (MCP3201 ↔ JP1 ขา 7, 8, 10, 29, 30) และส่วนที่ 2 (JP1 ขา 1–5, 12 ↔ S3 IO12, IO11, IO13, IO10, IO14, GND)",
             exp="ไม่ต้องถ่าย ทำเป็นตารางในรายงาน"),
        dict(id="hw4", t="Quartus · Compilation Report → Flow Summary",
             how="หลัง compile ด้วย <code>build.bat 0 3201</code> เปิด Compilation Report → Flow Summary แล้วจับหน้าจอ",
             exp="Logic elements ไม่ถึง 1,000 จาก 49,760 (ไม่ถึง 2%) · Memory bits ประมาณ 24,576 (บัฟเฟอร์ 2×1024×12 บิต) · M9K 3–4 บล็อก",
             fields=[("le", "Logic elements", "เช่น 812"), ("m9k", "Memory bits / M9K", "เช่น 24,576 / 3")]),
        dict(id="hw5", t="Quartus · RTL Viewer", opt=True,
             how="Tools → Netlist Viewers → RTL Viewer จับภาพระดับ top ที่เห็นบล็อก tick_gen, ADC reader, buffer, SPI slave",
             exp="ใช้แทน block diagram ได้"),
        dict(id="hw6", t="Quartus · หน้าตั้งค่า Modular ADC IP", opt=True,
             how="<b>ข้ามได้</b> เพราะชุดนี้ใช้ MCP3201 ทำเฉพาะถ้าลองโหมด MAX 10 ADC (<code>build.bat 1</code>)",
             exp="ADC control core only, clock 10 MHz, Internal 2.5 V, CH1"),
        dict(id="hw7", t="Simulation: TB PASSED + waveform", opt=True,
             how="ทำที่บ้านได้: รัน testbench ตาม README ข้อ 3.4 ด้วย <code>-gPART=3201 -gMSCLK=800000</code> จับข้อความ <code>TB PASSED</code> และ waveform ช่วง SPI กับช่วงอ่าน MCP",
             exp="หลักฐานว่า logic ถูกก่อนลงบอร์ด"),
        dict(id="hw8", t="โค้ดทั้งหมดสำหรับภาคผนวก",
             how="ไฟล์อยู่ใน <code>task3_fpga_audio.zip</code> แล้ว (VHDL, sketch ESP32, Python) ไม่ต้องทำอะไรเพิ่ม",
             exp="—"),
    ]),
    ("sc", "2", "วัดด้วยออสซิลโลสโคป", "ปากคีบ GND ของโพรบทุกเส้นที่ JP1 ขา 12 หรือ 30", [
        dict(id="sc1", t="(ก) จังหวะ sampling ที่ fs_tick", grp="ก · จังหวะ sampling ซึ่งสำคัญที่สุด",
             how="CH1 → <b>JP1 ขา 6</b> · Trigger CH1 rising · 50 µs/div · เปิด Measure: <b>Freq, Period, +Width</b> และ <b>Statistics</b> (min/max/std) · ถ่ายเพิ่มอีกรูปแบบ <b>infinite persistence</b> ทิ้งไว้ ~30 วินาที",
             exp="Freq <b>8.000 kHz</b> (ขานี้สลับทุก sample จึงเป็น Fs/2) · Period 125.00 µs · ขอบคมไม่บานใน persistence = jitter ต่ำ",
             fields=[("f_tick", "Freq", "kHz"), ("p_tick", "Period / std", "µs / ns")],
             imgs=[("scope_fs_tick.png", "สี่เหลี่ยม 8 kHz ขอบคมใน persistence")]),
        dict(id="sc2", t="(ก) จังหวะแปลงของ MCP3201",
             how="CH1 → <b>JP1 ขา 7</b> (ADC CS) · CH2 → <b>JP1 ขา 8</b> (ADC CLK) · Trigger CH1 falling · 3 µs/div",
             exp="CS ต่ำ ~21 µs มี CLK <b>16 ลูก</b> ที่ 800 kHz · CS เกิดซ้ำทุก <b>62.5 µs</b> (16.000 kHz) = sampling instant จริง",
             fields=[("f_cs", "CS Freq", "kHz"), ("f_aclk", "CLK Freq", "kHz")],
             imgs=[("scope_mcp.png", "CS ของ ADC และ 16 clock ต่อการแปลง")]),
        dict(id="sc3", t="(ก) เทียบ jitter กับ Task 1 (GPIO5 ของ ESP32)", opt=True,
             how="ถ้ายังมีบอร์ด Task 1: วัดขา GPIO5 ด้วยวิธีเดียวกับข้อแรก (Freq, Statistics, persistence)",
             exp="std ของ ESP32 timer ระดับหลายสิบ ns ถึง µs ส่วน FPGA ต่ำกว่า 1 ns ใช้ตอบข้อ 8 ได้ตรง ๆ",
             fields=[("std_t1", "std Task 1", "ns")]),
        dict(id="sc4", t="(ข) การส่งข้อมูลไม่รบกวน sampling", grp="ข · หลักฐานตอบข้อ 6 ของโจทย์",
             how="CH1 → <b>JP1 ขา 6</b> (fs_tick) · CH2 → <b>JP1 ขา 4</b> (SPI CS) · Trigger CH2 falling · 1 ms/div",
             exp="ระหว่างที่ CS ต่ำ (ESP32 กำลังอ่าน ~4 ms) CH1 ยังเป็นสี่เหลี่ยม 8 kHz สม่ำเสมอ ไม่มีช่องว่างหรือคาบยืด",
             imgs=[("scope_transfer.png", "fs_tick เดินต่อตลอดช่วง CS ต่ำ")]),
        dict(id="sc5", t="(ค) บัส SPI: SCLK และ decode", grp="ค · บัสส่งข้อมูล",
             how="CH1 → <b>JP1 ขา 1</b> (SCLK) · CH2 → <b>JP1 ขา 3</b> (MISO) · Trigger CH1 · 1 µs/div · เปิด SPI decode: CPOL 0, CPHA 0, MSB first, 8 บิต, CS = ขา 4 (ถ้ามีช่องที่ 3)",
             exp="SCLK <b>4.000 MHz</b> · 4 ไบต์แรกบน MISO = <code>C3 1x A5 5A</code> (C3 = ลายเซ็น, 1x = สถานะ, A55A = sync)",
             fields=[("f_sclk", "SCLK", "MHz"), ("dec", "ไบต์แรกที่ decode ได้", "C3 11 A5 5A")],
             imgs=[("scope_spi.png", "SCLK 4 MHz และข้อมูลบน MISO")]),
        dict(id="sc6", t="(ค) เวลาส่ง 1 block",
             how="ใช้ภาพเดียวกับข้อ (ข) วัด <b>−Width ของ CS</b> (ขา 4)",
             exp="ประมาณ <b>4.1–4.3 ms</b> (2060 ไบต์ × 8 ÷ 4 MHz = 4.12 ms) เทียบคาบ block 1024/16000 = <b>64 ms</b> ใช้เวลาแค่ ~7%",
             fields=[("t_blk", "เวลาส่ง 1 block", "ms")]),
        dict(id="sc7", t="(ค) สัญญาณ block-ready",
             how="CH1 → <b>JP1 ขา 13</b> (blk_tick) · CH2 → <b>JP1 ขา 5</b> (DRDY) · 20 ms/div",
             exp="DRDY ขึ้นทุก <b>64.00 ms</b> และตกเกือบทันที (~1 ms) เมื่อ ESP32 อ่านเสร็จ · blk_tick 7.8125 Hz",
             fields=[("p_drdy", "คาบ DRDY", "ms")],
             imgs=[("scope_drdy.png", "DRDY ทุก 64 ms")]),
        dict(id="sc8", t="(ง) แรงดัน DC ของไมค์ตอนเงียบ", grp="ง · ฝั่งสัญญาณแอนะล็อก",
             how="CH1 → <b>MCP3201 ขา 2 (IN+)</b> · DC coupling · Measure <b>Vavg</b> ตอนห้องเงียบ",
             exp="ราว <b>1.65 V</b> (ครึ่งหนึ่งของ 3.3 V) ≈ 2048 counts",
             fields=[("v_mic", "Vavg เงียบ", "V")]),
        dict(id="sc9", t="(ง) Function generator ก่อนต่อเข้าวงจร",
             how="ตั้ง Sine 1 kHz, 1.5 Vpp, offset 1.65 V, Load = High-Z · วัดที่ปลายสายก่อนเสียบ · Measure Freq, Vpp, Vavg, Vmax, Vmin",
             exp="Vmin ≈ 0.9 V (ไม่ติดลบ) · Vmax ≈ 2.4 V (ไม่เกิน 3.3 V)",
             fields=[("gen", "Vmax / Vmin", "V")],
             imgs=[("scope_gen.png", "ไซน์ 1 kHz อยู่ในช่วง 0.9–2.4 V")]),
        dict(id="sc10", t="(ง) FFT บนสโคป",
             how="Math → FFT ของ CH1 (Hanning) สัญญาณเดียวกับข้อก่อน",
             exp="peak ที่ 1.000 kHz ไว้วางเทียบกับ FFT ในโปรแกรม",
             imgs=[("scope_fft.png", "FFT ของสโคป peak ที่ 1 kHz")]),
    ]),
    ("ts", "3", "ทดสอบในโปรแกรม (waveform + FFT + spectrogram)", "ใช้ run_host.bat (Python) · กด Pause ก่อนถ่ายทุกรูป · ให้บรรทัดข้อความด้านบนติดมาด้วย", [
        dict(id="ts0", t="Test ramp (เช็กลิงก์ก่อน)",
             how="build แบบ <code>build.bat 2</code> แล้วกด <code>t</code> ในหน้าต่างกราฟ",
             exp="ข้อความ <b>TEST RAMP: OK</b> · spi_err = 0 · กด <code>n</code> กลับ",
             imgs=[("host_ramp.png", "ramp 0–1023")]),
        dict(id="ts1", t="Sine 1 kHz จาก generator",
             how="1 kHz, 1.5 Vpp, offset 1.65 V · Window Hann",
             exp="1000 ÷ 15.625 = bin 64 พอดี · peak อ่านได้ <b>1000.0 Hz</b> · Fs_est ≈ 16000",
             fields=[("pk1k", "peak ที่อ่านได้", "Hz")],
             imgs=[("host_1k.png", "peak เดียวคมที่ 1000 Hz")]),
        dict(id="ts2", t="Sine 1100 Hz ไม่ตรง bin · Rect เทียบ Hann",
             how="ตั้ง 1100 Hz (= bin 70.4) · ถ่าย 2 รูป: กดปุ่ม Window เป็น Rect แล้วเป็น Hann",
             exp="Rect: ฐาน peak กว้าง ไหลไปทั้งแกน (spectral leakage) · Hann: ฐานแคบลงชัด",
             imgs=[("host_1100_rect.png", "Rect: leakage กว้าง"), ("host_1100_hann.png", "Hann: leakage ลดลง")]),
        dict(id="ts3", t="ไล่ความถี่ 500 Hz, 2 kHz, 5 kHz, 7.5 kHz",
             how="เปลี่ยนความถี่ generator ทีละค่า จดค่า peak (ถ่ายรูปเฉพาะค่าที่อยากใส่รายงาน)",
             exp="ทุกค่าคลาดไม่เกิน ~1 Hz (มี interpolation)",
             fields=[("sw500", "500 Hz →", "Hz"), ("sw2k", "2 kHz →", "Hz"), ("sw5k", "5 kHz →", "Hz"), ("sw75", "7.5 kHz →", "Hz")]),
        dict(id="ts4", t="Sine 9 kHz เกิน Nyquist",
             how="ตั้ง 9 kHz (เกิน Fs/2 = 8 kHz)",
             exp="peak ไปโผล่ที่ |9000 − 16000| = <b>7000 Hz</b> = aliasing (ลองเพิ่ม 15 kHz → ไปโผล่ 1 kHz)",
             fields=[("pk9k", "peak ที่อ่านได้", "Hz")],
             imgs=[("host_9k_alias.png", "9 kHz ไปโผล่ที่ 7 kHz")]),
        dict(id="ts5", t="Square 1 kHz",
             how="เปลี่ยนรูปคลื่นเป็น Square 1 kHz 1.5 Vpp offset 1.65 V",
             exp="harmonic คี่ 1, 3, 5, 7 kHz ลดลงตาม 1/n · harmonic ที่เกิน 8 kHz (9, 11, 13 kHz…) พับกลับมาทับที่ 7, 5, 3 kHz",
             imgs=[("host_square.png", "harmonic คี่ของ square wave")]),
        dict(id="ts6", t="สัญญาณ 2 โทน",
             how="ถ้า generator มี 2 ช่อง รวมผ่านตัวต้านทาน 1 kΩ สองตัว · ถ้าไม่มี ใช้ test tone ของ FPGA (<code>build.bat 2</code>, SW6 + SW9 ขึ้น = 1 kHz + 3 kHz)",
             exp="2 peak แยกกันชัด ที่ 1 kHz และ 3 kHz",
             imgs=[("host_twotone.png", "1 kHz + 3 kHz")]),
        dict(id="ts7", t="Clipping",
             how="เพิ่ม Vpp ของ generator จนเกินช่วง 0–3.3 V (ห้ามเกิน 3.6 V และ ห้ามต่ำกว่า −0.3 V ที่ขา ADC · ตัวต้านทาน 1 kΩ ช่วยจำกัดกระแส) หรือพูดดังใกล้ไมค์",
             exp="ยอดแบนที่ 0 V / 3.3 V · LEDR3 ติด · clip% ขึ้น · มี harmonic ใหม่ใน FFT · เทียบกับ Task 1",
             imgs=[("host_clip.png", "ยอดแบนและ harmonic ที่เกิดขึ้น")]),
        dict(id="ts8", t="เงียบ / พูด / ตบมือ / ผิวปาก ผ่านไมค์",
             how="เงียบ: ถ่ายทันที · พูด: ลากเสียง “อาาา” · ตบมือ: ตั้ง <b>Trigger SINGLE + level + rise</b> แล้วตบ 1 ครั้ง ภาพหยุดเอง · ผิวปาก: เส้นเดียวใน spectrogram",
             exp="เงียบ: noise ต่ำ อาจมีหนาม 50 Hz · พูด: harmonic เป็นเส้นซ้อนห่างเท่ากัน · ตบมือ: เส้นตั้งกว้างทุกความถี่",
             imgs=[("host_silence.png", "เงียบ"), ("host_speech.png", "พูด (สระอา)"), ("host_clap.png", "ตบมือ ที่ทริกเกอร์จับได้")]),
        dict(id="ts9", t="รันยาวหลายนาที",
             how="<code>run_host.bat --check 300</code> (5 นาที) แล้วจับหน้าจอบรรทัดสุดท้าย",
             exp="<code>RESULT: Fs_est = 16000.xx … OK; lost blocks = 0</code> · spi_err = 0 · esp_drop = 0 · bad_usb = 0",
             fields=[("long", "จำนวน block / lost", "เช่น 4688 / 0"), ("errs", "spi_err / esp_drop / bad_usb", "0 / 0 / 0")]),
    ]),
]

NUMS = [
    ("n_fs", "F_s ที่ตั้งไว้", "16 000 S/s"),
    ("n_div", "วิธีสร้างจาก 50 MHz", "หาร 3125 (ตัวนับ 0–3124 ให้ tick 1 ครั้ง)"),
    ("n_bits", "ความละเอียด ADC", "12 บิต · 1 LSB = 3.3/4096 ≈ 0.81 mV"),
    ("n_mean", "ค่าเฉลี่ยตอนเงียบ", "≈ 2048 counts (กรอกค่าที่วัดได้)"),
    ("n_sclk", "SCLK FPGA ↔ ESP32", "4 MHz (ADC CLK 800 kHz)"),
    ("n_tblk", "เวลาส่ง 1 block", "≈ 4.1–4.3 ms จากคาบ 64 ms"),
    ("n_baud", "Baud ESP32 → PC", "921 600"),
    ("n_cnt", "จำนวน block ที่รัน / lost / bad", "กรอกจากข้อ 3 รันยาว"),
]

CSS = """
:root{
  /* layout: lab clipboard -- sticky progress bar, items as rows: text left, example picture right */
  --bg:#f1f3f2; --paper:#ffffff; --ink:#18201d; --muted:#5b6964; --line:#d6ddd9;
  --accent:#0d6b5c; --accent2:#e3f2ed; --opt:#8a6d1f; --done:#eef4f1;
  --display:"IBM Plex Sans Thai",system-ui,sans-serif;
  --body:"IBM Plex Sans Thai","Noto Sans Thai",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0f1412; --paper:#171e1b; --ink:#e3eae7; --muted:#97a6a0; --line:#2a3530;
  --accent:#4cc3a6; --accent2:#173029; --opt:#d9b55a; --done:#13201b; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0f1412; --paper:#171e1b; --ink:#e3eae7; --muted:#97a6a0; --line:#2a3530;
  --accent:#4cc3a6; --accent2:#173029; --opt:#d9b55a; --done:#13201b; color-scheme:dark;}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.6 var(--body)}
main{max-width:1180px;margin:0 auto;padding:0 16px 80px;display:flex;flex-direction:column;gap:22px}
main>*{min-width:0}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0 10px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.bar h1{font:600 22px/1.3 var(--display);margin:0;flex:1 1 320px;text-wrap:balance}
.prog{flex:1 1 240px;display:flex;align-items:center;gap:10px;font:600 14px var(--mono)}
.prog .track{flex:1;height:10px;border-radius:99px;background:var(--line);overflow:hidden}
.prog .fill{height:100%;width:0;background:var(--accent);transition:width .2s}
.btn{font:600 14px var(--display);border:1px solid var(--accent);color:var(--accent);background:var(--paper);border-radius:8px;padding:6px 12px;cursor:pointer}
.btn:hover{background:var(--accent2)}
.btn.ghost{border-color:var(--line);color:var(--muted)}
p{margin:6px 0;max-width:80ch}
code{font-family:var(--mono);font-size:.9em;overflow-wrap:anywhere}
.note{background:var(--paper);border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:10px;padding:14px 18px}
.note h2{font:600 17px var(--display);margin:0 0 6px}
.note ul{margin:4px 0;padding-left:20px}
section{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden}
section>header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
section>header .n{font:700 22px var(--mono);color:var(--accent)}
section>header h2{font:600 20px var(--display);margin:0;text-wrap:balance}
section>header .sub{color:var(--muted);font-size:14px;flex-basis:100%}
section>header .cnt{margin-left:auto;font:600 13px var(--mono);color:var(--muted)}
.grp{padding:10px 20px 0;font:600 13px var(--display);color:var(--accent);letter-spacing:.02em}
.item{display:grid;grid-template-columns:34px minmax(0,1fr) minmax(0,520px);gap:14px 16px;padding:16px 20px;border-bottom:1px solid var(--line)}
.item:last-child{border-bottom:0}
.item.noimg{grid-template-columns:34px minmax(0,1fr)}
.item.done{background:var(--done)}
.item.done h3{text-decoration:line-through;text-decoration-color:var(--accent);text-decoration-thickness:2px}
.item input[type=checkbox]{width:22px;height:22px;margin-top:3px;accent-color:var(--accent);cursor:pointer}
.item h3{font:600 16.5px var(--display);margin:0 0 4px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.item h3 label{cursor:pointer}
.opt{font:600 11.5px var(--display);color:var(--opt);border:1px solid var(--opt);border-radius:99px;padding:0 8px}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:14.5px}
dt{font:600 13px var(--display);color:var(--muted);padding-top:2px;white-space:nowrap}
dd{margin:0}
dd.exp{color:var(--ink)}
.fields{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.fields label{display:flex;flex-direction:column;font:600 12px var(--display);color:var(--muted);gap:2px}
.fields input{font:14px var(--mono);padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);width:170px}
.pics{display:grid;gap:10px}
.pics.n2{grid-template-columns:1fr 1fr} .pics.n3{grid-template-columns:1fr 1fr 1fr}
figure{margin:0}
figure button{all:unset;cursor:zoom-in;display:block;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
figure button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
figure img{display:block;width:100%;height:auto}
figcaption{font-size:12.5px;color:var(--muted);margin-top:4px}
.tag{font:600 11px var(--display);background:var(--accent2);color:var(--accent);border-radius:4px;padding:1px 6px;margin-right:6px}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font:600 13px var(--display);color:var(--muted)}
td input{font:14px var(--mono);padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);width:100%;min-width:140px}
.tw{overflow-x:auto;padding:6px 8px 10px}
.warns{padding:14px 20px;display:grid;gap:10px}
.warns div{border-left:4px solid #c0392b;padding:6px 12px;background:var(--bg);border-radius:4px}
dialog{border:0;padding:0;border-radius:10px;max-width:min(96vw,1200px);background:var(--paper)}
dialog img{display:block;max-width:100%;height:auto}
dialog::backdrop{background:rgba(0,0,0,.7)}
dialog p{margin:8px 12px;color:var(--muted);font-size:14px}
#out{width:100%;min-height:160px;font:13px var(--mono);margin-top:8px;display:none;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}
.foot{font-size:13px;color:var(--muted)}
@media (max-width:860px){
  .item,.item.noimg{grid-template-columns:30px minmax(0,1fr)}
  .item .pics{grid-column:2}
  .pics.n3{grid-template-columns:1fr 1fr}
}
@media (max-width:600px){ .bar{position:static} }
@media (max-width:480px){ .pics.n2,.pics.n3{grid-template-columns:1fr} dl{grid-template-columns:1fr} }
@media (prefers-reduced-motion:reduce){.prog .fill{transition:none}}
"""


def render_item(it):
    imgs = it.get("imgs", [])
    cls = "item" + ("" if imgs else " noimg")
    opt = '<span class="opt">ไม่บังคับ</span>' if it.get("opt") else ""
    f = ""
    if it.get("fields"):
        f = '<div class="fields">' + "".join(
            f'<label for="v-{fid}">{e(lab)}<input id="v-{fid}" data-v="{fid}" data-label="{e(it["t"])} · {e(lab)}" placeholder="{e(hint)}"></label>'
            for fid, lab, hint in it["fields"]) + "</div>"
    pics = ""
    if imgs:
        n = len(imgs)
        pics = f'<div class="pics n{n}">' + "".join(
            f'<figure><button type="button" data-zoom="img/{fn}" data-cap="{e(cap)}" aria-label="ขยายภาพ: {e(cap)}">'
            f'<img src="img/{fn}" alt="{e(cap)}" loading="lazy"></button><figcaption><span class="tag">ตัวอย่าง</span>{e(cap)}</figcaption></figure>'
            for fn, cap in imgs) + "</div>"
    return (f'<div class="{cls}" id="it-{it["id"]}"><input type="checkbox" id="c-{it["id"]}" data-c="{it["id"]}">'
            f'<div><h3><label for="c-{it["id"]}">{e(it["t"])}</label>{opt}</h3>'
            f'<dl><dt>ทำอย่างไร</dt><dd>{it["how"]}</dd><dt>ต้องได้</dt><dd class="exp">{it["exp"]}</dd></dl>{f}</div>{pics}</div>')


def render_sections():
    out = []
    for sid, num, title, sub, items in SECTIONS:
        body = []
        for it in items:
            if it.get("grp"):
                body.append(f'<div class="grp">{e(it["grp"])}</div>')
            body.append(render_item(it))
        out.append(f'<section id="{sid}" aria-labelledby="h-{sid}"><header><span class="n">{num}</span>'
                   f'<h2 id="h-{sid}">{e(title)}</h2><span class="cnt" data-cnt="{sid}"></span>'
                   f'<span class="sub">{e(sub)}</span></header>{"".join(body)}</section>')
    return "".join(out)


def render_nums():
    rows = "".join(f'<tr><td><b>{e(lab)}</b></td><td class="foot">{e(hint)}</td>'
                   f'<td><input id="v-{nid}" data-v="{nid}" data-label="{e(lab)}" aria-label="{e(lab)}" placeholder="ค่าที่ได้"></td></tr>'
                   for nid, lab, hint in NUMS)
    return (f'<section id="nums" aria-labelledby="h-nums"><header><span class="n">4</span><h2 id="h-nums">ตัวเลขที่ต้องจด</h2>'
            f'<span class="sub">ค่าที่ออกแบบไว้อยู่คอลัมน์กลาง กรอกค่าที่วัดหรืออ่านได้จริงในคอลัมน์ขวา</span></header>'
            f'<div class="tw"><table><thead><tr><th>รายการ</th><th>ค่าที่ออกแบบ / คาดไว้</th><th>ค่าที่ได้</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')


JS = r"""
(function(){
  var KEY='task3-checklist-v1', st={c:{},v:{}};
  try{ var raw=localStorage.getItem(KEY); if(raw){ st=JSON.parse(raw)||st; st.c=st.c||{}; st.v=st.v||{}; } }catch(e){}
  function save(){ try{ localStorage.setItem(KEY, JSON.stringify(st)); }catch(e){} }
  var boxes=[].slice.call(document.querySelectorAll('input[data-c]'));
  var vals=[].slice.call(document.querySelectorAll('input[data-v]'));
  function refresh(){
    var req=0, reqDone=0;
    boxes.forEach(function(b){
      var it=b.closest('.item'); it.classList.toggle('done', b.checked);
      var opt=!!it.querySelector('.opt'); if(!opt){ req++; if(b.checked) reqDone++; }
    });
    document.getElementById('pc').textContent=reqDone+' / '+req;
    document.getElementById('pf').style.width=(req? reqDone*100/req:0)+'%';
    document.querySelectorAll('[data-cnt]').forEach(function(el){
      var s=document.getElementById(el.getAttribute('data-cnt'));
      var bs=s.querySelectorAll('input[data-c]'), d=0; bs.forEach(function(b){ if(b.checked) d++; });
      el.textContent=d+'/'+bs.length;
    });
  }
  boxes.forEach(function(b){ var id=b.getAttribute('data-c'); b.checked=!!st.c[id];
    b.addEventListener('change',function(){ st.c[id]=b.checked; save(); refresh(); }); });
  vals.forEach(function(i){ var id=i.getAttribute('data-v'); if(st.v[id]) i.value=st.v[id];
    i.addEventListener('input',function(){ st.v[id]=i.value; save(); }); });
  refresh();

  var dlg=document.getElementById('zoom'), zi=document.getElementById('zimg'), zc=document.getElementById('zcap');
  document.querySelectorAll('[data-zoom]').forEach(function(b){
    b.addEventListener('click',function(){ zi.src=b.getAttribute('data-zoom'); zi.alt=b.getAttribute('data-cap');
      zc.textContent='ตัวอย่างจำลอง · '+b.getAttribute('data-cap')+' · คลิกหรือกด Esc เพื่อปิด';
      if(dlg.showModal) dlg.showModal(); });
  });
  dlg.addEventListener('click',function(){ dlg.close(); });

  document.getElementById('copy').addEventListener('click',function(){
    var lines=['Task 3 checklist'];
    boxes.forEach(function(b){ var it=b.closest('.item');
      lines.push((b.checked?'[x] ':'[ ] ')+it.querySelector('h3 label').textContent); });
    lines.push(''); lines.push('ค่าที่จด:');
    vals.forEach(function(i){ if(i.value) lines.push('- '+i.getAttribute('data-label')+': '+i.value); });
    var txt=lines.join('\n'), out=document.getElementById('out');
    out.value=txt; out.style.display='block';
    var msg=document.getElementById('copymsg');
    try{ navigator.clipboard.writeText(txt).then(function(){ msg.textContent='คัดลอกแล้ว วางในแชทได้เลย'; },
      function(){ out.select(); msg.textContent='คัดลอกอัตโนมัติไม่ได้ ให้คัดลอกจากกล่องด้านล่าง'; }); }
    catch(e){ out.select(); msg.textContent='คัดลอกอัตโนมัติไม่ได้ ให้คัดลอกจากกล่องด้านล่าง'; }
  });
  document.getElementById('reset').addEventListener('click',function(){
    var r=document.getElementById('resetc'); if(r.hidden){ r.hidden=false; return; } });
  document.getElementById('resetyes').addEventListener('click',function(){
    st={c:{},v:{}}; save(); boxes.forEach(function(b){b.checked=false;}); vals.forEach(function(i){i.value='';});
    document.getElementById('resetc').hidden=true; refresh(); });
  document.getElementById('resetno').addEventListener('click',function(){ document.getElementById('resetc').hidden=true; });
})();
"""


def page():
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Task 3 Report Checklist</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans+Thai:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<main>
<div class="bar">
  <h1>Task 3 · เช็กลิสต์เก็บหลักฐานทำรายงาน</h1>
  <div class="prog" aria-live="polite"><span>ข้อบังคับ</span><div class="track"><div class="fill" id="pf"></div></div><span id="pc">0 / 0</span></div>
  <button class="btn" id="copy" type="button">คัดลอกผลทั้งหมด</button>
  <button class="btn ghost" id="reset" type="button">ล้าง</button>
  <span id="resetc" hidden>ล้างติ๊กและค่าทั้งหมด? <button class="btn" id="resetyes" type="button">ล้างเลย</button> <button class="btn ghost" id="resetno" type="button">ไม่</button></span>
  <span id="copymsg" class="foot"></span>
  <textarea id="out" aria-label="ผลที่คัดลอก" readonly></textarea>
</div>

<div class="note">
  <h2>ปรับจากร่างเดิมให้ตรงกับชุดที่ใช้จริง</h2>
  <ul>
    <li>ชุดนี้ใช้ <b>MCP3201</b> บน JP1 ไม่ได้ใช้ขา A0–A5 และ Modular ADC IP จึงย้ายเรื่องนั้นไปเป็นข้อไม่บังคับ</li>
    <li>ช่วงแรงดันเข้าคือ <b>0–3.3 V</b> (VREF ของ MCP3201) ไม่ใช่ 0–5 V แบบ header Arduino</li>
    <li>ทุกจุดวัดระบุขา JP1 จริงแล้ว: ขา 6 = sample strobe, 7/8 = ADC, 1/3/4 = SPI, 5 = DRDY, 13 = block</li>
    <li>โปรแกรมแสดงผลใช้ Python (<code>run_host.bat</code>) ชื่อตัวนับคือ lost, fpga_drop, spi_err, esp_drop, bad_usb</li>
  </ul>
  <p class="foot">รูปทุกรูปในหน้านี้เป็น<b>ตัวอย่างจำลอง</b>: หน้าจอโปรแกรมคือ <code>task3_host.py</code> ตัวจริงที่ป้อนสัญญาณจำลอง ส่วนหน้าจอสโคปวาดจากค่าที่ออกแบบไว้ ภาพจริงควรหน้าตาคล้ายกัน ติ๊กและค่าที่กรอกจำไว้ในเบราว์เซอร์นี้เท่านั้น กด “คัดลอกผลทั้งหมด” แล้ววางในแชทเพื่อให้เขียนรายงานต่อ</p>
</div>

{render_sections()}
{render_nums()}

<section id="warn" aria-labelledby="h-warn"><header><span class="n">5</span><h2 id="h-warn">ข้อควรระวังก่อนวัด</h2></header>
<div class="warns">
  <div><b>ช่วงแรงดันเข้า ADC:</b> MCP3201 รับ 0–3.3 V (เท่า VREF) ต่อ generator ต้อง offset 1.65 V, ไม่เกิน 2 Vpp, Load = High-Z และวัดก่อนเสียบทุกครั้ง ห้ามติดลบ</div>
  <div><b>ห้ามแตะ JP1 ขา 11 (5 V)</b> ด้วยโพรบหรือสาย ถ้าโพรบลื่นไปชนขาข้าง ๆ อาจลัดวงจรได้ ใช้ปากคีบหรือสายจัมเปอร์ต่อออกมาวัดจะปลอดภัยกว่า</div>
  <div><b>Logic level:</b> ESP32-S3 และ GPIO ของ DE10-Lite เป็น 3.3 V ทั้งคู่ ต่อตรงได้ แต่ต้องมี GND ร่วมเสมอ และห้ามต่อไฟเลี้ยงข้ามบอร์ด</div>
  <div><b>ถ้าลองโหมด MAX 10 ADC:</b> ขา A0–A5 ผ่าน op-amp และตัวแบ่งแรงดัน 0–5 V → 0–2.5 V ไมค์ 3.3 V จะใช้ช่วงได้ราวครึ่งเดียว (bias ~1.65 V) จ่ายไมค์ 5 V ได้ช่วงเต็มกว่า (bias ~2.5 V)</div>
</div></section>

<p class="foot">ต่อสายตาม Task 3 Wiring Manual ก่อนเริ่มข้อ 2–3</p>
</main>
<dialog id="zoom" aria-label="ภาพขยาย"><img id="zimg" alt=""><p id="zcap"></p></dialog>
<script>{JS}</script>
</body>
</html>
"""


OUT.write_text(page(), encoding="utf-8")
print("wrote", OUT, sum(len(s[4]) for s in SECTIONS), "items")
