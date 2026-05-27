"""
DriveSync - Configuration Module
Paths, platform detection, and app configuration.
"""

import os
import platform
from pathlib import Path

# ---------------------------
# Paths
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = BASE_DIR / "music_downloads"
PLAYLIST_DIR = BASE_DIR / "playlists"
THUMBNAIL_DIR = MUSIC_DIR / ".thumbnails"
FRONTEND_DIR = BASE_DIR / "frontend"

# ---------------------------
# Platform
# ---------------------------
IS_WINDOWS = platform.system() == "Windows"

# ---------------------------
# Runtime State
# ---------------------------
# Download progress shared across requests
download_progress = {"current": None, "status": "idle", "percent": 0}

# Ensure directories exist on import
for d in [MUSIC_DIR, PLAYLIST_DIR, THUMBNAIL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Valid audio extensions for import
VALID_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma"}