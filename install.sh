#!/usr/bin/env bash
# =============================================================================
# DriveSync Installer for Linux (Raspberry Pi / Ubuntu / Debian)
# =============================================================================
# This script creates a Python virtual environment and installs all dependencies.
#
# Usage:
#   ./install.sh              - Install dependencies only
#   ./install.sh --service    - Install dependencies + create systemd service
#   ./install.sh --help       - Show this help
# =============================================================================

set -e

# ── Parse arguments ─────────────────────────────────────────────────────
CREATE_SERVICE=false
SERVICE_USER=""
SERVICE_PORT=5000

usage() {
    echo "DriveSync Installer"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --service             Install and create a systemd service for auto-start on boot"
    echo "  --user <username>     User to run the service as (default: current user)"
    echo "  --port <port>         Port for the web server (default: 5000)"
    echo "  --help                Show this help message"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --service)
            CREATE_SERVICE=true
            shift
            ;;
        --user)
            SERVICE_USER="$2"
            shift 2
            ;;
        --port)
            SERVICE_PORT="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

echo "========================================"
echo "  DriveSync - Linux Installer"
echo "========================================"
echo ""

# Navigate to project root (directory where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Determine service user
if [ -z "$SERVICE_USER" ]; then
    SERVICE_USER=$(whoami)
fi

# Check Python availability
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &> /dev/null; then
        PYTHON=$cmd
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Python not found. Please install Python 3.9+"
    echo "   sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

echo "✅ Found Python: $($PYTHON --version)"

# Check for ffmpeg (required for audio conversion)
if command -v ffmpeg &> /dev/null; then
    echo "✅ Found ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "⚠️  ffmpeg not found. Installing..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    elif command -v pacman &> /dev/null; then
        sudo pacman -S ffmpeg
    elif command -v dnf &> /dev/null; then
        sudo dnf install ffmpeg
    else
        echo "⚠️  Could not install ffmpeg automatically."
        echo "   Install it manually: sudo apt install ffmpeg"
    fi
fi

# Create virtual environment
echo ""
echo "📦 Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "   Virtual environment already exists. Removing..."
    rm -rf venv
fi

$PYTHON -m venv venv
echo "✅ Virtual environment created"

# Activate and install dependencies
echo ""
echo "📦 Installing Python dependencies..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install core dependencies
pip install flask flask-cors yt-dlp mutagen pillow requests langid

# Install ffmpeg-python for cross-platform support
pip install ffmpeg-python

# Check that key packages installed correctly
echo ""
echo "🔍 Verifying installation..."
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
" 2>&1 || {
    echo "❌ Some packages failed to install. Trying pip install individually..."
    pip install flask==3.1.3 || pip install flask
    pip install yt-dlp mutagen pillow requests
}

# Create directories
mkdir -p music_downloads playlists
mkdir -p music_downloads/.thumbnails

# Create .gitkeep files
touch music_downloads/.gitkeep playlists/.gitkeep music_downloads/.thumbnails/.gitkeep

echo ""
echo "========================================"
echo "✅ DriveSync installation complete!"
echo "========================================"
echo ""
echo "To start the server:"
echo "  cd $(pwd)"
echo "  source venv/bin/activate"
echo "  python backend/drivesync.py"
echo ""
echo "Or use the launch script:"
echo "  ./run.sh"
echo ""

# Create run script
cat > run.sh << 'RUNEOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run install.sh first."
    exit 1
fi

source venv/bin/activate
echo "🎵 Starting DriveSync..."
python backend/main.py "$@"
deactivate
RUNEOF

chmod +x run.sh
echo "✅ Created run.sh launcher"

# ── Systemd Service ─────────────────────────────────────────────────────
if [ "$CREATE_SERVICE" = true ]; then
    echo ""
    echo "⏱️  Creating systemd service for auto-start on boot..."
    SERVICE_NAME="drivesync"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    cat > /tmp/${SERVICE_NAME}.service << SERVICEEOF
[Unit]
Description=DriveSync - Music Manager
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/venv/bin/python ${SCRIPT_DIR}/backend/main.py --host 0.0.0.0 --port ${SERVICE_PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

    sudo mv /tmp/${SERVICE_NAME}.service "$SERVICE_FILE"
    sudo chmod 644 "$SERVICE_FILE"

    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable ${SERVICE_NAME}.service

    echo ""
    echo "========================================"
    echo "✅ Systemd service created!"
    echo "========================================"
    echo ""
    echo "Service name: ${SERVICE_NAME}"
    echo "Service file: ${SERVICE_FILE}"
    echo "User:         ${SERVICE_USER}"
    echo "Port:         ${SERVICE_PORT}"
    echo ""
    echo "Commands:"
    echo "  sudo systemctl start  ${SERVICE_NAME}   # Start now"
    echo "  sudo systemctl stop   ${SERVICE_NAME}   # Stop"
    echo "  sudo systemctl status ${SERVICE_NAME}   # Check status"
    echo "  sudo journalctl -u    ${SERVICE_NAME}   # View logs"
    echo ""
    echo "The service will auto-start on every boot."
    echo ""
    echo "⚠️  You may need to reboot or start the service manually:"
    echo "   sudo systemctl start ${SERVICE_NAME}"
fi
