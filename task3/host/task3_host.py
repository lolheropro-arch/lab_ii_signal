#!/usr/bin/env python3
"""
task3_host.py  --  Task 3 host program (Python)
Receives audio blocks  FPGA -> ESP32 -> USB serial  and shows, in real time:
    * time-domain waveform (volts)
    * FFT magnitude spectrum (Hann or rectangular window, dB)
    * scrolling spectrogram (with trigger-event markers)
plus link statistics: sequence gaps, FPGA/ESP32 drops, checksum errors and the
sample rate measured from block arrival times.

EVENT TRIGGER (like an oscilloscope, but for "something changed suddenly"):
    The continuous stream is cut into 16 ms frames. Each frame is compared with
    a slowly-adapting background (~0.5 s):
      level    : 20*log10(frame RMS / background RMS)        -> claps, speech
                 onset, a tone switching on/off
      spectrum : power-weighted mean |dB difference| between the frame
                 spectrum and the background spectrum -> a tone
                 changing frequency at the same loudness, a new instrument...
    A trigger fires when the score exceeds the threshold (slider, dB); the
    next trigger is allowed only after the score has dropped back below
    threshold - 6 dB (hysteresis), so one event = one trigger.
    Edge (level only): rise = gets louder, fall = gets quieter, both.
    The capture window is CAP_PRE before + CAP_POST after the trigger, taken
    from a ring buffer, so nothing is lost between screen refreshes.
    Modes:  OFF    = live view only
            NORMAL = every new event replaces the captured view
            SINGLE = capture one event, then freeze the whole display
                     (press "Re-arm" to wait for the next one)
    In the captured view the waveform shows -64..+192 ms around the event and
    the spectrum panel compares BEFORE (grey) vs AFTER (blue) the trigger.

Works on Windows, Linux and macOS.

Install :  pip install pyserial numpy matplotlib
Run     :  python task3_host.py                   (auto-detect serial port)
           python task3_host.py --port COM5       (Windows)
           python task3_host.py --port /dev/ttyUSB0  (Linux)
           python task3_host.py --demo            (no hardware: synthetic data
                                                   with claps + tone changes)
           python task3_host.py --check 10        (no GUI: 10 s link/Fs report)

Buttons at the bottom of the window (keyboard shortcut in brackets):
    Pause/Resume [p]   Trigger mode OFF/NORMAL/SINGLE [g]   Re-arm [r]
    Detect level/spectrum [d]   Edge rise/fall/both [e]   Window Hann/Rect [w]
    Save [s] -> PNG of the window + .npz/.wav of the capture (or last 10 s)
    Threshold slider (dB)
Other keys:  t = FPGA test ramp, n = normal audio, l = linear/dB spectrum
"""
import argparse
import collections
import struct
import sys
import threading
import time
import wave

import numpy as np

# =============================== SETTINGS ====================================
BAUD            = 921600        # must match SERIAL_BAUD in the ESP32 sketch
N               = 1024          # samples per block
FS_NOMINAL      = 16000
SPEC_SECONDS    = 4.0           # spectrogram history
SPEC_NFFT       = 512           # spectrogram window length
SPEC_HOP        = 256
RECORD_SECONDS  = 10.0          # length saved with 's' when nothing is captured
# ---- event trigger
TRIG_FRAME      = 256           # analysis frame (16 ms @ 16 kS/s)
TRIG_DB_DEFAULT = 12.0          # threshold [dB]
TRIG_BG_ALPHA   = 0.03          # background adapts up slowly (~0.5 s) ...
TRIG_BG_FAST    = 0.20          # ... and fast when quieter / after an event (~0.1 s)
TRIG_HYST_DB    = 6.0           # re-arm only when score < threshold - this
TRIG_MIN_RMS_V  = 0.004         # ignore changes quieter than this (V rms)
TRIG_HOLDOFF_S  = 0.30          # minimum time between two triggers
TRIG_WARMUP     = 20            # frames before the detector is enabled
CAP_PRE         = 1024          # samples kept before the trigger (64 ms)
CAP_POST        = 3072          # samples after the trigger (192 ms)
RING_SECONDS    = 12.0          # history kept in memory (>= RECORD_SECONDS)
# full-scale voltage per source id (flags bits 3..2)
VFS = {0: 3.3,                  # MCP3201/3202/..., VREF = VDD = 3.3 V
       1: 5.0,                  # MAX 10 ADC through DE10-Lite Arduino header divider
       2: 3.3}                  # internal test tone (arbitrary)
SRC_NAME = {0: "MCP320x ADC", 1: "MAX10 ADC", 2: "FPGA test tone", 3: "?"}
# =============================================================================

SYNC = b"\xAA\x55\x33\xCC"
HDR = struct.Struct("<4sHHBBHHIH")          # 20 bytes
assert HDR.size == 20


class Block:
    __slots__ = ("seq", "n", "flags", "fpga_drops", "spi_errs", "esp_drops",
                 "t_us", "fs", "samples", "host_t")

    @property
    def source(self):
        return (self.flags >> 2) & 0x3

    @property
    def is_test(self):
        return bool(self.flags & 0x02)


class FrameParser:
    """Byte-stream -> Block objects. Resynchronises on SYNC, checks checksum."""

    def __init__(self):
        self.buf = bytearray()
        self.bad_frames = 0

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:
                del self.buf[:-3]            # keep a possible partial sync
                break
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < HDR.size:
                break
            (_, seq, n, flags, fdrop, serr, edrop, t_us, fs) = HDR.unpack_from(self.buf, 0)
            if n == 0 or n > 8192:
                del self.buf[:4]
                self.bad_frames += 1
                continue
            total = HDR.size + 2 * n + 2
            if len(self.buf) < total:
                break
            samples = np.frombuffer(self.buf, dtype="<u2", count=n, offset=HDR.size).copy()
            chk = struct.unpack_from("<H", self.buf, HDR.size + 2 * n)[0]
            if (int(samples.sum(dtype=np.uint64)) & 0xFFFF) != chk:
                self.bad_frames += 1
                del self.buf[:4]             # resync inside the frame
                continue
            del self.buf[:total]
            b = Block()
            b.seq, b.n, b.flags, b.fpga_drops = seq, n, flags, fdrop
            b.spi_errs, b.esp_drops, b.t_us, b.fs = serr, edrop, t_us, fs
            b.samples, b.host_t = samples, time.perf_counter()
            out.append(b)
        return out


def build_frame(seq, samples, flags=0x01, t_us=0, fs=FS_NOMINAL):
    """Same format as the ESP32 sketch (used by --demo and for self-tests)."""
    s = np.asarray(samples, dtype="<u2")
    hdr = HDR.pack(SYNC, seq & 0xFFFF, len(s), flags, 0, 0, 0, t_us & 0xFFFFFFFF, fs)
    chk = int(s.sum(dtype=np.uint64)) & 0xFFFF
    return hdr + s.tobytes() + struct.pack("<H", chk)


# ------------------------------------------------------------------ sources
class SerialSource:
    def __init__(self, port, baud):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.05)
        self.ser.reset_input_buffer()

    def read(self):
        return self.ser.read(max(1, self.ser.in_waiting))

    def write(self, b):
        self.ser.write(b)


class DemoSource:
    """Synthetic 16 kS/s stream for trying the program without hardware:
    quiet 1 kHz tone (1.5 kHz between 4-5 s of every 6 s -> 'spectrum'
    trigger), 2.5 kHz tone, a slow chirp, and a loud 'clap' (decaying noise
    burst) at 1.5 s of every 3 s -> 'level' trigger."""

    def __init__(self):
        self.seq = 0
        self.t0 = time.perf_counter()
        self.n_sent = 0
        self.test = False

    def read(self):
        time.sleep(0.01)
        due = int((time.perf_counter() - self.t0) * FS_NOMINAL / N)
        out = b""
        while self.n_sent < due:
            k = np.arange(self.n_sent * N, (self.n_sent + 1) * N)
            if self.test:
                x = np.arange(N)
                flags = 0x03 | (2 << 2)
            else:
                t = k / FS_NOMINAL
                f1 = np.where((t % 6.0 >= 4.0) & (t % 6.0 < 5.0), 1500.0, 1000.0)
                f_chirp = 300 + 200 * (t % 5.0) ** 1.5
                tc = (t % 3.0) - 1.5
                clap = np.where((tc >= 0) & (tc < 0.08),
                                1400 * np.exp(-np.clip(tc, 0, None) / 0.012), 0.0)
                x = (2048 + 150 * np.sin(2 * np.pi * f1 * t)
                     + 50 * np.sin(2 * np.pi * 2500 * t)
                     + 40 * np.sin(2 * np.pi * f_chirp * t)
                     + clap * np.random.randn(N)
                     + 15 * np.random.randn(N))
                x = np.clip(np.round(x), 0, 4095)
                flags = 0x01 | (2 << 2)
            out += build_frame(self.seq, x, flags, int(self.n_sent * N / FS_NOMINAL * 1e6))
            self.seq += 1
            self.n_sent += 1
        return out

    def write(self, b):
        if b == b"t":
            self.test = True
        if b == b"n":
            self.test = False


def find_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    keys = ("CP210", "CH34", "CH91", "USB", "UART", "ESP", "JTAG")
    for p in ports:
        text = f"{p.device} {p.description} {p.hwid}".upper()
        if any(k in text for k in keys):
            return p.device
    if ports:
        return ports[0].device
    sys.exit("No serial port found -- use --port")


# ----------------------------------------------------------- event trigger
class EventTrigger:
    """Detects sudden significant changes in the continuous sample stream.
    Runs inside the receiver thread, so no event is missed between frames of
    the GUI. All public attributes may be changed from the GUI thread."""

    MODES = ("OFF", "NORMAL", "SINGLE")
    KINDS = ("level", "spectrum")
    EDGES = ("rise", "fall", "both")

    def __init__(self, fs):
        self.fs = fs
        self.mode = "OFF"
        self.kind = "level"
        self.edge = "rise"
        self.thr_db = TRIG_DB_DEFAULT
        self.armed = True
        self.count = 0
        self.events = collections.deque(maxlen=100)   # absolute sample indices
        self.capture = None          # dict, see _finish()
        self.capture_id = 0
        self.armed_at = 0
        self.score = 0.0             # latest detector score (dB) for display
        self._pending = np.zeros(0)
        self._pos = 0                # absolute index of _pending[0]
        self._dc = None
        self._bg = None
        self._bg_spec = None
        self._nframes = 0
        self._last_trig = -10 ** 12
        self._latched = False        # event in progress (hysteresis)
        self._waiting = None         # (trig_idx, score, info)
        self._win = np.hanning(TRIG_FRAME)

    def rearm(self):
        self.armed = True
        self.armed_at = self.capture_id    # SINGLE: freeze on a capture newer than this

    def reset_stream(self):
        """Call when the stream is discontinuous (test ramp, source change)."""
        self._pending = np.zeros(0)
        self._dc = self._bg = self._bg_spec = None
        self._nframes = 0
        self._waiting = None
        self._latched = False

    def process(self, volts, start_idx, ring):
        if len(self._pending) == 0:
            self._pos = start_idx
        self._pending = np.concatenate([self._pending, volts])
        while len(self._pending) >= TRIG_FRAME:
            f = self._pending[:TRIG_FRAME]
            self._frame(f, self._pos)
            self._pending = self._pending[TRIG_FRAME:]
            self._pos += TRIG_FRAME
        if self._waiting is not None:
            trig_idx = self._waiting[0]
            if ring.total >= trig_idx + CAP_POST:
                self._finish(ring)

    def _frame(self, f, idx):
        m = f.mean()
        self._dc = m if self._dc is None else 0.95 * self._dc + 0.05 * m
        x = f - self._dc
        r = float(np.sqrt(np.mean(x * x)))
        P = np.abs(np.fft.rfft(x * self._win)) ** 2 + 1e-14
        Pdb = 10 * np.log10(P)
        if self._bg is None:
            self._bg, self._bg_spec = r, Pdb.copy()
        self._nframes += 1

        bg = self._bg
        lvl_db = float(20 * np.log10((r + 1e-9) / (bg + 1e-9)))
        if self.kind == "level":
            if self.edge == "rise":
                score, loud_enough = lvl_db, r > TRIG_MIN_RMS_V
            elif self.edge == "fall":
                score, loud_enough = -lvl_db, bg > TRIG_MIN_RMS_V
            else:
                score, loud_enough = abs(lvl_db), max(r, bg) > TRIG_MIN_RMS_V
        else:
            # power-weighted mean |dB change| per frequency bin: strong
            # components (tones, harmonics) dominate, noise bins hardly count
            w = np.maximum(P, 10 ** (self._bg_spec / 10))
            score = float(np.sum(w * np.abs(Pdb - self._bg_spec)) / np.sum(w))
            loud_enough = max(r, bg) > TRIG_MIN_RMS_V
        self.score = score

        if self._latched and score < max(self.thr_db - TRIG_HYST_DB, 0.5 * self.thr_db):
            self._latched = False
        fire = (self.mode != "OFF" and self.armed and self._waiting is None
                and not self._latched
                and self._nframes > TRIG_WARMUP and loud_enough
                and score > self.thr_db
                and idx - self._last_trig > TRIG_HOLDOFF_S * self.fs)
        if fire:
            self._last_trig = idx
            self._latched = True
            self._waiting = (idx, score, dict(level_db=lvl_db, rms_before=bg, rms_after=r,
                                              kind=self.kind, edge=self.edge))
            self.events.append(idx)
            if self.mode == "SINGLE":
                self.armed = False

        # background: slow upwards, fast downwards; fast in both directions
        # while an event is latched, so a new steady state is learnt quickly
        if self._latched:
            a = TRIG_BG_FAST
            a_spec = TRIG_BG_FAST
        else:
            a = TRIG_BG_ALPHA if r > bg else TRIG_BG_FAST
            a_spec = np.where(Pdb > self._bg_spec, TRIG_BG_ALPHA, TRIG_BG_FAST)
        self._bg = (1 - a) * bg + a * r
        self._bg_spec = (1 - a_spec) * self._bg_spec + a_spec * Pdb

    def _finish(self, ring):
        trig_idx, score, info = self._waiting
        self._waiting = None
        seg = ring.get(trig_idx - CAP_PRE, trig_idx + CAP_POST)
        if seg is None:
            return
        self.count += 1
        self.capture_id += 1
        self.capture = dict(id=self.capture_id, n=self.count, idx=trig_idx, score=score,
                            samples=seg, wall=time.strftime("%H:%M:%S"), **info)
        print(f"[trigger #{self.count}] {self.capture['wall']}  {info['kind']}/{info['edge']}"
              f"  score={score:5.1f} dB  level change={info['level_db']:+5.1f} dB  "
              f"rms {info['rms_before'] * 1e3:.1f} -> {info['rms_after'] * 1e3:.1f} mV")


class Ring:
    """Ring buffer of the continuous stream (volts), addressed by absolute index."""

    def __init__(self, size):
        self.buf = np.zeros(size)
        self.size = size
        self.total = 0

    def append(self, x):
        n = len(x)
        i = self.total % self.size
        if i + n <= self.size:
            self.buf[i:i + n] = x
        else:
            k = self.size - i
            self.buf[i:] = x[:k]
            self.buf[:n - k] = x[k:]
        self.total += n

    def get(self, start, stop):
        if start < 0 or start < self.total - self.size or stop > self.total:
            return None
        idx = np.arange(start, stop) % self.size
        return self.buf[idx].copy()

    def last(self, n):
        n = min(n, self.total, self.size)
        return self.get(self.total - n, self.total)


# ---------------------------------------------------------------- receiver
class Receiver(threading.Thread):
    def __init__(self, src):
        super().__init__(daemon=True)
        self.src = src
        self.parser = FrameParser()
        self.lock = threading.Lock()
        self.latest = None
        self.new_blocks = collections.deque(maxlen=512)
        self.ring = Ring(int(RING_SECONDS * FS_NOMINAL))
        self.trigger = EventTrigger(FS_NOMINAL)
        self.stats = dict(blocks=0, seq_gaps=0, lost_blocks=0, fs_est=float("nan"),
                          test_ok=None, bytes=0)
        self._first = None          # (seq_unwrapped, t_us) for Fs estimate
        self._last_seq = None
        self._seq_unwrapped = 0
        self._t_wraps = 0
        self._last_t = None
        self._last_src = None
        self.running = True

    def run(self):
        while self.running:
            data = self.src.read()
            if not data:
                continue
            self.stats["bytes"] += len(data)
            for b in self.parser.feed(data):
                self._update_stats(b)
                with self.lock:
                    self.latest = b
                    self.new_blocks.append(b)
                    if b.is_test:
                        self.trigger.reset_stream()
                        continue
                    if b.source != self._last_src:
                        self.trigger.reset_stream()
                        self._last_src = b.source
                    v = b.samples * (VFS.get(b.source, 3.3) / 4096.0)
                    start = self.ring.total
                    self.ring.append(v)
                    self.trigger.process(v, start, self.ring)

    def _update_stats(self, b):
        st = self.stats
        st["blocks"] += 1
        if self._last_seq is not None:
            d = (b.seq - self._last_seq) & 0xFFFF
            if d != 1 and not b.is_test:
                st["seq_gaps"] += 1
                st["lost_blocks"] += (d - 1) if d > 1 else 0
            self._seq_unwrapped += d
        self._last_seq = b.seq
        # unwrap ESP32 micros() (32-bit, wraps after 71 min)
        if self._last_t is not None and b.t_us < self._last_t:
            self._t_wraps += 1
        self._last_t = b.t_us
        t = b.t_us + self._t_wraps * 2**32
        if self._first is None or b.is_test:
            self._first = (self._seq_unwrapped, t)
        else:
            dseq = self._seq_unwrapped - self._first[0]
            dt = (t - self._first[1]) * 1e-6
            if dseq >= 4 and dt > 0:
                # Fs = samples produced by the FPGA / elapsed time.  Uses the
                # FPGA sequence number, so dropped blocks do not bias the result.
                st["fs_est"] = dseq * b.n / dt
        if b.is_test:
            st["test_ok"] = bool(np.array_equal(b.samples, np.arange(b.n)))

    def take_new(self):
        with self.lock:
            out = list(self.new_blocks)
            self.new_blocks.clear()
            return out, self.latest


# ---------------------------------------------------------------- analysis
def spectrum(x, fs, use_hann):
    x = x.astype(float) - np.mean(x)
    w = np.hanning(len(x)) if use_hann else np.ones(len(x))
    X = np.fft.rfft(x * w)
    mag = 2.0 * np.abs(X) / np.sum(w)          # amplitude-corrected (peak units)
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    return f, mag


def peak_freq(f, mag):
    """Dominant frequency with parabolic interpolation on the log magnitude."""
    k = int(np.argmax(mag[1:])) + 1
    if 1 <= k < len(mag) - 1:
        a, b, c = np.log(mag[k - 1:k + 2] + 1e-12)
        p = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    else:
        p = 0.0
    df = f[1] - f[0]
    return (k + p) * df, mag[k]


def write_wav(path, volts, vfs):
    code = volts / vfs * 4096.0
    pcm = ((code - 2048) * 16).clip(-32768, 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(FS_NOMINAL)
        wf.writeframes(pcm.tobytes())


def save_recording(rx, fig=None, capture=None, vfs=3.3):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if fig is not None:
        fig.savefig(f"task3_{stamp}.png", dpi=150)
        print(f"saved task3_{stamp}.png")
    if capture is not None:
        np.savez(f"task3_event{capture['n']}_{stamp}.npz", volts=capture["samples"],
                 fs=FS_NOMINAL, pre=CAP_PRE, trigger_index=CAP_PRE,
                 score_db=capture["score"], level_db=capture["level_db"],
                 kind=capture["kind"], edge=capture["edge"])
        write_wav(f"task3_event{capture['n']}_{stamp}.wav", capture["samples"], vfs)
        print(f"saved task3_event{capture['n']}_{stamp}.npz/.wav (captured event)")
        return
    with rx.lock:
        x = rx.ring.last(int(RECORD_SECONDS * FS_NOMINAL))
    if x is None or len(x) == 0:
        print("nothing to save")
        return
    np.savez(f"task3_rec_{stamp}.npz", volts=x, fs=FS_NOMINAL)
    write_wav(f"task3_rec_{stamp}.wav", x, vfs)
    print(f"saved task3_rec_{stamp}.wav / .npz  ({len(x) / FS_NOMINAL:.1f} s)")


# ------------------------------------------------------------- check mode
def run_check(rx, seconds):
    print(f"collecting for {seconds:.0f} s ...")
    t_end = time.time() + seconds
    while time.time() < t_end:
        time.sleep(1.0)
        _, b = rx.take_new()
        st = rx.stats
        if b is None:
            print("  no frames yet")
            continue
        print(f"  blocks={st['blocks']:5d}  seq={b.seq:5d}  Fs_est={st['fs_est']:9.2f} S/s  "
              f"gaps={st['seq_gaps']} lost={st['lost_blocks']}  fpga_drop={b.fpga_drops}  "
              f"spi_err={b.spi_errs} esp_drop={b.esp_drops} bad_usb={rx.parser.bad_frames}  "
              f"src={SRC_NAME[b.source]}"
              + (f"  ramp_ok={st['test_ok']}" if b.is_test else ""))
    st = rx.stats
    ok = abs(st["fs_est"] - FS_NOMINAL) < 0.002 * FS_NOMINAL
    print(f"\nRESULT: Fs_est = {st['fs_est']:.2f} S/s (nominal {FS_NOMINAL})  -> "
          f"{'OK' if ok else 'CHECK'};  lost blocks = {st['lost_blocks']}")


# ---------------------------------------------------------------- GUI mode
def run_gui(rx, src):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from matplotlib.widgets import Button, Slider

    trig = rx.trigger
    state = dict(hann=True, paused=False, db=True, shown_capture=0, vfs=3.3)
    fs = FS_NOMINAL
    n_cols = int(SPEC_SECONDS * fs / SPEC_HOP)
    n_bins = SPEC_NFFT // 2 + 1
    spec = dict(img=np.full((n_bins, n_cols), -100.0), tail=np.zeros(0), count=0)
    spec_win = np.hanning(SPEC_NFFT)

    fig = plt.figure(figsize=(12, 9))
    fig.canvas.manager.set_window_title("Task 3 - FPGA audio sampling")
    gs = fig.add_gridspec(3, 1, left=0.07, right=0.97, top=0.92, bottom=0.17, hspace=0.45)
    ax_t = fig.add_subplot(gs[0])
    ax_f = fig.add_subplot(gs[1])
    ax_s = fig.add_subplot(gs[2])

    # ---- waveform panel
    t_ms = np.arange(N) / fs * 1e3
    (l_t,) = ax_t.plot(t_ms, np.zeros(N), lw=0.8)
    l_t0 = ax_t.axvline(0, color="r", lw=1.2, ls="--", visible=False)
    ax_t.set_xlim(0, t_ms[-1])
    ax_t.set_ylim(0, 3.3)
    ax_t.set_xlabel("time [ms]")
    ax_t.set_ylabel("voltage [V]")
    ax_t.grid(alpha=0.3)
    ttl_t = ax_t.set_title("LIVE", loc="left", fontsize=9, fontweight="bold")

    # ---- spectrum panel
    f_axis = np.fft.rfftfreq(N, 1 / fs)
    (l_f2,) = ax_f.plot(f_axis, np.full_like(f_axis, np.nan), lw=0.8, color="0.6",
                        label="before trigger")
    (l_f,) = ax_f.plot(f_axis, np.zeros_like(f_axis), lw=0.8, color="C0", label="after trigger")
    (l_pk,) = ax_f.plot([], [], "rv")
    ax_f.set_xlim(0, fs / 2)
    ax_f.set_ylim(-110, 10)
    ax_f.set_xlabel("frequency [Hz]")
    ax_f.set_ylabel("amplitude [dBV]")
    ax_f.grid(alpha=0.3)
    leg = ax_f.legend(loc="upper right", fontsize=8)
    leg.set_visible(False)

    # ---- spectrogram panel
    im = ax_s.imshow(spec["img"], origin="lower", aspect="auto", cmap="viridis",
                     extent=[-SPEC_SECONDS, 0, 0, fs / 2], vmin=-100, vmax=-10)
    (l_ev,) = ax_s.plot([], [], "v", color="red", ms=8, clip_on=True)
    ax_s.set_xlim(-SPEC_SECONDS, 0)
    ax_s.set_ylim(0, fs / 2)
    ax_s.set_xlabel("time [s]   (red marks = trigger events)")
    ax_s.set_ylabel("frequency [Hz]")
    fig.colorbar(im, ax=ax_s, label="dBV", pad=0.01)

    info = fig.text(0.01, 0.995, "", va="top", ha="left", family="monospace", fontsize=8)

    # ---- widgets
    widgets = []

    def add_button(x, w, label, cb, y=0.06):
        ax = fig.add_axes([x, y, w, 0.045])
        b = Button(ax, label)
        b.on_clicked(cb)
        widgets.append(b)
        return b

    def set_pause(p):
        state["paused"] = p
        b_pause.label.set_text("Resume" if p else "Pause")
        b_pause.color = "#f4b6b6" if p else "0.85"
        b_pause.ax.set_facecolor(b_pause.color)
        fig.canvas.draw_idle()

    def cycle(seq, cur):
        return seq[(seq.index(cur) + 1) % len(seq)]

    def on_pause(_=None):
        set_pause(not state["paused"])

    def on_mode(_=None):
        trig.mode = cycle(EventTrigger.MODES, trig.mode)
        trig.rearm()
        b_mode.label.set_text(f"Trigger: {trig.mode}")
        if trig.mode == "OFF":
            state["shown_capture"] = 0
            show_live_axes()
        fig.canvas.draw_idle()

    def on_rearm(_=None):
        trig.rearm()
        if state["paused"]:
            set_pause(False)

    def on_kind(_=None):
        trig.kind = cycle(EventTrigger.KINDS, trig.kind)
        b_kind.label.set_text(f"Detect: {trig.kind}")
        fig.canvas.draw_idle()

    def on_edge(_=None):
        trig.edge = cycle(EventTrigger.EDGES, trig.edge)
        b_edge.label.set_text(f"Edge: {trig.edge}")
        fig.canvas.draw_idle()

    def on_win(_=None):
        state["hann"] = not state["hann"]
        b_win.label.set_text(f"Window: {'Hann' if state['hann'] else 'Rect'}")
        fig.canvas.draw_idle()

    def on_save(_=None):
        cap = trig.capture if state["shown_capture"] else None
        save_recording(rx, fig, cap, state["vfs"])

    b_pause = add_button(0.07, 0.09, "Pause", on_pause)
    b_mode = add_button(0.17, 0.14, "Trigger: OFF", on_mode)
    add_button(0.32, 0.08, "Re-arm", on_rearm)
    b_kind = add_button(0.41, 0.14, "Detect: level", on_kind)
    b_edge = add_button(0.56, 0.11, "Edge: rise", on_edge)
    b_win = add_button(0.68, 0.13, "Window: Hann", on_win)
    add_button(0.82, 0.08, "Save", on_save)

    ax_sl = fig.add_axes([0.17, 0.015, 0.45, 0.025])
    sl = Slider(ax_sl, "Threshold [dB]", 3.0, 40.0, valinit=TRIG_DB_DEFAULT, valstep=0.5)
    sl.on_changed(lambda v: setattr(trig, "thr_db", float(v)))
    widgets.append(sl)
    score_txt = fig.text(0.66, 0.02, "", family="monospace", fontsize=8)

    def on_key(ev):
        k = ev.key
        if k == "p":
            on_pause()
        elif k == "g":
            on_mode()
        elif k == "r":
            on_rearm()
        elif k == "d":
            on_kind()
        elif k == "e":
            on_edge()
        elif k == "w":
            on_win()
        elif k == "s":
            on_save()
        elif k == "l":
            state["db"] = not state["db"]
            ax_f.set_ylabel("amplitude [dBV]" if state["db"] else "amplitude [V]")
        elif k == "t":
            src.write(b"t")
        elif k == "n":
            src.write(b"n")
    fig.canvas.mpl_connect("key_press_event", on_key)

    # ---- helpers
    def show_live_axes():
        l_t0.set_visible(False)
        l_f2.set_ydata(np.full_like(f_axis, np.nan))
        leg.set_visible(False)
        ax_t.set_xlim(0, t_ms[-1])
        ax_t.set_xlabel("time [ms]")

    def set_spectrum_line(line, v):
        f, mag = spectrum(v, fs, state["hann"])
        line.set_ydata(20 * np.log10(mag + 1e-9) if state["db"] else mag)
        return f, mag

    def draw_capture(cap):
        v = cap["samples"]
        tt = (np.arange(len(v)) - CAP_PRE) / fs * 1e3
        l_t.set_data(tt, v)
        ax_t.set_xlim(tt[0], tt[-1])
        ax_t.set_xlabel("time relative to trigger [ms]")
        l_t0.set_visible(True)
        before = v[CAP_PRE - N:CAP_PRE] if CAP_PRE >= N else v[:CAP_PRE]
        after = v[CAP_PRE:CAP_PRE + N]
        set_spectrum_line(l_f2, before)
        f, mag = set_spectrum_line(l_f, after)
        leg.set_visible(True)
        fpk, apk = peak_freq(f, mag)
        l_pk.set_data([fpk], [20 * np.log10(apk + 1e-9) if state["db"] else apk])
        ttl_t.set_text(
            f"CAPTURED EVENT #{cap['n']}  ({cap['wall']})  {cap['kind']}/{cap['edge']}  "
            f"score={cap['score']:.1f} dB  level {cap['level_db']:+.1f} dB  "
            f"rms {cap['rms_before'] * 1e3:.1f} -> {cap['rms_after'] * 1e3:.1f} mV  "
            f"peak after = {fpk:.1f} Hz")
        ttl_t.set_color("C3")

    def update(_):
        new, b = rx.take_new()
        if b is None or state["paused"]:
            return
        vfs = VFS.get(b.source, 3.3)
        state["vfs"] = vfs
        scale = vfs / 4096.0

        # ---- spectrogram (STFT over the continuous stream)
        img = spec["img"]
        for nb in new:
            if nb.is_test:
                continue
            spec["count"] += nb.n
            spec["tail"] = np.concatenate([spec["tail"], nb.samples.astype(float) * scale])
            cols = []
            while len(spec["tail"]) >= SPEC_NFFT:
                seg = spec["tail"][:SPEC_NFFT]
                seg = (seg - seg.mean()) * spec_win
                m = 2 * np.abs(np.fft.rfft(seg)) / spec_win.sum()
                cols.append(20 * np.log10(m + 1e-9))
                spec["tail"] = spec["tail"][SPEC_HOP:]
            if cols:
                c = np.array(cols).T
                img = np.hstack([img[:, c.shape[1]:], c])
        spec["img"] = img
        im.set_data(img)
        ev = [-(spec["count"] - e) / fs for e in list(trig.events)]
        ev = [x for x in ev if x >= -SPEC_SECONDS]
        l_ev.set_data(ev, [fs / 2 * 0.95] * len(ev))

        # ---- waveform + spectrum: captured event or live block
        cap = trig.capture
        if trig.mode == "SINGLE" and cap is not None and cap["id"] <= trig.armed_at:
            cap = None                       # waiting for a NEW single shot
        if trig.mode != "OFF" and cap is not None:
            state["shown_capture"] = cap["id"]
            draw_capture(cap)                # redraw: window / dB may change
            ax_t.set_ylim(0, vfs)
            if (trig.mode == "SINGLE" and not trig.armed and cap["id"] > trig.armed_at
                    and not state.get("froze_" + str(cap["id"]))):
                state["froze_" + str(cap["id"])] = True
                set_pause(True)              # freeze the whole display
        else:
            v = b.samples * scale
            l_t.set_data(t_ms, v)
            ax_t.set_ylim(0, vfs)
            f, mag = set_spectrum_line(l_f, v)
            fpk, apk = peak_freq(f, mag)
            l_pk.set_data([fpk], [20 * np.log10(apk + 1e-9) if state["db"] else apk])
            if trig.mode == "OFF":
                ttl_t.set_text("LIVE")
            else:
                ttl_t.set_text(f"LIVE - waiting for trigger ({trig.mode}, "
                               f"{trig.kind}/{trig.edge}, > {trig.thr_db:.1f} dB)")
            ttl_t.set_color("k")
        if not state["db"]:
            ax_f.set_ylim(0, max(1e-3, np.nanmax(l_f.get_ydata()[1:]) * 1.2))
        else:
            ax_f.set_ylim(-110, 10)

        armed = "ARMED" if trig.armed else "done (Re-arm)"
        score_txt.set_text(f"score {trig.score:5.1f} dB  {armed if trig.mode != 'OFF' else ''}"
                           f"  events={trig.count}")

        st = rx.stats
        v_live = b.samples * scale
        clip = np.mean((b.samples <= 4) | (b.samples >= 4091)) * 100
        info.set_text(
            f"src={SRC_NAME[b.source]:<14} seq={b.seq:5d}  Fs_est={st['fs_est']:8.1f} S/s  "
            f"df=Fs/N={fs / N:.3f} Hz  window={'Hann' if state['hann'] else 'Rect'}\n"
            f"Vpp={np.ptp(v_live):.3f} V  DC={np.mean(v_live):.3f} V  clip={clip:4.1f}%  "
            f"lost={st['lost_blocks']} fpga_drop={b.fpga_drops} spi_err={b.spi_errs} "
            f"esp_drop={b.esp_drops} bad_usb={rx.parser.bad_frames}"
            + (f"\nTEST RAMP: {'OK' if st['test_ok'] else 'ERROR'}" if b.is_test else ""))

    state["widgets"] = widgets
    state["anim"] = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.show()
    return fig, update, state


def main(argv=None):
    ap = argparse.ArgumentParser(description="Task 3 host: FPGA audio via ESP32")
    ap.add_argument("--port", help="serial port (COMx or /dev/ttyUSBx); default auto")
    ap.add_argument("--baud", type=int, default=BAUD)
    ap.add_argument("--demo", action="store_true", help="synthetic data, no hardware")
    ap.add_argument("--check", type=float, metavar="SEC",
                    help="no GUI: print link statistics and Fs estimate")
    a = ap.parse_args(argv)

    if a.demo:
        src = DemoSource()
    else:
        port = a.port or find_port()
        print(f"opening {port} @ {a.baud} baud")
        src = SerialSource(port, a.baud)
        src.write(b"n")

    rx = Receiver(src)
    rx.start()
    try:
        if a.check:
            run_check(rx, a.check)
        else:
            run_gui(rx, src)
    finally:
        rx.running = False


if __name__ == "__main__":
    main()
