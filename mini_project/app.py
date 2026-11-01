"""
app.py — หน้าต่างโปรแกรม (GUI)   ▶ รันด้วย:  python app.py
=====================================================================
ซ้าย : ฐานข้อมูลเพลง / เลือกแหล่งเสียง / ปุ่มฟังและค้นหา / ผลลัพธ์
ขวา  : กราฟ 3 ช่อง
        1. Waveform ของเสียงที่อัดได้
        2. Spectrogram + จุดยอด (constellation map)
        3. Histogram ของ offset → แท่งสูงโด่ง = เจอเพลง

งานที่ใช้เวลานาน (อัดเสียง, อ่านไฟล์เพลง) ทำใน thread แยก
แล้วส่งผลกลับผ่าน queue เพื่อไม่ให้หน้าต่างค้าง
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import audio_input
import config as C
import fingerprint as fp
from database import FingerprintDB


class MiniShazamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini Shazam — ESP32 + FPGA Audio Fingerprinting")
        self.root.geometry("1250x780")

        C.SONGS_DIR.mkdir(exist_ok=True)
        self.db = FingerprintDB()
        self.jobs = queue.Queue()      # ข้อความจาก worker thread → GUI
        self.busy = False

        self._build_left_panel()
        self._build_plot_panel()
        self.refresh_song_list()
        self.refresh_ports()
        self.root.after(100, self._poll_jobs)

    # =================================================================
    # ส่วนหน้าตา
    # =================================================================
    def _build_left_panel(self):
        left = ttk.Frame(self.root, padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y)

        # --- ฐานข้อมูลเพลง ---
        box = ttk.LabelFrame(left, text="ฐานข้อมูลเพลง", padding=8)
        box.pack(fill=tk.X)
        self.song_list = tk.Listbox(box, height=7, width=42)
        self.song_list.pack(fill=tk.X)
        self.db_info = ttk.Label(box, text="")
        self.db_info.pack(anchor="w", pady=(4, 4))
        ttk.Button(box, text="เพิ่มเพลงทั้งหมดในโฟลเดอร์ songs/",
                   command=self.add_songs_folder).pack(fill=tk.X)
        ttk.Button(box, text="เพิ่มไฟล์เพลง...",
                   command=self.add_song_files).pack(fill=tk.X, pady=2)
        row = ttk.Frame(box)
        row.pack(fill=tk.X)
        ttk.Button(row, text="ลบเพลงที่เลือก",
                   command=self.remove_selected).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(row, text="ล้างฐานข้อมูล",
                   command=self.clear_db).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # --- แหล่งเสียง ---
        box = ttk.LabelFrame(left, text="แหล่งเสียง", padding=8)
        box.pack(fill=tk.X, pady=8)
        self.source = tk.StringVar(value=C.DEFAULT_SOURCE)
        for value, label in [("serial", "ESP32 (USB-Serial)"),
                             ("file", "ไฟล์ทดสอบ (สุ่มช่วงจากไฟล์เพลง)")]:
            ttk.Radiobutton(box, text=label, value=value,
                            variable=self.source).pack(anchor="w")

        row = ttk.Frame(box)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="พอร์ต").pack(side=tk.LEFT)
        self.port = ttk.Combobox(row, width=18)
        self.port.pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="↻", width=3, command=self.refresh_ports).pack(side=tk.LEFT)

        row = ttk.Frame(box)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="ฟังนาน (วินาที)").pack(side=tk.LEFT)
        self.seconds = tk.IntVar(value=C.RECORD_SECONDS)
        ttk.Spinbox(row, from_=2, to=30, width=5,
                    textvariable=self.seconds).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="Noise SNR (dB)").pack(side=tk.LEFT, padx=(8, 0))
        self.snr = tk.StringVar(value="")       # ว่าง = ไม่ใส่ noise (ใช้กับโหมดไฟล์เท่านั้น)
        ttk.Entry(row, width=5, textvariable=self.snr).pack(side=tk.LEFT, padx=4)

        # --- ปุ่มหลัก + ผลลัพธ์ ---
        self.listen_btn = ttk.Button(left, text="🎤  ฟังและค้นหาเพลง", command=self.listen)
        self.listen_btn.pack(fill=tk.X, ipady=6, pady=(4, 4))
        self.progress = ttk.Progressbar(left, maximum=1.0)
        self.progress.pack(fill=tk.X)
        self.status = ttk.Label(left, text="พร้อม", foreground="gray")
        self.status.pack(anchor="w", pady=(2, 8))

        box = ttk.LabelFrame(left, text="ผลลัพธ์", padding=8)
        box.pack(fill=tk.BOTH, expand=True)
        self.result_title = ttk.Label(box, text="—", font=("TkDefaultFont", 16, "bold"),
                                      wraplength=390)
        self.result_title.pack(anchor="w")
        self.result_detail = ttk.Label(box, text="", justify=tk.LEFT, wraplength=390)
        self.result_detail.pack(anchor="w", pady=(6, 0))

    def _build_plot_panel(self):
        self.fig = Figure(figsize=(8, 7), dpi=100)
        self.ax_wave = self.fig.add_subplot(3, 1, 1)
        self.ax_spec = self.fig.add_subplot(3, 1, 2)
        self.ax_hist = self.fig.add_subplot(3, 1, 3)
        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    # =================================================================
    # ฐานข้อมูลเพลง
    # =================================================================
    def refresh_song_list(self):
        songs = self.db.list_songs()
        self.song_list.delete(0, tk.END)
        for name, duration, n in songs:
            self.song_list.insert(tk.END, f"{name}   ({duration/60:.1f} นาที, {n:,} hash)")
        total = sum(s[2] for s in songs)
        self.db_info.config(text=f"{len(songs)} เพลง, {total:,} hash")

    def add_songs_folder(self):
        files = sorted(p for p in C.SONGS_DIR.iterdir()
                       if p.suffix.lower() in C.AUDIO_EXTENSIONS)
        if not files:
            messagebox.showinfo("ไม่พบไฟล์", f"ยังไม่มีไฟล์เพลงใน\n{C.SONGS_DIR}")
            return
        self._run_in_background(self._add_files_job, files)

    def add_song_files(self):
        paths = filedialog.askopenfilenames(
            title="เลือกไฟล์เพลง",
            filetypes=[("Audio", " ".join("*" + e for e in C.AUDIO_EXTENSIONS))])
        if paths:
            self._run_in_background(self._add_files_job, list(paths))

    def _add_files_job(self, files):
        added = 0
        for i, path in enumerate(files):
            self.jobs.put(("status", f"กำลังเพิ่ม: {getattr(path, 'name', path)}"))
            self.jobs.put(("progress", i / len(files)))
            try:
                added += self.db.add_file(path)
            except Exception as e:
                self.jobs.put(("error", f"อ่านไฟล์ไม่ได้: {path}\n{e}"))
        self.jobs.put(("progress", 1.0))
        self.jobs.put(("songs_changed", f"เพิ่มเพลงใหม่ {added} เพลง (ข้ามที่มีอยู่แล้ว)"))

    def remove_selected(self):
        sel = self.song_list.curselection()
        if sel:
            name = self.song_list.get(sel[0]).rsplit("   (", 1)[0]
            self.db.remove_song(name)
            self.refresh_song_list()

    def clear_db(self):
        if messagebox.askyesno("ยืนยัน", "ลบเพลงทั้งหมดออกจากฐานข้อมูล?"):
            self.db.clear()
            self.refresh_song_list()

    def refresh_ports(self):
        ports = audio_input.list_serial_ports()
        self.port["values"] = ports
        if not self.port.get():
            self.port.set(ports[0] if ports else C.SERIAL_PORT)

    # =================================================================
    # ฟังและค้นหา
    # =================================================================
    def listen(self):
        source = self.source.get()
        test_file = None
        if source == "file":
            test_file = filedialog.askopenfilename(
                title="เลือกไฟล์ที่จะใช้เป็นเสียงทดสอบ", initialdir=C.SONGS_DIR)
            if not test_file:
                return
        self._run_in_background(self._listen_job, source, test_file)

    def _listen_job(self, source, test_file):
        seconds = int(self.seconds.get())
        progress = lambda p: self.jobs.put(("progress", p))

        # 1) รับเสียง
        self.jobs.put(("status", "กำลังฟัง..."))
        extra = ""
        if source == "serial":
            samples, fs = audio_input.record_serial(seconds, self.port.get(), C.BAUD_RATE, progress)
        else:
            snr = float(self.snr.get()) if self.snr.get().strip() else None
            samples, fs, start = audio_input.load_test_clip(test_file, seconds, snr_db=snr)
            extra = f"\n(เฉลย: ตัดจากวินาทีที่ {start:.1f}" + (f", SNR {snr:g} dB)" if snr is not None else ")")

        # 2) fingerprint + ค้นหา
        self.jobs.put(("status", "กำลังค้นหา..."))
        t0 = time.time()
        query = fp.fingerprint(samples, fs)
        result = self.db.match(query["hashes"])
        result["elapsed"] = time.time() - t0
        result["extra"] = extra
        self.jobs.put(("result", (query, result)))

    def _show_result(self, query, result):
        if result["confident"]:
            m, s = divmod(result["offset_sec"], 60)
            self.result_title.config(text=f"🎵 {result['song']}", foreground="darkgreen")
            head = f"ตำแหน่งในเพลง ≈ {int(m)}:{s:04.1f}\n"
        else:
            self.result_title.config(text="ไม่พบเพลงในฐานข้อมูล", foreground="firebrick")
            head = ""
        ranking = "\n".join(f"  {i+1}. {n}  ({sc})" for i, (n, sc) in enumerate(result["ranking"][:3]))
        self.result_detail.config(text=(
            f"{head}คะแนน = {result['score']} (เกณฑ์ ≥ {C.MIN_MATCHES}),  "
            f"ห่างคู่แข่ง {result['ratio']:.1f} เท่า (เกณฑ์ ≥ {C.MIN_RATIO:g})\n"
            f"hash ในคลิป = {result['n_query_hashes']:,},  "
            f"เวลาค้นหา = {result['elapsed']*1000:.0f} ms{result['extra']}\n"
            f"อันดับคะแนน:\n{ranking or '  -'}"))
        self._draw_plots(query, result)

    def _draw_plots(self, q, result):
        for ax in (self.ax_wave, self.ax_spec, self.ax_hist):
            ax.clear()

        t = np.arange(len(q["x"])) / C.FS
        self.ax_wave.plot(t, q["x"], lw=0.5)
        self.ax_wave.set(title="Recorded waveform (after DC removal & resample)",
                         xlabel="Time (s)", ylabel="Amplitude")

        if q["S_db"].size:
            self.ax_spec.pcolormesh(q["t"], q["f"], q["S_db"], shading="auto", cmap="magma")
            self.ax_spec.scatter(q["t"][q["peak_t"]], q["f"][q["peak_f"]],
                                 s=8, c="cyan", label="peaks")
            self.ax_spec.axhspan(C.FREQ_MIN, C.FREQ_MAX, fill=False, ls="--", ec="white", lw=0.6)
            self.ax_spec.set_ylim(0, C.FS / 2)
            self.ax_spec.legend(loc="upper right", fontsize=8)
        self.ax_spec.set(title=f"Spectrogram + constellation ({len(q['peak_t'])} peaks)",
                         xlabel="Time (s)", ylabel="Frequency (Hz)")

        offs = result["offsets"]
        if len(offs):
            secs = fp.frames_to_seconds(np.asarray(offs))
            self.ax_hist.hist(secs, bins=min(200, max(10, len(np.unique(offs)))), color="steelblue")
            if result["confident"]:
                self.ax_hist.axvline(result["offset_sec"], color="red", ls="--",
                                     label=f"match @ {result['offset_sec']:.1f}s")
                self.ax_hist.legend(fontsize=8)
        self.ax_hist.set(title=f"Offset histogram — top candidate: {result['song'] or '-'}",
                         xlabel="Offset = t_song − t_clip (s)", ylabel="Matching hashes")
        self.fig.tight_layout()
        self.canvas.draw()

    # =================================================================
    # ระบบ thread / queue
    # =================================================================
    def _run_in_background(self, func, *args):
        if self.busy:
            return
        self.busy = True
        self.listen_btn.state(["disabled"])
        self.progress["value"] = 0

        def worker():
            try:
                func(*args)
            except Exception as e:
                self.jobs.put(("error", str(e)))
            finally:
                self.jobs.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        try:
            while True:
                kind, data = self.jobs.get_nowait()
                if kind == "status":
                    self.status.config(text=data)
                elif kind == "progress":
                    self.progress["value"] = data
                elif kind == "songs_changed":
                    self.refresh_song_list()
                    self.status.config(text=data)
                elif kind == "result":
                    self._show_result(*data)
                    self.status.config(text="เสร็จ")
                elif kind == "error":
                    self.status.config(text="เกิดข้อผิดพลาด")
                    messagebox.showerror("Error", data)
                elif kind == "done":
                    self.busy = False
                    self.listen_btn.state(["!disabled"])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_jobs)


if __name__ == "__main__":
    root = tk.Tk()
    MiniShazamApp(root)
    root.mainloop()
