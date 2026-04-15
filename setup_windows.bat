@echo off
:: ScreenReader — Windows setup
:: Just double-click this file. No PowerShell. No registry changes.
:: Requires: Python 3.x installed from python.org (with "Add to PATH" ticked)

echo.
echo   ScreenReader — Windows setup
echo   ==============================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found.
    echo   Download from: https://www.python.org/downloads/
    echo   Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: pip not found. Reinstall Python with pip included.
    pause
    exit /b 1
)

echo   Installing Python packages...
pip install Pillow pytesseract pynput --quiet
if errorlevel 1 (
    echo   ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo   Python packages installed.
echo.
echo   ── Tesseract OCR ──────────────────────────────────────────────────
echo   You need Tesseract installed separately:
echo.
echo     1. Go to:  https://github.com/UB-Mannheim/tesseract/wiki
echo     2. Download and run the installer (tesseract-ocr-w64-setup-*.exe)
echo     3. During install, tick "Add to PATH"
echo     4. Come back here and press any key to continue.
echo.
pause

:: Verify tesseract
tesseract --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   WARNING: tesseract not found in PATH.
    echo   If you just installed it, close this window and re-open.
    echo   Or add Tesseract manually to PATH:
    echo     C:\Program Files\Tesseract-OCR
    echo.
    pause
)

echo.
echo   ── Piper TTS ──────────────────────────────────────────────────────
echo   For natural voice (optional but recommended):
echo.
echo     1. Go to: https://github.com/rhasspy/piper/releases/latest
echo     2. Download: piper_windows_amd64.zip
echo     3. Extract the 'piper' folder next to this setup file
echo     4. Download a voice from:
echo        https://huggingface.co/rhasspy/piper-voices
echo        (Recommended: en/en_US/amy/medium — grab .onnx + .onnx.json)
echo     5. Put the voice files in the 'piper' folder too
echo.
echo   If you skip this, the app will use Windows built-in TTS instead.
echo.
pause

echo.
echo   ── Creating launcher ──────────────────────────────────────────────

:: Write run.bat next to this file
set HERE=%~dp0
echo @echo off > "%HERE%run.bat"
echo python "%HERE%screenreader.py" >> "%HERE%run.bat"

echo   Created run.bat
echo.
echo   ── Done! ──────────────────────────────────────────────────────────
echo.
echo   To use ScreenReader:
echo     Double-click  run.bat
echo.
echo   Or right-click run.bat and choose
echo   "Create shortcut" to put it on your desktop.
echo.
pause
