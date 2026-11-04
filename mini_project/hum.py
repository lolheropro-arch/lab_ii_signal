"""
hum.py — โหมดฮัมเพลง (Query by Humming)
=====================================================================
เสียงฮัม ─► จับ pitch (pYIN) ─► เส้นระดับเสียง ─► เทียบกับทำนองอ้างอิงด้วย DTW ─► ชื่อเพลง

ต่างจาก fingerprint ตรงที่เทียบ "ทำนอง" จึงฮัมคนละคีย์ได้ (ลองเลื่อนระดับเสียงหลายค่า)
ฮัมเร็วหรือช้ากว่าเดิมได้ (DTW ยืดหดเวลา) และฮัมแค่ท่อนเดียวได้ (subsequence DTW)
"""
import numpy as np
from scipy import signal

import config as C
from melodies import MELODIES

_STRETCH_PENALTY = 0.25                        # ค่าปรับเมื่อยืดหดเวลา กันไม่ให้ลากโน้ตเดียวยาวเกินจริง


def extract_pitch(samples, fs):
    """คืน (เวลาเป็นวินาที, ระดับเสียงเป็นโน้ต MIDI) เฟรมที่ไม่มีเสียงฮัมเป็น NaN"""
    import librosa

    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()
    if int(fs) != C.HUM_FS:
        g = np.gcd(int(fs), C.HUM_FS)
        x = signal.resample_poly(x, C.HUM_FS // g, int(fs) // g)
    peak = np.max(np.abs(x)) if x.size else 0.0
    if peak > 0:
        x = x / peak
    hop = C.HUM_FS // 100                      # 10 ms ต่อเฟรม
    f0, voiced, _ = librosa.pyin(x, fmin=C.HUM_FMIN, fmax=C.HUM_FMAX, sr=C.HUM_FS,
                                 frame_length=1024, hop_length=hop)
    midi = librosa.hz_to_midi(np.where(voiced, f0, np.nan))
    # เฟรมที่เบามากมักเป็นเสียงห้อง ไม่ใช่เสียงฮัม
    level = librosa.feature.rms(y=x, frame_length=1024, hop_length=hop)[0][:len(midi)]
    midi = midi[:len(level)]
    midi[level < np.percentile(level, 99) * C.HUM_GATE] = np.nan
    return np.arange(len(midi)) * hop / C.HUM_FS, midi


def _contour(midi):
    """ตัดช่วงเงียบออก กรองค่ากระโดด แล้วลดเหลือหนึ่งค่าต่อ C.HUM_STEP วินาที"""
    v = midi[np.isfinite(midi)]
    if v.size < 5:
        return v
    v = signal.medfilt(v, 5)
    n = max(int(round(C.HUM_STEP / 0.01)), 1)
    return np.array([np.median(v[i:i + n]) for i in range(0, len(v), n)])


def _reference(notes):
    """แปลงรายการโน้ตเป็นเส้นระดับเสียงที่ความละเอียดเดียวกับเสียงฮัม"""
    return np.concatenate([np.full(max(int(round(d * C.HUM_BEAT / C.HUM_STEP)), 1), float(m))
                           for m, d in notes])


def _subsequence_dtw(cost):
    """
    DTW ที่เริ่มและจบตรงไหนของทำนองก็ได้ แต่ละก้าวเดิน (1,1), (1,2) หรือ (2,1)
    จึงฮัมเร็วหรือช้ากว่าทำนองอ้างอิงได้ไม่เกินราว 2 เท่า คืน path เป็น array [[เฟรมฮัม, เฟรมทำนอง], ...]
    """
    n, m = cost.shape
    D = np.full((n, m), np.inf)
    step = np.zeros((n, m), dtype=np.int8)
    D[0] = cost[0]
    for i in range(1, n):
        options = np.full((3, m), np.inf)
        options[0, 1:] = D[i - 1, :-1]
        options[1, 2:] = D[i - 1, :-2] + _STRETCH_PENALTY
        if i >= 2:
            options[2, 1:] = D[i - 2, :-1] + _STRETCH_PENALTY
        step[i] = np.argmin(options, axis=0)
        D[i] = cost[i] + options[step[i], np.arange(m)]
    i, j = n - 1, int(np.argmin(D[-1]))
    path = [(i, j)]
    while i > 0 and np.isfinite(D[i, j]):
        di, dj = ((1, 1), (1, 2), (2, 1))[step[i, j]]
        i, j = i - di, j - dj
        path.append((i, j))
    return np.array(path[::-1])


def _align(query, ref):
    """เทียบเสียงฮัมกับทำนอง 1 เพลง โดยลองเลื่อนคีย์ คืน (ค่าคลาดเฉลี่ยเป็นครึ่งเสียง, เส้นที่เลื่อนแล้ว, path)"""
    base = query - np.median(query) + np.median(ref)
    best = (np.inf, None, None)
    for shift in range(-C.HUM_MAX_SHIFT, C.HUM_MAX_SHIFT + 1):
        q = base + shift
        d = np.abs(q[:, None] - ref[None, :]) % 12
        cost = np.minimum(np.minimum(d, 12 - d), C.HUM_COST_CAP)   # เสียงฮัมมักคนละ octave จึงคิดแบบวนรอบ 12
        if cost.shape[1] < 3:
            continue
        wp = _subsequence_dtw(cost)
        value = float(cost[wp[:, 0], wp[:, 1]].mean())
        if value < best[0]:
            best = (value, q, wp)
    return best


def match(samples, fs):
    """
    คืน dict:
        song, similarity, margin, confident → คำตอบ (similarity 0-100, margin = ห่างจากอันดับ 2)
        ranking                             → [(ชื่อเพลง, similarity), ...]
        t, midi                             → pitch ที่จับได้ (ไว้วาดกราฟ)
        query, reference                    → เส้นระดับเสียงของเสียงฮัม และท่อนในทำนองที่ตรงกัน
        voiced_sec, reason                  → ความยาวเสียงฮัมที่จับได้ และเหตุผลถ้าประเมินไม่ได้
    """
    t, midi = extract_pitch(samples, fs)
    query = _contour(midi)
    voiced_sec = float(np.isfinite(midi).sum()) * 0.01
    out = {"song": None, "similarity": 0.0, "margin": 0.0, "confident": False, "ranking": [],
           "t": t, "midi": midi, "query": query, "reference": np.array([]),
           "voiced_sec": voiced_sec, "reason": ""}
    if voiced_sec < C.HUM_MIN_VOICED_SEC:
        out["reason"] = f"จับเสียงฮัมได้แค่ {voiced_sec:.1f} วินาที (ต้องมีอย่างน้อย {C.HUM_MIN_VOICED_SEC:g})"
        return out
    if np.ptp(np.percentile(query, [10, 90])) < C.HUM_MIN_RANGE:
        out["reason"] = "เสียงฮัมแทบไม่ขึ้นลง จึงเทียบทำนองไม่ได้"
        return out

    scores = []
    for name, notes in MELODIES.items():
        ref = _reference(notes)
        cost, q, wp = _align(query, ref)
        scores.append((100 * (1 - cost / C.HUM_COST_CAP), name, q, ref, wp))
    scores.sort(key=lambda s: s[0], reverse=True)

    similarity, name, q, ref, wp = scores[0]
    margin = similarity - scores[1][0] if len(scores) > 1 else similarity
    out.update(song=name, similarity=similarity, margin=margin,
               confident=similarity >= C.HUM_MIN_SIMILARITY and margin >= C.HUM_MIN_MARGIN,
               ranking=[(s[1], s[0]) for s in scores],
               query=q[wp[:, 0]], reference=ref[wp[:, 1]])
    return out
