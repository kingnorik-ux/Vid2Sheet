# video2sheet

Turn a short video clip into a transparent **sprite sheet** — a grid of evenly-sampled frames with
the background removed. Built for game/pixel-art workflows (e.g. cutting an AI-generated walk-cycle
clip into a ready-to-use animation sheet), but it works on any video.

There's a **command-line tool** and a tiny **desktop GUI**, both driven by the same pipeline.

<!-- Tip: drop a sample sheet at docs/example.png and uncomment the next line to show it here.
![5x2 sprite sheet example](docs/example.png) -->

---

## What it does

For each run it:

1. **Samples** N evenly-spaced frames from the video (via `ffmpeg`).
2. **Removes the background** — green/purple chroma key, a manual colour key, or the `rembg` AI
   matting model — and **isolates the subject**.
3. **Re-centers** each frame so the subject animates *in place* (the typical look for a walk cycle),
   or leaves positions absolute (for moving/multi-element clips).
4. **Scales** uniformly to a target height, **capped so wide subjects still fit** the cell, and
   **foot-anchors** it at the bottom of each cell.
5. **Tiles** the frames into a `columns × rows` grid of square cells and writes one PNG.

Defaults give a **10-frame, 5×2 grid of 256 px cells → a 1280×512 PNG**.

---

## Requirements

- **Python 3.9+**
- **ffmpeg** (provides `ffmpeg` + `ffprobe`) on your `PATH`:
  - Windows: `winget install Gyan.FFmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` (or your distro's package)
- Python packages: `pillow`, `numpy`, `scipy`
- *(optional)* `rembg` + `onnxruntime` — only for `--bg ai`

```bash
pip install -r requirements.txt
# optional AI matting:
pip install rembg onnxruntime
```

> Tkinter (for the GUI) ships with the standard Python installer — no extra install needed.

---

## Usage

### GUI

```bash
python video2sheet_gui.py
```

Open a video, set the grid and options, click **Generate** to preview the sheet on a checkerboard,
then **Save As…**.

### Command line

```bash
# Green-screen walk cycle (default 5x2 / 256px), mirror so it faces the other way:
python video2sheet.py walk.mp4 -o walk_sheet.png --mirror

# 12-frame 6x2 sheet:
python video2sheet.py clip.mp4 -o out.png --columns 6 --rows 2

# Purple/magenta screen instead of green:
python video2sheet.py clip.mp4 -o out.png --bg purple

# No chroma screen — let the rembg model cut the subject:
python video2sheet.py clip.mp4 -o out.png --bg ai

# rembg, but also clear the screen colour left in gaps (between legs / arm-to-body):
python video2sheet.py clip.mp4 -o out.png --bg ai --ai-clean green

# Keep the background, just tile raw frames (contact sheet):
python video2sheet.py clip.mp4 -o contact_sheet.png --bg none
```

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `input` | — | Source video (mp4/mov/webm/…). |
| `-o, --output` | `<video>_sheet.png` | Output PNG path. |
| `--columns` / `--rows` | `5` / `2` | Grid size. Frame count defaults to `columns × rows`. |
| `--frames` | `columns×rows` | Override frame count (must equal `columns × rows`). |
| `--cell` | `256` | Square cell size, px. |
| `--subject-height` | `226` | Target subject height in the cell (auto-capped so width also fits). |
| `--margin` | `8` | Gap (px) from the cell bottom/sides to the subject. |
| `--bg` | `green` | `green` · `purple` · `color` · `none` · `ai`. |
| `--ai-clean` | `none` | With `--bg ai`: also key out `green`/`purple` left in enclosed gaps. |
| `--color` / `--tolerance` | — / `60` | For `--bg color`: background `'R G B'` and match distance. |
| `--green-threshold` / `--green-floor` | `35` / `80` | Green key sensitivity. |
| `--purple-threshold` / `--purple-floor` | `35` / `60` | Purple key sensitivity. |
| `--no-isolate` | (isolate on) | Keep **every** non-background blob, not just the largest. |
| `--no-recenter` | (recenter on) | Keep each subject's absolute position (no in-place centering). |
| `--mirror` | off | Flip each frame horizontally. |

---

## Tips

- **Background mode**
  - *Chroma key* (`green` / `purple`) is fast and clears gaps between limbs for free, because it
    removes **every** matching pixel.
  - `ai` (rembg) handles non-chroma / busy backgrounds and gives a clean silhouette, but can leave
    the screen colour in enclosed pockets — pair it with `--ai-clean green` (or `purple`) to fix that.
  - `color` keys one exact colour by RGB distance; `none` keeps the background (handy as a contact sheet).
- **Multiple subjects in frame** (e.g. a character *and* a portal effect): use **`--no-isolate`** so
  every large element is kept. Isolate-mode keeps only the single largest blob.
- **Wide subjects** (spiders, mounts) are automatically scaled down so their full width fits the cell —
  no clipping.
- **Moving / one-shot clips** (a dash, a teleport): add **`--no-recenter`** to preserve the real
  positions across frames instead of centering each one.
- **Facing direction**: `--mirror` flips the whole sheet if your engine expects the opposite facing.

---

## How the pieces fit

- `video2sheet.py` — the CLI **and** the shared pipeline (`generate_sheet()`).
- `video2sheet_gui.py` — a Tkinter front-end that calls `generate_sheet()` (no duplicated logic).

---

## License

[MIT](LICENSE)
