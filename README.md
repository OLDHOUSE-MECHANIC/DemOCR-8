![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Tesseract](https://img.shields.io/badge/Tesseract-OCR-green)
![Platform](https://img.shields.io/badge/Platform-Linux%20|%20Windows-lightgrey)
![License](https://img.shields.io/badge/License-Apache%202.0-orange)
![Offline](https://img.shields.io/badge/Offline-100%25-brightgreen)

# DemOCR-8

Drag a box over anything on your screen, and "THE THING" reads it out loud for ya!. Text in images, screenshots, memes, PDFs, whatever. If you can see it, this can read it.

Plus: 100% offline. No API. No subscription. No internet after setup.

---

## Why I Built This?

Started as a single file with a TTS module — copy the text, feed it in, it speaks. Did the job. But copy-pasting got old. We're apparently in the era of AI taking over industries and somehow manually selecting text had become the most exhausting part of my day.

Thought screenshotting would be easier. Then came the obvious problem — how does it find the text inside an image? Spent about a week on that, landed on OCR. Wasn't the original plan but it became the whole backbone so it ended up in the name.

Voice was robotic for a while. Piper fixed that.

Then my brother wanted his own version. So now it runs on Windows too with an actual setup and GUI so people besides me can use it.

Honestly, I made this because I was tired of having to read Book. Wanted to just listen instead. Turns out building your own audiobook machine is apparently what it takes.

---

## What It Does

Select a region, it reads it. That's the whole thing.

Works on anything visible — images, PDFs, scanned docs, that one meme with text your friend sent. No copy-pasting, no cloud, nothing phoning home. Just OCR → voice, locally, every time.

---

## Jump-Start — Linux

```bash
git clone https://github.com/OLDHOUSE-MECHANIC/DemOCR-8
cd DemOCR-8
bash setup.sh
bash run.sh
```

Or search **ScreenReader** in your app menu if that's more your thing.

`setup.sh` handles tesseract, espeak-ng, a local `.venv`, Piper TTS, and the neural voice (~60 MB one-time). Nothing auto-starts. Re-run it if something breaks.


---

## Jump-Start — Windows
Double-click setup_windows.bat
Genuinely the whole step. Downloads everything, drops it into a `tools\` folder, nothing touches the registry. You get `run.bat` when it's done.

Launch: **double-click `run.bat`**  
Pin it: right-click → *Create shortcut* → drag to desktop.

---

## The Stack (if you're curious)

| Component | What it does |
|---|---|
| **Tesseract OCR** | Finds and pulls text out of the selected region |
| **Pillow** | Cleans the image up so it doesn't fumble stylised or embedded text |
| **Piper TTS** | Offline neural voice — sounds like an actual person |
| **Tkinter** | The GUI and transparent selection overlay |


## What You Need

**Linux** — Debian Trixie / Ubuntu 22.04+ with apt, Even Arch linux! Python 3.10+, X11 (Wayland untested and probably broken)  
**Windows** — Windows 10/11 64-bit, internet for first-time setup (~150 MB total)



## Something Not Working?

**Overlay is solid black** — you're on Wayland. Log out, pick an X11 session. Run `echo $XDG_SESSION_TYPE` if you're unsure which you're on. The overlay uses `-transparentcolor` on X11 to show the actual screen through — Wayland doesn't do that.

**No audio on Linux**:
```bash
sudo apt install alsa-utils
aplay -l  # check if your device shows up
```

**OCR missing text** — select a bigger area, or zoom in before selecting. Tiny text is still a weak spot.

**Piper voice not found** — re-run the setup script, it re-downloads everything.

**Windows "16-bit application" error** — old installer got cached. Delete `tools\` and re-run `setup_windows.bat`.

**`tesseract: command not found`**:
```bash
sudo apt install tesseract-ocr
```

---

## Swapping the Voice

**Linux** — voices live in `~/.local/share/piper-voices/`. Grab any `.onnx` + `.onnx.json` pair from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), drop them in, app picks up the first `.onnx` it finds.

**Windows** — same files go into `tools\piper-voices\`, update the filename in `win_config.py`.

---

## Kill a Stuck Instance

```bash
pkill -f screenreader.py
# really stuck:
pkill -9 -f screenreader.py
```

---

## What's Next

Palette customisation, playback controls, and a hands-free reading mode. Basically making it a proper audiobook experience without needing to buy one.

---

## License

Apache 2.0 — see LICENSE
