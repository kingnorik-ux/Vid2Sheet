#!/usr/bin/env python3
"""Professional launcher for the standalone Sprite Design Tools."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"

TOOLS = (
    ("Video to Sprite Sheet", "Build clean, evenly spaced animation sheets from video clips.", "video2sheet_gui.py", "01"),
    ("Background Remover", "Remove solid or connected backgrounds with live before/after preview.", "removebg_gui.py", "02"),
    ("Sprite Sheet Scaler", "Normalize character size and baseline across one or two sprite sheets.", "sheetscaler_gui.py", "03"),
)


class Launcher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Sprite Design Tools")
        root.geometry("820x590")
        root.minsize(760, 540)
        root.configure(bg="#10151d")
        self._style()
        self._build()

    def _style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background="#10151d")
        style.configure("Header.TLabel", background="#10151d", foreground="#f4f7fb", font=("Segoe UI Semibold", 27))
        style.configure("Sub.TLabel", background="#10151d", foreground="#91a0b5", font=("Segoe UI", 11))
        style.configure("Card.TFrame", background="#19212c", relief="flat")
        style.configure("Number.TLabel", background="#26364a", foreground="#71b7ff", font=("Segoe UI Semibold", 12), anchor="center")
        style.configure("CardTitle.TLabel", background="#19212c", foreground="#f4f7fb", font=("Segoe UI Semibold", 15))
        style.configure("CardText.TLabel", background="#19212c", foreground="#aeb9c8", font=("Segoe UI", 10))
        style.configure("Launch.TButton", font=("Segoe UI Semibold", 10), padding=(18, 9), background="#2878c8", foreground="white")
        style.map("Launch.TButton", background=[("active", "#3592ed")])
        style.configure("Footer.TLabel", background="#10151d", foreground="#718096", font=("Segoe UI", 9))

    def _build(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(40, 32))
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Sprite Design Tools", style="Header.TLabel").pack(anchor="w")
        ttk.Label(shell, text="A focused workspace for building production-ready 2D sprite assets.", style="Sub.TLabel").pack(anchor="w", pady=(4, 25))

        for title, description, script, number in TOOLS:
            card = ttk.Frame(shell, style="Card.TFrame", padding=(18, 15))
            card.pack(fill="x", pady=(0, 12))
            badge = ttk.Label(card, text=number, style="Number.TLabel", width=4, padding=(4, 12))
            badge.pack(side="left", padx=(0, 16))
            copy = ttk.Frame(card, style="Card.TFrame")
            copy.pack(side="left", fill="x", expand=True)
            ttk.Label(copy, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(copy, text=description, style="CardText.TLabel").pack(anchor="w", pady=(4, 0))
            ttk.Button(card, text="Open Tool", style="Launch.TButton", command=lambda s=script: self.open_tool(s)).pack(side="right", padx=(16, 0))

        ffmpeg = "Ready" if shutil.which("ffmpeg") else "ffmpeg needed for video conversion"
        ttk.Label(shell, text=f"Local desktop tools  |  {ffmpeg}", style="Footer.TLabel").pack(anchor="w", pady=(8, 0))

    def open_tool(self, script: str) -> None:
        path = APP / script
        try:
            subprocess.Popen([sys.executable, str(path)], cwd=str(APP))
        except OSError as exc:
            messagebox.showerror("Could not open tool", str(exc))


def main() -> int:
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
