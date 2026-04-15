#!/usr/bin/env bash
# ScreenReader — setup for Debian Trixie
# Run once: bash setup.sh
# Creates run.sh and a .desktop launcher. Nothing auto-starts.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PIPER_DIR="$HOME/.local/share/piper"
VOICES_DIR="$HOME/.local/share/piper-voices"
BIN="$HOME/.local/bin"

G='\033[0;32m'; Y='\033[1;33m'; N='\033[0m'
info() { echo -e "${G}[info]${N} $*"; }
warn() { echo -e "${Y}[warn]${N} $*"; }

echo ""
echo "  ScreenReader — setup"
echo "  ─────────────────────"

# 1. System packages
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-tk \
    tesseract-ocr tesseract-ocr-eng \
    espeak-ng alsa-utils libnotify-bin wget

# 2. Python venv
info "Setting up Python environment..."
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip -q
pip install -q Pillow pytesseract pynput
deactivate

# 3. Piper binary
PIPER_OK=false
if command -v piper &>/dev/null; then
    info "Piper already installed."
    PIPER_OK=true
else
    info "Downloading Piper TTS..."
    mkdir -p "$PIPER_DIR" "$BIN"
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  ARC="piper_linux_x86_64.tar.gz" ;;
        aarch64) ARC="piper_linux_aarch64.tar.gz" ;;
        *)       warn "Unknown arch $ARCH — skipping Piper, will use espeak-ng."; ARC="" ;;
    esac
    if [[ -n "$ARC" ]]; then
        URL="https://github.com/rhasspy/piper/releases/latest/download/$ARC"
        if wget -q --show-progress -O "$PIPER_DIR/$ARC" "$URL"; then
            tar -xzf "$PIPER_DIR/$ARC" -C "$PIPER_DIR" --strip-components=1
            rm -f "$PIPER_DIR/$ARC"
            chmod +x "$PIPER_DIR/piper"
            ln -sf "$PIPER_DIR/piper" "$BIN/piper"
            info "Piper installed."
            PIPER_OK=true
        else
            warn "Piper download failed — will use espeak-ng."
        fi
    fi
fi

# 4. Voice model
if $PIPER_OK; then
    if find "$VOICES_DIR" -name "*.onnx" 2>/dev/null | grep -q .; then
        info "Voice model already present."
    else
        info "Downloading en_US-amy-medium voice..."
        mkdir -p "$VOICES_DIR/en_US/amy"
        BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium"
        ONNX="$VOICES_DIR/en_US/amy/en_US-amy-medium.onnx"
        JSON="$VOICES_DIR/en_US/amy/en_US-amy-medium.onnx.json"
        if wget -q --show-progress -O "$ONNX" "$BASE/en_US-amy-medium.onnx" && \
           wget -q --show-progress -O "$JSON" "$BASE/en_US-amy-medium.onnx.json"; then
            info "Voice downloaded."
        else
            warn "Voice download failed — will use espeak-ng."
            rm -f "$ONNX" "$JSON"
        fi
    fi
fi

# 5. run.sh launcher
cat > "$SCRIPT_DIR/run.sh" << RUN
#!/usr/bin/env bash
source "\$(dirname "\$0")/.venv/bin/activate"
exec python3 "\$(dirname "\$0")/screenreader.py" "\$@"
RUN
chmod +x "$SCRIPT_DIR/run.sh"

# 6. .desktop entry (app menu only — no autostart)
DESK="$HOME/.local/share/applications/screenreader.desktop"
mkdir -p "$(dirname "$DESK")"
cat > "$DESK" << DESKEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ScreenReader
Comment=Select screen region and read it aloud
Exec=$SCRIPT_DIR/run.sh
Terminal=false
Categories=Utility;Accessibility;
DESKEOF
chmod +x "$DESK"
xdg-desktop-menu forceupdate 2>/dev/null || true

echo ""
echo "  ─────────────────────"
echo "  Done."
echo ""
echo "  To launch:  bash $SCRIPT_DIR/run.sh"
echo "  Or search 'ScreenReader' in your app menu."
echo ""
