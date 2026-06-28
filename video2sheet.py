#!/usr/bin/env python3
"""
video2sheet.py - Turn a video clip into a sprite sheet.

Samples N evenly-spaced frames from a video, optionally removes the background (chroma key or an
AI matting model) and isolates the subject, re-centers each frame so the subject animates IN PLACE,
then tiles the frames into a COLS x ROWS grid of square cells.

Defaults produce a 10-frame, 5 x 2 grid of 256 px cells -> a 1280 x 512 PNG, a common walk-cycle
sprite-sheet layout. Everything is configurable (see --help).

Requires ffmpeg/ffprobe on PATH (on Windows it also auto-finds a `winget install Gyan.FFmpeg`).
Install Python deps:  pip install -r requirements.txt           (pillow, numpy, scipy)
Optional AI matting:  pip install rembg onnxruntime             (for --bg ai)

Examples:
  # Green-screen walk cycle, mirror so it faces the other way:
  python video2sheet.py walk.mp4 -o walk_sheet.png --mirror

  # A 12-frame 6x2 sheet instead of 10:
  python video2sheet.py clip.mp4 -o out.png --columns 6 --rows 2

  # Keep the background, just tile raw frames (contact sheet):
  python video2sheet.py clip.mp4 -o contact_sheet.png --bg none

  # Purple/magenta screen instead of green:
  python video2sheet.py clip.mp4 -o out.png --bg purple

  # Non-chroma background, use the rembg model to cut the subject:
  python video2sheet.py clip.mp4 -o out.png --bg ai

  # rembg, but also clear the screen colour left in gaps between legs / arm-to-body:
  python video2sheet.py clip.mp4 -o out.png --bg ai --ai-clean green
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _fail(message: str):
    print(f"video2sheet: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_deps():
    try:
        import numpy as np
        from PIL import Image, ImageOps
        from scipy import ndimage
        return np, Image, ImageOps, ndimage
    except ImportError as exc:  # pragma: no cover - environment guidance
        _fail(f"missing dependency ({exc.name}). Install with:\n  pip install -r requirements.txt")


def find_tool(name: str) -> str | None:
    """Locate ffmpeg/ffprobe on PATH, or under a Windows winget Gyan.FFmpeg install."""
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if base.exists():
            for exe in base.rglob(f"{name}.exe"):
                return str(exe)
    return None


def probe_duration(ffprobe: str, video: Path) -> float:
    for entries in ("stream=duration", "format=duration"):
        try:
            out = subprocess.check_output(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", entries, "-of", "default=nokey=1:noprint_wrappers=1", str(video)],
                stderr=subprocess.STDOUT, text=True).strip().splitlines()
            for line in out:
                if line and line != "N/A":
                    return float(line)
        except (subprocess.CalledProcessError, ValueError):
            continue
    _fail(f"could not read duration of {video}")


def extract_frames(ffmpeg: str, video: Path, count: int, duration: float, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(video),
         "-vf", f"fps={count}/{duration}", "-frames:v", str(count), str(dest / "f_%03d.png")],
        check=True)
    frames = sorted(dest.glob("f_*.png"))
    if len(frames) < count:
        _fail(f"ffmpeg produced only {len(frames)}/{count} frames from {video}")
    return frames[:count]


# ---- masking -------------------------------------------------------------------

def green_keep_mask(np, rgb, threshold: int, floor: int):
    """True where a pixel is NOT green-screen (i.e. part of the subject)."""
    r = rgb[:, :, 0].astype(np.int32)
    g = rgb[:, :, 1].astype(np.int32)
    b = rgb[:, :, 2].astype(np.int32)
    green = (g > r + threshold) & (g > b + threshold) & (g > floor)
    return ~green


def purple_keep_mask(np, rgb, threshold: int, floor: int):
    """True where a pixel is NOT purple/magenta-screen (i.e. part of the subject).

    Purple/magenta screens have red AND blue both clearly above green."""
    r = rgb[:, :, 0].astype(np.int32)
    g = rgb[:, :, 1].astype(np.int32)
    b = rgb[:, :, 2].astype(np.int32)
    purple = (r > g + threshold) & (b > g + threshold) & ((r + b) // 2 > floor)
    return ~purple


def screen_keep_mask(np, rgb, name, args):
    """Dispatch a named chroma-screen keep-mask (used for both --bg and AI gap-clean)."""
    if name == "purple":
        return purple_keep_mask(np, rgb, args.purple_threshold, args.purple_floor)
    return green_keep_mask(np, rgb, args.green_threshold, args.green_floor)


def color_keep_mask(np, rgb, color, tolerance: float):
    diff = rgb.astype(np.float32) - np.array(color, dtype=np.float32)
    dist = np.sqrt((diff ** 2).sum(axis=2))
    return dist > tolerance


def largest_component(np, ndimage, keep):
    labels, n = ndimage.label(keep)
    if n <= 1:
        return keep
    sizes = ndimage.sum(np.ones_like(labels), labels, index=range(1, n + 1))
    return labels == (int(np.argmax(sizes)) + 1)


def trimmed_bbox(np, keep, trim):
    """Bounding box of the subject, ignoring the sparsest `trim`% of pixels on each edge.

    This keeps glow wisps / sparkles / stray edge pixels from inflating the box (which would
    shrink the subject when scaling). trim=0 returns the full tight bbox."""
    ys, xs = np.where(keep)
    if len(xs) == 0:
        return None
    if trim <= 0:
        return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    lo, hi = trim, 100 - trim
    return (int(np.percentile(xs, lo)), int(np.percentile(ys, lo)),
            int(np.percentile(xs, hi)) + 1, int(np.percentile(ys, hi)) + 1)


def _remove_bg_ai(img):
    """Cut the subject with the rembg model. Returns an RGBA PIL image."""
    try:
        from rembg import remove
    except ImportError:
        _fail("--bg ai needs rembg. Install with:\n  pip install rembg onnxruntime")
    return remove(img.convert("RGBA"))


def subject_alpha(np, Image, ImageOps, ndimage, frame_path, args):
    """Return (rgba_array, keep_mask) for one frame after background handling."""
    img = Image.open(frame_path).convert("RGBA")
    arr = np.asarray(img).copy()
    if args.bg == "none":
        arr[:, :, 3] = 255
        keep = np.ones(arr.shape[:2], dtype=bool)
        return arr, keep
    if args.bg == "ai":
        orig_rgb = np.asarray(img.convert("RGB"))  # screen test uses the original colours
        cut = _remove_bg_ai(img)
        arr = np.asarray(cut.convert("RGBA")).copy()
        keep = arr[:, :, 3] > 16
        # rembg nails the outer silhouette but tends to leave the screen colour in enclosed
        # gaps (between legs, arm-to-body). If a screen colour is given, also key it out so
        # those pockets clear without touching the clean silhouette rembg already found.
        if args.ai_clean != "none":
            keep = keep & screen_keep_mask(np, orig_rgb, args.ai_clean, args)
    elif args.bg == "color":
        keep = color_keep_mask(np, arr[:, :, :3], args.color, args.tolerance)
    elif args.bg == "purple":
        keep = purple_keep_mask(np, arr[:, :, :3], args.purple_threshold, args.purple_floor)
    else:  # "green"
        keep = green_keep_mask(np, arr[:, :, :3], args.green_threshold, args.green_floor)
    if args.isolate:
        keep = largest_component(np, ndimage, keep)
    arr[:, :, 3] = (keep * 255).astype(np.uint8)
    return arr, keep


# ---- assembly ------------------------------------------------------------------

def generate_sheet(args):
    """Run the full pipeline and return (PIL RGBA sheet, frame_count, cell). Does not save.

    Shared by the CLI (build_sheet) and the GUI (video2sheet_gui.py)."""
    np, Image, ImageOps, ndimage = _load_deps()
    ffmpeg = find_tool("ffmpeg") or _fail(
        "ffmpeg not found. Install it (Windows: `winget install Gyan.FFmpeg`) or add it to PATH.")
    ffprobe = find_tool("ffprobe") or _fail("ffprobe not found (ships with ffmpeg).")

    video = Path(args.input)
    if not video.exists():
        _fail(f"input not found: {video}")

    count = args.frames if args.frames else args.columns * args.rows
    if count != args.columns * args.rows:
        _fail(f"--frames {count} must equal --columns*--rows ({args.columns}x{args.rows}={args.columns*args.rows})")

    duration = probe_duration(ffprobe, video)
    with tempfile.TemporaryDirectory(prefix="video2sheet_") as tmp:
        frames = extract_frames(ffmpeg, video, count, duration, Path(tmp))

        arrays, masks, bboxes = [], [], []
        for f in frames:
            arr, keep = subject_alpha(np, Image, ImageOps, ndimage, f, args)
            ys, xs = np.where(keep)
            if len(xs) == 0:
                _fail(f"no subject found in a frame of {video} (try --bg none / adjust --tolerance)")
            arrays.append(arr)
            masks.append(keep)
            bboxes.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))

        cell = args.cell
        target_h = args.cell - 2 * args.margin if args.subject_height is None else args.subject_height
        full_h, full_w = arrays[0].shape[:2]

        # Size from a TRIMMED bbox per frame: ignore the sparsest `--trim`% of subject pixels
        # (glow wisps, sparkles, stray edges) so the scale targets the DENSE subject and it
        # actually fills the cell, instead of being shrunk by a few far-flung effect pixels.
        tb = [trimmed_bbox(np, m, args.trim) for m in masks]
        heights = [b[3] - b[1] for b in tb]
        widths = [b[2] - b[0] for b in tb]
        ref_h = max(1.0, float(np.percentile(heights, 80)))
        ref_w = max(1.0, float(np.percentile(widths, 80)))
        feet_y = max(b[3] for b in tb)

        # Fit the subject to the target height, but never let it overflow the cell width.
        avail_w = max(1, cell - 2 * args.margin)
        scale = min(target_h / ref_h, avail_w / ref_w)
        win = max(1, round(cell / scale))                            # square source window -> one cell
        src_top = int(round(feet_y - (cell - args.margin) / scale))  # feet land at cell bottom - margin

        sheet = Image.new("RGBA", (cell * args.columns, cell * args.rows), (0, 0, 0, 0))
        for i, arr in enumerate(arrays):
            img = Image.fromarray(arr, "RGBA")
            if args.recenter and args.bg != "none":
                cx = (tb[i][0] + tb[i][2]) // 2
            else:
                cx = full_w // 2
            left = int(round(cx - win / 2))
            # PIL fills out-of-bounds crop area as transparent, so anything beyond the window
            # (effect pixels above the head / past the sides) is simply clipped.
            cut = img.crop((left, src_top, left + win, src_top + win)).resize((cell, cell), Image.LANCZOS)
            if args.mirror:
                cut = ImageOps.mirror(cut)
            c, r = i % args.columns, i // args.columns
            sheet.alpha_composite(cut, (c * cell, r * cell))

    return sheet, count, cell


def build_sheet(args):
    sheet, count, cell = generate_sheet(args)
    video = Path(args.input)
    out = Path(args.output) if args.output else video.with_name(f"{video.stem}_sheet.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"video2sheet: {out}  ({sheet.width}x{sheet.height}, {count} frames, "
          f"{args.columns}x{args.rows} @ {cell}px, bg={args.bg}"
          f"{', mirrored' if args.mirror else ''})")
    return 0


def parse_color(value):
    if not value:
        return None
    parts = value.replace(",", " ").split()
    if len(parts) != 3:
        _fail("--color must be 'R G B' (e.g. '5 204 32')")
    return tuple(int(p) for p in parts)


def main(argv=None):
    p = argparse.ArgumentParser(description="Turn a video into a tiled sprite sheet.")
    p.add_argument("input", help="Source video (mp4/mov/webm/...)")
    p.add_argument("-o", "--output", help="Output PNG (default: <video>_sheet.png)")
    p.add_argument("--columns", type=int, default=5, help="Grid columns. Default 5")
    p.add_argument("--rows", type=int, default=2, help="Grid rows. Default 2")
    p.add_argument("--frames", type=int, default=0, help="Frame count (default columns*rows)")
    p.add_argument("--cell", type=int, default=256, help="Square cell size in px. Default 256")
    p.add_argument("--subject-height", type=int, default=228,
                   help="Target subject height within the cell, px (capped so width also fits). Default 228")
    p.add_argument("--margin", type=int, default=8, help="Gap (px) from cell bottom/sides to the subject. Default 8")
    p.add_argument("--trim", type=float, default=2.0,
                   help="Ignore the sparsest TRIM%% of subject pixels when measuring size, so glow/sparkle "
                        "outliers don't shrink the subject (those pixels get clipped). 0 = full bbox. Default 2")
    p.add_argument("--bg", choices=["green", "purple", "color", "none", "ai"], default="green",
                   help="Background handling: green-screen key (default), purple/magenta-screen key, "
                        "euclidean --color key, none (keep bg), or ai (rembg model).")
    p.add_argument("--ai-clean", choices=["none", "green", "purple"], default="none",
                   help="For --bg ai: ALSO key out this screen colour after rembg, to clear the "
                        "background left in enclosed gaps (between legs / arm-to-body). Default none.")
    p.add_argument("--color", type=parse_color, default=None, help="For --bg color: background 'R G B'")
    p.add_argument("--tolerance", type=float, default=60.0, help="For --bg color: colour distance. Default 60")
    p.add_argument("--green-threshold", type=int, default=35,
                   help="For --bg green: how much green must exceed red/blue. Default 35")
    p.add_argument("--green-floor", type=int, default=80,
                   help="For --bg green: minimum green value to count as screen. Default 80")
    p.add_argument("--purple-threshold", type=int, default=35,
                   help="For --bg purple: how much red AND blue must exceed green. Default 35")
    p.add_argument("--purple-floor", type=int, default=60,
                   help="For --bg purple: minimum (red+blue)/2 to count as screen. Default 60")
    p.add_argument("--no-isolate", dest="isolate", action="store_false",
                   help="Don't keep only the largest blob (keep every non-bg pixel)")
    p.add_argument("--no-recenter", dest="recenter", action="store_false",
                   help="Don't re-center per frame (subject keeps its absolute position / can drift)")
    p.add_argument("--mirror", action="store_true",
                   help="Flip each frame horizontally (e.g. when the source faces the wrong way).")
    p.set_defaults(isolate=True, recenter=True)
    args = p.parse_args(argv)

    if args.bg == "color" and not args.color:
        _fail("--bg color requires --color 'R G B'")
    return build_sheet(args)


if __name__ == "__main__":
    raise SystemExit(main())
