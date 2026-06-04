$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DriveSync - Windows Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ---- Check Python ----

Write-Host "Checking for Python..." -ForegroundColor Yellow
$PythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = $cmd
            break
        }
    } catch {
        continue
    }
}

if (-not $PythonCmd) {
    Write-Host "Python not found. Please install Python 3.9+ from:" -ForegroundColor Red
    Write-Host "  https://python.org"
    exit 1
}

$PyVersion = & $PythonCmd --version 2>&1
Write-Host "Found Python: $PyVersion" -ForegroundColor Green

# ---- Check FFmpeg ----

Write-Host "Checking for FFmpeg..." -ForegroundColor Yellow
try {
    $ffVer = & ffmpeg -version 2>&1
    Write-Host "Found FFmpeg" -ForegroundColor Green
} catch {
    Write-Host "FFmpeg not found. Download from:" -ForegroundColor Yellow
    Write-Host "  https://gyan.dev"
    Write-Host ""
    $choice = Read-Host "Continue without FFmpeg? (y/N)"
    if ($choice -ne "y" -and $choice -ne "Y") {
        exit 1
    }
}

# ---- Create virtual environment ----

Write-Host ""
Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  Removing old virtual environment..."
    Remove-Item -Recurse -Force "venv" -ErrorAction SilentlyContinue
}

& $PythonCmd -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "venv/Scripts/python.exe")) {
    Write-Host "Virtual environment was not created properly" -ForegroundColor Red
    exit 1
}
Write-Host "Virtual environment created" -ForegroundColor Green

# ---- Install dependencies ----

Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow

# Use a string array joined by slashes to guarantee compatibility across all PowerShell versions
$VenvPip = "$ScriptDir\venv\Scripts\pip.exe"
$VenvPython = "$ScriptDir\venv\Scripts\python.exe"

Write-Host "  Upgrading pip..."
# Temporarily allow errors so pip warnings do not crash the script
$OldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $VenvPython -m pip install --upgrade pip > $null 2>&1
$ErrorActionPreference = $OldPreference

Write-Host "  Installing flask, yt-dlp, mutagen, pillow, requests, langid..."
& $VenvPip install flask flask-cors yt-dlp mutagen pillow requests langid 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Package installation failed" -ForegroundColor Red
    Write-Host "Try manually: $VenvPip install -r requirements.txt"
    exit 1
}

# ---- Verify installation ----
# Write a temp Python script to avoid all PowerShell quoting issues

Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow

$verifyFile = "$ScriptDir\verify_install.py"
Clear-Content $verifyFile -Force -ErrorAction SilentlyContinue

# Using a modern, bulletproof metadata approach that won't break on library internal API changes
Add-Content $verifyFile "import importlib.metadata"
Add-Content $verifyFile "packages = ['flask', 'flask-cors', 'yt-dlp', 'mutagen', 'pillow', 'requests']"
Add-Content $verifyFile "for pkg in packages:"
Add-Content $verifyFile "    try:"
Add-Content $verifyFile "        ver = importlib.metadata.version(pkg)"
Add-Content $verifyFile "        print(f'  {pkg.capitalize()}: {ver}')"
Add-Content $verifyFile "    except importlib.metadata.PackageNotFoundError:"
Add-Content $verifyFile "        print(f'  {pkg.capitalize()}: FAILED TO IMPORT')"
Add-Content $verifyFile "        exit(1)"

# Execute script with warnings silenced
$output = & $VenvPython -W ignore $verifyFile 2>&1
Remove-Item $verifyFile -Force -ErrorAction SilentlyContinue

# If any package is missing, the Python script exits with code 1
if ($LASTEXITCODE -eq 0) {
    Write-Host $output -ForegroundColor Gray
    Write-Host "All dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host $output -ForegroundColor Red
    Write-Host "Some packages failed to verify" -ForegroundColor Red
    Write-Host "Try manually: pip install -r requirements.txt"
}


# ---- Create directories ----

Write-Host ""
Write-Host "Creating data directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "music_downloads/.thumbnails" | Out-Null
New-Item -ItemType Directory -Force -Path "playlists" | Out-Null
Write-Host "Directories created" -ForegroundColor Green

# ---- Create batch launcher ----

Write-Host ""
Write-Host "Creating launcher (run.bat)..." -ForegroundColor Yellow

Clear-Content "run.bat" -Force -ErrorAction SilentlyContinue
Add-Content "run.bat" "@echo off"
Add-Content "run.bat" 'cd /d "%~dp0"'
Add-Content "run.bat" 'if not exist "venv\Scripts\python.exe" ('
Add-Content "run.bat" "    echo Virtual environment not found. Run install.ps1 first."
Add-Content "run.bat" "    pause"
Add-Content "run.bat" "    exit /b 1"
Add-Content "run.bat" ")"
Add-Content "run.bat" "echo Starting DriveSync..."
Add-Content "run.bat" 'call venv\Scripts\activate'
Add-Content "run.bat" "python backend\main.py %*"
Add-Content "run.bat" "if errorlevel 1 ("
Add-Content "run.bat" "    echo."
Add-Content "run.bat" "    echo Press any key to exit..."
Add-Content "run.bat" "    pause"
Add-Content "run.bat" ")"

Write-Host "Created run.bat" -ForegroundColor Green

# ---- Done ----

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "DriveSync installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "To start the server:" -ForegroundColor White
Write-Host "  .\run.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "Or manually:" -ForegroundColor White
Write-Host "  venv\Scripts\activate" -ForegroundColor Gray
Write-Host "  python backend\main.py" -ForegroundColor Gray
Write-Host ""
Write-Host "Then open http://localhost:5000 in your browser" -ForegroundColor White
Write-Host ""

Write-Host "Your LAN IP:" -ForegroundColor White
$ip = ipconfig | Select-String -Pattern "IPv4.*: (\d+\.\d+\.\d+\.\d+)"
if ($ip) {
    $ip.Matches.Groups.Value
} else {
    Write-Host "(could not detect automatically)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "Then open http://[YOUR_IP]:5000 from other devices" -ForegroundColor Cyan
