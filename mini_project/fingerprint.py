"""
fingerprint.py — สร้าง "ลายนิ้วมือ" (fingerprint) ของเสียง
=====================================================================
ขั้นตอน (ตามเปเปอร์ Avery Wang, Shazam, 2003)

    เสียง ──► prepare() ──► spectrogram() ──► find_peaks() ──► make_hashes()
             ลบ DC,        STFT + Hann       หาจุดยอดเด่น        จับคู่จุดยอด
             resample      window            (constellation)     เป็น hash

ฟังก์ชัน fingerprint() ด้านล่างสุดเรียกทุกขั้นตอนต่อกันให้ในครั้งเดียว
"""
import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter

import config as C


# ---------------------------------------------------------------------
# 0) โหลดไฟล์เพลง
# ---------------------------------------------------------------------
def load_audio_file(path, offset=0.0, duration=None):
    """โหลดไฟล์เสียง แปลงเป็นโมโนและ sample rate = C.FS"""
    import librosa  # import ตรงนี้เพราะโหลดช้า ใช้เฉพาะตอนอ่านไฟล์
    y, _ = librosa.load(str(path), sr=C.FS, mono=True, offset=offset, duration=duration)
    return y.astype(np.float32)


# ---------------------------------------------------------------------
# 1) เตรียมสัญญาณ
# ---------------------------------------------------------------------
def prepare(samples, fs_in):
    """ลบ DC offset, resample เป็น C.FS และ normalize ให้อยู่ในช่วง -1..1"""
    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()                                   # ลบ DC (สำคัญมากกับ ADC ที่มี offset)
    if int(fs_in) != C.FS:
        g = np.gcd(int(fs_in), int(C.FS))
        # resample_poly มี anti-aliasing low-pass filter ในตัว
        x = signal.resample_poly(x, C.FS // g, int(fs_in) // g)
    peak = np.max(np.abs(x)) if x.size else 0.0
    if peak > 0:
        x = x / peak
    return x.astype(np.float32)


# ---------------------------------------------------------------------
# 2) Spectrogram
# ---------------------------------------------------------------------
def spectrogram(x):
    """
    คืนค่า
        f    : ความถี่ของแต่ละแถว (Hz)
        t    : เวลาของแต่ละคอลัมน์ (วินาที)
        S_db : ขนาด (dB) รูปร่าง [ความถี่, เวลา]
    """
    f, t, Z = signal.stft(
        x, fs=C.FS, window="hann",
        nperseg=C.NFFT, noverlap=C.NFFT - C.HOP,
        boundary=None, padded=False,
    )
    S_db = 20 * np.log10(np.abs(Z) + 1e-10)
    return f, t, S_db


# ---------------------------------------------------------------------
# 3) หาจุดยอด (Constellation map)
# ---------------------------------------------------------------------
def find_peaks(S_db, f):
    """
    จุดยอด = จุดที่ดังที่สุดในพื้นที่รอบตัว (local maximum ใน 2 มิติ)
             และดังกว่าค่ากลางของทั้งภาพอย่างน้อย PEAK_MIN_DB
    คืนค่า (ดัชนีความถี่, ดัชนีเฟรม) เรียงตามเวลา
    """
    band = (f >= C.FREQ_MIN) & (f <= C.FREQ_MAX)
    if S_db.size == 0 or not band.any():
        return np.array([], int), np.array([], int)

    local_max = maximum_filter(S_db, size=C.PEAK_NEIGHBORHOOD,
                               mode="constant", cval=-np.inf) == S_db
    threshold = np.median(S_db[band]) + C.PEAK_MIN_DB
    mask = local_max & (S_db > threshold) & band[:, None]

    fi, ti = np.nonzero(mask)
    order = np.argsort(ti, kind="stable")
    return fi[order], ti[order]


# ---------------------------------------------------------------------
# 4) สร้าง hash จากคู่จุดยอด
# ---------------------------------------------------------------------
def make_hashes(fi, ti):
    """
    จุดยึด (anchor) แต่ละจุด จับคู่กับจุดถัดไปที่อยู่ใน "target zone"
    hash = (ความถี่จุดยึด, ความถี่จุดคู่, ระยะเวลาห่าง) อัดรวมเป็นจำนวนเต็มตัวเดียว
        บิต 16–25 : f1   บิต 6–15 : f2   บิต 0–5 : dt
    คืนค่า list ของ (hash, เฟรมของจุดยึด)
    """
    hashes = []
    n = len(fi)
    for i in range(n):
        paired = 0
        for j in range(i + 1, n):
            dt = ti[j] - ti[i]
            if dt < C.TARGET_DT_MIN:
                continue
            if dt > C.TARGET_DT_MAX:
                break                         # เรียงตามเวลาแล้ว จุดถัดไปไกลเกินแน่นอน
            if abs(int(fi[j]) - int(fi[i])) > C.TARGET_DF_MAX:
                continue
            h = (int(fi[i]) << 16) | (int(fi[j]) << 6) | int(dt)
            hashes.append((h, int(ti[i])))
            paired += 1
            if paired >= C.FAN_OUT:
                break
    return hashes


# ---------------------------------------------------------------------
# รวมทุกขั้นตอน
# ---------------------------------------------------------------------
def fingerprint(samples, fs_in=C.FS):
    """คืน dict ที่มีทุกอย่าง (ใช้ทั้งตอนเก็บเข้าฐานข้อมูล และตอนวาดกราฟใน GUI)"""
    x = prepare(samples, fs_in)
    f, t, S_db = spectrogram(x)
    fi, ti = find_peaks(S_db, f)
    hashes = make_hashes(fi, ti)
    return {"x": x, "f": f, "t": t, "S_db": S_db,
            "peak_f": fi, "peak_t": ti, "hashes": hashes}


def frames_to_seconds(frames):
    return frames * C.HOP / C.FS
