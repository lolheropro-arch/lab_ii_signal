"""
database.py — เก็บ hash ของเพลง และค้นหาเพลงที่ตรงกัน
=====================================================================
ใช้ SQLite (มากับ Python อยู่แล้ว ไม่ต้องติดตั้งเพิ่ม) เก็บเป็นไฟล์ fingerprints.db

ตาราง songs        : id, ชื่อเพลง, ความยาว, จำนวน hash
ตาราง fingerprints : hash, song_id, เฟรมของจุดยึด   (มี index ที่ hash ให้ค้นเร็ว)

หลักการจับคู่ (match)
    ทุก hash ที่ตรงกัน คำนวณ offset = เวลาในเพลง − เวลาในคลิปที่อัด
    ถ้าเป็นเพลงที่ถูก offset ส่วนใหญ่จะ "เท่ากัน" → histogram มีแท่งสูงโด่ง
    ถ้าเป็นเพลงอื่น offset จะกระจายมั่ว ๆ ไม่มีแท่งสูง
"""
import sqlite3
import threading
from collections import defaultdict
from pathlib import Path

import numpy as np

import config as C
import fingerprint as fp


class FingerprintDB:
    def __init__(self, path=C.DB_PATH):
        self.lock = threading.Lock()          # GUI เรียกจากหลาย thread
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS songs (
                id        INTEGER PRIMARY KEY,
                name      TEXT UNIQUE,
                duration  REAL,
                n_hashes  INTEGER
            );
            CREATE TABLE IF NOT EXISTS fingerprints (
                hash     INTEGER,
                song_id  INTEGER,
                t        INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_hash ON fingerprints(hash);
        """)

    # ----------------------------- จัดการเพลง -----------------------------
    def list_songs(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT name, duration, n_hashes FROM songs ORDER BY name").fetchall()
        return rows

    def has_song(self, name):
        with self.lock:
            return self.conn.execute(
                "SELECT 1 FROM songs WHERE name=?", (name,)).fetchone() is not None

    def add_file(self, path):
        """อ่านไฟล์เพลง → fingerprint → บันทึก  (ข้ามถ้ามีชื่อนี้แล้ว) คืน True ถ้าเพิ่มใหม่"""
        path = Path(path)
        name = path.stem
        if self.has_song(name):
            return False
        y = fp.load_audio_file(path)
        result = fp.fingerprint(y, C.FS)
        self._insert(name, len(y) / C.FS, result["hashes"])
        return True

    def _insert(self, name, duration, hashes):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO songs(name, duration, n_hashes) VALUES (?,?,?)",
                (name, duration, len(hashes)))
            song_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO fingerprints(hash, song_id, t) VALUES (?,?,?)",
                [(h, song_id, t) for h, t in hashes])
            self.conn.commit()

    def remove_song(self, name):
        with self.lock:
            row = self.conn.execute("SELECT id FROM songs WHERE name=?", (name,)).fetchone()
            if row:
                self.conn.execute("DELETE FROM fingerprints WHERE song_id=?", row)
                self.conn.execute("DELETE FROM songs WHERE id=?", row)
                self.conn.commit()

    def clear(self):
        with self.lock:
            self.conn.execute("DELETE FROM fingerprints")
            self.conn.execute("DELETE FROM songs")
            self.conn.commit()
            self.conn.execute("VACUUM")

    # ----------------------------- ค้นหาเพลง -----------------------------
    def match(self, query_hashes, top_n=5):
        """
        คืน dict:
            song, score, offset_sec, confident  → คำตอบ
            runner_up, ratio                    → คะแนนคู่แข่ง และ score / runner_up
            ranking                             → [(ชื่อเพลง, คะแนน), ...] อันดับต้น ๆ
            offsets                             → offset ทั้งหมดของเพลงอันดับ 1 (ไว้วาด histogram)
        """
        empty = {"song": None, "score": 0, "runner_up": 0, "ratio": 0.0,
                 "offset_sec": 0.0, "confident": False,
                 "ranking": [], "offsets": np.array([]), "n_query_hashes": len(query_hashes)}
        if not query_hashes:
            return empty

        # hash → รายการเฟรมในคลิปที่อัด (hash เดียวกันอาจเกิดหลายครั้ง)
        query_map = defaultdict(list)
        for h, t in query_hashes:
            query_map[h].append(t)
        keys = list(query_map)

        # ดึง hash ที่ตรงกันจากฐานข้อมูล (แบ่งเป็นชุดเพราะ SQLite จำกัดจำนวนตัวแปร)
        rows = []
        with self.lock:
            for i in range(0, len(keys), 900):
                chunk = keys[i:i + 900]
                q = "SELECT hash, song_id, t FROM fingerprints WHERE hash IN (%s)" % ",".join("?" * len(chunk))
                rows.extend(self.conn.execute(q, chunk).fetchall())
            names = dict(self.conn.execute("SELECT id, name FROM songs").fetchall())

        # รวบรวม offset ของแต่ละเพลง
        offsets_by_song = defaultdict(list)
        for h, song_id, t_db in rows:
            for t_q in query_map[h]:
                offsets_by_song[song_id].append(t_db - t_q)

        # ให้คะแนน = จำนวน offset ที่ตรงกันมากที่สุด (ยอมคลาด ±1 เฟรม)
        scores = []
        for song_id, offs in offsets_by_song.items():
            offs = np.asarray(offs)
            counts = np.bincount(offs - offs.min())
            smoothed = np.convolve(counts, [1, 1, 1], mode="same")
            best = int(np.argmax(smoothed))
            scores.append((int(smoothed[best]), song_id, best + offs.min(), offs))
        if not scores:
            return empty
        scores.sort(key=lambda s: s[0], reverse=True)

        score, song_id, best_offset, offs = scores[0]

        # คะแนน "คู่แข่ง" = max(คะแนนเพลงอันดับ 2, ยอดสูงสุดอื่นใน histogram ของเพลงอันดับ 1)
        # เพลงที่ไม่มีในฐานข้อมูลจะได้คะแนนพอ ๆ กับคู่แข่ง → ratio ใกล้ 1 → ตอบ "ไม่พบ"
        runner_up = scores[1][0] if len(scores) > 1 else 0
        counts = np.convolve(np.bincount(offs - offs.min()), [1, 1, 1], mode="same")
        b = best_offset - offs.min()
        counts[max(b - 3, 0):b + 4] = 0
        runner_up = max(runner_up, int(counts.max()) if counts.size else 0)
        ratio = score / max(runner_up, 1)

        return {
            "song": names.get(song_id, "?"),
            "score": score,
            "runner_up": runner_up,
            "ratio": ratio,
            "offset_sec": fp.frames_to_seconds(best_offset),
            "confident": score >= C.MIN_MATCHES and ratio >= C.MIN_RATIO,
            "ranking": [(names.get(s[1], "?"), s[0]) for s in scores[:top_n]],
            "offsets": offs,
            "n_query_hashes": len(query_hashes),
        }
