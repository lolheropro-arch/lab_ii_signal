"""
audio_input.py — แหล่งรับเสียง 2 แบบ (ทุกฟังก์ชันคืนค่า (samples, sample_rate))
=====================================================================
1. record_serial()  : ไมค์ → FPGA → ESP32 → USB-Serial (ใช้งานจริง)
2. load_test_clip() : ตัดช่วงหนึ่งจากไฟล์เพลง + ใส่ noise (ทดสอบอัลกอริทึมโดยไม่ต้องต่อบอร์ด)

รูปแบบข้อมูลที่ ESP32 ต้องส่ง (ตั้งค่าใน config.py)
    [SYNC_BYTES][BLOCK_SIZE samples แบบ binary][SYNC_BYTES][BLOCK_SIZE samples]...
    ค่าเริ่มต้น:  AA 55  ตามด้วย 1024 × int16 little-endian
"""
import random
import time

import numpy as np

import config as C


# ---------------------------------------------------------------------
# 1) ESP32 ผ่าน Serial
# ---------------------------------------------------------------------
def list_serial_ports():
    """รายชื่อพอร์ตที่เสียบอยู่ (ใช้เติมใน dropdown ของ GUI)"""
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


def _wait_for_sync(ser, deadline):
    """อ่านทีละไบต์จนเจอ SYNC_BYTES (ใช้หาจุดเริ่มบล็อก)"""
    sync = C.SYNC_BYTES
    window = b""
    while time.time() < deadline:
        b = ser.read(1)
        if not b:
            continue
        window = (window + b)[-len(sync):]
        if window == sync:
            return
    raise TimeoutError("ไม่พบ header ของบล็อก — ตรวจ SYNC_BYTES / baud rate / ว่าบอร์ดกำลังส่งข้อมูล")


def record_serial(seconds, port=C.SERIAL_PORT, baud=C.BAUD_RATE, progress=None):
    import serial

    dtype = np.dtype(C.SAMPLE_DTYPE)
    n_needed = int(seconds * C.INPUT_FS)
    n_blocks = int(np.ceil(n_needed / C.BLOCK_SIZE))
    block_bytes = C.BLOCK_SIZE * dtype.itemsize
    blocks = []

    with serial.Serial(port, baud, timeout=C.SERIAL_TIMEOUT) as ser:
        ser.reset_input_buffer()               # ทิ้งข้อมูลเก่าที่ค้างใน buffer
        while len(blocks) < n_blocks:
            if C.SYNC_BYTES:
                _wait_for_sync(ser, time.time() + C.SERIAL_TIMEOUT)
            data = ser.read(block_bytes)
            if len(data) < block_bytes:
                raise TimeoutError("ได้ข้อมูลไม่ครบบล็อก — ตรวจ BLOCK_SIZE / SAMPLE_DTYPE ใน config.py")
            blocks.append(np.frombuffer(data, dtype=dtype))
            if progress:
                progress(len(blocks) / n_blocks)

    samples = np.concatenate(blocks)[:n_needed].astype(np.float64)
    return samples, C.INPUT_FS


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
