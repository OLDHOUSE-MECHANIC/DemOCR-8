#!/usr/bin/env python3
"""
ScreenReader — select screen region → OCR → Piper TTS
Launch: python3 screenreader.py  (or double-click / .desktop)
Click the floating button to start a selection.
No hotkeys. No autostart. Just open and use.
Optimised for Debian Trixie / low-spec hardware.
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
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
import pytesseract

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("screenreader")

# ─── Config ───────────────────────────────────────────────────────────────────
CONFIG = {
    "piper_bin":      "",
    "piper_model":    "",
    "tesseract_lang": "eng",
    "tts_rate":       1.0,
    "sel_color":      "#FF6B00",
    "sel_width":      2,
}

# ─── Auto-detect Piper ────────────────────────────────────────────────────────
def find_piper():
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
        try:
            r = subprocess.run(["which", "piper"], capture_output=True, text=True)
            if r.returncode == 0:
                piper_bin = r.stdout.strip()
        except Exception:
            pass

    model_dirs = [
        os.path.expanduser("~/.local/share/piper-voices"),
        os.path.expanduser("~/piper-voices"),
        "/usr/share/piper-voices",
        "/usr/local/share/piper-voices",
        os.path.expanduser("~/piper"),
    ]
    piper_model = None
    for d in model_dirs:
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
CONFIG["piper_bin"]   = PIPER_BIN  or ""
CONFIG["piper_model"] = PIPER_MODEL or ""

# ─── TTS ──────────────────────────────────────────────────────────────────────
def speak(text: str):
    text = text.strip()
    if not text:
        return
    threading.Thread(target=_speak_worker, args=(text,), daemon=True).start()

def _speak_worker(text: str):
    try:
        pb = CONFIG["piper_bin"]
        pm = CONFIG["piper_model"]
        if pb and pm and os.path.isfile(pm):
            log.info("TTS via Piper")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name
            r = subprocess.run(
                [pb, "--model", pm, "--output_file", wav,
                 "--length-scale", str(1.0 / max(CONFIG["tts_rate"], 0.5))],
                input=text, capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and os.path.getsize(wav) > 0:
                subprocess.run(["aplay", "-q", wav], timeout=120)
            else:
                log.warning("Piper failed, trying espeak-ng")
                _espeak(text)
            try:
                os.unlink(wav)
            except Exception:
                pass
        else:
            _espeak(text)
    except Exception as e:
        log.error(f"TTS error: {e}")
        _espeak(text)

def _espeak(text: str):
    try:
        subprocess.run(["espeak-ng", "-s", "145", "-p", "50", text],
                       timeout=120, capture_output=True)
    except FileNotFoundError:
        log.error("espeak-ng not found.  sudo apt install espeak-ng")
    except Exception as e:
        log.error(f"espeak-ng: {e}")

# ─── Image preprocessing + OCR ────────────────────────────────────────────────
def preprocess(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w < 600 or h < 400:
        s = max(3, int(600 / max(w, 1)))
        img = img.resize((w * s, h * s), Image.LANCZOS)
    img = img.convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
    img = img.convert("L")
    img = img.point(lambda x: 0 if x < 140 else 255, "1").convert("L")
    return img

def ocr(img: Image.Image) -> str:
    results = []
    for psm in [6, 11, 3]:
        try:
            raw = pytesseract.image_to_string(
                img, lang=CONFIG["tesseract_lang"], config=f"--oem 3 --psm {psm}")
            c = clean(raw)
            if c:
                results.append(c)
        except Exception as e:
            log.warning(f"OCR psm={psm}: {e}")
    return max(results, key=len) if results else ""

def clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(re.sub(r"[^a-zA-Z0-9]", "", l)) >= 2]
    text = " ".join(lines)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([.,;:!?])([a-zA-Z])", r"\1 \2", text)
    return text.strip()

# ─── Crop Overlay ─────────────────────────────────────────────────────────────
class CropOverlay:
    """
    Real-time transparent selection overlay.
    Uses -transparentcolor trick — works on X11 without a compositor.
    The background colour (#010101) is declared transparent so the
    actual screen content shows through; only the orange border is drawn.
    """

    TRANS = "#010101"   # colour that becomes see-through

    def __init__(self, on_done, on_cancel):
        self.on_done   = on_done
        self.on_cancel = on_cancel
        self.sx = self.sy = self.cx = self.cy = 0

        self.win = tk.Toplevel()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", self.TRANS)
        self.win.configure(bg=self.TRANS)

        self.canvas = tk.Canvas(
            self.win, bg=self.TRANS,
            highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Small hint strip — dark so it's readable
        self.hint = tk.Label(
            self.win,
            text=" Select region — ESC cancel ",
            bg="#1a1a1a", fg="#FF6B00",
            font=("Sans", 9), pady=2,
        )
        self.hint.place(relx=0.5, y=4, anchor="n")

        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda e: self._abort())
        self.win.focus_force()

    def _press(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        self.cx, self.cy = e.x_root, e.y_root
        self._redraw()

    def _drag(self, e):
        self.cx, self.cy = e.x_root, e.y_root
        self._redraw()

    def _redraw(self):
        self.canvas.delete("sel")
        x1 = min(self.sx, self.cx); y1 = min(self.sy, self.cy)
        x2 = max(self.sx, self.cx); y2 = max(self.sy, self.cy)
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=CONFIG["sel_color"], width=CONFIG["sel_width"],
            fill=self.TRANS,   # fill with transparent colour
            tags="sel",
        )
        w, h = x2 - x1, y2 - y1
        if w > 50 and h > 18:
            self.canvas.create_text(
                x1 + w // 2, y1 + h // 2,
                text=f"{w}×{h}", fill="white",
                font=("Sans", 9), tags="sel",
            )

    def _release(self, e):
        self.cx, self.cy = e.x_root, e.y_root
        x1 = min(self.sx, self.cx); y1 = min(self.sy, self.cy)
        x2 = max(self.sx, self.cx); y2 = max(self.sy, self.cy)
        self.win.destroy()
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.on_done(x1, y1, x2, y2)
        else:
            self.on_cancel()

    def _abort(self):
        self.win.destroy()
        self.on_cancel()

# ─── Tiny floating control panel ──────────────────────────────────────────────
class ControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ScreenReader")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a1a", padx=8, pady=6)

        tk.Label(self.root, text="ScreenReader",
                 bg="#1a1a1a", fg="#FF6B00",
                 font=("Sans", 10, "bold")).pack(anchor="w")

        self._status = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self._status,
                 bg="#1a1a1a", fg="#888888",
                 font=("Sans", 8)).pack(anchor="w")

        self._btn = tk.Button(
            self.root, text="▶  Select & Read",
            command=self._start,
            bg="#FF6B00", fg="white",
            activebackground="#cc5500", activeforeground="white",
            font=("Sans", 10, "bold"),
            relief=tk.FLAT, padx=10, pady=5, cursor="hand2",
        )
        self._btn.pack(fill=tk.X, pady=(5, 2))

        tts = ("Piper ✓" if CONFIG["piper_bin"] and CONFIG["piper_model"]
               else "espeak-ng")
        tk.Label(self.root, text=f"Voice: {tts}",
                 bg="#1a1a1a", fg="#444444", font=("Sans", 7)).pack(anchor="w")

        self._busy = False
        self.root.protocol("WM_DELETE_WINDOW", self.root.quit)

    def _set(self, msg):
        self._status.set(msg)
        self.root.update_idletasks()

    def _start(self):
        if self._busy:
            return
        self._busy = True
        self._btn.config(state=tk.DISABLED)
        self._set("Drag to select…")
        self.root.withdraw()
        self.root.after(80, lambda: CropOverlay(
            on_done=self._done, on_cancel=self._cancel))

    def _done(self, x1, y1, x2, y2):
        self.root.deiconify()
        self._set("Reading…")
        threading.Thread(target=self._process, args=(x1,y1,x2,y2), daemon=True).start()

    def _cancel(self):
        self.root.deiconify()
        self._busy = False
        self._btn.config(state=tk.NORMAL)
        self._set("Ready")

    def _process(self, x1, y1, x2, y2):
        try:
            time.sleep(0.12)
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            text = ocr(preprocess(img))
            if text:
                preview = (text[:38] + "…") if len(text) > 38 else text
                self.root.after(0, self._set, preview)
                notify("ScreenReader", f"{text[:60]}{'…' if len(text)>60 else ''}")
                speak(text)
                self.root.after(3500, self._set, "Ready")
            else:
                self.root.after(0, self._set, "No text found")
                speak("No text found in the selected region.")
                self.root.after(2000, self._set, "Ready")
        except Exception as e:
            log.error(f"Process error: {e}")
            self.root.after(0, self._set, "Error — see terminal")
        finally:
            self._busy = False
            self.root.after(0, self._btn.config, {"state": tk.NORMAL})

# ─── Notify helper ────────────────────────────────────────────────────────────
def notify(title, body):
    try:
        subprocess.Popen(["notify-send", "--expire-time=3000", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print("ERROR: Tesseract not found.\n  Run: sudo apt install tesseract-ocr")
        sys.exit(1)

    tts = (f"Piper ({os.path.basename(CONFIG['piper_model'])})"
           if CONFIG["piper_bin"] and CONFIG["piper_model"] else "espeak-ng")
    print(f"ScreenReader ready  —  TTS: {tts}")

    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()

if __name__ == "__main__":
    main()
