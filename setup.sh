#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ScreenReader v2.0 — Setup Script (Linux / Debian / Ubuntu)
# Run once: bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PIPER_DIR="$HOME/.local/share/piper"
VOICES_DIR="$HOME/.local/share/piper-voices"
BIN_DIR="$HOME/.local/bin"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "\n${CYAN}──────────────────────────────────────${NC}"; echo -e "${CYAN}$*${NC}"; echo -e "${CYAN}──────────────────────────────────────${NC}"; }

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║     ScreenReader v2.0 — Setup for Linux       ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# ─── 1. System packages ───────────────────────────────────────────────────────
step "1. Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-tk \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    espeak-ng \
    libnotify-bin \
    alsa-utils pulseaudio-utils \
    wget curl xdg-utils \
    2>/dev/null || true
info "System packages installed."

# ─── 2. Python venv ───────────────────────────────────────────────────────────
step "2. Creating Python virtual environment"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip -q
pip install -q \
    Pillow \
    pytesseract \
    pynput \
    numpy
info "Python packages installed."

# ─── 3. Piper TTS binary ─────────────────────────────────────────────────────
step "3. Installing Piper TTS"
PIPER_INSTALLED=false

if command -v piper &>/dev/null || [ -f "$BIN_DIR/piper" ]; then
    info "Piper already installed."
    PIPER_INSTALLED=true
else
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  PIPER_ARCHIVE="piper_linux_x86_64.tar.gz" ;;
        aarch64) PIPER_ARCHIVE="piper_linux_aarch64.tar.gz" ;;
        armv7l)  PIPER_ARCHIVE="piper_linux_armv7l.tar.gz" ;;
        *) warn "Unknown arch $ARCH — skipping Piper."; PIPER_ARCHIVE="" ;;
    esac

    if [[ -n "${PIPER_ARCHIVE:-}" ]]; then
        mkdir -p "$PIPER_DIR" "$BIN_DIR"
        PIPER_URL="https://github.com/rhasspy/piper/releases/latest/download/$PIPER_ARCHIVE"
        info "Downloading Piper: $PIPER_URL"
        if wget -q --show-progress -O "$PIPER_DIR/$PIPER_ARCHIVE" "$PIPER_URL"; then
            tar -xzf "$PIPER_DIR/$PIPER_ARCHIVE" -C "$PIPER_DIR" --strip-components=1
            rm -f "$PIPER_DIR/$PIPER_ARCHIVE"
            chmod +x "$PIPER_DIR/piper"
            ln -sf "$PIPER_DIR/piper" "$BIN_DIR/piper"
            info "Piper installed → $BIN_DIR/piper"
            PIPER_INSTALLED=true
        else
            warn "Piper download failed — will use espeak-ng."
        fi
    fi
fi

# ─── 4. Voice models ──────────────────────────────────────────────────────────
step "4. Downloading voice models"

download_voice() {
    local name="$1"
    local url_base="$2"
    local onnx_file="$3"
    local save_dir="$4"

    if [ -f "$save_dir/$onnx_file" ]; then
        info "$name voice already present."
        return 0
    fi

    mkdir -p "$save_dir"
    info "Downloading $name voice…"
    if wget -q --show-progress -O "$save_dir/$onnx_file"      "$url_base/$onnx_file" && \
       wget -q --show-progress -O "$save_dir/$onnx_file.json" "$url_base/$onnx_file.json"; then
        info "$name voice downloaded."
        return 0
    else
        warn "$name voice download failed."
        rm -f "$save_dir/$onnx_file" "$save_dir/$onnx_file.json"
        return 1
    fi
}

if $PIPER_INSTALLED; then
    # English — Amy medium
    ENG_DIR="$VOICES_DIR/en_US/amy"
    download_voice \
        "English (en_US-amy-medium)" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium" \
        "en_US-amy-medium.onnx" \
        "$ENG_DIR" || true

    # Hindi — if available on HuggingFace
    HIN_DIR="$VOICES_DIR/hi_IN/female"
    # Try downloading Hindi voice (may not exist; gracefully skip)
    download_voice \
        "Hindi (hi_IN-female-medium)" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/female/medium" \
        "hi_IN-female-medium.onnx" \
        "$HIN_DIR" || warn "Hindi Piper voice not available — Hindi will use espeak-ng -v hi"
fi

# ─── 5. run.sh launcher ───────────────────────────────────────────────────────
step "5. Creating launcher"
cat > "$SCRIPT_DIR/run.sh" << 'LAUNCH'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
# Wayland workaround
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
    echo "⚠  Wayland detected. Forcing X11 backend for screengrab."
    export GDK_BACKEND=x11
fi
exec python3 "$SCRIPT_DIR/screenreader.py" "$@"
LAUNCH
chmod +x "$SCRIPT_DIR/run.sh"
info "Launcher: $SCRIPT_DIR/run.sh"

# ─── 6. .desktop entry ───────────────────────────────────────────────────────
step "6. Installing desktop entry"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/screenreader.desktop" << DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=ScreenReader
Comment=Crop screen → OCR → Speak (Ctrl+Shift+S) | Hindi+English
Exec=$SCRIPT_DIR/run.sh
Icon=$SCRIPT_DIR/icon.png
Terminal=false
StartupNotify=true
Categories=Utility;Accessibility;
Keywords=ocr;tts;screen;read;accessibility;hindi;english;
DESK

chmod +x "$DESKTOP_DIR/screenreader.desktop"
xdg-desktop-menu forceupdate 2>/dev/null || true
info ".desktop entry installed."

# ─── 7. Autostart ────────────────────────────────────────────────────────────
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/screenreader.desktop" << AUTO
[Desktop Entry]
Type=Application
Name=ScreenReader
Exec=$SCRIPT_DIR/run.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTO
info "Autostart entry created."

# ─── 8. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║            Setup Complete! ✓                  ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""
echo -e "  ${GREEN}✓${NC} OCR         : $(tesseract --version 2>&1 | head -1)"
echo -e "  ${GREEN}✓${NC} OCR Hindi   : $(tesseract --list-langs 2>/dev/null | grep -q hin && echo 'hin ✓' || echo 'not installed')"
if $PIPER_INSTALLED; then
    echo -e "  ${GREEN}✓${NC} Piper TTS   : $(command -v piper 2>/dev/null || echo $BIN_DIR/piper)"
    [ -f "$ENG_DIR/en_US-amy-medium.onnx" ] && echo -e "  ${GREEN}✓${NC} EN voice    : en_US-amy-medium"
    [ -f "$HIN_DIR/hi_IN-female-medium.onnx" ] && echo -e "  ${GREEN}✓${NC} HI voice    : hi_IN-female-medium"
else
    echo -e "  ${YELLOW}⚠${NC} Piper not available — using espeak-ng"
fi
echo -e "  ${GREEN}✓${NC} Launcher    : $SCRIPT_DIR/run.sh"
echo ""
echo "  ▶  Launch now  :  bash $SCRIPT_DIR/run.sh"
echo "  ▶  App menu    :  Search 'ScreenReader'"
echo "  ▶  Hotkey      :  Ctrl + Shift + S  (anywhere)"
echo ""
