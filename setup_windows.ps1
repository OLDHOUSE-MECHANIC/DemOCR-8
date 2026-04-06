# ScreenReader v2.0 — Windows Setup Script
# Run once in PowerShell (as Administrator for Tesseract):
#   Set-ExecutionPolicy -Scope CurrentUser Bypass
#   .\setup_windows.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir   = "$ScriptDir\.venv"
$PiperDir  = "$env:LOCALAPPDATA\piper"
$VoicesDir = "$env:APPDATA\piper-voices"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗"
Write-Host "║    ScreenReader v2.0 — Setup for Windows      ║"
Write-Host "╚═══════════════════════════════════════════════╝"
Write-Host ""

# ─── 1. Check Python ─────────────────────────────────────────────────────────
Write-Host "[1] Checking Python..." -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Please install from https://python.org (check 'Add to PATH')" -ForegroundColor Red
    exit 1
}
python --version

# ─── 2. Virtual environment ───────────────────────────────────────────────────
Write-Host "[2] Creating virtual environment..." -ForegroundColor Cyan
python -m venv $VenvDir
& "$VenvDir\Scripts\python.exe" -m pip install --upgrade pip -q
& "$VenvDir\Scripts\pip.exe" install -q Pillow pytesseract pynput numpy
Write-Host "Python packages installed." -ForegroundColor Green

# ─── 3. Tesseract ─────────────────────────────────────────────────────────────
Write-Host "[3] Checking Tesseract..." -ForegroundColor Cyan
$TessPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (-not (Test-Path $TessPath)) {
    Write-Host "Tesseract not found at $TessPath" -ForegroundColor Yellow
    Write-Host "Please download and install from:"
    Write-Host "  https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Cyan
    Write-Host "  → Install to: C:\Program Files\Tesseract-OCR\"
    Write-Host "  → During install, check: Additional language data → Hindi"
    Read-Host "Press Enter after installing Tesseract, then continue"
} else {
    Write-Host "Tesseract found: $TessPath" -ForegroundColor Green
}

# ─── 4. Piper TTS ─────────────────────────────────────────────────────────────
Write-Host "[4] Installing Piper TTS..." -ForegroundColor Cyan
$PiperExe = "$PiperDir\piper.exe"

if (-not (Test-Path $PiperExe)) {
    New-Item -ItemType Directory -Force -Path $PiperDir | Out-Null
    $PiperUrl = "https://github.com/rhasspy/piper/releases/latest/download/piper_windows_amd64.zip"
    $PiperZip = "$PiperDir\piper.zip"
    Write-Host "Downloading Piper from $PiperUrl ..."
    Invoke-WebRequest -Uri $PiperUrl -OutFile $PiperZip
    Expand-Archive -Path $PiperZip -DestinationPath $PiperDir -Force
    Remove-Item $PiperZip
    Write-Host "Piper installed: $PiperExe" -ForegroundColor Green
} else {
    Write-Host "Piper already installed." -ForegroundColor Green
}

# ─── 5. Voice models ──────────────────────────────────────────────────────────
Write-Host "[5] Downloading voice models..." -ForegroundColor Cyan

function Get-Voice($Name, $BaseUrl, $OnnxFile, $SaveDir) {
    if (-not (Test-Path "$SaveDir\$OnnxFile")) {
        New-Item -ItemType Directory -Force -Path $SaveDir | Out-Null
        Write-Host "Downloading $Name voice..."
        try {
            Invoke-WebRequest -Uri "$BaseUrl/$OnnxFile"      -OutFile "$SaveDir\$OnnxFile"
            Invoke-WebRequest -Uri "$BaseUrl/$OnnxFile.json" -OutFile "$SaveDir\$OnnxFile.json"
            Write-Host "$Name voice downloaded." -ForegroundColor Green
        } catch {
            Write-Host "$Name voice download failed: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "$Name voice already present." -ForegroundColor Green
    }
}

$EngDir = "$VoicesDir\en_US\amy"
Get-Voice "English (en_US-amy)" `
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium" `
    "en_US-amy-medium.onnx" $EngDir

$HinDir = "$VoicesDir\hi_IN\female"
Get-Voice "Hindi (hi_IN-female)" `
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/female/medium" `
    "hi_IN-female-medium.onnx" $HinDir

# ─── 6. run.bat launcher ─────────────────────────────────────────────────────
Write-Host "[6] Creating launcher..." -ForegroundColor Cyan
@"
@echo off
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
python "%SCRIPT_DIR%screenreader.py" %*
"@ | Set-Content "$ScriptDir\run.bat"

# Also create a .vbs launcher for no-console-window startup
@"
Set WshShell = WScript.CreateObject("WScript.Shell")
WshShell.Run Chr(34) & WScript.Arguments(0) & Chr(34), 0
Set WshShell = Nothing
"@ | Set-Content "$ScriptDir\run_hidden.vbs"

Write-Host "Launcher: $ScriptDir\run.bat" -ForegroundColor Green

# ─── 7. Summary ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗"
Write-Host "║            Setup Complete! ✓                  ║"
Write-Host "╚═══════════════════════════════════════════════╝"
Write-Host ""
Write-Host "  Launch: double-click run.bat"
Write-Host "  Hotkey: Ctrl + Shift + S (anywhere)"
Write-Host ""
