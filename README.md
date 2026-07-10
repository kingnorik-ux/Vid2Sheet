# Sprite Design Tools

Three standalone desktop utilities for a 2D sprite workflow:

- **Video to Sprite Sheet** samples a video into a configurable sheet.
- **Background Remover** previews and exports transparent PNGs.
- **Sprite Sheet Scaler** normalizes subject height and feet baselines.

## Install

Double-click `Install.bat`, or open a terminal in this folder and run:

```bat
.\Install.bat
```

The installer creates a private `.venv` inside this folder and installs the Python image libraries there. It does not create an EXE or modify the project that the tools came from. During setup, it asks whether to install optional local AI background removal.

After setup, use `Start Sprite Design Tools.bat` whenever you want to open the launcher.

## Video support

Video conversion uses FFmpeg. If it is not already installed, run:

```bat
winget install Gyan.FFmpeg
```

Then close and reopen the launcher.

## Optional local AI background removal

The installer offers this as a yes/no choice. AI removal runs locally with `rembg` and ONNX Runtime, using the user's own CPU and memory. Images are not uploaded to a cloud service. The required model downloads automatically the first time AI mode is used.

The fast Connected and Color Key modes work without the AI add-on. If AI installation was skipped, it can be added later with:

```bat
.venv\Scripts\python.exe -m pip install rembg onnxruntime
```
