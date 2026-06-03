"""
DriveSync - Configuration Module
Paths, platform detection, and app configuration.
"""

import os
import platform
import shutil
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
# Extra library locations (configured via env var or config file)
# ---------------------------
# Users can set DRIVESYNC_MUSIC_DIRS env var to a comma-separated list of paths
# e.g. DRIVESYNC_MUSIC_DIRS=/mnt/usb1/music,/mnt/usb2/music
_extra_dirs = os.environ.get("DRIVESYNC_MUSIC_DIRS", "")
EXTRA_MUSIC_DIRS = [Path(p.strip()) for p in _extra_dirs.split(",") if p.strip()]

# ---------------------------
# Platform
# ---------------------------
IS_WINDOWS = platform.system() == "Windows"

# ---------------------------
# Runtime State (shared across all users/requests)
# ---------------------------
download_progress = {
    "current": None,          # Current song title / filename
    "status": "idle",         # idle, starting, downloading, processing, completed, error, cancelled, cancelling
    "percent": 0,             # Overall progress (0-100)
    # Playlist-specific fields
    "is_playlist": False,     # True if currently downloading a playlist
    "total_songs": 0,         # Total songs in the playlist
    "current_song_index": 0,  # 1-based index of current song
    "current_song_name": "",  # Name of current song being downloaded
    "song_percent": 0,        # Progress of current individual song (0-100)
    "downloaded_count": 0,    # Successfully downloaded so far
    "error_count": 0,         # Failed so far
    "errors": [],             # List of error messages
    "url": "",                # The URL being downloaded
    # Download management
    "action": None,           # Set to "cancel" to signal cancellation
}

# Ensure directories exist on import
for d in [MUSIC_DIR, PLAYLIST_DIR, THUMBNAIL_DIR]:
    d.mkdir(parents=True, exist_ok=True)
for d in EXTRA_MUSIC_DIRS:
    d.mkdir(parents=True, exist_ok=True)

# Valid audio extensions for import
VALID_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma"}


def get_all_music_dirs():
    """Return list of all directories where music is stored (local + extras)."""
    dirs = [MUSIC_DIR]
    dirs.extend(EXTRA_MUSIC_DIRS)
    return dirs


def get_storage_info():
    """Return disk usage info for each music directory."""
    info = []
    seen = set()
    for d in get_all_music_dirs():
        resolved = str(d.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            usage = shutil.disk_usage(d)
            mp3_count = len(list(d.glob("*.mp3")))
            info.append({
                "path": str(d),
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "song_count": mp3_count,
            })
        except Exception:
            pass
    return info