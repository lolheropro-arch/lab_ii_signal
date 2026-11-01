#!/usr/bin/env python3
"""Generates wiring.html -- Task 3 wiring manual
(DE10-Lite + ESP32-S3 UNO + MCP3201 + MAX4466).  Run:  python gen_wiring.py"""
import html
import pathlib

OUT = pathlib.Path(__file__).with_name("wiring.html")

# wire colours (identical in light/dark themes, readable on both)
C = {
    "sclk": "#d9a400", "mosi": "#2e9d4a", "miso": "#2f6fd6", "cs": "#e0701b",
    "drdy": "#8a4fd0", "gnd": "#6b7280", "v33": "#d23b3b", "aclk": "#0f9aa8",
    "adout": "#c2408f", "acs": "#a5762b", "sig": "#3aa37a", "scope": "#7c8a96",
    "usb": "#8b96a3",
}


def esc(s):
    return html.escape(str(s))


def T(x, y, s, cls="t", anchor="start"):
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{esc(s)}</text>'


def path(d, c, w=4, halo=True):
    out = []
    if halo:
        out.append(f'<path d="{d}" class="halo" stroke-width="{w + 5}"/>')
    out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" '
               f'stroke-linejoin="round"/>')
    return "".join(out)


def orth(pts, c, w=4):
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return path(d, c, w)


def jumper_down(x1, y1, x2, y2, c, dn=140, w=4):
    """Curved jumper wire from a point above (x1,y1) down to a header below (x2,y2)."""
    d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dn:.1f} {x2:.1f},{y2 - dn:.1f} {x2:.1f},{y2:.1f}"
    return path(d, c, w)


def dot(x, y, c, r=5):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{c}"/>'


# --------------------------------------------------------------------- JP1
JP1_USE = {1: ("SCLK", "sclk"), 2: ("MOSI", "mosi"), 3: ("MISO", "miso"), 4: ("CS", "cs"),
           5: ("DRDY", "drdy"), 6: ("fs_tick", "scope"), 7: ("ADC CS", "acs"), 8: ("ADC CLK", "aclk"),
           9: ("ว่าง", None), 10: ("ADC DOUT", "adout"), 11: ("5V ห้าม!", "danger"),
           12: ("GND", "gnd"), 13: ("blk_tick", "scope"), 29: ("3.3V", "v33"), 30: ("GND", "gnd")}


class JP1:
    """2x20 header drawn as on the user's photo (header along the top edge of the
    board); pin 1 = bottom row, left end -- to be confirmed with a meter."""

    def __init__(self, x0, yt, pitch=36, gap=34, show=None, names=None):
        self.x0, self.yt, self.p, self.gap = x0, yt, pitch, gap
        self.yb = yt + gap
        self.show = show
        self.names = names or {}

    def xy(self, n):
        col = (n - 1) // 2
        return self.x0 + col * self.p, (self.yb if n % 2 else self.yt)

    def svg(self, labels=True, small=False):
        p, x0 = self.p, self.x0
        r = 7 if small else 12
        s = [f'<rect x="{x0 - p * .6:.1f}" y="{self.yt - p * .55:.1f}" width="{p * 20.2:.1f}" '
             f'height="{self.gap + p * 1.1:.1f}" rx="5" class="shroud"/>']
        for n in range(1, 41):
            x, y = self.xy(n)
            u = JP1_USE.get(n)
            on = u and (self.show is None or n in self.show)
            if on and u[1] == "danger":
                s.append(f'<circle cx="{x}" cy="{y}" r="{r}" class="pinx"/>')
                if not small:
                    s.append(T(x, y + 4, n, "pnd", "middle"))
            elif on and u[1]:
                s.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{C[u[1]]}"/>')
                if not small:
                    s.append(T(x, y + 4, n, "pnw", "middle"))
            else:
                s.append(f'<circle cx="{x}" cy="{y}" r="{r * .5:.1f}" class="pinf"/>')
                if not small:
                    s.append(T(x, y + (-17 if n % 2 == 0 else 25), n, "pg", "middle"))
            if labels and on and not small:
                col = (n - 1) // 2
                stag = 15 if col % 2 else 0
                top_edge = self.yt - p * .55
                bot_edge = self.yb + p * .55
                ly = top_edge - 8 - stag if n % 2 == 0 else bot_edge + 16 + stag
                name = self.names.get(n, u[0])
                if name:
                    s.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{ly + (4 if n % 2 == 0 else -12)}" class="tick"/>' if stag else "")
                    s.append(T(x, ly, name, "pld" if u[1] == "danger" else "pl", "middle"))
        return "".join(s)


# --------------------------------------------------------------------- S3 header
S3_PINS = [("D0", "RXD"), ("D1", "TXD"), ("D2", "IO18"), ("D3", "IO17"), ("D4", "IO19"), ("D5", "IO20"),
           ("D6", "IO3"), ("D7", "IO14"), None, ("D8", "IO21"), ("D9", "IO46"), ("D10", "IO10"),
           ("D11", "IO11"), ("D12", "IO13"), ("D13", "IO12"), ("", "GND"), ("", "RST"), ("SDA", "IO8"),
           ("SCL", "IO9")]
S3_USE = {"IO14": ("DRDY", "drdy"), "IO10": ("CS", "cs"), "IO11": ("MOSI", "mosi"),
          "IO13": ("MISO", "miso"), "IO12": ("SCLK", "sclk"), "GND": ("GND", "gnd")}
S3_AVOID = {"IO19": "USB", "IO20": "USB", "IO3": "strap", "IO46": "strap"}


def s3_header(x0, y, pitch=44):
    pos, s = {}, []
    s.append(f'<rect x="{x0 - pitch / 2 - 4:.1f}" y="{y - 18}" width="{8 * pitch + 8:.1f}" height="36" rx="5" class="hdr"/>')
    s.append(f'<rect x="{x0 + 9 * pitch - pitch / 2 - 4:.1f}" y="{y - 18}" width="{10 * pitch + 8:.1f}" height="36" rx="5" class="hdr"/>')
    for i, p in enumerate(S3_PINS):
        if p is None:
            continue
        x = x0 + i * pitch
        uno, io = p
        pos[io] = (x, y)
        u = S3_USE.get(io)
        if u:
            s.append(f'<rect x="{x - 17:.1f}" y="{y - 13}" width="34" height="26" rx="4" fill="{C[u[1]]}"/>')
            s.append(T(x, y + 5, io.replace("IO", ""), "pnw", "middle"))
            s.append(T(x, y - 26, u[0], "plw", "middle"))
        else:
            s.append(f'<rect x="{x - 17:.1f}" y="{y - 13}" width="34" height="26" rx="4" class="pinf"/>')
            s.append(T(x, y + 5, io.replace("IO", ""), "pn", "middle"))
            if io in S3_AVOID:
                s.append(T(x, y - 26, S3_AVOID[io], "pldw", "middle"))
        s.append(T(x, y - 42, uno, "pgw", "middle"))
    return "".join(s), pos


# ===================================================================== FIG 1: overview
def fig_overview():
    W, H = 1200, 780
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="ภาพรวม: ไมค์ต่อเข้า MCP3201 บน breadboard, MCP3201 ต่อ 5 สายเข้า JP1 ของ DE10-Lite (ส่วนที่ 1), JP1 ต่อ 6 สายไป ESP32-S3 UNO (ส่วนที่ 2), ทั้งสองบอร์ดเสียบ USB เข้าคอม">']
    s.append('<defs><pattern id="holes" width="10" height="10" patternUnits="userSpaceOnUse">'
             '<circle cx="5" cy="5" r="1.4" class="hole"/></pattern></defs>')
    # zones
    s.append('<rect x="16" y="16" width="556" height="376" rx="14" class="zone1"/>')
    s.append(T(34, 44, "ส่วนที่ 1 · เก็บสัญญาณ (แอนะล็อก → ตัวเลข)", "zt1"))
    s.append('<rect x="780" y="16" width="404" height="376" rx="14" class="zone2"/>')
    s.append(T(798, 44, "ส่วนที่ 2 · ส่งข้อมูลไปคอม", "zt2"))

    # mic
    s.append('<rect x="40" y="80" width="150" height="120" rx="10" class="mic"/>')
    s.append('<circle cx="82" cy="140" r="26" class="miccap"/>')
    s.append(T(118, 124, "MAX4466", "btw"))
    s.append(T(118, 144, "ไมค์", "bsw"))
    # generator alternative
    s.append('<rect x="40" y="250" width="150" height="90" rx="10" class="gen"/>')
    s.append(T(115, 280, "Function generator", "bt", "middle"))
    s.append(T(115, 302, "ใช้แทนไมค์", "bs", "middle"))
    s.append(T(115, 320, "ตอนทดสอบความถี่", "bs", "middle"))

    # breadboard + chip
    s.append('<rect x="250" y="70" width="270" height="300" rx="8" class="bb"/>')
    s.append('<rect x="250" y="70" width="270" height="300" rx="8" fill="url(#holes)"/>')
    s.append(f'<line x1="262" y1="90" x2="508" y2="90" stroke="{C["v33"]}" stroke-width="3"/>')
    s.append(f'<line x1="262" y1="104" x2="508" y2="104" stroke="{C["gnd"]}" stroke-width="3"/>')
    s.append('<rect x="250" y="216" width="270" height="10" class="chan"/>')
    s.append('<rect x="340" y="190" width="96" height="62" rx="4" class="chip"/>')
    s.append('<path d="M340,212 a9,9 0 0 1 0,18" class="notch"/>')
    s.append(T(388, 226, "MCP3201", "chipl", "middle"))
    s.append('<rect x="280" y="300" width="44" height="14" rx="3" class="res"/>')
    s.append(T(302, 292, "1 kΩ", "bs", "middle"))
    s.append('<rect x="452" y="144" width="12" height="22" rx="3" class="capc"/>')
    s.append(T(458, 136, "100 nF", "bs", "middle"))
    s.append(T(385, 356, "breadboard", "bs", "middle"))

    # mic -> breadboard (3 wires) and generator (dashed alternative)
    s.append(orth([(190, 110), (226, 110), (226, 90), (262, 90)], C["v33"], 3))
    s.append(orth([(190, 130), (238, 130), (238, 104), (262, 104)], C["gnd"], 3))
    s.append(orth([(190, 172), (260, 172), (260, 307), (280, 307)], C["sig"], 3))
    s.append(f'<path d="M190,295 L218,295 L218,250 L260,250" fill="none" stroke="{C["sig"]}" stroke-width="2.5" stroke-dasharray="6 5"/>')
    s.append(orth([(324, 307), (360, 307), (360, 252)], C["sig"], 3))

    # DE10-Lite board
    bx, by = 600, 440
    s.append(f'<rect x="{bx}" y="{by}" width="440" height="300" rx="12" class="de10"/>')
    jp = JP1(bx + 30, by + 30, pitch=20, gap=18)
    s.append(jp.svg(labels=False, small=True))
    s.append(T(bx + 428, by + 82, "JP1", "bsw", "end"))
    s.append(f'<rect x="{bx + 170}" y="{by + 110}" width="90" height="90" rx="4" class="fpga"/>')
    s.append(T(bx + 215, by + 160, "MAX 10", "chipl", "middle"))
    s.append(T(bx + 20, by + 286, "DE10-Lite", "btw"))
    for i in range(10):
        s.append(f'<rect x="{bx + 240 + i * 18}" y="{by + 250}" width="10" height="20" rx="2" class="swr"/>')
        s.append(f'<circle cx="{bx + 245 + i * 18}" cy="{by + 236}" r="4" class="led"/>')
    s.append(f'<rect x="{bx - 22}" y="{by + 120}" width="36" height="46" rx="4" class="usbb"/>')
    s.append(T(bx + 22, by + 150, "USB-B", "bsw"))

    # S3 board
    sx, sy = 800, 70
    s.append(f'<rect x="{sx}" y="{sy}" width="360" height="270" rx="12" class="s3"/>')
    s.append(f'<rect x="{sx + 20}" y="{sy + 34}" width="110" height="120" rx="6" class="esp"/>')
    s.append(T(sx + 75, sy + 100, "ESP32-S3", "chipd", "middle"))
    s.append(f'<rect x="{sx + 338}" y="{sy + 110}" width="34" height="42" rx="5" class="usbb"/>')
    s.append(T(sx + 330, sy + 136, "USB-C", "bsw", "end"))
    s.append(T(sx + 150, sy + 60, "ESP32-S3 UNO", "btw"))
    hp, hx, hy = 18, sx + 26, sy + 246
    s3x = {}
    for i, p in enumerate(S3_PINS):
        if p is None:
            continue
        x = hx + i * hp
        s3x[p[1]] = x
        u = S3_USE.get(p[1])
        fill = C[u[1]] if u else "#2b2233"
        s.append(f'<rect x="{x - 6}" y="{hy - 7}" width="12" height="14" rx="2" fill="{fill}"/>')
    s.append(T(sx + 180, hy - 18, "header DIGITAL", "bsw", "middle"))

    # Part 1 bundle: breadboard -> JP1 7, 8, 10, 29, 30
    edge = {8: (520, 200, "aclk"), 10: (520, 214, "adout"), 7: (520, 238, "acs"),
            29: (520, 326, "v33"), 30: (520, 342, "gnd")}
    s.append(orth([(436, 200), (520, 200)], C["aclk"], 3))
    s.append(orth([(436, 214), (520, 214)], C["adout"], 3))
    s.append(orth([(436, 238), (520, 238)], C["acs"], 3))
    s.append(orth([(500, 90), (500, 326), (520, 326)], C["v33"], 3))
    s.append(orth([(488, 104), (488, 342), (520, 342)], C["gnd"], 3))
    for n, (ax, ay, ck) in edge.items():
        x, y = jp.xy(n)
        d = f"M{ax},{ay} C{ax + 110},{ay} {x},{y - 170} {x},{y}"
        s.append(path(d, C[ck], 3.5))
    # Part 2 bundle: S3 header -> JP1 1..5, 12
    for n, io in ((1, "IO12"), (2, "IO11"), (3, "IO13"), (4, "IO10"), (5, "IO14"), (12, "GND")):
        x, y = jp.xy(n)
        s.append(jumper_down(s3x[io], hy + 7, x, y, C[JP1_USE[n][1]], dn=110, w=3.5))

    # badges
    s.append('<circle cx="560" cy="420" r="18" class="badge1"/>')
    s.append(T(560, 426, "1", "badget", "middle"))
    s.append(T(488, 418, "5 สาย", "bt", "end"))
    s.append(T(488, 436, "ADC ↔ FPGA", "bs", "end"))
    s.append('<circle cx="1100" cy="372" r="18" class="badge2"/>')
    s.append(T(1100, 378, "2", "badget", "middle"))
    s.append(T(1100, 412, "6 สาย", "bt", "middle"))
    s.append(T(1100, 430, "FPGA ↔ ESP32", "bs", "middle"))

    # PC
    s.append('<rect x="150" y="560" width="290" height="160" rx="10" class="pc"/>')
    s.append('<rect x="166" y="576" width="258" height="104" rx="4" class="scr"/>')
    s.append('<polyline points="180,650 220,610 250,640 290,590 330,630 370,600 410,620" fill="none" stroke="#4cc3a6" stroke-width="2"/>')
    s.append(T(295, 704, "คอม · Quartus, Arduino IDE, Python", "bs", "middle"))
    # USB cables
    s.append(path(f"M{bx - 22},{by + 143} C{bx - 110},{by + 143} 500,610 440,610", C["usb"], 6))
    s.append(T(295, 548, "USB-B: โปรแกรม FPGA + ไฟเลี้ยง", "bs", "middle"))
    s.append(path(f"M{sx + 372},{sy + 131} C{W - 10},{sy + 131} {W - 10},{H - 20} 900,{H - 20} "
                  f"L500,{H - 20} C470,{H - 20} 470,690 440,690", C["usb"], 6))
    s.append(T(1150, 600, "USB-C: ข้อมูลเสียง", "bs", "end"))
    s.append(T(1150, 618, "+ ไฟเลี้ยง ESP32", "bs", "end"))
    s.append("</svg>")
    return "".join(s)


# ===================================================================== FIG 2: JP1 map
def fig_jp1():
    W, H = 900, 290
    jp = JP1(90, 112, pitch=40, gap=50, names={10: "DOUT", 11: "5V ห้าม!"})
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="ผังขา JP1 ของ DE10-Lite 2 แถว 20 คอลัมน์ ขา 1 อยู่แถวล่างปลายซ้าย ขาที่ใช้ระบายสี">']
    s.append(jp.svg())
    for col in (5, 14):
        x = 90 + col * 40
        s.append(f'<rect x="{x - 19}" y="80" width="38" height="104" rx="8" class="colmark"/>')
    for col, lab in ((0, "คอลัมน์ 1"), (5, "คอลัมน์ 6 (5V)"), (14, "คอลัมน์ 15 (3.3V)")):
        s.append(T(90 + col * 40, 254, lab, "pl", "middle"))
    s.append(T(36, 116, "แถวบน", "pg", "middle"))
    s.append(T(36, 166, "แถวล่าง", "pg", "middle"))
    s.append(T(90, 280, "← ปลายด้านไฟ CONF / USB-B", "pg"))
    s.append(T(870, 280, "ปลายด้าน VGA →", "pg", "end"))
    s.append("</svg>")
    return "".join(s)


# ===================================================================== FIG 3: part 1 zoom
def fig_part1():
    W, H = 1060, 780
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="ส่วนที่ 1: ไมค์ ตัวต้านทาน 1 kΩ และ MCP3201 บน breadboard ต่อเข้า JP1 ขา 7, 8, 10, 29, 30">']
    s.append('<defs><pattern id="holes2" width="12" height="12" patternUnits="userSpaceOnUse">'
             '<circle cx="6" cy="6" r="1.6" class="hole"/></pattern></defs>')
    bx0, bx1, by0, by1 = 220, 850, 40, 430
    s.append(f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" rx="10" class="bb"/>')
    s.append(f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" rx="10" fill="url(#holes2)"/>')
    RT, RTG, RB, RBG = 68, 90, 380, 402
    for y, ck, lab in ((RT, "v33", "+ 3.3 V"), (RTG, "gnd", "− GND"), (RB, "v33", "+ 3.3 V"), (RBG, "gnd", "− GND")):
        s.append(f'<line x1="{bx0 + 14}" y1="{y}" x2="{bx1 - 14}" y2="{y}" stroke="{C[ck]}" stroke-width="3" opacity=".55"/>')
        s.append(T(600, y - 5, lab, "rail"))
    s.append(f'<rect x="{bx0}" y="224" width="{bx1 - bx0}" height="12" class="chan"/>')

    px = [420, 460, 500, 540]
    yT, yB = 196, 264
    s.append('<rect x="396" y="196" width="168" height="68" rx="5" class="chip"/>')
    s.append('<path d="M396,219 a11,11 0 0 1 0,22" class="notch"/>')
    s.append('<circle cx="408" cy="254" r="3.5" class="pin1"/>')
    top = [(8, "VDD"), (7, "CLK"), (6, "DOUT"), (5, "CS")]
    bot = [(1, "VREF"), (2, "IN+"), (3, "IN−"), (4, "VSS")]
    for x, (n, l) in zip(px, top):
        s.append(f'<rect x="{x - 5}" y="{yT - 12}" width="10" height="12" class="leg"/>')
        s.append(T(x, yT + 15, n, "chipn", "middle"))
        s.append(T(x, yT + 29, l, "chipt", "middle"))
    for x, (n, l) in zip(px, bot):
        s.append(f'<rect x="{x - 5}" y="{yB}" width="10" height="12" class="leg"/>')
        s.append(T(x, yB - 20, l, "chipt", "middle"))
        s.append(T(x, yB - 6, n, "chipn", "middle"))
    s.append(T(480, 452, "MCP3201: รอยบากอยู่ซ้าย → ขา 1 = ล่างซ้าย", "pg", "middle"))

    # mic module (off-board, left)
    s.append('<rect x="24" y="110" width="150" height="240" rx="10" class="mic"/>')
    s.append('<circle cx="78" cy="168" r="30" class="miccap"/>')
    s.append(T(36, 232, "ไมค์ MAX4466", "btw"))
    for y, l in ((262, "VCC"), (292, "GND"), (322, "OUT")):
        s.append(T(160, y + 4, l, "monow", "end"))
        s.append(dot(174, y, "#c7cdd2", 4))
    s.append(orth([(174, 262), (244, 262), (244, RT)], C["v33"]))
    s.append(orth([(174, 292), (262, 292), (262, RTG)], C["gnd"]))
    s.append(orth([(174, 322), (300, 322)], C["sig"]))
    s.append('<rect x="300" y="314" width="56" height="16" rx="5" class="res"/>')
    for i in range(3):
        s.append(f'<rect x="{312 + i * 12}" y="314" width="4" height="16" class="band{i}"/>')
    s.append(T(328, 350, "1 kΩ", "bs", "middle"))
    s.append(orth([(356, 322), (460, 322), (460, yB + 12)], C["sig"]))

    s.append(orth([(420, yT - 12), (420, RT)], C["v33"]))    # VDD
    s.append(orth([(420, yB + 12), (420, RB)], C["v33"]))    # VREF
    s.append(orth([(500, yB + 12), (500, RBG)], C["gnd"]))   # IN-
    s.append(orth([(540, yB + 12), (540, RBG)], C["gnd"]))   # VSS
    s.append(f'<rect x="374" y="{RT - 8}" width="16" height="{RTG - RT + 16}" rx="4" class="capc"/>')
    s.append(T(382, 52, "100 nF", "bs", "middle"))
    s.append(orth([(830, RT), (830, RB)], C["v33"]))
    s.append(orth([(814, RTG), (814, RBG)], C["gnd"]))
    s.append(T(862, 226, "สายเชื่อม", "pg"))
    s.append(T(862, 240, "รางบน ↔ ล่าง", "pg"))

    # JP1
    jp = JP1(110, 630, pitch=38, gap=46, show={7, 8, 9, 10, 11, 29, 30},
             names={7: "CS", 8: "CLK", 10: "DOUT", 9: "ว่าง", 11: "5V ห้าม"})
    s.append(T(110 + 19.4 * 38, 768, "JP1 · DE10-Lite", "bt", "end"))
    # digital jumpers: leave chip upward, loop right and down onto JP1
    for chipx, n, ck, h, loopx in ((460, 8, "aclk", 150, 660), (500, 10, "adout", 132, 700), (540, 7, "acs", 114, 740)):
        x, y = jp.xy(n)
        d = (f"M{chipx},{yT - 12} L{chipx},{h + 18} Q{chipx},{h} {chipx + 18},{h} L{loopx - 18},{h} "
             f"Q{loopx},{h} {loopx},{h + 18} L{loopx},{470} C{loopx},{560} {x},{y - 120} {x},{y}")
        s.append(path(d, C[ck], 4))
    x29, y29 = jp.xy(29)
    x30, y30 = jp.xy(30)
    s.append(jumper_down(770, RB, x29, y29, C["v33"], dn=150))
    s.append(jumper_down(790, RBG, x30, y30, C["gnd"], dn=120))
    s.append(dot(770, RB, C["v33"], 6))
    s.append(dot(790, RBG, C["gnd"], 6))
    s.append(jp.svg())

    calls = [(1, 600, 150), (2, 620, 132), (3, 640, 114), (4, 432, 140), (5, 770, 452), (6, 812, 440),
             (7, 352, 78), (8, 300, 296), (9, 524, 340)]
    for k, x, y in calls:
        s.append(f'<circle cx="{x}" cy="{y}" r="11" class="call"/>')
        s.append(T(x, y + 4, k, "callt", "middle"))
    s.append("</svg>")
    return "".join(s)


# ===================================================================== FIG 4: part 2 zoom
def fig_part2():
    W, H = 1000, 620
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="ส่วนที่ 2: header DIGITAL ของ ESP32-S3 UNO ต่อ 6 สายไป JP1 ขา 1-5 และ 12">']
    s.append('<rect x="40" y="16" width="930" height="170" rx="14" class="s3"/>')
    s.append(T(60, 44, "ESP32-S3 UNO · header DIGITAL (ขอบล่างของบอร์ด)", "btw"))
    hdr, pos = s3_header(104, 140, pitch=46)
    s.append(hdr)
    s.append('<rect x="936" y="24" width="30" height="40" rx="6" class="usbb"/>')
    s.append(T(926, 50, "USB-C", "bsw", "end"))

    jp = JP1(150, 460, pitch=38, gap=46, show={1, 2, 3, 4, 5, 11, 12}, names={11: "5V ห้าม"})
    s.append(T(150 + 19.4 * 38, 606, "JP1 · DE10-Lite", "bt", "end"))
    order = ((5, "IO14", 1), (4, "IO10", 2), (2, "IO11", 3), (3, "IO13", 4), (1, "IO12", 5), (12, "GND", 6))
    for n, io, k in order:
        x1, y1 = pos[io]
        x2, y2 = jp.xy(n)
        s.append(jumper_down(x1, y1 + 13, x2, y2, C[JP1_USE[n][1]], dn=160))
    s.append(jp.svg())
    for n, io, k in order:
        x1, y1 = pos[io]
        s.append(f'<circle cx="{x1}" cy="{y1 + 40}" r="11" class="call"/>')
        s.append(T(x1, y1 + 44, k, "callt", "middle"))
    s.append("</svg>")
    return "".join(s)


# ===================================================================== tables
P1 = [
    (1, "JP1 ขา 8 → MCP3201 ขา 7 (CLK)", "aclk",
     "FPGA ส่งนาฬิกา 800 kHz ให้ ADC เลื่อนบิตผลลัพธ์ออกมาทีละบิต การแปลงหนึ่งครั้งใช้ 16 ลูก = 20 µs เสร็จทันในคาบ 62.5 µs ของ 16 kS/s"),
    (2, "MCP3201 ขา 6 (DOUT) → JP1 ขา 10", "adout",
     "ผลแปลง 12 บิตออกมาทีละบิต (MSB ก่อน) เข้า FPGA เป็นสายเดียวที่ข้อมูลเสียงไหลเข้ามา"),
    (3, "JP1 ขา 7 → MCP3201 ขา 5 (CS)", "acs",
     "FPGA ดึงขานี้ลงทุก 62.5 µs จากตัวนับคริสตัล 50 MHz ขอบนี้คือ<b>จังหวะ sampling จริง</b> ไม่มีซอฟต์แวร์เกี่ยว (ใบงานข้อ 6)"),
    (4, "MCP3201 ขา 8 (VDD) → ราง + บน", "v33",
     "เลี้ยง ADC ด้วย 3.3 V ไม่ใช่ 5 V เพราะ DOUT ส่งแรงดันสูงเท่า VDD เข้า FPGA ถ้าเป็น 5 V ขา FPGA ซึ่งรับได้ 3.3 V อาจเสีย"),
    (5, "ราง + ล่าง → JP1 ขา 29 (3.3 V)", "v33",
     "ไฟ 3.3 V ของทั้ง breadboard มาจาก DE10-Lite เส้นเดียว ADC กับ FPGA จึงมีระดับลอจิกเดียวกัน"),
    (6, "ราง − ล่าง → JP1 ขา 30 (GND)", "gnd",
     "กราวด์อ้างอิงร่วม ADC วัดแรงดันเทียบจุดนี้ FPGA ก็อ่าน DOUT เทียบจุดเดียวกัน"),
    (7, "ตัวเก็บประจุ 100 nF คร่อมราง + / − ข้างชิป", "v33",
     "ADC ดึงกระแสเป็นพัลส์ตอนแปลง ตัวเก็บประจุเป็นแหล่งไฟสำรองระยะสั้นข้างชิป ลดสัญญาณรบกวนในบิตล่าง ๆ"),
    (8, "ไมค์ OUT → 1 kΩ → MCP3201 ขา 2 (IN+)", "sig",
     "สัญญาณเสียงที่จะแปลง ตัวต้านทานจำกัดกระแสถ้าแรงดันเกิน 0–3.3 V (เช่นตั้ง generator ผิด) และแทบไม่กระทบการวัดเพราะตัวเก็บประจุ sampling ใน ADC เล็กมาก"),
    (9, "MCP3201 ขา 1 (VREF) → ราง +, ขา 3 (IN−) และ 4 (VSS) → ราง −", "gnd",
     "VREF 3.3 V ทำให้ 4096 ระดับครอบช่วง 0–3.3 V ที่ไมค์แกว่งพอดี (1 LSB ≈ 0.8 mV). MCP3201 วัด IN+ ลบ IN− จึงต่อ IN− ลงกราวด์ให้เป็นการวัดเทียบกราวด์ธรรมดา"),
]
P1_EXTRA = [
    ("ไมค์ VCC → ราง + บน, ไมค์ GND → ราง − บน", "v33",
     "ไมค์ใช้ 3.3 V เหมือน ADC แรงดัน DC ของเอาต์พุตไมค์จึงอยู่ราว 1.65 V กลางช่วง ADC พอดี"),
    ("สายเชื่อมราง บน ↔ ล่าง (แดงกับแดง, ดำกับดำ)", "gnd",
     "breadboard ส่วนใหญ่รางบนกับรางล่างไม่ได้ต่อถึงกัน ต้องเชื่อมเอง"),
    ("JP1 ขา 9 ไม่ต้องต่อ", None,
     "เป็นขา DIN สำหรับ MCP3202 เท่านั้น MCP3201 มีช่องเดียวจึงไม่ต้องรับคำสั่งเลือกช่อง"),
]
P2 = [
    (1, "DRDY", "IO14 (D7)", 5, "drdy", "FPGA → S3",
     "FPGA ยกขานี้เมื่อบล็อก 1024 ค่าเต็ม ESP32 ได้ interrupt แล้วมาอ่านทันที ถ้าไม่มีสายนี้ ESP32 ต้องถามซ้ำ ๆ ผ่าน SPI ซึ่งเปลืองบัสและช้ากว่า"),
    (2, "CS", "IO10 (D10)", 4, "cs", "S3 → FPGA",
     "ครอบหนึ่งรอบการอ่าน: ขอบลง FPGA ล็อกบัฟเฟอร์ที่พร้อม ขอบขึ้นปล่อยคืน ฝั่ง ADC จึงเขียนอีกบัฟเฟอร์ต่อได้ไม่ต้องหยุด"),
    (3, "MOSI", "IO11 (D11)", 2, "mosi", "S3 → FPGA",
     "ไบต์แรกเป็นคำสั่ง: 0x01 อ่านบล็อกเสียง, 0x02 ขอ ramp ทดสอบสาย"),
    (4, "MISO", "IO13 (D12)", 3, "miso", "FPGA → S3",
     "ข้อมูลจริงไหลบนสายนี้: หัวเฟรม + 1024 ค่า + checksum รวม 2060 ไบต์ต่อบล็อก"),
    (5, "SCLK", "IO12 (D13)", 1, "sclk", "S3 → FPGA",
     "ESP32 เป็น master จึงให้จังหวะ 4 MHz ส่งหนึ่งบล็อกใช้ ~4 ms จาก 64 ms ที่บล็อกใหม่จะเต็ม เหลือเวลามาก"),
    (6, "GND", "GND (ถัดจาก IO12)", 12, "gnd", "ร่วม",
     "สองบอร์ดใช้ไฟคนละแหล่ง ระดับ 0/1 ต้องวัดเทียบกราวด์เดียวกัน ไม่มีสายนี้ข้อมูลจะมั่วทั้งหมด"),
]


def swatch(ck):
    return f'<span class="swc" style="background:{C[ck]}"></span>' if ck else '<span class="swc sw0"></span>'


def table_p1():
    r = ['<table class="chk"><thead><tr><th>✓</th><th>#</th><th>ต่อจาก → ไป</th><th>ทำไม</th></tr></thead><tbody>']
    for i, (k, what, ck, why) in enumerate(P1):
        r.append(f'<tr><td><input type="checkbox" id="p1-{i}" aria-label="ต่อแล้ว"></td><td class="k">{k}</td>'
                 f'<td class="what">{swatch(ck)}<b>{what}</b></td><td>{why}</td></tr>')
    for i, (what, ck, why) in enumerate(P1_EXTRA):
        r.append(f'<tr><td><input type="checkbox" id="p1x-{i}" aria-label="ต่อแล้ว"></td><td class="k">+</td>'
                 f'<td class="what">{swatch(ck)}<b>{what}</b></td><td>{why}</td></tr>')
    r.append("</tbody></table>")
    return "".join(r)


def table_p2():
    r = ['<table class="chk"><thead><tr><th>✓</th><th>#</th><th>สัญญาณ</th><th>ESP32-S3 UNO</th>'
         '<th>JP1 ขา</th><th>ทิศ</th><th>ทำไม</th></tr></thead><tbody>']
    for i, (k, sig, s3, pin, ck, d, why) in enumerate(P2):
        r.append(f'<tr><td><input type="checkbox" id="p2-{i}" aria-label="ต่อแล้ว"></td><td class="k">{k}</td>'
                 f'<td class="nw">{swatch(ck)}<b>{sig}</b></td><td class="nw"><b>{s3}</b></td><td class="big">{pin}</td>'
                 f'<td class="nw">{d}</td><td>{why}</td></tr>')
    r.append("</tbody></table>")
    return "".join(r)


# ===================================================================== CSS
CSS = """
:root{
  /* layout: one reading column; every diagram is followed by its checklist */
  --bg:#eef1f0; --paper:#ffffff; --ink:#17201d; --muted:#5a6863; --line:#d3dbd7;
  --accent:#0d6b5c; --p1:#0d8e9a; --p2:#7d45c4; --warn:#b4231a; --warnbg:#fdecea;
  --board:#1f3f73; --s3:#5b2a86; --chip:#23272b; --chipt:#f1f1f1; --bbfill:#f7f5ef; --hole:#d4cfbf;
  --display:"IBM Plex Sans Thai",system-ui,sans-serif;
  --body:"IBM Plex Sans Thai","Noto Sans Thai",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0f1513; --paper:#171f1c; --ink:#e3eae7; --muted:#97a6a0; --line:#2b3732;
  --accent:#4cc3a6; --p1:#3cc6d3; --p2:#b48af0; --warn:#ff7b6e; --warnbg:#3a1c19;
  --board:#1d3a66; --s3:#55287c; --chip:#0b0d0e; --chipt:#ececec; --bbfill:#2a2925; --hole:#4a473e;
  color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0f1513; --paper:#171f1c; --ink:#e3eae7; --muted:#97a6a0; --line:#2b3732;
  --accent:#4cc3a6; --p1:#3cc6d3; --p2:#b48af0; --warn:#ff7b6e; --warnbg:#3a1c19;
  --board:#1d3a66; --s3:#55287c; --chip:#0b0d0e; --chipt:#ececec; --bbfill:#2a2925; --hole:#4a473e;
  color-scheme:dark;}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 var(--body)}
main{max-width:1120px;margin:0 auto;padding:28px 16px 72px;display:flex;flex-direction:column;gap:26px}
main>*{min-width:0}
h1{font:600 32px/1.25 var(--display);margin:0;text-wrap:balance}
h2{font:600 23px/1.3 var(--display);margin:0 0 6px;text-wrap:balance;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h3{font:600 17px var(--display);margin:16px 0 4px}
.tag{font:600 13px var(--display);padding:3px 12px;border-radius:99px;color:#fff;background:var(--accent)}
.tag.p1{background:var(--p1)} .tag.p2{background:var(--p2)}
p{margin:6px 0;max-width:78ch}
code{font-family:var(--mono);font-size:.92em;overflow-wrap:anywhere}
section{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px 22px 24px}
section.s1{border-top:5px solid var(--p1)} section.s2{border-top:5px solid var(--p2)}
.lead{color:var(--muted);max-width:80ch}
figure{margin:12px 0 4px}
.fig{overflow-x:auto}
.fig svg{min-width:760px;width:100%;height:auto;display:block}
figcaption{font-size:14px;color:var(--muted);margin-top:6px;max-width:92ch}
.warn{border-left:4px solid var(--warn);background:var(--warnbg);padding:10px 14px;border-radius:6px;margin:12px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-top:12px}
.card{border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{margin-top:0}
.card.p1{border-left:5px solid var(--p1)} .card.p2{border-left:5px solid var(--p2)}
.flow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0 0;font-size:14px}
.flow span{border:1px solid var(--line);border-radius:8px;padding:4px 10px;background:var(--bg)}
.flow i{color:var(--muted);font-style:normal}
.tw{overflow-x:auto;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:14.5px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:var(--display);font-weight:600;color:var(--muted);font-size:13px}
td.k{font:600 14px var(--mono);color:var(--accent)}
td.big{font:600 20px var(--mono)}
td.nw{white-space:nowrap}
td.what{min-width:220px}
.swc{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:8px;vertical-align:-1px}
.sw0{border:1px solid var(--line)}
.chk input{width:18px;height:18px;accent-color:var(--accent)}
.chk tr:has(input:checked) td{opacity:.45}
ol.steps{margin:6px 0;padding-left:22px;display:flex;flex-direction:column;gap:10px}
.cmd{display:inline-block;max-width:100%;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-family:var(--mono);font-size:14px}
.meter{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:10px}
.meter div{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--bg)}
.meter b{font-family:var(--display)}
.src{font-size:13px;color:var(--muted)}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
/* --- svg --- */
svg .halo{fill:none;stroke:var(--paper);stroke-linecap:round;stroke-linejoin:round}
svg .t{font:14px var(--body);fill:var(--ink)}
svg .bt{font:600 15px var(--display);fill:var(--ink)}
svg .bs{font:12.5px var(--body);fill:var(--muted)}
svg .btw{font:600 15px var(--display);fill:#fff}
svg .bsw{font:12.5px var(--body);fill:#e9e2f2}
svg .monow{font:13px var(--mono);fill:#fff}
svg .zone1{fill:none;stroke:var(--p1);stroke-width:2;stroke-dasharray:8 6}
svg .zone2{fill:none;stroke:var(--p2);stroke-width:2;stroke-dasharray:8 6}
svg .zt1{font:600 15px var(--display);fill:var(--p1)}
svg .zt2{font:600 15px var(--display);fill:var(--p2)}
svg .mic{fill:#1d6b3a}
svg .miccap{fill:#c9ccd0;stroke:#8d939a;stroke-width:3}
svg .gen{fill:none;stroke:var(--muted);stroke-width:1.5;stroke-dasharray:6 5}
svg .bb{fill:var(--bbfill);stroke:var(--line);stroke-width:1.5}
svg .hole{fill:var(--hole)}
svg .chan{fill:var(--line)}
svg .chip{fill:var(--chip)}
svg .chipl{font:600 13px var(--mono);fill:var(--chipt)}
svg .chipd{font:600 13px var(--mono);fill:#2b2f33}
svg .chipn{font:600 11px var(--mono);fill:#9aa3ab}
svg .chipt{font:600 12px var(--mono);fill:var(--chipt)}
svg .notch{fill:var(--bbfill)}
svg .pin1{fill:var(--chipt)}
svg .leg{fill:#b8bec4}
svg .res{fill:#d8c39a;stroke:#9c8a63}
svg .band0{fill:#6b3f1f} svg .band1{fill:#1b1b1b} svg .band2{fill:#c0392b}
svg .capc{fill:#e0a33a;stroke:#9a6b18}
svg .de10{fill:var(--board)}
svg .fpga{fill:#15171a;stroke:#5c6a7a}
svg .swr{fill:#4a4f57} svg .led{fill:#ff5a4f}
svg .usbb{fill:#b7bdc4;stroke:#7d848c}
svg .s3{fill:var(--s3)}
svg .esp{fill:#b9bec4;stroke:#80878f}
svg .pc{fill:var(--bg);stroke:var(--line);stroke-width:1.5}
svg .scr{fill:#0f1a17}
svg .shroud{fill:#141414}
svg .pinf{fill:#3a3a3a;stroke:#5a5a5a}
svg .pinx{fill:#3a1c19;stroke:#ff6b5e;stroke-width:2;stroke-dasharray:3 2}
svg .pn{font:12px var(--mono);fill:#cfd3d7}
svg .pnw{font:600 12px var(--mono);fill:#fff}
svg .pnd{font:600 12px var(--mono);fill:#ff8a7f}
svg .pl{font:600 12px var(--body);fill:var(--ink)}
svg .plw{font:600 12px var(--body);fill:#fff}
svg .pld{font:600 12px var(--body);fill:var(--warn)}
svg .pldw{font:600 12px var(--body);fill:#ffb3ab}
svg .pg{font:11px var(--mono);fill:var(--muted)}
svg .pgw{font:11px var(--mono);fill:#d9c9e8}
svg .hdr{fill:#151515}
svg .rail{font:600 12px var(--body);fill:var(--muted)}
svg .tick{stroke:var(--muted);stroke-width:1}
svg .colmark{fill:none;stroke:var(--accent);stroke-width:2;stroke-dasharray:5 4}
svg .badge1{fill:var(--p1)} svg .badge2{fill:var(--p2)}
svg .badget{font:700 17px var(--display);fill:#fff}
svg .call{fill:var(--ink)}
svg .callt{font:700 12px var(--display);fill:var(--paper)}
@media print{section{break-inside:avoid}}
"""


def page():
    sw = swatch
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Task 3 Wiring Manual</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Thai:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<main>

<header>
  <h1>คู่มือต่อสาย Task 3 · DE10-Lite + ESP32-S3 UNO + MCP3201</h1>
  <p class="lead">ดูภาพรวมก่อนว่าอะไรต่อกับอะไร แล้วต่อจริงตามส่วนที่ 1 และ 2 ทีละเส้น ติ๊กช่องในตารางเมื่อต่อเสร็จ. ขาทั้งหมดตรงกับ <code>fpga/de10lite_pins.tcl</code> ซึ่งโหลดเข้าโปรเจกต์ให้อัตโนมัติ ไม่ต้องเปิด Pin Planner</p>
</header>

<section aria-labelledby="ov">
  <h2 id="ov"><span class="tag">ภาพรวม</span>ทั้งระบบต่อกันแบบนี้</h2>
  <figure>
    <div class="fig">{fig_overview()}</div>
    <figcaption>สายสัญญาณระหว่างบอร์ดมี 11 เส้น: ส่วนที่ 1 มี 5 เส้น (breadboard → JP1) ส่วนที่ 2 มี 6 เส้น (JP1 → ESP32-S3) และ USB อีก 2 เส้นเข้าคอม. เส้นประจาก function generator คือทางเลือกแทนไมค์</figcaption>
  </figure>
  <div class="flow"><span>เสียง</span><i>→</i><span>แรงดัน 0–3.3 V</span><i>→</i><span>MCP3201 · 12 บิต</span><i>→</i><span>FPGA · 16 000 ครั้ง/วินาที</span><i>→</i><span>บล็อกละ 1024 ค่า (64 ms)</span><i>→</i><span>SPI 4 MHz</span><i>→</i><span>ESP32-S3</span><i>→</i><span>USB</span><i>→</i><span>กราฟ + FFT</span></div>
</section>

<section aria-labelledby="parts">
  <h2 id="parts"><span class="tag">แบ่งงาน</span>ใบงานเป็นงานเดียว แต่สายแบ่งได้ 2 ส่วน</h2>
  <p>Task 3 ในใบงานเป็นงานก้อนเดียว 8 ข้อ แต่สายแยกเป็น 2 ส่วนที่ไม่ยุ่งกัน จึงต่อและทดสอบทีละส่วนได้</p>
  <div class="grid2">
    <div class="card p1"><h3>ส่วนที่ 1 · เก็บสัญญาณ</h3><p>ไมค์ → MCP3201 → FPGA (5 สายเข้า JP1). ตรงกับใบงานข้อ 1–2 และ Hint 2: ใช้ ADC ภายนอก, FPGA คุมจังหวะ 16 kS/s, เก็บลง Block RAM</p></div>
    <div class="card p2"><h3>ส่วนที่ 2 · ส่งข้อมูล</h3><p>FPGA → ESP32-S3 → คอม (6 สายจาก JP1). ตรงกับใบงานข้อ 3–5: ออกแบบ interface และโปรโตคอล, ESP32 <b>รับ</b>บล็อกจาก FPGA แล้วส่งต่อทาง USB, Python แสดงผล</p></div>
  </div>
  <div class="warn"><b>ต่อส่วนที่ 2 ก่อน</b> แล้วทดสอบด้วยโหมด test tone (<code>build.bat 2</code>) ซึ่ง FPGA สร้างคลื่นไซน์เองโดยไม่ต้องมี ADC. ถ้ากราฟขึ้น <b>TEST RAMP: OK</b> แปลว่าส่วนที่ 2 ถูกแล้ว ค่อยต่อส่วนที่ 1 แล้ว build ใหม่ด้วย <code>build.bat 0 3201</code>. ถ้ามีปัญหาจะรู้ทันทีว่าอยู่ฝั่งไหน</div>
</section>

<section aria-labelledby="pin1">
  <h2 id="pin1"><span class="tag">ก่อนต่อ</span>หาขา 1 ของ JP1 ให้แน่ใจ (1 นาที)</h2>
  <p>JP1 คือ header ตัวผู้ 2×20 ที่มีกรอบพลาสติกดำ อยู่ขอบบนของบอร์ด (header ตัวเมียที่อยู่ใต้มันคือ Arduino ไม่ได้ใช้). ในรูปที่ส่งมา ปลายซ้ายของ JP1 มีเลข <b>2</b> พิมพ์ข้างแถวบน จึงน่าจะเป็นขา 1 อยู่<b>แถวล่าง ปลายซ้าย</b> ตามผังนี้ แต่คู่มือ Terasic (Figure 3-18) บอกแค่เลขขา ไม่ได้บอกว่าขา 1 อยู่ปลายไหนของบอร์ด ให้ยืนยันด้วยมัลติมิเตอร์ก่อน</p>
  <figure>
    <div class="fig">{fig_jp1()}</div>
    <figcaption>JP1 มองจากด้านบน วางบอร์ดแบบในรูปที่ส่งมา (7-segment อยู่ล่าง). ขาสีคือขาที่ใช้ ขา 11 (5 V) กรอบแดงประ ห้ามต่อ</figcaption>
  </figure>
  <div class="meter">
    <div><b>1. เสียบ USB ให้ DE10-Lite</b><br>ตั้งมิเตอร์ที่ DC V สายดำแตะ GND ใดก็ได้ เช่นขา GND บน header Arduino ขอบล่างของบอร์ด</div>
    <div><b>2. สายแดงแตะคอลัมน์ 6 แถวล่าง</b><br>ได้ <b>5.0 V</b> = ผังถูก (นั่นคือขา 11). คอลัมน์ 15 แถวล่างต้องได้ <b>3.3 V</b> (ขา 29)</div>
    <div><b>3. ถ้าไม่ได้ตามนั้น</b><br>ลองคอลัมน์ 6 นับจาก<b>ขวา</b> แถว<b>บน</b> ถ้าได้ 5 V แปลว่าขา 1 อยู่ขวาบน ให้หมุนผังทุกรูปในหน้านี้ 180° (เลขขาเหมือนเดิม)</div>
  </div>
</section>

<section class="s1" aria-labelledby="p1">
  <h2 id="p1"><span class="tag p1">ส่วนที่ 1</span>MCP3201 + ไมค์ → JP1 ขา 7, 8, 10, 29, 30</h2>
  <div class="warn">ถอด USB ของ DE10-Lite ก่อนต่อ · เช็กตัวอักษรบนชิปว่าเป็น <b>MCP3201</b> (ถ้าเป็น MCP3202 ขาไม่เหมือนกัน ดูกล่องท้ายส่วนนี้) · ชิปในรูปเสียบอยู่ใน socket ให้เสียบทั้ง socket คร่อมร่องกลาง breadboard ได้เลย</div>
  <figure>
    <div class="fig">{fig_part1()}</div>
    <figcaption>เลขในวงกลมตรงกับลำดับในตาราง. สายที่ข้ามกันในรูปไม่ได้แตะกัน เป็นแค่สายจัมเปอร์พาดผ่าน. ราง + ทุกเส้นคือ 3.3 V ห้ามเอา 5 V มาต่อ</figcaption>
  </figure>
  <div class="tw">{table_p1()}</div>
  <div class="grid2">
    <div class="card"><h3>ถ้าชิปเป็น MCP3202</h3><p>ขา 1 CS ← JP1 ขา 7, ขา 2 CH0 ← ไมค์ผ่าน 1 kΩ, ขา 3 CH1 → GND, ขา 4 VSS → GND, ขา 5 DIN ← <b>JP1 ขา 9</b>, ขา 6 DOUT → JP1 ขา 10, ขา 7 CLK ← JP1 ขา 8, ขา 8 VDD → 3.3 V. Build ด้วย <code>build.bat 0 3202</code></p></div>
    <div class="card"><h3>ใช้ function generator แทนไมค์</h3><p>ตั้ง Sine, offset 1.65 V, ไม่เกิน 2 Vpp, Output load = <b>High-Z</b>. วัดด้วยสโคปก่อนว่าอยู่ใน 0–3.3 V แล้วจึงต่อสายแดงเข้าตัวต้านทาน 1 kΩ (แทนไมค์ OUT) สายดำเข้าราง −</p></div>
  </div>
</section>

<section class="s2" aria-labelledby="p2">
  <h2 id="p2"><span class="tag p2">ส่วนที่ 2</span>JP1 ขา 1–5, 12 → ESP32-S3 UNO</h2>
  <div class="warn">ถอด USB ทั้งสองบอร์ดก่อนต่อ · ใช้สาย <b>ผู้–เมีย</b>: ฝั่งเมียเสียบ JP1 ฝั่งผู้เสียบ header ของ S3 · ต่อแค่ GND ร่วม ห้ามต่อไฟ 3.3 V หรือ 5 V ข้ามบอร์ด เพราะแต่ละบอร์ดมีไฟจาก USB ของตัวเองอยู่แล้ว ต่อข้ามกัน regulator สองตัวจะดันกัน</div>
  <figure>
    <div class="fig">{fig_part2()}</div>
    <figcaption>ขาที่ใช้บน S3 อยู่ในช่วงที่มีป้าย SPI ติดกันหมด (IO10–IO13 และ GND) ยกเว้น DRDY ที่ IO14 ในแถบซ้าย. ขาที่มีป้ายแดง (USB, strap) ห้ามใช้</figcaption>
  </figure>
  <div class="tw">{table_p2()}</div>
  <div class="grid2">
    <div class="card p2"><h3>ทำไม S3 ใช้ IO10–IO13</h3><p>เป็นขา FSPI ประจำชิป ต่อกับ SPI hardware ผ่าน IO MUX ตรง ๆ จึงได้ timing แน่นอนกว่าขาอื่นที่ต้องผ่าน GPIO matrix และอยู่ติดกันบน header มี GND ถัดไปทันที. ห้ามใช้ IO19/IO20 เพราะเป็นสาย USB ของบอร์ด ส่วน IO3/IO46 ชิปอ่านค่าตอนบูต ถ้า FPGA ดึงไว้ S3 อาจบูตผิดโหมด</p></div>
    <div class="card p2"><h3>ทำไม FPGA ใช้ JP1 ขา 1–5</h3><p>ขาเรียงติดกันไม่มีขาไฟคั่น อยู่ใน I/O bank เดียวที่ 3.3-V LVTTL ต่อกับ ESP32 ได้ตรง ๆ ไม่ต้องแปลงระดับ และมี GND ที่ขา 12 ใกล้ ๆ. แยกจากขา 7–10 ของ ADC เพื่อให้ ADC กับ ESP32 ใช้บัสคนละชุด FPGA จึงสั่งแปลงตามจังหวะของตัวเองได้ตลอดแม้ ESP32 กำลังอ่าน</p></div>
  </div>
</section>

<section aria-labelledby="run">
  <h2 id="run"><span class="tag">รัน</span>ลำดับการเปิดใช้งาน</h2>
  <ol class="steps">
    <li><b>ต่อส่วนที่ 2</b> ตามตาราง แล้วเสียบ USB ทั้งสองบอร์ดเข้าคอม</li>
    <li><b>อัปโหลด sketch ลง S3</b> (ครั้งเดียว): Arduino IDE เปิด <code>esp32/task3_esp32_bridge/task3_esp32_bridge.ino</code> → บอร์ด <b>ESP32S3 Dev Module</b> → Upload. ถ้าไม่เข้า กด BOOT ค้าง กด RST แล้วปล่อย</li>
    <li><b>ดับเบิลคลิก</b> <code>fpga\\build.bat</code> (โหมด test tone) รอจนขึ้น DONE แล้ว LEDR0 จะกะพริบ</li>
    <li><b>ดับเบิลคลิก</b> <code>host\\run_host.bat</code> คลิกที่หน้าต่างกราฟแล้วกด <code>t</code> ต้องขึ้น <b>TEST RAMP: OK</b> แล้วกด <code>n</code></li>
    <li><b>ถอด USB ของ DE10-Lite</b> ต่อส่วนที่ 1 แล้วเสียบกลับ รัน <span class="cmd">build.bat 0 3201</span> แล้วเปิด <code>run_host.bat</code> อีกครั้ง พูดใส่ไมค์ต้องเห็นกราฟขยับ</li>
  </ol>
  <h3>จุดวัดด้วยสโคป (ปากคีบ GND ที่ JP1 ขา 12 หรือ 30)</h3>
  <div class="tw"><table><thead><tr><th>โพรบที่</th><th>สิ่งที่เห็น</th><th>ค่าที่ต้องได้</th></tr></thead><tbody>
    <tr><td class="nw">{sw('scope')}JP1 ขา 6</td><td>จังหวะ sampling (สลับทุก sample)</td><td>สี่เหลี่ยม 8.000 kHz</td></tr>
    <tr><td class="nw">{sw('acs')}JP1 ขา 7</td><td>CS ของ MCP3201</td><td>16.00 kHz ช่วงต่ำมี CLK 16 ลูก</td></tr>
    <tr><td class="nw">{sw('cs')}JP1 ขา 4</td><td>ช่วงที่ ESP32 อ่าน</td><td>ต่ำ ~4 ms ทุก 64 ms โดยขา 6 ไม่สะดุด</td></tr>
    <tr><td class="nw">{sw('scope')}JP1 ขา 13</td><td>บล็อกเต็ม</td><td>สลับทุก 64 ms</td></tr>
  </tbody></table></div>
</section>

<p class="src">ขา FPGA และตำแหน่ง 5 V / 3.3 V / GND บน JP1: Terasic DE10-Lite User Manual (ฉบับ 5 มิ.ย. 2020 ที่ส่งมา) Figure 3-18 และตาราง 3-7 ตรงกับไฟล์ pin ทุกขา. ขาของ ESP32-S3 UNO อ่านจากป้ายบนบอร์ดในรูปที่ส่งมา. ขา MCP3201 ตามลำดับ 1–8: VREF, IN+, IN−, VSS, CS, DOUT, CLK, VDD</p>

</main>
</body>
</html>
"""


OUT.write_text(page(), encoding="utf-8")
print("wrote", OUT)
