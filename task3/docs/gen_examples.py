#!/usr/bin/env python3
"""Renders the example pictures for the Task 3 report checklist.

  * host_*.png  : the real task3_host.py window, fed with simulated MCP3201
                  data (16 kS/s, 12 bit, VREF 3.3 V) instead of the serial port
  * scope_*.png : what the oscilloscope screens should look like (simulated)

Run:  python gen_examples.py   (needs numpy, matplotlib)
"""
import pathlib
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "host"))
import task3_host as h  # noqa: E402

OUT = HERE / "img"
OUT.mkdir(exist_ok=True)
FS, N = 16000, 1024
rng = np.random.default_rng(7)


# ------------------------------------------------------------------ host window
class SimSource:
    """Feeds pre-computed 12-bit samples as ESP32 frames (source id 0 = MCP320x)."""

    def __init__(self, gen, seconds, test=False):
        self.frames = []
        n_blk = int(seconds * FS / N)
        for b in range(n_blk):
            t = (np.arange(N) + b * N) / FS
            if test:
                x, flags = np.arange(N), 0x03
            else:
                v = gen(t)
                x, flags = np.clip(np.round(v / 3.3 * 4096), 0, 4095), 0x01
            self.frames.append(h.build_frame(b, x, flags, int(b * N / FS * 1e6)))
        self.i = 0

    def read(self):
        if self.i >= len(self.frames):
            time.sleep(0.02)
            return b""
        out = b"".join(self.frames[self.i:self.i + 8])
        self.i += 8
        return out

    def write(self, b):
        pass


def host_shot(name, gen, seconds=4.0, hann=True, test=False, trigger=None):
    src = SimSource(gen, seconds, test)
    rx = h.Receiver(src)
    if trigger:
        rx.trigger.mode = "SINGLE"
        rx.trigger.kind = trigger
        rx.trigger.rearm()
    rx.start()
    fig, update, state = h.run_gui(rx, src)
    btn = {w.label.get_text().split(":")[0]: w for w in state["widgets"] if hasattr(w, "label")}
    if not hann:
        btn["Window"]._observers.process("clicked", None)
    if trigger:
        btn["Trigger"].label.set_text("Trigger: SINGLE")
        btn["Detect"].label.set_text(f"Detect: {trigger}")
    t0 = time.time()
    while src.i < len(src.frames) and time.time() - t0 < 30:
        time.sleep(0.05)
        if not state["paused"]:
            update(0)
    time.sleep(0.2)
    if not state["paused"]:
        update(0)
    fig.savefig(OUT / f"host_{name}.png", dpi=72)
    plt.close(fig)
    rx.running = False
    print("host", name, "events", rx.trigger.count)


def noise(t, mv=3):
    return mv * 1e-3 * rng.standard_normal(len(t))


def sine(f, vpp=1.5, off=1.65):
    return lambda t: off + vpp / 2 * np.sin(2 * np.pi * f * t) + noise(t)


def square(f, vpp=1.5, off=1.65):
    return lambda t: off + vpp / 2 * np.sign(np.sin(2 * np.pi * f * t + 1e-3)) + noise(t)


def two_tone(t):
    return 1.65 + 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.25 * np.sin(2 * np.pi * 3000 * t) + noise(t)


def clipped(t):
    return np.clip(1.65 + 2.2 * np.sin(2 * np.pi * 1000 * t), 0, 3.3) + noise(t)


def silence(t):
    return 1.65 + 0.004 * np.sin(2 * np.pi * 50 * t) + noise(t, 2)


def vowel(t):
    f0 = 140 * (1 + 0.02 * np.sin(2 * np.pi * 3 * t))
    ph = 2 * np.pi * np.cumsum(f0) / FS
    v = sum(a * np.sin(k * ph) for k, a in ((1, .18), (2, .25), (3, .2), (5, .12), (6, .1), (8, .05), (9, .04), (17, .02)))
    env = np.clip((t % 2.5) / 0.1, 0, 1) * (t % 2.5 < 1.8)
    return 1.65 + env * v + noise(t)


def clap(t):
    tc = (t % 2.0) - 1.2
    burst = np.where((tc >= 0) & (tc < 0.1), 0.9 * np.exp(-np.clip(tc, 0, None) / 0.015), 0.0)
    return 1.65 + burst * rng.standard_normal(len(t)) + noise(t, 2)


# ------------------------------------------------------------------ scope screens
SCOPE_BG, GRID = "#0b1110", "#24413a"
CH = {"1": "#f2d43d", "2": "#3fc6e8", "3": "#e86ad2", "4": "#7be36b"}


def scope(name, traces, t_div, title, meas, v_div=None, persist=False):
    """traces: list of (channel, t[s], v[V], volts/div, offset_div)."""
    fig = plt.figure(figsize=(8.4, 4.6), dpi=80, facecolor="#1b1f22")
    ax = fig.add_axes([0.03, 0.17, 0.72, 0.74], facecolor=SCOPE_BG)
    for x in range(11):
        ax.axvline(x, color=GRID, lw=0.6)
    for y in range(9):
        ax.axhline(y, color=GRID, lw=0.6)
    ax.axvline(5, color="#3d6b5f", lw=0.9)
    ax.axhline(4, color="#3d6b5f", lw=0.9)
    for ch, t, v, vd, off in traces:
        x = t / t_div
        y = v / vd + off
        if persist:
            for k in range(25):
                j = rng.normal(0, 0.004)
                ax.plot(x + j, y, color=CH[ch], lw=0.8, alpha=0.08)
        ax.plot(x, y, color=CH[ch], lw=1.3)
        ax.text(-0.15, off, f"{ch}▸", color=CH[ch], fontsize=10, va="center", ha="right", family="monospace")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#41504b")
    fig.text(0.03, 0.95, title, color="#e8ece9", fontsize=11, family="monospace")
    tdiv = f"{t_div * 1e3:g} ms/div" if t_div >= 1e-3 else f"{t_div * 1e6:g} us/div"
    chans = "   ".join(f"CH{ch} {vd:g} V/div" for ch, _, _, vd, _ in traces)
    fig.text(0.03, 0.07, f"{chans}    {tdiv}", color="#b9c4c0", fontsize=9.5, family="monospace")
    fig.text(0.78, 0.88, "Measure", color="#e8ece9", fontsize=11, family="monospace", weight="bold")
    for i, (k, v, ch) in enumerate(meas):
        fig.text(0.78, 0.80 - i * 0.075, f"{k}", color=CH.get(ch, "#b9c4c0"), fontsize=9.5, family="monospace")
        fig.text(0.985, 0.80 - i * 0.075, f"{v}", color="#e8ece9", fontsize=9.5, family="monospace", ha="right")
    fig.savefig(OUT / f"scope_{name}.png", facecolor=fig.get_facecolor())
    plt.close(fig)
    print("scope", name)


def sq(t, period, duty=0.5, phase=0.0):
    return ((((t / period) + phase) % 1.0) < duty).astype(float)


def scope_all():
    # (a) fs_tick 8 kHz
    t = np.linspace(0, 500e-6, 4000)
    scope("fs_tick", [("1", t, 3.3 * sq(t, 125e-6, 0.5, 0.1), 2, 2)], 50e-6,
          "CH1 = JP1 pin 6 (fs_tick)   Trig CH1 rising", [
              ("Freq", "8.0000 kHz", "1"), ("Period", "125.00 us", "1"), ("+Width", "62.50 us", "1"),
              ("Std dev", "< 1 ns", "1"), ("Vmax", "3.30 V", "1")], persist=True)
    # (b) fs_tick vs SPI CS: transfer does not disturb sampling
    t = np.linspace(0, 10e-3, 20000)
    cs = 3.3 * (1 - ((t > 3.0e-3) & (t < 7.2e-3)))
    scope("transfer", [("1", t, 3.3 * sq(t, 125e-6), 2, 4.5), ("2", t, cs, 2, 0.8)], 1e-3,
          "CH1 = pin 6 fs_tick   CH2 = pin 4 SPI CS   Trig CH2 falling", [
              ("CH1 Freq", "8.0000 kHz", "1"), ("CH2 -Width", "4.18 ms", "2"),
              ("CH1 during CS", "steady", "1")])
    # (c) SPI burst zoom with SCLK + MISO
    t = np.linspace(0, 10e-6, 6000)
    sclk = 3.3 * sq(t, 0.25e-6, 0.5, 0.5) * (t > 1e-6)
    bits = rng.integers(0, 2, 60)
    miso = 3.3 * bits[np.minimum((np.clip(t - 1e-6, 0, None) / 0.25e-6).astype(int), 59)]
    scope("spi", [("1", t, sclk, 2, 4.6), ("2", t, miso, 2, 0.8)], 1e-6,
          "CH1 = pin 1 SCLK   CH2 = pin 3 MISO   (decode: SPI mode 0, MSB first)", [
              ("SCLK Freq", "4.000 MHz", "1"), ("Decode", "C3 11 A5 5A", "2"), ("Mode", "CPOL0 CPHA0", "1")])
    # (d) DRDY / blk_tick 64 ms
    t = np.linspace(0, 200e-3, 20000)
    drdy = 3.3 * (((t % 64e-3) > 0.0) & ((t % 64e-3) < 0.8e-3) | False)
    blk = 3.3 * sq(t, 128e-3)
    scope("drdy", [("1", t, blk, 2, 4.5), ("2", t, drdy, 2, 0.8)], 20e-3,
          "CH1 = pin 13 blk_tick   CH2 = pin 5 DRDY", [
              ("CH2 Period", "64.00 ms", "2"), ("CH2 +Width", "~0.8 ms", "2"), ("CH1 Freq", "7.8125 Hz", "1")])
    # (e) MCP3201 conversion: CS + 16 CLK
    t = np.linspace(0, 30e-6, 9000)
    cs = 3.3 * (1 - ((t > 2e-6) & (t < 23.3e-6)))
    clk = 3.3 * sq(t - 2.6e-6, 1.25e-6, 0.5) * ((t > 2.6e-6) & (t < 22.6e-6))
    scope("mcp", [("1", t, cs, 2, 4.6), ("2", t, clk, 2, 0.8)], 3e-6,
          "CH1 = pin 7 ADC CS   CH2 = pin 8 ADC CLK", [
              ("CH2 Freq", "800 kHz", "2"), ("CLK count", "16", "2"), ("CH1 Period", "62.50 us", "1"),
              ("CH1 Freq", "16.000 kHz", "1")])
    # (f) generator signal before connecting
    t = np.linspace(0, 5e-3, 5000)
    v = 1.65 + 0.75 * np.sin(2 * np.pi * 1000 * t)
    scope("gen", [("1", t, v, 0.5, 1)], 0.5e-3,
          "CH1 = function generator output (High-Z), before connecting", [
              ("Freq", "1.000 kHz", "1"), ("Vpp", "1.50 V", "1"), ("Vavg", "1.65 V", "1"),
              ("Vmax", "2.40 V", "1"), ("Vmin", "0.90 V", "1")])
    # (g) scope FFT of same signal
    fig = plt.figure(figsize=(8.4, 4.6), dpi=80, facecolor="#1b1f22")
    ax = fig.add_axes([0.06, 0.17, 0.69, 0.74], facecolor=SCOPE_BG)
    x = 1.65 + 0.75 * np.sin(2 * np.pi * 1000 * np.arange(8192) / 100e3) + 0.002 * rng.standard_normal(8192)
    X = 20 * np.log10(np.abs(np.fft.rfft((x - x.mean()) * np.hanning(8192))) / 2048 * 2 + 1e-7)
    f = np.fft.rfftfreq(8192, 1 / 100e3)
    ax.plot(f / 1e3, X, color="#e86ad2", lw=1)
    ax.set_xlim(0, 10)
    ax.set_ylim(-110, 0)
    ax.grid(color=GRID)
    ax.tick_params(colors="#b9c4c0", labelsize=8)
    fig.text(0.03, 0.95, "MATH = FFT(CH1), Hanning, 1 kHz/div, 10 dB/div", color="#e8ece9", fontsize=11, family="monospace")
    fig.text(0.78, 0.88, "Cursor", color="#e8ece9", fontsize=11, family="monospace", weight="bold")
    fig.text(0.78, 0.80, "Peak f", color="#e86ad2", fontsize=9.5, family="monospace")
    fig.text(0.985, 0.80, "1.000 kHz", color="#e8ece9", fontsize=9.5, family="monospace", ha="right")
    fig.savefig(OUT / "scope_fft.png", facecolor=fig.get_facecolor())
    plt.close(fig)
    print("scope fft")


if __name__ == "__main__":
    scope_all()
    host_shot("ramp", None, 1.0, test=True)
    host_shot("1k", sine(1000))
    host_shot("1100_rect", sine(1100), hann=False)
    host_shot("1100_hann", sine(1100))
    host_shot("9k_alias", sine(9000))
    host_shot("square", square(1000))
    host_shot("twotone", two_tone)
    host_shot("clip", clipped)
    host_shot("silence", silence)
    host_shot("speech", vowel, 3.0)
    host_shot("clap", clap, 3.0, trigger="level")
