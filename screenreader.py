#!/usr/bin/env python3
"""
ScreenReader — crop overlay → OCR → Piper TTS
Hotkey: Ctrl+Shift+S
Optimised for Debian Trixie / low-spec hardware (Lenovo IdeaPad 145s)
"""

import os
import sys
import subprocess
import threading
import tempfile
import time
import re
import logging
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter, ImageOps
import pytesseract
from pynput import keyboard

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("screenreader")

# ─── Config ────────────────────────────────────────────────────────────────────
CONFIG = {
    "hotkey": "<ctrl>+<shift>+s",
    "piper_bin": "",          # auto-detected below
    "piper_model": "",        # auto-detected below
    "tesseract_lang": "eng",
    "tts_rate": 1.0,          # speech rate multiplier (piper --length-scale inverse)
    "overlay_color": "#FF6B00",
    "overlay_alpha": 0.35,
}

# ─── Auto-detect Piper ─────────────────────────────────────────────────────────
def find_piper():
    """Find piper binary and a voice model on the system."""
    # Common install locations
    candidates = [
        "/usr/local/bin/piper",
        "/usr/bin/piper",
        os.path.expanduser("~/.local/bin/piper"),
        os.path.expanduser("~/piper/piper"),
    ]
    piper_bin = None
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            piper_bin = c
            break
    if not piper_bin:
        # Try PATH
        try:
            result = subprocess.run(["which", "piper"], capture_output=True, text=True)
            if result.returncode == 0:
                piper_bin = result.stdout.strip()
        except Exception:
            pass

    # Find a .onnx voice model
    model_search_dirs = [
        os.path.expanduser("~/.local/share/piper-voices"),
        os.path.expanduser("~/piper-voices"),
        "/usr/share/piper-voices",
        "/usr/local/share/piper-voices",
        os.path.expanduser("~/piper"),
    ]
    piper_model = None
    for d in model_search_dirs:
        if os.path.isdir(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith(".onnx"):
                        piper_model = os.path.join(root, f)
                        break
                if piper_model:
                    break
        if piper_model:
            break

    return piper_bin, piper_model


PIPER_BIN, PIPER_MODEL = find_piper()
CONFIG["piper_bin"] = PIPER_BIN or ""
CONFIG["piper_model"] = PIPER_MODEL or ""

# ─── TTS ───────────────────────────────────────────────────────────────────────
def speak(text: str):
    """Speak text using Piper TTS, fall back to espeak-ng if unavailable."""
    text = text.strip()
    if not text:
        return

    def _run():
        try:
            if CONFIG["piper_bin"] and CONFIG["piper_model"] and os.path.isfile(CONFIG["piper_model"]):
                log.info("Speaking via Piper TTS")
                # Piper reads stdin, outputs wav to stdout → pipe to aplay
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav:
                    wav_path = wav.name
                proc = subprocess.run(
                    [
                        CONFIG["piper_bin"],
                        "--model", CONFIG["piper_model"],
                        "--output_file", wav_path,
                        "--length-scale", str(1.0 / max(CONFIG["tts_rate"], 0.5)),
                    ],
                    input=text,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0 and os.path.getsize(wav_path) > 0:
                    subprocess.run(["aplay", "-q", wav_path], timeout=120)
                else:
                    log.warning("Piper failed, falling back to espeak-ng")
                    _espeak(text)
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass
            else:
                log.info("Piper not available, using espeak-ng")
                _espeak(text)
        except Exception as e:
            log.error(f"TTS error: {e}")
            _espeak(text)

    threading.Thread(target=_run, daemon=True).start()


def _espeak(text: str):
    """Fallback TTS via espeak-ng."""
    try:
        subprocess.run(
            ["espeak-ng", "-s", "145", "-p", "50", text],
            timeout=120,
            capture_output=True,
        )
    except FileNotFoundError:
        log.error("espeak-ng not found. Install: sudo apt install espeak-ng")
    except Exception as e:
        log.error(f"espeak-ng error: {e}")


# ─── OCR / Image Processing ────────────────────────────────────────────────────
def preprocess_image(img: Image.Image) -> Image.Image:
    """
    Multi-stage image preprocessing to maximise OCR accuracy on:
    - Normal screen text
    - Image-embedded / stylised text (logos, banners, memes, etc.)
    """
    # Upscale small regions — Tesseract works best at ~300 DPI
    w, h = img.size
    scale = 1
    if w < 600 or h < 400:
        scale = max(3, int(600 / max(w, 1)))
        img = img.resize((w * scale, h * scale), Image.LANCZOS)

    # Convert to RGB to be safe
    img = img.convert("RGB")

    # Increase contrast
    img = ImageEnhance.Contrast(img).enhance(2.5)

    # Sharpen
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)

    # Convert to grayscale
    img = img.convert("L")

    # Adaptive threshold via point — turns image to clean B&W
    img = img.point(lambda x: 0 if x < 140 else 255, "1")
    img = img.convert("L")

    return img


def ocr_region(img: Image.Image) -> str:
    """Run Tesseract OCR with multiple PSM modes and pick the best result."""
    results = []

    for psm in [6, 11, 3]:   # 6=block, 11=sparse, 3=auto
        try:
            cfg = f"--oem 3 --psm {psm}"
            raw = pytesseract.image_to_string(img, lang=CONFIG["tesseract_lang"], config=cfg)
            cleaned = clean_text(raw)
            if cleaned:
                results.append(cleaned)
        except Exception as e:
            log.warning(f"OCR psm={psm} failed: {e}")

    if not results:
        return ""

    # Return longest result (most text extracted)
    return max(results, key=len)


def clean_text(text: str) -> str:
    """Clean and normalise OCR output for natural TTS reading."""
    if not text:
        return ""

    # Remove non-printable chars except newlines/spaces
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)

    # Collapse excessive whitespace/newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Remove lines that are just punctuation/noise
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(re.sub(r"[^a-zA-Z0-9]", "", l)) >= 2]

    text = " ".join(lines)

    # Normalise punctuation spacing
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([.,;:!?])([a-zA-Z])", r"\1 \2", text)

    return text.strip()


# ─── Crop Overlay ──────────────────────────────────────────────────────────────
class CropOverlay:
    """Full-screen transparent Tkinter overlay for dragging a crop region."""

    def __init__(self, on_done_callback):
        self.callback = on_done_callback
        self.start_x = self.start_y = 0
        self.cur_x = self.cur_y = 0
        self.rect_id = None
        self.cancelled = False

        self.root = tk.Tk()
        self.root.title("ScreenReader — Select Region")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.25)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.config(cursor="crosshair")

        # Instructions label
        self.label = tk.Label(
            self.root,
            text="Drag to select region  •  ESC to cancel",
            bg="black",
            fg="white",
            font=("Monospace", 14, "bold"),
            pady=6,
        )
        self.label.pack(side=tk.TOP, fill=tk.X)

        self.canvas = tk.Canvas(
            self.root,
            bg="black",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", self._on_cancel)

    def run(self):
        self.root.mainloop()

    def _on_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.cur_x = event.x_root
        self.cur_y = event.y_root
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _on_drag(self, event):
        self.cur_x = event.x_root
        self.cur_y = event.y_root
        cx = event.x - (event.x_root - self.start_x)
        cy = event.y - (event.y_root - self.start_y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            min(cx, event.x),
            min(cy, event.y),
            max(cx, event.x),
            max(cy, event.y),
            outline=CONFIG["overlay_color"],
            width=2,
            fill=CONFIG["overlay_color"],
            stipple="gray25",
        )

    def _on_release(self, event):
        x1, y1 = min(self.start_x, self.cur_x), min(self.start_y, self.cur_y)
        x2, y2 = max(self.start_x, self.cur_x), max(self.start_y, self.cur_y)
        self.root.destroy()
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.callback(x1, y1, x2, y2)
        else:
            log.info("Selection too small, ignored.")

    def _on_cancel(self, event=None):
        self.cancelled = True
        self.root.destroy()


# ─── Pipeline ──────────────────────────────────────────────────────────────────
_tts_active = False   # simple guard to prevent overlapping speech


def on_region_selected(x1, y1, x2, y2):
    """Capture → preprocess → OCR → speak."""
    log.info(f"Region selected: ({x1},{y1}) → ({x2},{y2})")

    # Brief pause so overlay is fully gone before screenshotting
    time.sleep(0.15)

    try:
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
    except Exception as e:
        log.error(f"Screenshot failed: {e}")
        notify("ScreenReader", "Screenshot failed.")
        return

    processed = preprocess_image(img)
    text = ocr_region(processed)

    if not text:
        log.info("No text found in selection.")
        notify("ScreenReader", "No text detected in selected region.")
        speak("No text found in the selected region.")
        return

    log.info(f"OCR result ({len(text)} chars): {text[:120]}{'...' if len(text)>120 else ''}")
    notify("ScreenReader", f"Reading: {text[:60]}{'…' if len(text)>60 else ''}")
    speak(text)


def notify(title: str, body: str):
    """Send desktop notification (non-blocking, optional)."""
    try:
        subprocess.Popen(
            ["notify-send", "--expire-time=4000", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # notify-send not installed, silently skip


def trigger_overlay():
    """Open the crop overlay in the main thread via Tk."""
    log.info("Overlay triggered via hotkey")
    overlay = CropOverlay(on_done_callback=on_region_selected)
    overlay.run()


# ─── Global Hotkey Listener ────────────────────────────────────────────────────
_current_keys: set = set()
_overlay_open = False


def on_press(key):
    global _overlay_open
    try:
        _current_keys.add(key)
    except Exception:
        pass

    required = {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode.from_char("s")}
    required_r = {keyboard.Key.ctrl_r, keyboard.Key.shift, keyboard.KeyCode.from_char("s")}

    pressed = set()
    for k in _current_keys:
        pressed.add(k)

    def _matches(req):
        ctrl = keyboard.Key.ctrl_l in pressed or keyboard.Key.ctrl_r in pressed
        shift = keyboard.Key.shift in pressed or keyboard.Key.shift_l in pressed or keyboard.Key.shift_r in pressed
        s = keyboard.KeyCode.from_char("s") in pressed or keyboard.KeyCode.from_char("S") in pressed
        return ctrl and shift and s

    if _matches(required) and not _overlay_open:
        _overlay_open = True
        t = threading.Thread(target=_launch_overlay_thread, daemon=True)
        t.start()


def _launch_overlay_thread():
    global _overlay_open
    try:
        trigger_overlay()
    finally:
        _overlay_open = False


def on_release(key):
    try:
        _current_keys.discard(key)
    except Exception:
        pass


# ─── Main ──────────────────────────────────────────────────────────────────────
def print_banner():
    print("""
╔═══════════════════════════════════════════════╗
║           ScreenReader  v1.0                  ║
║   Crop → OCR → Piper TTS  (100% offline)      ║
╠═══════════════════════════════════════════════╣
║  Hotkey : Ctrl + Shift + S                    ║
║  ESC    : Cancel selection                    ║
║  Ctrl+C : Quit                                ║
╚═══════════════════════════════════════════════╝
""")
    if CONFIG["piper_bin"]:
        print(f"  ✓ Piper TTS : {CONFIG['piper_bin']}")
        if CONFIG["piper_model"]:
            print(f"  ✓ Voice     : {os.path.basename(CONFIG['piper_model'])}")
        else:
            print("  ⚠ No Piper voice model found — will fall back to espeak-ng")
            print("    Install a model: see README or run ./setup.sh")
    else:
        print("  ⚠ Piper not found — using espeak-ng as TTS")
        print("    For natural voice: see README or run ./setup.sh")
    print()


def main():
    print_banner()

    # Verify tesseract is available
    try:
        ver = pytesseract.get_tesseract_version()
        log.info(f"Tesseract {ver} ready")
    except Exception:
        log.error("Tesseract not found. Install: sudo apt install tesseract-ocr")
        sys.exit(1)

    log.info("Listening for Ctrl+Shift+S ...")
    notify("ScreenReader", "Running — press Ctrl+Shift+S to capture")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    try:
        listener.join()
    except KeyboardInterrupt:
        log.info("Exiting.")
        listener.stop()


if __name__ == "__main__":
    main()
