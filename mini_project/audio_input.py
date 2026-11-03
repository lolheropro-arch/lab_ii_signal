"""
audio_input.py — แหล่งรับเสียง 2 แบบ (ทุกฟังก์ชันคืนค่า (samples, sample_rate))
=====================================================================
1. record_serial()  : ไมค์ → FPGA → ESP32 → USB-Serial (ใช้งานจริง)
2. load_test_clip() : ตัดช่วงหนึ่งจากไฟล์เพลง + ใส่ noise (ทดสอบอัลกอริทึมโดยไม่ต้องต่อบอร์ด)

รูปแบบ frame ของ Task 3 (ตั้งค่าใน config.py)  ยาว 2070 ไบต์
    offset 0   sync  AA 55 33 CC
    offset 4   seq (uint16)   offset 6   n (uint16)   offset 8   flags (uint8)
    offset 20  1024 × uint16 little-endian
    offset 2068  checksum = ผลรวม sample mod 2^16
"""
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from scipy import signal

import config as C


# ---------------------------------------------------------------------
# 1) ESP32 ผ่าน Serial
# ---------------------------------------------------------------------
def list_serial_ports():
    """รายชื่อพอร์ตที่เสียบอยู่ (ใช้เติมใน dropdown ของ GUI)"""
    try:
        from serial.tools import list_ports
        # พอร์ต USB ขึ้นก่อน: GUI ใช้ตัวแรกเป็นค่าเริ่มต้น และ /dev/ttyS* บน Linux มักเปิดไม่ได้
        return [p.device for p in sorted(list_ports.comports(), key=lambda p: p.vid is None)]
    except Exception:
        return []


def _read_frames(ser):
    """คืน (seq, flags, samples) ทีละ frame: หา SYNC_BYTES ใหม่เองและข้าม frame ที่ checksum ไม่ผ่าน"""
    sync = C.SYNC_BYTES
    dtype = np.dtype(C.SAMPLE_DTYPE)
    checksum_at = C.FRAME_HEADER_BYTES + C.BLOCK_SIZE * dtype.itemsize
    frame_bytes = checksum_at + 2
    buf = bytearray()
    deadline = time.time() + C.SERIAL_TIMEOUT

    while True:
        if time.time() > deadline:
            raise TimeoutError("ไม่ได้รับ frame ที่ถูกต้อง — ตรวจ baud rate / ว่าบอร์ดกำลังส่งข้อมูล / ปิดโปรแกรมอื่นที่เปิดพอร์ต")
        buf += ser.read(max(1, ser.in_waiting))
        while True:
            i = buf.find(sync)
            if i < 0:
                del buf[:-(len(sync) - 1)]     # เก็บท้ายไว้ เผื่อ sync ถูกตัดคร่อมการอ่าน
                break
            del buf[:i]
            if len(buf) < frame_bytes:
                break
            seq, n, flags = struct.unpack_from("<HHB", buf, len(sync))
            samples = np.frombuffer(buf, dtype, C.BLOCK_SIZE, C.FRAME_HEADER_BYTES).copy()
            checksum = struct.unpack_from("<H", buf, checksum_at)[0]
            if n != C.BLOCK_SIZE or int(samples.sum()) & 0xFFFF != checksum:
                del buf[:len(sync)]            # frame เสีย: หา sync ถัดไป
                continue
            del buf[:frame_bytes]
            deadline = time.time() + C.SERIAL_TIMEOUT
            yield seq, flags, samples


def record_serial(seconds, port=C.SERIAL_PORT, baud=C.BAUD_RATE, progress=None):
    import serial

    n_needed = int(seconds * C.INPUT_FS)
    n_blocks = int(np.ceil(n_needed / C.BLOCK_SIZE))
    blocks = []
    last_seq = None

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, baud, C.SERIAL_TIMEOUT
    ser.dtr, ser.rts = False, False            # ไม่ให้การเปิดพอร์ต reset ESP32
    with ser:
        ser.reset_input_buffer()               # ทิ้งข้อมูลเก่าที่ค้างใน buffer
        for seq, flags, samples in _read_frames(ser):
            if flags & C.FLAG_TEST_RAMP:
                raise ValueError("FPGA กำลังส่ง test ramp ไม่ใช่เสียงจากไมค์ — ปิดสวิตช์ทดสอบบนบอร์ด")
            if last_seq is not None:
                # บล็อกที่หายเติมด้วยค่า DC เพื่อไม่ให้เวลาเลื่อน (fingerprint อาศัยระยะห่างตามเวลา)
                lost = ((seq - last_seq) & 0xFFFF) - 1
                lost = min(lost, n_blocks - len(blocks))
                blocks.extend([np.full(C.BLOCK_SIZE, blocks[-1].mean())] * lost)
            blocks.append(samples)
            last_seq = seq
            if progress:
                progress(min(len(blocks) / n_blocks, 1.0))
            if len(blocks) >= n_blocks:
                break

    samples = np.concatenate(blocks)[:n_needed].astype(np.float64)
    return samples, C.INPUT_FS


# ---------------------------------------------------------------------
# ลดเสียงพื้นหลัง และเล่นเสียงที่อัด
# ---------------------------------------------------------------------
def reduce_noise(x, fs):
    """
    ลดเสียงพื้นหลังด้วย 2 ขั้น (ไมค์ตัวเดียววัดระยะไม่ได้ จึงใช้ "ความดัง" แทนระยะ)
    1. spectral gating : ความถี่ไหนดังไม่พ้นระดับพื้นของมันเอง ให้ลดลง
    2. near gate       : ช่วงเวลาที่เบากว่าช่วงดังมาก ๆ ถือว่าเป็นเสียงไกล ให้ลดลง
    """
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean()
    _, _, Z = signal.stft(x, fs, nperseg=C.NOISE_NFFT)
    mag = np.abs(Z) + 1e-12
    floor = 10 ** (C.NOISE_FLOOR_DB / 20)

    noise = np.percentile(mag, C.NOISE_PERCENTILE, axis=1, keepdims=True)
    gain = np.clip(1 - C.NOISE_OVERSUB * noise / mag, floor, 1.0)

    level = np.sqrt(np.sum(mag ** 2, axis=0))
    near = level >= np.percentile(level, 95) * 10 ** (-C.NEAR_GATE_DB / 20)
    gain = gain * np.where(near, 1.0, floor)

    # เกลี่ยตามเวลา ลดเสียงกระพริบ (musical noise)
    gain = signal.convolve2d(gain, np.ones((1, 5)) / 5, mode="same", boundary="symm")
    _, y = signal.istft(Z * gain, fs, nperseg=C.NOISE_NFFT)
    return y[:len(x)]


def play_audio(x, fs):
    """เล่นเสียงผ่านลำโพงโดยไม่รอจนจบ คืน process ไว้หยุดด้วย stop_audio()"""
    y = np.asarray(x, dtype=np.float64)
    y = y - y.mean()
    peak = np.max(np.abs(y)) if y.size else 0.0
    if peak > 0:
        y = y / peak * 0.8                     # เผื่อขอบไว้ ไม่ให้แตกที่ลำโพง
    path = Path(tempfile.gettempdir()) / "mini_shazam_last.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(fs))
        w.writeframes((y * 32767).astype("<i2").tobytes())

    if sys.platform.startswith("win"):
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return None
    for cmd in (["pw-play"], ["paplay"], ["aplay", "-q"], ["afplay"],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]):
        if shutil.which(cmd[0]):
            return subprocess.Popen(cmd + [str(path)])
    raise RuntimeError("ไม่พบโปรแกรมเล่นเสียง (pw-play, paplay, aplay, afplay หรือ ffplay)")


def stop_audio(player):
    if sys.platform.startswith("win"):
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    elif player is not None:
        player.terminate()


# ---------------------------------------------------------------------
# 2) คลิปทดสอบจากไฟล์
# ---------------------------------------------------------------------
def add_noise(x, snr_db):
    """ใส่ white noise ให้ได้ SNR ตามที่กำหนด (dB)"""
    if snr_db is None:
        return x
    p_signal = np.mean(x ** 2)
    p_noise = p_signal / (10 ** (snr_db / 10))
    return x + np.random.normal(0, np.sqrt(p_noise), size=x.shape)


def load_test_clip(path, seconds, start=None, snr_db=None):
    """
    ตัดคลิปยาว `seconds` จากไฟล์เพลง (ถ้า start=None จะสุ่มตำแหน่ง)
    คืน (samples, fs, start ที่ใช้จริง)
    """
    import librosa
    from fingerprint import load_audio_file

    total = librosa.get_duration(path=str(path))
    if start is None:
        start = random.uniform(0, max(total - seconds, 0))
    x = load_audio_file(path, offset=start, duration=seconds).astype(np.float64)
    return add_noise(x, snr_db), C.FS, start
