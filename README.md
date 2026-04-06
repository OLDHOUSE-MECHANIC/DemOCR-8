# ScreenReader v2.0

**Select any region on your screen → OCR → Spoken aloud. Hindi + English. 100% offline. Free forever.**

Works on **Linux** (Debian/Ubuntu) and **Windows 10/11**.

---

## What's New in v2.0

| Feature | Details |
|---|---|
| **GUI Control Panel** | Full app window — no more shell running in background |
| **Stop speech** | Kill TTS mid-sentence with one click |
| **Replay** | Re-read the last capture with ▶ Play Last |
| **Speed control** | Slider from 0.5× (slow) to 2.5× (fast), persists across sessions |
| **Hindi support** | OCR + TTS in Hindi, auto-detects Devanagari text |
| **Hindi voice** | Piper `hi_IN-female-medium` voice if available, espeak-ng `-v hi` fallback |
| **Dark / Light theme** | Toggle with ☀/🌙 button, saves preference |
| **History** | Last 50 captures saved — click any to re-read |
| **Clipboard copy** | Copy OCR'd text to clipboard with one click |
| **Windows support** | Works on Windows 10/11 with PowerShell installer |
| **Better OCR** | Auto-invert for dark backgrounds, Devanagari-aware text cleaning |

---

## Install

### Linux (Debian/Ubuntu/Trixie)

```bash
cd screenreader/
bash setup.sh
```

Installs: Tesseract (eng+hin), espeak-ng, Piper TTS, English + Hindi voices, Python deps.

### Windows

```powershell
# In PowerShell (run as Administrator for Tesseract)
Set-ExecutionPolicy -Scope CurrentUser Bypass
.\setup_windows.ps1
```

You'll be prompted to install Tesseract separately (with Hindi language pack). Everything else is automatic.

---

## Run

**Linux:**
```bash
bash run.sh
```

**Windows:**
```
Double-click run.bat
```

Or search **ScreenReader** in your application menu (Linux).

---

## Usage

1. Press **`Ctrl + Shift + S`** anywhere — or click **⊹ Capture Region** in the app
2. Screen dims — drag a rectangle over the text you want read
3. Release mouse — text is OCR'd and spoken aloud
4. The text appears in the app window — you can copy it, replay it, or adjust speed

### Language Selection

In the app window, set language to:
- **eng** — English only (faster)
- **hin** — Hindi only (Devanagari)
- **hin+eng** — Mixed content, auto-detects which voice to use

### Speed Control

Use the **SPEED** slider in the app. Changes take effect on the next capture or replay.

Keyboard shortcuts (when app window is focused):
- Increase speed: drag slider right
- Decrease speed: drag slider left

### Stop Speech

Click **■ Stop** in the Playback section — stops immediately.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| No voice output (Linux) | `sudo apt install espeak-ng alsa-utils` |
| No voice output (Windows) | PowerShell SAPI is used as fallback — check Windows audio |
| Hindi OCR not working | `sudo apt install tesseract-ocr-hin` (Linux) or re-run setup selecting Hindi in Tesseract installer (Windows) |
| Hindi voice sounds robotic | Piper `hi_IN` voice not found — re-run setup.sh, it will download |
| Hotkey not working | Make sure ScreenReader app window is open (check taskbar) |
| Wayland (Linux) | Launch with `GDK_BACKEND=x11 bash run.sh` |
| Screen capture fails | On Wayland, run.sh sets `GDK_BACKEND=x11` automatically |
| `aplay` not found | `sudo apt install alsa-utils` |

---

## File Structure

```
screenreader/
├── screenreader.py        ← main program (GUI + OCR + TTS)
├── setup.sh               ← Linux one-time installer
├── setup_windows.ps1      ← Windows one-time installer
├── run.sh                 ← Linux launcher (auto-generated)
├── run.bat                ← Windows launcher (auto-generated)
└── README.md
```

Config and history are saved to:
- **Linux:** `~/.config/screenreader/`
- **Windows:** `%APPDATA%\ScreenReader\`

---

## Voices

### English
Piper `en_US-amy-medium` — natural neural voice, ~70 MB one-time download.

### Hindi
Piper `hi_IN-female-medium` — if available from the Piper voices registry.
Falls back to `espeak-ng -v hi` (robotic but works offline).

To add more voices: download any `.onnx` + `.onnx.json` from  
https://github.com/rhasspy/piper/blob/master/VOICES.md  
and place in `~/.local/share/piper-voices/` (Linux) or `%APPDATA%\piper-voices\` (Windows).

---

## Changing the Hotkey

Open `screenreader.py` and edit the check in `_start_hotkey_listener()`.  
The default is `Ctrl + Shift + S`.
