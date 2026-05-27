"""
DriveSync - Drive/Disk Export Module
Cross-platform detection of removable drives and playlist export.
Supports custom sub-folders and management of existing playlist folders.
"""

import os
import re
import shutil
from pathlib import Path

from config import MUSIC_DIR, IS_WINDOWS
from playlist import get_playlist


# ── Detection ──────────────────────────────────────────────────────────

def find_removable_drives():
    """Return a list of removable drive mount-points (e.g. ``D:\\`` or ``/media/pi/``)."""
    if IS_WINDOWS:
        return _windows_drives()
    return _linux_mounts()


def _windows_drives():
    """Detect removable drives via GetDriveTypeW."""
    import string
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive) and drive.upper() != "C:\\":
            try:
                import ctypes
                dtype = ctypes.windll.kernel32.GetDriveTypeW(drive)  # 2 = DRIVE_REMOVABLE
                if dtype == 2:
                    drives.append(drive)
            except Exception:
                drives.append(drive)
    return drives


def _linux_mounts():
    """Detect removable drives from common mount points and df output."""
    mounts = set()
    user = os.environ.get("USER", "")

    for base in [Path(f"/media/{user}"), Path("/media"), Path("/mnt"),
                 Path(f"/run/media/{user}")]:
        if base.exists():
            for item in base.iterdir():
                if item.is_dir() and item.name.upper() != "CDROM":
                    mounts.add(str(item))

    try:
        import subprocess
        result = subprocess.run(["df", "-h"], capture_output=True, text=True)
        for line in result.stdout.split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[5].startswith(("/media/", "/mnt/")):
                mounts.add(parts[5])
    except Exception:
        pass

    return list(mounts)


def get_drive_info():
    """Return a list of dicts with capacity info for each removable drive."""
    info = []
    for drive in find_removable_drives():
        try:
            usage = shutil.disk_usage(drive)
            try:
                files = len(list(Path(drive).glob("*")))
            except Exception:
                files = 0
            info.append({
                "drive": drive,
                "label": drive,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "files": files,
            })
        except Exception:
            pass
    return info


# ── List existing playlist folders on a drive ──────────────────────────

def list_playlist_folders(drive_path, subfolder=""):
    """
    List folders on the given drive that look like they were created by DriveSync
    (i.e. contain MP3 files). Returns a list of {name, path, song_count, size}.
    """
    base = Path(drive_path)
    if subfolder:
        base = base / subfolder

    if not base.exists():
        return []

    folders = []
    for item in sorted(base.iterdir()):
        if item.is_dir():
            mp3_files = list(item.glob("*.mp3"))
            if mp3_files:
                folders.append({
                    "name": item.name,
                    "path": str(item),
                    "song_count": len(mp3_files),
                    "size": sum(f.stat().st_size for f in mp3_files),
                })
    return folders


def delete_playlist_folder(folder_path):
    """Delete a folder and its contents from the drive."""
    path = Path(folder_path)
    if path.exists() and path.is_dir():
        shutil.rmtree(str(path))
        return True
    return False


# ── Export ─────────────────────────────────────────────────────────────

def export_playlist(playlist_id, drive_path, subfolder="", shuffle_prefix=False):
    """
    Create a folder named after the playlist on the given drive/subfolder
    and copy all songs into it. Optionally adds a ``001_``, ``002_`` … prefix.
    """
    playlist = get_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found"}

    drives = find_removable_drives()
    if drive_path not in drives and not any(drive_path.startswith(d) for d in drives):
        return {"error": f"Drive not found at {drive_path}"}

    # Build destination path
    name = re.sub(r'[<>:"/\\|?*\s]', "_", playlist["name"])
    dest = Path(drive_path)
    if subfolder:
        dest = dest / subfolder
    dest = dest / name

    # Ensure parent exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Clean existing folder
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.mkdir(parents=True, exist_ok=True)

    songs = playlist.get("songs", [])
    copied = 0
    errors = []

    for i, ref in enumerate(songs):
        src = MUSIC_DIR / ref
        if not src.exists():
            src = Path(ref)
        if not src.exists():
            errors.append(f"Not found: {ref}")
            continue

        try:
            fname = f"{i+1:03d}_{src.name}" if shuffle_prefix else src.name
            shutil.copy2(str(src), str(dest / fname))
            copied += 1
        except Exception as exc:
            errors.append(f"Copy failed for {ref}: {exc}")

    return {
        "success": True,
        "playlist": playlist["name"],
        "sd_path": str(dest),
        "copied": copied,
        "total": len(songs),
        "errors": errors,
    }