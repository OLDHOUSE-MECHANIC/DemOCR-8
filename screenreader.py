#!/usr/bin/env python3
"""
ScreenReader — select screen region → OCR → speak
Click ▶ Select & Read, drag a box, release — done.
No hotkeys. No autostart. 100% offline.
"""

import os, sys, subprocess, threading, tempfile, time, re, logging, tkinter as tk
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
import pytesseract

IS_WIN = sys.platform.startswith("win")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("screenreader")

# ─── Config ───────────────────────────────────────────────────────────────────
CONFIG = {
    "piper_bin":      "",
    "piper_model":    "",
    "tesseract_cmd":  "",   # if empty, pytesseract uses PATH
    "tesseract_lang": "eng",
    "tts_rate":       1.0,
    "sel_color":      "#FF6B00",
    "sel_width":      2,
}

# ─── Auto-detect everything ───────────────────────────────────────────────────
def _here():
    return os.path.dirname(os.path.abspath(__file__))

def _find_file(name, dirs):
    """Return first path where `name` exists inside any of `dirs`."""
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None

def _walk_for_ext(dirs, ext):
    """Walk dirs and return first file ending with ext."""
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(ext):
                    return os.path.join(root, f)
    return None

def _which(name):
    """Cross-platform which — checks PATH."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        if IS_WIN:
            pe = p + ".exe"
            if os.path.isfile(pe):
                return pe
    return None

def find_piper():
    here = _here()
    if IS_WIN:
        bin_name  = "piper.exe"
        bin_dirs  = [
            os.path.join(here, "tools", "piper"),
            os.path.join(here, "piper"),
            os.path.expanduser("~/piper"),
        ]
        model_dirs = [
            os.path.join(here, "tools", "piper-voices"),
            os.path.join(here, "piper-voices"),
            os.path.expanduser("~/piper-voices"),
        ]
    else:
        bin_name  = "piper"
        bin_dirs  = [
            "/usr/local/bin", "/usr/bin",
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/piper"),
            os.path.join(here, "piper"),
        ]
        model_dirs = [
            os.path.expanduser("~/.local/share/piper-voices"),
            os.path.expanduser("~/piper-voices"),
            "/usr/share/piper-voices",
            "/usr/local/share/piper-voices",
            os.path.expanduser("~/piper"),
            os.path.join(here, "piper"),
        ]

    piper_bin = _find_file(bin_name, bin_dirs) or _which("piper")
    piper_model = _walk_for_ext(model_dirs, ".onnx")
    return piper_bin or "", piper_model or ""

def find_tesseract():
    here = _here()
    if IS_WIN:
        dirs = [
            os.path.join(here, "tools", "tesseract"),
            r"C:\Program Files\Tesseract-OCR",
            r"C:\Program Files (x86)\Tesseract-OCR",
            os.path.expanduser(r"~\AppData\Local\Tesseract-OCR"),
        ]
        t = _find_file("tesseract.exe", dirs) or _which("tesseract")
    else:
        t = _which("tesseract")
    return t or ""

# Run detection
CONFIG["piper_bin"],   CONFIG["piper_model"]   = find_piper()
CONFIG["tesseract_cmd"]                         = find_tesseract()

# Apply tesseract path to pytesseract
if CONFIG["tesseract_cmd"]:
    pytesseract.pytesseract.tesseract_cmd = CONFIG["tesseract_cmd"]

log.info(f"Piper bin  : {CONFIG['piper_bin']  or 'NOT FOUND'}")
log.info(f"Piper model: {CONFIG['piper_model'] or 'NOT FOUND'}")
log.info(f"Tesseract  : {CONFIG['tesseract_cmd'] or 'system PATH'}")

# ─── TTS ──────────────────────────────────────────────────────────────────────
def speak(text: str):
    text = text.strip()
    if not text:
        return
    threading.Thread(target=_speak_worker, args=(text,), daemon=True).start()

def _speak_worker(text: str):
    pb = CONFIG["piper_bin"]
    pm = CONFIG["piper_model"]

    # ── Try Piper first ───────────────────────────────────────────────────────
    if pb and pm and os.path.isfile(pb) and os.path.isfile(pm):
        log.info("TTS: Piper")
        wav = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name
            r = subprocess.run(
                [pb, "--model", pm, "--output_file", wav,
                 "--length-scale", str(1.0 / max(CONFIG["tts_rate"], 0.5))],
                input=text, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                log.warning(f"Piper exit {r.returncode}: {r.stderr.strip()}")
                raise RuntimeError("piper failed")
            if not os.path.isfile(wav) or os.path.getsize(wav) == 0:
                raise RuntimeError("piper produced empty wav")
            _play_wav(wav)
            return
        except Exception as e:
            log.warning(f"Piper error: {e} — falling back")
        finally:
            if wav:
                try: os.unlink(wav)
                except: pass

    # ── Fallback ──────────────────────────────────────────────────────────────
    if IS_WIN:
        log.info("TTS: Windows SAPI")
        _sapi(text)
    else:
        log.info("TTS: espeak-ng")
        _espeak(text)

def _play_wav(path: str):
    """Play a wav file cross-platform."""
    if IS_WIN:
        # winsound is stdlib — no extra install, no PowerShell
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    else:
        # Try aplay, then paplay, then afplay
        for player in (["aplay", "-q", path], ["paplay", path], ["ffplay", "-nodisp", "-autoexit", path]):
            try:
                r = subprocess.run(player, timeout=120, capture_output=True)
                if r.returncode == 0:
                    return
            except FileNotFoundError:
                continue
        log.error("No audio player found (aplay/paplay/ffplay). Install: sudo apt install alsa-utils")

def _espeak(text: str):
    try:
        subprocess.run(["espeak-ng", "-s", "145", "-p", "50", text],
                       timeout=120, capture_output=True)
    except FileNotFoundError:
        log.error("espeak-ng not found: sudo apt install espeak-ng")
    except Exception as e:
        log.error(f"espeak-ng: {e}")

def _sapi(text: str):
    """Windows SAPI TTS — tries multiple methods in order of preference."""

    # ── Method 1: pyttsx3 (pure-Python SAPI, no PowerShell needed) ───────────
    try:
        import pyttsx3
        engine = pyttsx3.init()
        rate = engine.getProperty("rate")
        engine.setProperty("rate", int(rate * CONFIG["tts_rate"]))
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return
    except ImportError:
        log.debug("pyttsx3 not installed — trying next method")
    except Exception as e:
        log.warning(f"pyttsx3 error: {e} — trying next method")

    # ── Method 2: win32com SAPI (pywin32) ────────────────────────────────────
    try:
        import win32com.client
        sapi = win32com.client.Dispatch("SAPI.SpVoice")
        sapi.Speak(text)
        return
    except ImportError:
        log.debug("pywin32 not installed — trying next method")
    except Exception as e:
        log.warning(f"win32com SAPI error: {e} — trying next method")

    # ── Method 3: PowerShell (full path fallback) ─────────────────────────────
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$t = [Console]::In.ReadToEnd();"
        "$s.Speak($t);"
    )
    ps_paths = [
        "powershell",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Program Files\PowerShell\7\pwsh.exe",  # PowerShell 7
    ]
    for ps in ps_paths:
        try:
            r = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-Command", script],
                input=text, text=True, timeout=120, capture_output=True,
            )
            if r.returncode == 0:
                return
        except FileNotFoundError:
            continue
        except Exception as e:
            log.warning(f"PowerShell TTS ({ps}): {e}")
            continue

    log.error(
        "All Windows TTS methods failed.\n"
        "Fix: run  pip install pyttsx3  and restart the app."
    )

# ─── OCR ──────────────────────────────────────────────────────────────────────
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
            c = _clean(raw)
            if c:
                results.append(c)
        except Exception as e:
            log.warning(f"OCR psm={psm}: {e}")
    return max(results, key=len) if results else ""

def _clean(text: str) -> str:
    if not text: return ""
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(re.sub(r"[^a-zA-Z0-9]", "", l)) >= 2]
    text = " ".join(lines)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([.,;:!?])([a-zA-Z])", r"\1 \2", text)
    return text.strip()

# ─── Screen grab (DPI-aware on Windows) ───────────────────────────────────────
def grab_region(x1, y1, x2, y2) -> Image.Image:
    """
    Grab a screen region. On Windows with display scaling > 100%,
    logical coords differ from physical pixels — compensate.
    """
    if IS_WIN:
        try:
            import ctypes
            # Get DPI scale factor (physical / logical)
            awareness = ctypes.c_int()
            ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
            scale = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
            if scale != 1.0:
                x1 = int(x1 * scale); y1 = int(y1 * scale)
                x2 = int(x2 * scale); y2 = int(y2 * scale)
        except Exception:
            pass  # if DPI query fails, just use coords as-is
    return ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)

# ─── Crop Overlay ─────────────────────────────────────────────────────────────
class CropOverlay:
    """
    Full-screen selection overlay.
    Linux/X11 : -transparentcolor → real screen shows through (no compositor needed)
    Windows   : -alpha 0.35 dark tint (transparentcolor makes canvas click-through on Win)
    """
    TRANS = "#010101"

    def __init__(self, on_done, on_cancel):
        self.on_done   = on_done
        self.on_cancel = on_cancel
        self.sx = self.sy = self.cx = self.cy = 0
        self.pressed = False

        self.win = tk.Toplevel()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        if IS_WIN:
            bg = "#1a1a1a"
            self.win.configure(bg=bg)
            self.win.attributes("-alpha", 0.35)
        else:
            bg = self.TRANS
            self.win.configure(bg=bg)
            self.win.attributes("-transparentcolor", self.TRANS)

        self.canvas = tk.Canvas(self.win, bg=bg, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.hint = tk.Label(self.win, text=" Select region — ESC to cancel ",
                             bg="#1a1a1a", fg="#FF6B00", font=("Sans", 9), pady=2)
        self.hint.place(relx=0.5, y=4, anchor="n")

        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda e: self._abort())
        self.win.focus_force()

    def _press(self, e):
        self.pressed = True
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
        fill = self.TRANS if not IS_WIN else ""
        self.canvas.create_rectangle(x1, y1, x2, y2,
            outline=CONFIG["sel_color"], width=CONFIG["sel_width"],
            fill=fill, tags="sel")
        w, h = x2 - x1, y2 - y1
        if w > 50 and h > 18:
            self.canvas.create_text(x1 + w//2, y1 + h//2,
                text=f"{w}×{h}", fill="white", font=("Sans", 9), tags="sel")

    def _release(self, e):
        if not self.pressed:
            return
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

# ─── Control Panel ────────────────────────────────────────────────────────────
class ControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ScreenReader")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a1a", padx=8, pady=6)

        tk.Label(self.root, text="ScreenReader",
                 bg="#1a1a1a", fg="#FF6B00", font=("Sans", 10, "bold")).pack(anchor="w")

        self._status = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self._status,
                 bg="#1a1a1a", fg="#888888", font=("Sans", 8)).pack(anchor="w")

        self._btn = tk.Button(self.root, text="▶  Select & Read",
            command=self._start,
            bg="#FF6B00", fg="white",
            activebackground="#cc5500", activeforeground="white",
            font=("Sans", 10, "bold"), relief=tk.FLAT,
            padx=10, pady=5, cursor="hand2")
        self._btn.pack(fill=tk.X, pady=(5, 2))

        # Show actual TTS engine being used
        if CONFIG["piper_bin"] and CONFIG["piper_model"]:
            voice_label = f"Piper ✓  {os.path.basename(CONFIG['piper_model'])}"
        elif IS_WIN:
            voice_label = "Voice: Windows SAPI"
        else:
            voice_label = "Voice: espeak-ng"
        tk.Label(self.root, text=voice_label,
                 bg="#1a1a1a", fg="#444444", font=("Sans", 7)).pack(anchor="w")

        self._busy = False
        self.root.protocol("WM_DELETE_WINDOW", self.root.quit)

    def _set(self, msg):
        self._status.set(msg)
        self.root.update_idletasks()

    def _start(self):
        if self._busy: return
        self._busy = True
        self._btn.config(state=tk.DISABLED)
        self._set("Drag to select…")
        self.root.withdraw()
        self.root.after(80, lambda: CropOverlay(on_done=self._done, on_cancel=self._cancel))

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
            img  = grab_region(x1, y1, x2, y2)
            text = ocr(preprocess(img))
            if text:
                log.info(f"OCR: {text[:80]}{'…' if len(text)>80 else ''}")
                preview = (text[:38] + "…") if len(text) > 38 else text
                self.root.after(0, self._set, preview)
                _notify("ScreenReader", f"{text[:60]}{'…' if len(text)>60 else ''}")
                speak(text)
                self.root.after(4000, self._set, "Ready")
            else:
                log.info("No text found in selection")
                self.root.after(0, self._set, "No text found")
                speak("No text found in the selected region.")
                self.root.after(2000, self._set, "Ready")
        except Exception as e:
            log.error(f"Process error: {e}")
            self.root.after(0, self._set, "Error — see terminal")
        finally:
            self._busy = False
            self.root.after(0, self._btn.config, {"state": tk.NORMAL})

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _notify(title, body):
    if IS_WIN:
        return  # skip on Windows (no notify-send)
    try:
        subprocess.Popen(["notify-send", "--expire-time=3000", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Verify Tesseract
    try:
        pytesseract.get_tesseract_version()
        log.info(f"Tesseract OK")
    except Exception:
        msg = ("Tesseract not found.\n"
               "Linux:   sudo apt install tesseract-ocr\n"
               "Windows: run setup_windows.bat")
        print(f"ERROR: {msg}")
        if IS_WIN:
            import tkinter.messagebox as mb
            _r = tk.Tk(); _r.withdraw()
            mb.showerror("ScreenReader — Missing dependency", msg)
            _r.destroy()
        sys.exit(1)

    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()

if __name__ == "__main__":
    main()
