#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Giao diện bấm chuột cho hardsub_extract.py — không cần gõ lệnh."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "hardsub_extract.py")
TRANSLATE_SCRIPT = os.path.join(HERE, "translate_srtpx.py")

FULL_FRAME_ROI = "0,0,1.0,1.0"   # luôn OCR toàn bộ khung hình
ENGINES = {
    "PaddleOCR (chính xác nhất, khuyên dùng)": "paddleocr",
    "EasyOCR (dễ cài hơn, chậm hơn)": "easyocr",
    "Tesseract (cần cài riêng)": "tesseract",
}
LANG_CODES = {
    ("paddleocr", "Giản thể"): "ch", ("paddleocr", "Phồn thể"): "chinese_cht",
    ("easyocr", "Giản thể"): "ch_sim", ("easyocr", "Phồn thể"): "ch_tra",
    ("tesseract", "Giản thể"): "chi_sim", ("tesseract", "Phồn thể"): "chi_tra",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bóc hardsub tiếng Trung → .srtpx")
        self.geometry("760x640")
        self.proc = None
        self.q = queue.Queue()

        pad = dict(padx=10, pady=4)
        frm = ttk.Frame(self)
        frm.pack(fill="x", **pad)

        # 1. Video
        ttk.Label(frm, text="1. Chọn video:").grid(row=0, column=0, sticky="w")
        self.video = tk.StringVar()
        ttk.Entry(frm, textvariable=self.video).grid(row=1, column=0, sticky="ew")
        ttk.Button(frm, text="Chọn file...", command=self.pick_video).grid(row=1, column=1, padx=6)

        # 2. Output
        ttk.Label(frm, text="2. Lưu kết quả ở đâu (tự điền, có thể đổi):").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.out = tk.StringVar()
        ttk.Entry(frm, textvariable=self.out).grid(row=3, column=0, sticky="ew")
        ttk.Button(frm, text="Đổi...", command=self.pick_out).grid(row=3, column=1, padx=6)
        frm.columnconfigure(0, weight=1)

        # 3. Options
        opt = ttk.LabelFrame(self, text="3. Tuỳ chọn (không rành thì cứ để mặc định)")
        opt.pack(fill="x", **pad)
        self.engine = tk.StringVar(value=list(ENGINES)[0])
        self.script = tk.StringVar(value="Giản thể")
        self.fps = tk.StringVar(value="12")
        self.debug = tk.BooleanVar(value=True)
        self.translate = tk.BooleanVar(value=False)

        rows = [
            ("Công cụ đọc chữ:", ttk.Combobox(opt, textvariable=self.engine, values=list(ENGINES), state="readonly", width=44)),
            ("Loại chữ Hán:", ttk.Combobox(opt, textvariable=self.script, values=["Giản thể", "Phồn thể"], state="readonly", width=44)),
            ("Số khung hình/giây quét (nhỏ = nhanh):", ttk.Spinbox(opt, from_=1, to=60, textvariable=self.fps, width=10)),
        ]
        for i, (label, w) in enumerate(rows):
            ttk.Label(opt, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            w.grid(row=i, column=1, sticky="w", padx=8)
        ttk.Checkbutton(opt, text="Lưu ảnh kiểm tra (có kẻ khung đỏ quanh chữ) vào thư mục 'debug' cạnh file kết quả",
                        variable=self.debug).grid(row=len(rows), column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(opt, text="Dịch sang tiếng Việt sau khi bóc (cần file keys.txt cạnh chương trình, mỗi dòng 1 API key Gemini)",
                        variable=self.translate).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        # Buttons
        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        self.btn_run = ttk.Button(bar, text="▶  BẮT ĐẦU", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="■ Dừng", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.btn_open = ttk.Button(bar, text="Mở thư mục kết quả", command=self.open_folder, state="disabled")
        self.btn_open.pack(side="right")

        self.pb = ttk.Progressbar(self, mode="indeterminate")
        self.pb.pack(fill="x", **pad)

        self.log = tk.Text(self, height=14, wrap="word", state="disabled", bg="#111", fg="#ddd")
        self.log.pack(fill="both", expand=True, **pad)
        self.say("Sẵn sàng. Chọn video rồi bấm BẮT ĐẦU.\n")
        self.after(150, self.poll)

    # ---------- helpers ----------
    def say(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def pick_video(self):
        p = filedialog.askopenfilename(title="Chọn video",
                                       filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts"), ("Tất cả", "*.*")])
        if p:
            self.video.set(p)
            self.out.set(os.path.splitext(p)[0] + ".srtpx")

    def pick_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".srtpx", filetypes=[("srtpx", "*.srtpx")])
        if p:
            self.out.set(p)

    def open_folder(self):
        d = os.path.dirname(self.out.get()) or "."
        if sys.platform.startswith("win"):
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    # ---------- run ----------
    def start(self):
        video, out = self.video.get().strip(), self.out.get().strip()
        if not os.path.isfile(video):
            messagebox.showwarning("Thiếu video", "Bạn chưa chọn file video hợp lệ.")
            return
        if not out:
            out = os.path.splitext(video)[0] + ".srtpx"
            self.out.set(out)
        try:
            fps = float(self.fps.get())
        except ValueError:
            messagebox.showwarning("Sai số", "Số khung hình/giây phải là một con số.")
            return

        engine = ENGINES[self.engine.get()]
        cmd = [sys.executable, "-u", SCRIPT, video, "-o", out,
               "--engine", engine, "--lang", LANG_CODES[(engine, self.script.get())],
               "--fps", str(fps), "--roi", FULL_FRAME_ROI, "--no-skip"]
        if self.debug.get():
            cmd += ["--debug-dir", os.path.join(os.path.dirname(out) or ".", "debug"), "--debug-every", "20"]

        self.translate_cmd = None
        if self.translate.get():
            if not os.path.isfile(os.path.join(HERE, "keys.txt")) and not (
                    os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")):
                messagebox.showwarning("Thiếu API key", "Chưa có file keys.txt (mỗi dòng 1 key Gemini) cạnh chương trình.")
                return
            self.translate_cmd = [sys.executable, "-u", TRANSLATE_SCRIPT, out,
                                  "--keep-original", os.path.splitext(out)[0] + ".zh.srtpx"]

        self.say("\n=== Bắt đầu (lần đầu có thể mất vài phút để tải model OCR) ===\n")
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_open.configure(state="disabled")
        self.pb.start(12)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace",
                                     env=env, creationflags=flags)
        threading.Thread(target=self.reader, daemon=True).start()

    def reader(self):
        for line in self.proc.stdout:
            self.q.put(line)
        self.proc.wait()
        code = self.proc.returncode
        if code == 0 and self.translate_cmd:
            self.q.put("\n=== Đang dịch sang tiếng Việt ===\n")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            self.proc = subprocess.Popen(self.translate_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding="utf-8", errors="replace",
                                         env=env, creationflags=flags)
            for line in self.proc.stdout:
                self.q.put(line)
            self.proc.wait()
            code = self.proc.returncode
        self.q.put(("DONE", code))

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    self.finish(item[1])
                else:
                    self.say(item)
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def finish(self, code):
        self.pb.stop()
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if code == 0:
            self.say("\n✔ HOÀN TẤT. Mở thư mục kết quả để lấy file .srtpx.\n"
                     "   Nên mở vài ảnh trong thư mục 'debug' để kiểm tra khung đỏ có bám đúng chữ không.\n")
            self.btn_open.configure(state="normal")
            messagebox.showinfo("Xong", "Đã bóc xong phụ đề!")
        else:
            self.say(f"\n✘ Có lỗi hoặc đã dừng (mã {code}). Xem log phía trên.\n")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


if __name__ == "__main__":
    App().mainloop()
