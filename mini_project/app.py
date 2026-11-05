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
from matplotlib import font_manager, rcParams
from matplotlib.figure import Figure

import audio_input
import config as C
import fingerprint as fp
import hum
from database import FingerprintDB


# ให้ชื่อเพลงภาษาไทยในกราฟแสดงได้ ถ้าเครื่องมีฟอนต์ไทย
THAI_FONTS = ["Noto Sans Thai", "Loma", "Garuda", "Waree", "Tahoma", "Leelawadee UI"]
INSTALLED_FONTS = {f.name for f in font_manager.fontManager.ttflist}
rcParams["font.family"] = ["DejaVu Sans"] + [f for f in THAI_FONTS if f in INSTALLED_FONTS]


class MiniShazamApp:
    PLOT_HEIGHT = 1300             # ความสูงพื้นที่กราฟ (พิกเซล) เกินจอแล้วเลื่อนด้วย scrollbar
    RECORDED_TEXT = "🔊  เล่นเสียงที่อัด"
    SECTION_TEXT = "🔊  เล่นท่อนที่คล้ายในเพลง"
    STOP_TEXT = "⏹  หยุดเล่น"

    def __init__(self, root):
        self.root = root
        self.root.title("Mini Shazam — ESP32 + FPGA Audio Fingerprinting")
        # ไม่ให้หน้าต่างสูงเกินจอ ไม่อย่างนั้นปลาย scrollbar จะตกขอบจอ
        height = min(780, self.root.winfo_screenheight() - 90)
        self.root.geometry(f"1250x{height}+0+0")

        C.SONGS_DIR.mkdir(exist_ok=True)
        self.db = FingerprintDB()
        self.jobs = queue.Queue()      # ข้อความจาก worker thread → GUI
        self.busy = False
        self.last_audio = None         # (samples, fs) เสียงดิบล่าสุด ไว้เล่นซ้ำ
        self.player = None
        self.player_btn = None         # ปุ่มที่กำลังเล่นเสียงอยู่
        self.candidates = []           # [(ชื่อเพลง, คะแนน, ตำแหน่งในเพลงเป็นวินาที), ...]
        self.candidate_index = 0
        self.last_query = None
        self.section = None            # (samples, fs) ท่อนเพลงของ candidate ที่เลือก

        self._build_left_panel()
        self._build_plot_panel()
        self.refresh_song_list()
        self.refresh_ports()
        self.root.after(100, self._poll_jobs)

    # =================================================================
    # ส่วนหน้าตา
    # =================================================================
    def _build_left_panel(self):
        left = self._build_scrollable_left()

        # --- ฐานข้อมูลเพลง ---
        box = ttk.LabelFrame(left, text="ฐานข้อมูลเพลง", padding=8)
        box.pack(fill=tk.X)
        self.song_list = tk.Listbox(box, height=7, width=42)
        self.song_list.pack(fill=tk.X)
        song_xbar = ttk.Scrollbar(box, orient=tk.HORIZONTAL, command=self.song_list.xview)
        song_xbar.pack(fill=tk.X)
        self.song_list.configure(xscrollcommand=song_xbar.set)
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
        self.filter_noise = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="กรองเสียงแอร์ (ตอนเล่นเสียงและโหมดฮัม)",
                        variable=self.filter_noise).pack(anchor="w", pady=(6, 0))
        self.denoise = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="ลดเสียงพื้นหลัง (ทั้งตอนเล่นและตอนค้นหา)",
                        variable=self.denoise).pack(anchor="w", pady=(6, 0))

        # --- ปุ่มหลัก + ผลลัพธ์ ---
        self.listen_btn = ttk.Button(left, text="🎤  ฟังและค้นหาเพลง", command=self.listen)
        self.listen_btn.pack(fill=tk.X, ipady=6, pady=(4, 4))
        self.hum_btn = ttk.Button(left, text="🎵  ฮัมแล้วค้นหาเพลง", command=self.listen_hum)
        self.hum_btn.pack(fill=tk.X, ipady=6, pady=(0, 4))
        self.play_btn = ttk.Button(left, text=self.RECORDED_TEXT, command=self.toggle_playback,
                                   state="disabled")
        self.play_btn.pack(fill=tk.X, ipady=2, pady=(0, 4))
        self.progress = ttk.Progressbar(left, maximum=1.0)
        self.progress.pack(fill=tk.X)
        self.status = ttk.Label(left, text="พร้อม", foreground="gray")
        self.status.pack(anchor="w", pady=(2, 8))

        box = ttk.LabelFrame(left, text="เทียบกับเพลง candidate", padding=8)
        box.pack(fill=tk.X, pady=(0, 8))
        self.candidate_box = ttk.Combobox(box, state="disabled")
        self.candidate_box.pack(fill=tk.X)
        self.candidate_box.bind("<<ComboboxSelected>>", self.on_candidate_selected)
        self.section_btn = ttk.Button(box, text=self.SECTION_TEXT, command=self.toggle_section,
                                      state="disabled")
        self.section_btn.pack(fill=tk.X, pady=(6, 0))

        box = ttk.LabelFrame(left, text="ผลลัพธ์", padding=8)
        box.pack(fill=tk.BOTH, expand=True)
        self.result_title = ttk.Label(box, text="—", font=("TkDefaultFont", 16, "bold"),
                                      wraplength=390)
        self.result_title.pack(anchor="w")
        self.result_detail = ttk.Label(box, text="", justify=tk.LEFT, wraplength=390)
        self.result_detail.pack(anchor="w", pady=(6, 0))

    def _build_scrollable_left(self):
        """แผงซ้ายอยู่ใน Canvas พร้อม scrollbar แนวตั้ง เผื่อเนื้อหายาวเกินจอ"""
        outer = ttk.Frame(self.root)
        outer.pack(side=tk.LEFT, fill=tk.Y)
        bg = ttk.Style().lookup("TFrame", "background")
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background=bg)
        bar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        left = ttk.Frame(canvas, padding=10)
        canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all"), width=left.winfo_reqwidth()))
        self.left_canvas = canvas

        def on_wheel(event):
            # ล้อเมาส์เลื่อนเฉพาะแผงซ้าย และไม่แย่งการเลื่อนของรายการเพลง
            if not str(event.widget).startswith(str(left)) or event.widget is self.song_list:
                return
            if canvas.yview() == (0.0, 1.0):
                return
            up = event.num == 4 or getattr(event, "delta", 0) > 0
            canvas.yview_scroll(-1 if up else 1, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, on_wheel, add="+")
        return left

    def _build_plot_panel(self):
        outer = ttk.Frame(self.root)
        outer.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        view = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=view.yview)
        view.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.plot_view = view

        self.fig = Figure(figsize=(8, self.PLOT_HEIGHT / 100), dpi=100)
        self.ax_wave = self.fig.add_subplot(5, 1, 1)
        self.ax_spec = self.fig.add_subplot(5, 1, 2)
        self.ax_hist = self.fig.add_subplot(5, 1, 3)
        self.ax_cand_wave = self.fig.add_subplot(5, 1, 4)
        self.ax_cand_spec = self.fig.add_subplot(5, 1, 5)
        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=view)
        self.canvas.mpl_connect("resize_event", lambda e: self.fig.tight_layout())
        window = view.create_window((0, 0), window=self.canvas.get_tk_widget(), anchor="nw")

        def on_resize(event):
            view.itemconfigure(window, width=event.width, height=self.PLOT_HEIGHT)
            view.configure(scrollregion=(0, 0, event.width, self.PLOT_HEIGHT))

        def on_wheel(event):
            if not str(event.widget).startswith(str(view)):
                return
            up = event.num == 4 or getattr(event, "delta", 0) > 0
            view.yview_scroll(-1 if up else 1, "units")

        view.bind("<Configure>", on_resize)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, on_wheel, add="+")

    # =================================================================
    # ฐานข้อมูลเพลง
    # =================================================================
    def refresh_song_list(self):
        songs = self.db.list_songs()
        self.song_list.delete(0, tk.END)
        stems = {p.stem for p in C.SONGS_DIR.iterdir() if p.suffix.lower() in C.AUDIO_EXTENSIONS}
        for name, duration, n in songs:
            missing = "" if name in stems else ", ไม่มีไฟล์เสียง"
            self.song_list.insert(tk.END, f"{name}   ({duration/60:.1f} นาที, {n:,} hash{missing})")
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

    def listen_hum(self):
        source = self.source.get()
        test_file = None
        if source == "file":
            test_file = filedialog.askopenfilename(
                title="เลือกไฟล์เสียงฮัม", initialdir=C.SONGS_DIR)
            if not test_file:
                return
        self._run_in_background(self._hum_job, source, test_file)

    def _hum_job(self, source, test_file):
        seconds = int(self.seconds.get())
        self.jobs.put(("status", "กำลังฟังเสียงฮัม..."))
        if source == "serial":
            samples, fs = audio_input.record_serial(
                seconds, self.port.get(), C.BAUD_RATE, lambda p: self.jobs.put(("progress", p)))
        else:
            samples, fs, _ = audio_input.load_test_clip(test_file, seconds, start=0.0)
        self.jobs.put(("recorded", (samples, fs)))
        self.jobs.put(("status", "กำลังเทียบทำนอง..."))
        query = audio_input.filter_noise(samples, fs) if self.filter_noise.get() else samples
        self.jobs.put(("hum_result", (samples, fs, hum.match(query, fs))))
        self.jobs.put(("status", "เสร็จ"))

    def _show_hum_result(self, samples, fs, result):
        self._stop_player()
        self.candidates = []
        self.section = None
        self.section_btn.state(["disabled"])
        self.candidate_box.set("")
        self.candidate_box.config(state="disabled")
        if result["confident"]:
            self.result_title.config(text=f"🎵 {result['song']}", foreground="darkgreen")
        else:
            self.result_title.config(text="ไม่แน่ใจว่าเป็นเพลงไหน", foreground="firebrick")
        ranking = "\n".join(f"  {i+1}. {n}  ({sc:.0f})" for i, (n, sc) in enumerate(result["ranking"]))
        detail = f"โหมดฮัม: จับเสียงได้ {result['voiced_sec']:.1f} วินาที\n"
        if result["reason"]:
            detail += result["reason"]
        else:
            detail += (f"ความคล้าย = {result['similarity']:.0f} (เกณฑ์ ≥ {C.HUM_MIN_SIMILARITY}),  "
                       f"ห่างอันดับ 2 = {result['margin']:.0f} (เกณฑ์ ≥ {C.HUM_MIN_MARGIN})\n"
                       f"อันดับความคล้าย:\n{ranking}")
        self.result_detail.config(text=detail)
        self._draw_hum_plots(samples, fs, result)

    def _draw_hum_plots(self, samples, fs, result):
        for ax in (self.ax_wave, self.ax_spec, self.ax_hist, self.ax_cand_wave, self.ax_cand_spec):
            ax.clear()
        x = np.asarray(samples, dtype=np.float64)
        self.ax_wave.plot(np.arange(len(x)) / fs, x - x.mean(), lw=0.5)
        self.ax_wave.set(title="Recorded hum", xlabel="Time (s)", ylabel="ADC counts")
        self.ax_spec.plot(result["t"], result["midi"], lw=1.2, color="tab:green")
        self.ax_spec.set(title="Detected pitch", xlabel="Time (s)", ylabel="Pitch (MIDI note)")
        if len(result["reference"]):
            step = np.arange(len(result["query"])) * C.HUM_STEP
            self.ax_hist.plot(step, result["reference"], lw=2, color="darkorange", label=f"melody: {result['song']}")
            self.ax_hist.plot(step, result["query"], lw=1, color="tab:green", label="hum (key shifted)")
            self.ax_hist.legend(fontsize=8)
        self.ax_hist.set(title="Hum aligned to best melody", xlabel="Aligned time (s)", ylabel="Pitch (MIDI note)")
        self.fig.tight_layout()
        self.canvas.draw()

    def toggle_playback(self):
        """กดครั้งแรกเล่นเสียงที่อัดล่าสุด กดอีกครั้งหยุด (ใช้เสียงตามสถานะช่องลดเสียงตอนกด)"""
        def audio():
            samples, fs = self.last_audio
            if self.filter_noise.get():
                samples = audio_input.filter_noise(samples, fs)
            if self.denoise.get():
                samples = audio_input.reduce_noise(samples, fs)
            return samples, fs
        self._toggle_player(self.play_btn, audio)

    def toggle_section(self):
        """เล่นท่อนเพลงของ candidate ที่เลือก ช่วงเดียวกับคลิปที่อัด"""
        self._toggle_player(self.section_btn, lambda: self.section)

    def _toggle_player(self, button, get_audio):
        """กดปุ่มเดิมระหว่างเล่น = หยุด, กดอีกปุ่ม = สลับไปเล่นเสียงของปุ่มนั้นทันที"""
        was_playing = self.player_btn
        self._stop_player()
        if was_playing is button:
            return
        try:
            self.player = audio_input.play_audio(*get_audio())
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        if self.player is not None:
            self.player_btn = button
            button.config(text=self.STOP_TEXT)

    def _stop_player(self):
        if self.player is not None:
            audio_input.stop_audio(self.player)
        self.player = None
        if self.player_btn is not None:
            self.player_btn.config(text=self.RECORDED_TEXT if self.player_btn is self.play_btn
                                   else self.SECTION_TEXT)
            self.player_btn = None

    def on_candidate_selected(self, event=None):
        index = self.candidate_box.current()
        if index == self.candidate_index:
            return
        if self.busy:
            self.candidate_box.current(self.candidate_index)
            self.status.config(text="รองานเดิมจบก่อน แล้วค่อยเลือก candidate")
            return
        self._run_in_background(self._candidate_job, index, self.candidates, self.last_query)

    def _candidate_job(self, index, candidates, query):
        """โหลดท่อนเพลงของ candidate แล้วส่งกลับไปวาดกราฟ"""
        name, score, offset = candidates[index]
        self.jobs.put(("status", f"กำลังโหลดท่อนเพลง: {name}"))
        seconds = len(query["x"]) / C.FS
        try:
            samples, fs = audio_input.load_song_section(audio_input.find_song_file(name), offset, seconds)
        except FileNotFoundError as e:
            self.jobs.put(("candidate", (index, query, None, None)))
            self.jobs.put(("status", str(e)))
            return
        self.jobs.put(("candidate", (index, query, (samples, fs), fp.fingerprint(samples, fs))))
        self.jobs.put(("status", "เสร็จ"))

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
        self.jobs.put(("recorded", (samples, fs)))

        # 2) fingerprint + ค้นหา
        self.jobs.put(("status", "กำลังค้นหา..."))
        t0 = time.time()
        if self.denoise.get():
            samples = audio_input.reduce_noise(samples, fs)
            extra += "\n(ลดเสียงพื้นหลังก่อนค้นหา)"
        query = fp.fingerprint(samples, fs)
        result = self.db.match(query["hashes"])
        result["elapsed"] = time.time() - t0
        result["extra"] = extra
        self.jobs.put(("result", (query, result)))
        if result["candidates"]:
            self._candidate_job(0, result["candidates"], query)

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
        self._stop_player()
        self.last_query = query
        self.candidates = result["candidates"]
        self.candidate_index = 0
        self.section = None
        self.section_btn.state(["disabled"])
        self.candidate_box["values"] = [f"{i+1}. {n}  (คะแนน {sc}, ตำแหน่ง {off:.1f} s)"
                                        for i, (n, sc, off) in enumerate(self.candidates)]
        if self.candidates:
            self.candidate_box.config(state="readonly")
            self.candidate_box.current(0)
        else:
            self.candidate_box.set("")
            self.candidate_box.config(state="disabled")
        self._draw_plots(query, result)

    def _show_candidate(self, index, query, section, cand):
        """วาดท่อนเพลงของ candidate ใต้กราฟเดิม ใช้แกนเวลาเดียวกับคลิปที่อัด"""
        self._stop_player()
        self.candidate_index = index
        self.candidate_box.current(index)
        self.section = section
        self.section_btn.state(["!disabled"] if section else ["disabled"])
        for ax in (self.ax_cand_wave, self.ax_cand_spec):
            ax.clear()
        name, score, offset = self.candidates[index]
        name = name if len(name) <= 40 else name[:39] + "…"
        seconds = len(query["x"]) / C.FS
        if cand is None:
            self.ax_cand_wave.set_title(f"Candidate #{index+1}: {name} — file not found in songs/")
        else:
            self.ax_cand_wave.plot(np.arange(len(cand["x"])) / C.FS, cand["x"], lw=0.5, color="darkorange")
            self.ax_cand_wave.set(
                title=f"Candidate #{index+1}: {name} — song {offset:.1f}–{offset + seconds:.1f} s (score {score})",
                xlabel="Time in clip (s)", ylabel="Amplitude", xlim=(0, seconds))
            if cand["S_db"].size:
                self.ax_cand_spec.pcolormesh(cand["t"], cand["f"], cand["S_db"], shading="auto", cmap="magma")
                self.ax_cand_spec.scatter(cand["t"][cand["peak_t"]], cand["f"][cand["peak_f"]],
                                          s=8, c="cyan", label="candidate peaks")
                self.ax_cand_spec.scatter(query["t"][query["peak_t"]], query["f"][query["peak_f"]],
                                          s=10, c="lime", marker="x", linewidths=0.6, label="recorded peaks")
                self.ax_cand_spec.axhspan(C.FREQ_MIN, C.FREQ_MAX, fill=False, ls="--", ec="white", lw=0.6)
                self.ax_cand_spec.set_ylim(0, C.FS / 2)
                self.ax_cand_spec.legend(loc="upper right", fontsize=8)
            self.ax_cand_spec.set(title="Candidate spectrogram vs recorded peaks",
                                  xlabel="Time in clip (s)", ylabel="Frequency (Hz)", xlim=(0, seconds))
        self.fig.tight_layout()
        self.canvas.draw()

    def _draw_plots(self, q, result):
        for ax in (self.ax_wave, self.ax_spec, self.ax_hist, self.ax_cand_wave, self.ax_cand_spec):
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
        self.hum_btn.state(["disabled"])
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
                elif kind == "recorded":
                    self.last_audio = data
                    self.play_btn.state(["!disabled"])
                elif kind == "result":
                    self._show_result(*data)
                    self.status.config(text="เสร็จ")
                elif kind == "candidate":
                    self._show_candidate(*data)
                elif kind == "hum_result":
                    self._show_hum_result(*data)
                elif kind == "error":
                    self.status.config(text="เกิดข้อผิดพลาด")
                    messagebox.showerror("Error", data)
                elif kind == "done":
                    self.busy = False
                    self.listen_btn.state(["!disabled"])
                    self.hum_btn.state(["!disabled"])
        except queue.Empty:
            pass
        if self.player is not None and self.player.poll() is not None:
            self._stop_player()
        self.root.after(100, self._poll_jobs)


if __name__ == "__main__":
    root = tk.Tk()
    MiniShazamApp(root)
    root.mainloop()
