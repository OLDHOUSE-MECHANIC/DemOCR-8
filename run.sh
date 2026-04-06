#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
# Wayland workaround
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
    echo "⚠  Wayland detected. Forcing X11 backend for screengrab."
    export GDK_BACKEND=x11
fi
exec python3 "$SCRIPT_DIR/screenreader.py" "$@"
