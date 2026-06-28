#!/usr/bin/env python3
"""
video2sheet_gui.py - Tiny desktop GUI for video2sheet.py.

Pick a video, set the grid/options, click Generate to preview the sprite sheet, then Save.
Reuses the pipeline from video2sheet.py (no duplicated logic).

Run:      python video2sheet_gui.py
Install:  pip install -r requirements.txt   (pillow, numpy, scipy; Tkinter ships with Python)
          + ffmpeg on PATH (Windows: winget install Gyan.FFmpeg)
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video2sheet as v2s  # noqa: E402  (same directory)

PREVIEW_W, PREVIEW_H = 780, 360


def _checkerboard(Image, size, square=16):
    from itertools import product
    w, h = size
    board = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    px = board.load()
    for y, x in product(range(h), range(w)):
        if ((x // square) + (y // square)) % 2 == 0:
            px[x, y] = (205, 205, 205, 255)
    return board


class App:
    def __init__(self, root):
        self.root = root
        root.title("Video → Sprite Sheet")
        root.minsize(840, 560)

        from PIL import Image, ImageTk
        self.Image, self.ImageTk = Image, ImageTk

        self.video_path = None
        self.sheet = None          # last generated PIL image
        self._tkimg = None         # keep a ref so Tk doesn't GC it

        self._build_ui()
        if not v2s.find_tool("ffmpeg"):
            self.status.set("ffmpeg not found — install it: winget install Gyan.FFmpeg")

    # ---- UI ---------------------------------------------------------------
    def _build_ui(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="Open Video…", command=self.open_video).pack(side="left")
        self.name_var = tk.StringVar(value="No video loaded")
        ttk.Label(bar, textvariable=self.name_var).pack(side="left", padx=12)

        ctrl = ttk.Frame(self.root, padding=(8, 0))
        ctrl.pack(side="top", fill="x")

        self.columns = tk.IntVar(value=5)
        self.rows = tk.IntVar(value=2)
        self.cell = tk.IntVar(value=256)
        self.subject_h = tk.IntVar(value=228)
        self.margin = tk.IntVar(value=8)
        self.trim = tk.DoubleVar(value=2.0)
        self._spin(ctrl, "Columns", self.columns, 1, 20, 0, 0)
        self._spin(ctrl, "Rows", self.rows, 1, 20, 0, 2)
        self._spin(ctrl, "Cell px", self.cell, 16, 1024, 0, 4)
        self._spin(ctrl, "Subject H", self.subject_h, 16, 1024, 1, 0)
        self._spin(ctrl, "Btm margin", self.margin, 0, 256, 1, 2)
        self._spin(ctrl, "Trim %", self.trim, 0, 20, 0, 6)

        self.bg = tk.StringVar(value="green")
        self.ai_clean = tk.StringVar(value="none")
        bgf = ttk.Frame(ctrl)
        bgf.grid(row=1, column=4, columnspan=2, padx=8, sticky="w")
        ttk.Label(bgf, text="Background").pack(side="left")
        ttk.OptionMenu(bgf, self.bg, "green", "green", "purple", "none", "ai").pack(side="left", padx=4)
        ttk.Label(bgf, text="AI gap-clean").pack(side="left", padx=(10, 0))
        ttk.OptionMenu(bgf, self.ai_clean, "none", "none", "green", "purple").pack(side="left", padx=4)

        opts = ttk.Frame(self.root, padding=(8, 4))
        opts.pack(side="top", fill="x")
        self.mirror = tk.BooleanVar(value=False)
        self.isolate = tk.BooleanVar(value=True)
        self.recenter = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Mirror (flip horizontally)", variable=self.mirror).pack(side="left")
        ttk.Checkbutton(opts, text="Isolate subject", variable=self.isolate).pack(side="left", padx=12)
        ttk.Checkbutton(opts, text="Re-center (animate in place)", variable=self.recenter).pack(side="left")
        ttk.Button(opts, text="Generate", command=self.generate).pack(side="right")
        ttk.Button(opts, text="Save As…", command=self.save_as).pack(side="right", padx=6)

        panel = ttk.Frame(self.root, padding=8)
        panel.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(panel, width=PREVIEW_W, height=PREVIEW_H, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.status = tk.StringVar(value="Open a video, set the grid, then Generate.")
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w", padding=4).pack(
            side="bottom", fill="x")

    def _spin(self, parent, label, var, lo, hi, row, col):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="e", padx=(8, 2), pady=2)
        ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=6).grid(
            row=row, column=col + 1, sticky="w", pady=2)

    # ---- actions ----------------------------------------------------------
    def open_video(self):
        path = filedialog.askopenfilename(
            title="Open video",
            filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.avi *.m4v"), ("All files", "*.*")])
        if not path:
            return
        self.video_path = Path(path)
        self.name_var.set(self.video_path.name)
        self.status.set("Ready. Click Generate.")

    def _args(self):
        return SimpleNamespace(
            input=str(self.video_path), output=None,
            columns=self.columns.get(), rows=self.rows.get(), frames=0,
            cell=self.cell.get(), subject_height=self.subject_h.get(), margin=self.margin.get(),
            trim=self.trim.get(),
            bg=self.bg.get(), ai_clean=self.ai_clean.get(), color=None, tolerance=60.0,
            green_threshold=35, green_floor=80, purple_threshold=35, purple_floor=60,
            isolate=self.isolate.get(), recenter=self.recenter.get(), mirror=self.mirror.get())

    def generate(self):
        if not self.video_path:
            messagebox.showinfo("No video", "Open a video first.")
            return
        if not v2s.find_tool("ffmpeg"):
            messagebox.showerror("ffmpeg missing", "ffmpeg not found.\nInstall: winget install Gyan.FFmpeg")
            return
        self.status.set("Generating… (extracting frames + building sheet)")
        self.root.update_idletasks()
        threading.Thread(target=self._generate_worker, args=(self._args(),), daemon=True).start()

    def _generate_worker(self, args):
        try:
            sheet, count, cell = v2s.generate_sheet(args)
        except SystemExit:
            self.root.after(0, lambda: self.status.set("Generation failed — see console for details."))
            return
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda e=exc: (
                self.status.set("Error."), messagebox.showerror("Generation failed", str(e))))
            return
        self.root.after(0, lambda: self._show(sheet, count))

    def _show(self, sheet, count):
        self.sheet = sheet
        scale = min(PREVIEW_W / sheet.width, PREVIEW_H / sheet.height, 1.0)
        disp = sheet.resize((max(1, int(sheet.width * scale)), max(1, int(sheet.height * scale))),
                            self.Image.LANCZOS)
        board = _checkerboard(self.Image, disp.size)
        board.alpha_composite(disp)
        self._tkimg = self.ImageTk.PhotoImage(board)
        self.canvas.delete("all")
        self.canvas.create_image(PREVIEW_W // 2, PREVIEW_H // 2, image=self._tkimg, anchor="center")
        self.status.set(f"{sheet.width}×{sheet.height} • {count} frames • "
                        f"{self.columns.get()}×{self.rows.get()} @ {self.cell.get()}px — Save As to export.")

    def save_as(self):
        if self.sheet is None:
            messagebox.showinfo("Nothing to save", "Generate a sheet first.")
            return
        default = f"{self.video_path.stem}_sheet.png"
        out = filedialog.asksaveasfilename(
            title="Save sprite sheet", defaultextension=".png", initialfile=default,
            filetypes=[("PNG", "*.png")])
        if not out:
            return
        self.sheet.save(out)
        self.status.set(f"Saved {Path(out).name}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
