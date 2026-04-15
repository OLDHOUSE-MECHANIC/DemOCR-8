# ScreenReader

Drag a rectangle over any part of your screen — it reads the text aloud. Works on text inside images, screenshots, memes, PDFs, anything visible on screen.

100% offline. No API. No subscription. No internet after setup.

---

## How it works

1. Open the app
2. Click **▶ Select & Read**
3. Drag a box over whatever you want read
4. Release — it extracts the text and speaks it

That's it. No hotkeys, no background processes, no autostart.

---

## Stack

| Component | What it does |
|---|---|
| **Tesseract OCR** | Extracts text from the screen region |
| **Pillow** | Image preprocessing (contrast, sharpen, threshold) to catch embedded/stylised text |
| **Piper TTS** | Natural offline neural voice (falls back to espeak-ng on Linux / Windows SAPI if unavailable) |
| **Tkinter** | Minimal GUI + transparent selection overlay |

---

## Install — Linux (Debian/Ubuntu)

```bash
git clone https://github.com/yourname/screenreader
cd screenreader
bash setup.sh
```

Then launch:

```bash
bash run.sh
```

Or search **ScreenReader** in your application menu.

`setup.sh` installs:
- `tesseract-ocr` and `espeak-ng` via apt
- Python packages (`Pillow`, `pytesseract`) in a local `.venv`
- Piper TTS binary to `~/.local/share/piper`
- `en_US-amy-medium` neural voice (~60 MB, one-time download)
- A `.desktop` entry for your app menu

Nothing auto-starts. Re-run `setup.sh` anytime to repair or update.

---

## Install — Windows

```
Double-click setup_windows.bat
```

That's the whole step. It automatically downloads and installs:

| | |
|---|---|
| Python 3.11 | (skipped if already installed) |
| Pillow + pytesseract | via pip |
| Tesseract OCR 5.4 64-bit | extracted to `tools\tesseract\` |
| Piper TTS | extracted to `tools\piper\` |
| en_US-amy-medium voice | saved to `tools\piper-voices\` |

Everything goes into a `tools\` folder next to the script — nothing is written to the registry. When done, it creates `run.bat`.

To launch: **double-click `run.bat`**

To pin to desktop: right-click `run.bat` → *Create shortcut* → drag shortcut to desktop.

---

## Files

```
screenreader/
├── screenreader.py        ← main program
├── setup.sh               ← Linux one-time installer
├── setup_windows.bat      ← Windows one-time installer
├── run.sh                 ← Linux launcher (created by setup.sh)
├── run.bat                ← Windows launcher (created by setup_windows.bat)
├── win_config.py          ← Windows local tool paths (auto-generated)
├── .venv/                 ← Python environment (Linux, created by setup.sh)
└── tools/                 ← Tesseract + Piper binaries (Windows, created by setup_windows.bat)
```

---

## Requirements

**Linux**
- Debian Trixie / Ubuntu 22.04+ (or any distro with apt)
- Python 3.10+
- X11 display (Wayland not tested)

**Windows**
- Windows 10 or 11, 64-bit
- Internet connection for first-time setup (~150 MB total downloads)

---

## Transparency / overlay note

The selection overlay uses `-transparentcolor` on X11 so the actual screen content shows through in real time — no compositor required. If you're on Wayland and the overlay appears black, switch to an X11 session (`echo $XDG_SESSION_TYPE` to check).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Overlay is solid black | You're on Wayland — log out and choose an X11 session |
| No audio on Linux | `sudo apt install alsa-utils` then check `aplay -l` |
| OCR misses text | Select a larger region; zoom in first if text is tiny |
| Piper voice not found | Re-run `setup.sh` / `setup_windows.bat` — it re-downloads |
| Windows: "16-bit application" error | Delete the `tools\` folder and re-run `setup_windows.bat` — old installer was cached |
| `tesseract: command not found` | Linux: `sudo apt install tesseract-ocr` |

---

## Changing the voice (Linux)

Piper voices live in `~/.local/share/piper-voices/`. Download any voice from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) — grab the `.onnx` and `.onnx.json` pair. The app picks up the first `.onnx` it finds automatically.

## Changing the voice (Windows)

Drop the `.onnx` and `.onnx.json` files into `tools\piper-voices\` and update the filename in `win_config.py`.

---

## Kill a stuck instance

```bash
pkill -f screenreader.py
# or if really stuck:
pkill -9 -f screenreader.py
```

---

## License
Apache 
