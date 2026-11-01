"""
experiment.py — ทดลองวัดความแม่นยำแบบอัตโนมัติ (ไว้ทำตาราง/กราฟใส่รายงาน)
=====================================================================
สุ่มตัดคลิปจากเพลงในโฟลเดอร์ songs/ → ใส่ noise → ค้นหา → นับว่าถูกกี่ %
ทำซ้ำทุกคู่ (ความยาวคลิป × ระดับ noise)

ตัวอย่างการรัน
    python experiment.py
    python experiment.py --lengths 2 5 10 --snr none 10 5 0 -5 --trials 30
    python experiment.py --negatives other_songs/     # ทดสอบเพลงที่ "ไม่มี" ในฐานข้อมูลด้วย

ผลลัพธ์: ตารางในหน้าจอ + ไฟล์ results/experiment_<เวลา>.csv และกราฟ .png
"""
import argparse
import csv
import random
import time
from pathlib import Path

import numpy as np

import audio_input
import config as C
import fingerprint as fp
from database import FingerprintDB


def audio_files(folder):
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in C.AUDIO_EXTENSIONS)


def run_trial(db, path, seconds, snr):
    x, fs, start = audio_input.load_test_clip(path, seconds, snr_db=snr)
    t0 = time.time()
    result = db.match(fp.fingerprint(x, fs)["hashes"])
    return result, time.time() - t0, start


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--songs", default=C.SONGS_DIR, help="โฟลเดอร์เพลง (ต้องเพิ่มเข้าฐานข้อมูลแล้ว)")
    ap.add_argument("--lengths", type=float, nargs="+", default=[2, 5, 10], help="ความยาวคลิป (วินาที)")
    ap.add_argument("--snr", nargs="+", default=["none", 10, 5, 0], help="SNR (dB) หรือ none")
    ap.add_argument("--trials", type=int, default=20, help="จำนวนครั้งต่อเงื่อนไข")
    ap.add_argument("--negatives", default=None, help="โฟลเดอร์เพลงที่ไม่มีในฐานข้อมูล (ทดสอบ false positive)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    db = FingerprintDB()

    # เพิ่มเพลงที่ยังไม่มีในฐานข้อมูล
    songs = audio_files(args.songs)
    if not songs:
        raise SystemExit(f"ไม่พบไฟล์เพลงใน {args.songs}")
    for p in songs:
        if db.add_file(p):
            print("เพิ่มเข้าฐานข้อมูล:", p.name)

    snrs = [None if str(s).lower() == "none" else float(s) for s in args.snr]
    rows = []
    print(f"\n{'clip(s)':>8} {'SNR(dB)':>8} {'accuracy':>9} {'avg score':>10} {'avg ms':>8}")
    for L in args.lengths:
        for snr in snrs:
            correct, scores, times = 0, [], []
            for _ in range(args.trials):
                path = random.choice(songs)
                res, dt, _ = run_trial(db, path, L, snr)
                ok = res["confident"] and res["song"] == path.stem
                correct += ok
                scores.append(res["score"])
                times.append(dt)
            acc = correct / args.trials
            snr_txt = "clean" if snr is None else f"{snr:g}"
            rows.append({"type": "in_db", "clip_s": L, "snr_db": snr_txt, "accuracy": acc,
                         "avg_score": np.mean(scores), "avg_ms": 1000 * np.mean(times)})
            print(f"{L:>8g} {snr_txt:>8} {acc:>8.0%} {np.mean(scores):>10.1f} {1000*np.mean(times):>8.0f}")

    # เพลงที่ไม่มีในฐานข้อมูล → ควรตอบว่า "ไม่พบ"
    if args.negatives:
        negs = audio_files(args.negatives)
        print("\nเพลงที่ไม่มีในฐานข้อมูล (ตอบ 'ไม่พบ' ถูกต้องกี่ %)")
        for L in args.lengths:
            rejected, scores = 0, []
            for _ in range(args.trials):
                res, _, _ = run_trial(db, random.choice(negs), L, None)
                rejected += not res["confident"]
                scores.append(res["score"])
            acc = rejected / args.trials
            rows.append({"type": "not_in_db", "clip_s": L, "snr_db": "clean", "accuracy": acc,
                         "avg_score": np.mean(scores), "avg_ms": ""})
            print(f"  clip {L:g}s: {acc:.0%}  (avg score {np.mean(scores):.1f})")

    # บันทึกผล
    C.RESULTS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = C.RESULTS_DIR / f"experiment_{stamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nบันทึกผล:", csv_path)

    # กราฟ accuracy vs SNR แยกตามความยาวคลิป
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = ["clean" if s is None else f"{s:g}" for s in snrs]
    for L in args.lengths:
        acc = [r["accuracy"] * 100 for r in rows if r["type"] == "in_db" and r["clip_s"] == L]
        ax.plot(labels, acc, marker="o", label=f"clip {L:g} s")
    ax.set(xlabel="SNR (dB)", ylabel="Accuracy (%)", ylim=(0, 105),
           title=f"Identification accuracy ({len(songs)} songs, {args.trials} trials each)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    png_path = csv_path.with_suffix(".png")
    fig.savefig(png_path, dpi=150)
    print("บันทึกกราฟ:", png_path)


if __name__ == "__main__":
    main()
