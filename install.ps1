# =============================================================================
# DriveSync Installer for Windows (PowerShell)
# =============================================================================
# This script creates a Python virtual environment and installs all dependencies.

param(
    [switch]$NoFfmpeg
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DriveSync - Windows Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check Python
$PythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = $cmd
            break
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host "❌ Python not found. Please install Python 3.9+ from:" -ForegroundColor Red
    Write-Host "   https://www.python.org/downloads/"
    Write-Host ""
    Write-Host "   Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    exit 1
}

$PyVersion = & $PythonCmd --version 2>&1
Write-Host "✅ Found Python: $PyVersion" -ForegroundColor Green

# Check ffmpeg
if (-not $NoFfmpeg) {
    try {
        $ffVer = & ffmpeg -version 2>&1
        Write-Host "✅ Found ffmpeg" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  ffmpeg not found." -ForegroundColor Yellow
        Write-Host "   Download from: https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials.zip)"
        Write-Host "   Extract and add the 'bin' folder to your PATH."
        Write-Host "   Or use: winget install Gyan.FFmpeg" -ForegroundColor Cyan
        Write-Host ""
        $choice = Read-Host "   Continue without ffmpeg? (y/N)"
        if ($choice -ne "y" -and $choice -ne "Y") {
            exit 1
        }
    }
}

# Create virtual environment
Write-Host ""
Write-Host "📦 Creating Python virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "   Removing existing virtual environment..."
    Remove-Item -Recurse -Force "venv"
}

# Try creating venv
try {
    & $PythonCmd -m venv venv
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to create virtual environment." -ForegroundColor Red
    Write-Host "   Try installing: pip install virtualenv"
    exit 1
}

# Activate and install dependencies
Write-Host ""
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow

$Activate = Join-Path $ScriptDir "venv\Scripts\Activate.ps1"
& $Activate

# Upgrade pip
pip install --upgrade pip

# Install core dependencies
Write-Host "   Installing Flask, yt-dlp, mutagen, etc..." -ForegroundColor Gray
pip install flask flask-cors yt-dlp mutagen pillow requests

# Verify installation
Write-Host ""
Write-Host "🔍 Verifying installation..." -ForegroundColor Yellow
try {
    python -c "
import flask
import yt_dlp
import mutagen
from PIL import Image
import requests
print('✅ Flask:', flask.__version__)
print('✅ yt-dlp:', yt_dlp.__version__)
print('✅ Mutagen:', mutagen.__version__)
print('✅ Pillow:', Image.__version__)
print('✅ Requests:', requests.__version__)
"
    Write-Host "✅ All dependencies installed successfully!" -ForegroundColor Green
} catch {
    Write-Host "❌ Some packages failed to verify." -ForegroundColor Red
    Write-Host "   Check the error above and try running: pip install -r requirements.txt"
}

# Create directories
New-Item -ItemType Directory -Force -Path "music_downloads\.thumbnails" | Out-Null
New-Item -ItemType Directory -Force -Path "playlists" | Out-Null

# Create a simple batch launcher
@"
@echo off
REM DriveSync Launcher for Windows
cd /d "%~dp0"
if not exist "venv" (
    echo Virtual environment not found. Run install.ps1 first.
    pause
    exit /b 1
)
call venv\Scripts\activate
echo 🎵 Starting DriveSync...
python backend\drivesync.py %*
if errorlevel 1 (
    echo.
    echo Press any key to exit...
    pause
)
"@ | Out-File -FilePath "run.bat" -Encoding ASCII

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ DriveSync installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the server:" -ForegroundColor White
Write-Host "  run.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "Or manually:" -ForegroundColor White
Write-Host "  venv\Scripts\activate" -ForegroundColor Gray
Write-Host "  python backend\drivesync.py" -ForegroundColor Gray
Write-Host ""
Write-Host "Then open http://localhost:5000 in your browser" -ForegroundColor White