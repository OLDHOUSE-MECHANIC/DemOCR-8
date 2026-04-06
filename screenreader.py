#!/usr/bin/env python3
"""
ScreenReader v2.0 — Crop → OCR → TTS
Features: GUI control panel, Hindi+English, speech rate control,
          stop/interrupt, dark/light theme, cross-platform (Linux + Windows)
"""

import os
import sys
import json
import subprocess
import threading
import tempfile
import time
import re
import logging
import platform
import queue
import shutil
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter, ImageOps
import pytesseract

# ─── Platform detection ───────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# ─── Try importing pynput (keyboard listener) ─────────────────────────────────
try:
    from pynput import keyboard as pynput_keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("screenreader")

# ─── Config paths ─────────────────────────────────────────────────────────────
if IS_WINDOWS:
    CONFIG_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "ScreenReader"
else:
    CONFIG_DIR = Path("~/.config/screenreader").expanduser()

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.jsonl"

# ─── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "theme": "dark",
    "tts_rate": 1.0,          # 0.5 = slow, 1.0 = normal, 2.0 = fast
    "ocr_lang": "eng",        # "eng", "hin", "hin+eng"
    "overlay_color": "#FF6B00",
    "piper_bin": "",
    "piper_model_eng": "",
    "piper_model_hin": "",
    "hotkey": "ctrl+shift+s",
    "history_limit": 50,
}

# ─── Themes ───────────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":         "#0f1117",
        "surface":    "#1a1d27",
        "surface2":   "#252836",
        "accent":     "#FF6B00",
        "accent2":    "#ff9d4d",
        "text":       "#f0f0f5",
        "text2":      "#8b8fa8",
        "text3":      "#5a5e70",
        "success":    "#4ade80",
        "warning":    "#fbbf24",
        "error":      "#f87171",
        "border":     "#2e3147",
        "btn":        "#252836",
        "btn_hover":  "#2e3147",
    },
    "light": {
        "bg":         "#f5f3ef",
        "surface":    "#ffffff",
        "surface2":   "#f0ede8",
        "accent":     "#d4500a",
        "accent2":    "#e8722e",
        "text":       "#1a1208",
        "text2":      "#5a4e3a",
        "text3":      "#9a8e7a",
        "success":    "#16a34a",
        "warning":    "#d97706",
        "error":      "#dc2626",
        "border":     "#ddd8d0",
        "btn":        "#ede9e2",
        "btn_hover":  "#ddd8d0",
    },
}

# ─── Config load/save ─────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg

def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        log.warning(f"Could not save config: {e}")

# ─── Auto-detect Piper ────────────────────────────────────────────────────────
def find_piper():
    if IS_WINDOWS:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA","")) / "piper" / "piper.exe",
            Path("C:/piper/piper.exe"),
            Path.home() / "piper" / "piper.exe",
        ]
    else:
        candidates = [
            Path("/usr/local/bin/piper"),
            Path("/usr/bin/piper"),
            Path.home() / ".local/bin/piper",
            Path.home() / "piper/piper",
        ]

    piper_bin = None
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            piper_bin = str(c)
            break
    if not piper_bin:
        found = shutil.which("piper")
        if found:
            piper_bin = found

    # Voice model search dirs
    if IS_WINDOWS:
        search_dirs = [
            Path(os.environ.get("APPDATA","")) / "piper-voices",
            Path.home() / "piper-voices",
        ]
    else:
        search_dirs = [
            Path.home() / ".local/share/piper-voices",
            Path.home() / "piper-voices",
            Path("/usr/share/piper-voices"),
            Path("/usr/local/share/piper-voices"),
        ]

    def find_voice(keyword: str) -> str:
        for d in search_dirs:
            if d.is_dir():
                for f in d.rglob("*.onnx"):
                    if keyword.lower() in f.stem.lower():
                        return str(f)
        # fallback: any onnx
        for d in search_dirs:
            if d.is_dir():
                for f in d.rglob("*.onnx"):
                    return str(f)
        return ""

    model_eng = find_voice("en_US") or find_voice("en")
    model_hin = find_voice("hi_IN") or find_voice("hin") or find_voice("hindi")

    return piper_bin or "", model_eng, model_hin


# ─── History ──────────────────────────────────────────────────────────────────
def save_history(text: str, lang: str):
    try:
        entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "lang": lang, "text": text}
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def load_history(limit=50) -> list:
    if not HISTORY_FILE.exists():
        return []
    lines = []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    entries = []
    for l in lines[-limit:]:
        try:
            entries.append(json.loads(l))
        except Exception:
            pass
    return list(reversed(entries))


# ─── Language detection (simple heuristic) ───────────────────────────────────
def detect_language(text: str) -> str:
    """Detect if text is primarily Hindi (Devanagari) or English."""
    devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    total = len([c for c in text if c.strip()])
    if total == 0:
        return "eng"
    ratio = devanagari / total
    if ratio > 0.3:
        return "hin"
    return "eng"


# ─── Image Processing ─────────────────────────────────────────────────────────
def preprocess_image(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w < 600 or h < 100:
        scale = max(3, int(600 / max(w, 1)))
        img = img.resize((w * scale, h * scale), Image.LANCZOS)

    img = img.convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.convert("L")

    # Auto-invert for dark backgrounds
    import numpy as np
    arr = np.array(img)
    if arr.mean() < 110:
        img = ImageOps.invert(img)

    img = img.point(lambda x: 0 if x < 140 else 255, "1")
    img = img.convert("L")
    return img


def ocr_image(img: Image.Image, lang: str) -> str:
    """Run OCR with best PSM for the given language."""
    processed = preprocess_image(img)
    results = []
    psm_modes = [6, 3, 11]

    for psm in psm_modes:
        try:
            cfg = f"--oem 3 --psm {psm}"
            raw = pytesseract.image_to_string(processed, lang=lang, config=cfg)
            cleaned = clean_text(raw)
            if cleaned:
                results.append(cleaned)
        except Exception as e:
            log.warning(f"OCR psm={psm} failed: {e}")

    if not results:
        return ""
    return max(results, key=len)


def clean_text(text: str) -> str:
    if not text:
        return ""
    # Keep Devanagari + ASCII printable + newlines
    text = re.sub(r"[^\x20-\x7E\u0900-\u097F\n]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(re.sub(r"[^a-zA-Z0-9\u0900-\u097F]", "", l)) >= 2]
    text = "\n".join(lines)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([.,;:!?])([a-zA-Z\u0900-\u097F])", r"\1 \2", text)
    return text.strip()


# ─── TTS Engine ───────────────────────────────────────────────────────────────
class TTSEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._proc = None          # current aplay/espeak/playsound process
        self._lock = threading.Lock()
        self._thread = None

    def stop(self):
        """Kill current TTS immediately."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.kill()
                    log.info("TTS stopped.")
                except Exception:
                    pass
            self._proc = None

    def speak(self, text: str, lang: str = "eng", on_done=None):
        """Stop any current speech, then start new speech in background."""
        self.stop()
        self._thread = threading.Thread(
            target=self._speak_worker,
            args=(text, lang, on_done),
            daemon=True,
        )
        self._thread.start()

    def _speak_worker(self, text: str, lang: str, on_done):
        try:
            piper_bin   = self.cfg.get("piper_bin", "")
            rate        = float(self.cfg.get("tts_rate", 1.0))

            # Pick voice based on language
            if lang == "hin":
                model = self.cfg.get("piper_model_hin", "") or self.cfg.get("piper_model_eng", "")
            else:
                model = self.cfg.get("piper_model_eng", "")

            if piper_bin and model and Path(model).is_file():
                self._speak_piper(text, piper_bin, model, rate)
            else:
                self._speak_espeak(text, lang, rate)
        except Exception as e:
            log.error(f"TTS error: {e}")
        finally:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

    def _speak_piper(self, text: str, piper_bin: str, model: str, rate: float):
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            length_scale = str(round(1.0 / max(rate, 0.25), 3))
            piper_cmd = [
                piper_bin,
                "--model", model,
                "--output_file", wav_path,
                "--length-scale", length_scale,
            ]
            proc = subprocess.run(
                piper_cmd,
                input=text, text=True,
                capture_output=True, timeout=45,
            )
            if proc.returncode != 0 or not os.path.getsize(wav_path):
                log.warning("Piper failed, falling back to espeak-ng")
                self._speak_espeak(text, "eng", rate)
                return

            # Play audio (cross-platform)
            if IS_WINDOWS:
                # Use PowerShell to play wav on Windows
                ps_cmd = f'(New-Object Media.SoundPlayer "{wav_path}").PlaySync()'
                with self._lock:
                    self._proc = subprocess.Popen(
                        ["powershell", "-c", ps_cmd],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                self._proc.wait()
            else:
                # Linux: try aplay, then paplay, then ffplay
                for player in [["aplay", "-q", wav_path], ["paplay", wav_path], ["ffplay", "-nodisp", "-autoexit", wav_path]]:
                    if shutil.which(player[0]):
                        with self._lock:
                            self._proc = subprocess.Popen(
                                player,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                        self._proc.wait()
                        break
                else:
                    log.error("No audio player found (aplay/paplay/ffplay)")
        finally:
            if wav_path:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass

    def _speak_espeak(self, text: str, lang: str, rate: float):
        speed = int(145 * rate)
        if lang == "hin":
            cmd = ["espeak-ng", "-v", "hi", "-s", str(speed), text]
        else:
            cmd = ["espeak-ng", "-s", str(speed), "-p", "50", text]

        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak:
            # Windows SAPI fallback
            if IS_WINDOWS:
                ps = f'Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate={int((rate-1)*5)}; $s.Speak("{text.replace(chr(34), chr(39))}")'
                with self._lock:
                    self._proc = subprocess.Popen(
                        ["powershell", "-c", ps],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                self._proc.wait()
            else:
                log.error("No TTS engine found.")
            return

        with self._lock:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        self._proc.wait()


# ─── Crop Overlay ─────────────────────────────────────────────────────────────
class CropOverlay:
    def __init__(self, on_done_callback, theme: str = "dark"):
        self.callback = on_done_callback
        self.start_x = self.start_y = 0
        self.cur_x = self.cur_y = 0
        self.rect_id = None
        self.size_label_id = None
        T = THEMES[theme]

        self.root = tk.Tk()
        self.root.title("ScreenReader")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.30)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#000000")
        self.root.config(cursor="crosshair")

        self.info = tk.Label(
            self.root,
            text="✦  Drag to select text region  •  ESC to cancel",
            bg="#000000", fg="#FF6B00",
            font=("Courier", 13, "bold"),
            pady=8,
        )
        self.info.pack(side=tk.TOP, fill=tk.X)

        self.canvas = tk.Canvas(
            self.root, bg="#000000",
            highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>",            self._on_cancel)

    def run(self):
        self.root.mainloop()

    def _on_press(self, e):
        self.start_x, self.start_y = e.x_root, e.y_root
        self.cur_x,   self.cur_y   = e.x_root, e.y_root
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _on_drag(self, e):
        self.cur_x, self.cur_y = e.x_root, e.y_root
        dx = e.x - (e.x_root - self.start_x)
        dy = e.y - (e.y_root - self.start_y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.size_label_id:
            self.canvas.delete(self.size_label_id)

        x1, y1 = min(dx, e.x), min(dy, e.y)
        x2, y2 = max(dx, e.x), max(dy, e.y)

        self.rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="#FF6B00", width=2,
            fill="#FF6B00", stipple="gray25",
        )
        # Live size display
        w = abs(self.cur_x - self.start_x)
        h = abs(self.cur_y - self.start_y)
        self.size_label_id = self.canvas.create_text(
            x2 + 6, y2 + 6,
            text=f" {w}×{h} ",
            fill="white", anchor="nw",
            font=("Courier", 10, "bold"),
        )

    def _on_release(self, e):
        x1, y1 = min(self.start_x, self.cur_x), min(self.start_y, self.cur_y)
        x2, y2 = max(self.start_x, self.cur_x), max(self.start_y, self.cur_y)
        self.root.destroy()
        if (x2 - x1) > 10 and (y2 - y1) > 10:
            self.callback(x1, y1, x2, y2)
        else:
            log.info("Selection too small, ignored.")

    def _on_cancel(self, e=None):
        self.root.destroy()


# ─── Main GUI ─────────────────────────────────────────────────────────────────
class ScreenReaderApp:
    def __init__(self):
        self.cfg = load_config()

        # Auto-detect Piper if not in config
        if not self.cfg.get("piper_bin"):
            piper_bin, eng, hin = find_piper()
            self.cfg["piper_bin"]       = piper_bin
            self.cfg["piper_model_eng"] = eng
            self.cfg["piper_model_hin"] = hin
            save_config(self.cfg)

        self.tts = TTSEngine(self.cfg)
        self._overlay_open = False
        self._current_text = ""
        self._current_lang = "eng"
        self._status_after = None

        # Hotkey state
        self._keys_down: set = set()

        self._build_ui()
        self._start_hotkey_listener()

        # Check tesseract
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            self._set_status("⚠ Tesseract not found — OCR will not work", "error")

    # ── UI Build ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        T = self._T()
        self.root = tk.Tk()
        self.root.title("ScreenReader")
        self.root.geometry("520x680")
        self.root.resizable(True, True)
        self.root.minsize(420, 580)
        self.root.configure(bg=T["bg"])

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=T["surface"], pady=0)
        hdr.pack(fill=tk.X)

        tk.Label(
            hdr, text="ScreenReader",
            bg=T["surface"], fg=T["accent"],
            font=("Courier", 20, "bold"),
            pady=14, padx=20,
        ).pack(side=tk.LEFT)

        # Theme toggle
        self.theme_btn = tk.Button(
            hdr,
            text="☀" if self.cfg["theme"] == "dark" else "🌙",
            bg=T["surface"], fg=T["text2"],
            font=("Courier", 16), relief="flat", bd=0,
            cursor="hand2",
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side=tk.RIGHT, padx=16)

        # Version badge
        tk.Label(
            hdr, text="v2.0",
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 9),
        ).pack(side=tk.RIGHT, padx=4)

        tk.Frame(self.root, bg=T["accent"], height=2).pack(fill=tk.X)

        # ── Main content ──────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=T["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # ── Capture button (big) ──────────────────────────────────────────────
        self.capture_btn = tk.Button(
            body,
            text="⊹  Capture Region",
            font=("Courier", 14, "bold"),
            bg=T["accent"], fg="white",
            activebackground=T["accent2"], activeforeground="white",
            relief="flat", bd=0, pady=14,
            cursor="hand2",
            command=self._trigger_overlay,
        )
        self.capture_btn.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            body, text="or press  Ctrl + Shift + S  anywhere",
            bg=T["bg"], fg=T["text3"],
            font=("Courier", 9),
        ).pack()

        # ── Settings row ──────────────────────────────────────────────────────
        settings = tk.Frame(body, bg=T["bg"])
        settings.pack(fill=tk.X, pady=(18, 0))

        # Language selector
        lang_frame = tk.Frame(settings, bg=T["surface"], padx=12, pady=10)
        lang_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,8))

        tk.Label(
            lang_frame, text="LANGUAGE",
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 8, "bold"),
        ).pack(anchor="w")

        self.lang_var = tk.StringVar(value=self.cfg.get("ocr_lang", "eng"))
        lang_menu = ttk.Combobox(
            lang_frame,
            textvariable=self.lang_var,
            values=["eng", "hin", "hin+eng"],
            state="readonly", width=11,
            font=("Courier", 11),
        )
        lang_menu.pack(anchor="w", pady=(4, 0))
        lang_menu.bind("<<ComboboxSelected>>", self._on_lang_change)

        # Rate control
        rate_frame = tk.Frame(settings, bg=T["surface"], padx=12, pady=10)
        rate_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            rate_frame, text="SPEED",
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 8, "bold"),
        ).pack(anchor="w")

        rate_row = tk.Frame(rate_frame, bg=T["surface"])
        rate_row.pack(anchor="w", pady=(4,0), fill=tk.X)

        self.rate_label = tk.Label(
            rate_row, text=f"{self.cfg['tts_rate']:.1f}×",
            bg=T["surface"], fg=T["accent"],
            font=("Courier", 12, "bold"), width=4,
        )
        self.rate_label.pack(side=tk.LEFT)

        rate_slider_frame = tk.Frame(rate_row, bg=T["surface"])
        rate_slider_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.rate_slider = tk.Scale(
            rate_slider_frame,
            from_=0.5, to=2.5,
            resolution=0.1, orient=tk.HORIZONTAL,
            bg=T["surface"], fg=T["text"],
            highlightthickness=0, troughcolor=T["surface2"],
            activebackground=T["accent"],
            showvalue=False, bd=0,
            command=self._on_rate_change,
        )
        self.rate_slider.set(self.cfg["tts_rate"])
        self.rate_slider.pack(fill=tk.X)

        # ── Playback controls ─────────────────────────────────────────────────
        ctrl_frame = tk.Frame(body, bg=T["surface"], pady=10, padx=14)
        ctrl_frame.pack(fill=tk.X, pady=(12, 0))

        tk.Label(
            ctrl_frame, text="PLAYBACK",
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 8, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        btns = tk.Frame(ctrl_frame, bg=T["surface"])
        btns.pack(fill=tk.X)

        btn_style = dict(
            bg=T["btn"], fg=T["text"],
            activebackground=T["btn_hover"], activeforeground=T["text"],
            font=("Courier", 12), relief="flat", bd=0,
            padx=10, pady=6, cursor="hand2",
        )

        self.play_btn = tk.Button(
            btns, text="▶  Play Last",
            command=self._play_last,
            **btn_style,
        )
        self.play_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = tk.Button(
            btns, text="■  Stop",
            command=self._stop_speech,
            bg=T["btn"], fg=T["error"],
            activebackground=T["btn_hover"], activeforeground=T["error"],
            font=("Courier", 12), relief="flat", bd=0,
            padx=10, pady=6, cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0,6))

        self.copy_btn = tk.Button(
            btns, text="⎘  Copy Text",
            command=self._copy_to_clipboard,
            **btn_style,
        )
        self.copy_btn.pack(side=tk.LEFT)

        # ── OCR result display ────────────────────────────────────────────────
        result_label_frame = tk.Frame(body, bg=T["bg"])
        result_label_frame.pack(fill=tk.X, pady=(16, 4))

        tk.Label(
            result_label_frame, text="LAST CAPTURED TEXT",
            bg=T["bg"], fg=T["text3"],
            font=("Courier", 8, "bold"),
        ).pack(side=tk.LEFT)

        self.lang_badge = tk.Label(
            result_label_frame, text="",
            bg=T["surface2"], fg=T["accent"],
            font=("Courier", 8, "bold"),
            padx=6, pady=1,
        )
        self.lang_badge.pack(side=tk.RIGHT)

        self.result_box = scrolledtext.ScrolledText(
            body,
            height=7, wrap=tk.WORD,
            bg=T["surface"], fg=T["text"],
            font=("Courier", 11),
            relief="flat", bd=0,
            padx=10, pady=8,
            insertbackground=T["accent"],
            selectbackground=T["accent"],
        )
        self.result_box.pack(fill=tk.BOTH, expand=True)
        self.result_box.insert("1.0", "Captured text will appear here…")
        self.result_box.config(state=tk.DISABLED)

        # ── History ───────────────────────────────────────────────────────────
        hist_header = tk.Frame(body, bg=T["bg"])
        hist_header.pack(fill=tk.X, pady=(14, 4))

        tk.Label(
            hist_header, text="HISTORY",
            bg=T["bg"], fg=T["text3"],
            font=("Courier", 8, "bold"),
        ).pack(side=tk.LEFT)

        tk.Button(
            hist_header, text="Clear",
            bg=T["bg"], fg=T["text3"],
            activebackground=T["bg"], activeforeground=T["error"],
            font=("Courier", 8), relief="flat", bd=0,
            cursor="hand2",
            command=self._clear_history,
        ).pack(side=tk.RIGHT)

        self.history_list = tk.Listbox(
            body, height=4,
            bg=T["surface"], fg=T["text2"],
            font=("Courier", 9),
            relief="flat", bd=0,
            selectbackground=T["surface2"],
            selectforeground=T["text"],
            activestyle="none",
        )
        self.history_list.pack(fill=tk.X)
        self.history_list.bind("<<ListboxSelect>>", self._on_history_select)
        self._refresh_history()

        # ── Status bar ────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=T["border"], height=1).pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready — press Ctrl+Shift+S to capture")
        self.status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 9),
            anchor="w", padx=16, pady=6,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # TTS info
        tts_info = "Piper TTS" if (self.cfg.get("piper_bin") and self.cfg.get("piper_model_eng")) else "espeak-ng"
        tk.Label(
            self.root,
            text=f"TTS: {tts_info}",
            bg=T["surface"], fg=T["text3"],
            font=("Courier", 8),
            anchor="e", padx=16,
        ).place(relx=1.0, rely=1.0, anchor="se")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Theme helpers ─────────────────────────────────────────────────────────
    def _T(self) -> dict:
        return THEMES[self.cfg.get("theme", "dark")]

    def _toggle_theme(self):
        self.cfg["theme"] = "light" if self.cfg["theme"] == "dark" else "dark"
        save_config(self.cfg)
        # Rebuild UI (simplest correct approach for full theme swap)
        self.root.destroy()
        self._build_ui()
        self._set_status("Theme changed.")

    # ── Event handlers ────────────────────────────────────────────────────────
    def _on_lang_change(self, _=None):
        lang = self.lang_var.get()
        self.cfg["ocr_lang"] = lang
        save_config(self.cfg)
        self._set_status(f"Language set to: {lang}")

    def _on_rate_change(self, val):
        rate = float(val)
        self.cfg["tts_rate"] = round(rate, 1)
        self.tts.cfg["tts_rate"] = self.cfg["tts_rate"]
        self.rate_label.config(text=f"{rate:.1f}×")
        save_config(self.cfg)

    def _stop_speech(self):
        self.tts.stop()
        self._set_status("Speech stopped.")

    def _play_last(self):
        if not self._current_text:
            self._set_status("Nothing to replay yet.", "warning")
            return
        self._set_status("▶ Playing…")
        self.tts.speak(
            self._current_text, self._current_lang,
            on_done=lambda: self._set_status("Done."),
        )

    def _copy_to_clipboard(self):
        if not self._current_text:
            self._set_status("Nothing to copy yet.", "warning")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._current_text)
        self._set_status("✓ Copied to clipboard.")

    def _clear_history(self):
        try:
            HISTORY_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        self._refresh_history()
        self._set_status("History cleared.")

    def _on_history_select(self, _=None):
        sel = self.history_list.curselection()
        if not sel:
            return
        idx = sel[0]
        entries = load_history(self.cfg.get("history_limit", 50))
        if idx < len(entries):
            entry = entries[idx]
            text = entry["text"]
            lang = entry.get("lang", "eng")
            self._show_text(text, lang)
            self.tts.speak(text, lang, on_done=lambda: self._set_status("Done."))
            self._set_status(f"▶ Re-reading: {text[:40]}…")

    def _refresh_history(self):
        try:
            self.history_list.delete(0, tk.END)
            entries = load_history(self.cfg.get("history_limit", 50))
            for e in entries:
                preview = e["text"][:60].replace("\n", " ")
                ts = e.get("ts", "")[-8:]  # HH:MM:SS
                lang = e.get("lang", "eng")
                flag = "🇮🇳" if lang == "hin" else "🇬🇧"
                self.history_list.insert(tk.END, f"  {ts}  {flag}  {preview}")
        except Exception:
            pass

    # ── Overlay trigger ───────────────────────────────────────────────────────
    def _trigger_overlay(self):
        if self._overlay_open:
            return
        self._overlay_open = True
        t = threading.Thread(target=self._overlay_thread, daemon=True)
        t.start()

    def _overlay_thread(self):
        try:
            overlay = CropOverlay(
                on_done_callback=self._on_region_selected,
                theme=self.cfg.get("theme", "dark"),
            )
            overlay.run()
        finally:
            self._overlay_open = False

    def _on_region_selected(self, x1, y1, x2, y2):
        log.info(f"Region: ({x1},{y1}) → ({x2},{y2})")
        self.root.after(0, lambda: self._set_status("📷 Capturing…"))
        time.sleep(0.15)

        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
        except Exception as e:
            log.error(f"Screenshot failed: {e}")
            self.root.after(0, lambda: self._set_status("Screenshot failed.", "error"))
            return

        ocr_lang = self.cfg.get("ocr_lang", "eng")
        self.root.after(0, lambda: self._set_status(f"🔍 Running OCR ({ocr_lang})…"))

        text = ocr_image(img, ocr_lang)

        if not text:
            self.root.after(0, lambda: self._set_status("No text found in region.", "warning"))
            self.tts.speak("No text was found in the selected region.", "eng")
            return

        # Detect language if auto
        if ocr_lang == "hin+eng":
            detected_lang = detect_language(text)
        elif ocr_lang == "hin":
            detected_lang = "hin"
        else:
            detected_lang = "eng"

        self._current_text = text
        self._current_lang = detected_lang

        save_history(text, detected_lang)
        self.root.after(0, lambda: self._show_text(text, detected_lang))
        self.root.after(0, lambda: self._refresh_history())
        self.root.after(0, lambda: self._set_status(f"▶ Reading {len(text)} chars…"))

        self.tts.speak(
            text, detected_lang,
            on_done=lambda: self.root.after(0, lambda: self._set_status("Done.")),
        )

    def _show_text(self, text: str, lang: str):
        T = self._T()
        self.result_box.config(state=tk.NORMAL)
        self.result_box.delete("1.0", tk.END)
        self.result_box.insert("1.0", text)
        self.result_box.config(state=tk.DISABLED)

        lang_labels = {"eng": "EN", "hin": "HI", "hin+eng": "HI+EN"}
        self.lang_badge.config(text=f" {lang_labels.get(lang, lang.upper())} ")

    def _set_status(self, msg: str, level: str = "normal"):
        T = self._T()
        color_map = {
            "normal":  T["text3"],
            "success": T["success"],
            "warning": T["warning"],
            "error":   T["error"],
        }
        try:
            self.status_var.set(msg)
            self.status_bar.config(fg=color_map.get(level, T["text3"]))
        except Exception:
            pass

    # ── Hotkey listener ───────────────────────────────────────────────────────
    def _start_hotkey_listener(self):
        if not HAS_PYNPUT:
            log.warning("pynput not installed — global hotkey disabled")
            return

        def on_press(key):
            try:
                self._keys_down.add(key)
            except Exception:
                pass
            ctrl  = pynput_keyboard.Key.ctrl_l in self._keys_down or pynput_keyboard.Key.ctrl_r in self._keys_down
            shift = any(k in self._keys_down for k in (
                pynput_keyboard.Key.shift, pynput_keyboard.Key.shift_l, pynput_keyboard.Key.shift_r
            ))
            s = any(
                pynput_keyboard.KeyCode.from_char(c) in self._keys_down
                for c in ("s", "S")
            )
            if ctrl and shift and s and not self._overlay_open:
                self._trigger_overlay()

        def on_release(key):
            self._keys_down.discard(key)

        self._listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    # ── Run / Close ───────────────────────────────────────────────────────────
    def _on_close(self):
        self.tts.stop()
        save_config(self.cfg)
        if HAS_PYNPUT:
            try:
                self._listener.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    # Wayland warning
    if IS_LINUX and os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        print("⚠  Wayland detected. For best results, launch with:")
        print("   GDK_BACKEND=x11 bash run.sh")

    app = ScreenReaderApp()
    app.run()


if __name__ == "__main__":
    main()
