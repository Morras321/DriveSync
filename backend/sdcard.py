"""
DriveSync - Drive/Disk Export Module
Cross-platform detection of removable drives and playlist export.
Supports custom sub-folders and management of existing playlist folders.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from config import MUSIC_DIR, IS_WINDOWS
from playlist import get_playlist


# ── Detection ──────────────────────────────────────────────────────────

def find_removable_drives():
    """
    Return a list of drive mount-points (e.g. ``D:\\`` or ``/media/pi/SD_CARD``).
    On Linux uses ``lsblk`` (preferred) with ``df`` fallback, also scans common
    mount directories.
    """
    if IS_WINDOWS:
        return _windows_drives()
    return _linux_drives()


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


def _get_all_mounts_via_lsblk():
    """
    Use ``lsblk`` to list all mounted filesystems.
    Returns a list of mount-point paths.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-o", "MOUNTPOINT", "-l", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            mounts = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and line != "" and os.path.exists(line):
                    mounts.append(line)
            return mounts
    except FileNotFoundError:
        pass  # lsblk not installed
    except Exception as exc:
        print(f"lsblk failed: {exc}")
    return []


def _get_all_mounts_via_findmnt():
    """
    Fallback: use ``findmnt`` (more widely available).
    """
    try:
        result = subprocess.run(
            ["findmnt", "-o", "TARGET", "-l", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            mounts = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and line != "" and os.path.exists(line):
                    mounts.append(line)
            return mounts
    except Exception:
        pass
    return []


def _get_all_mounts_via_df():
    """
    Last-resort fallback: parse ``df -h`` output.
    Filters to only real filesystems (skips tmpfs, devtmpfs, etc.).
    """
    try:
        result = subprocess.run(
            ["df", "-h", "-t", "ext4", "-t", "ext3", "-t", "ext2",
             "-t", "vfat", "-t", "exfat", "-t", "ntfs", "-t", "fuseblk",
             "-t", "btrfs", "-t", "xfs"],
            capture_output=True, text=True, timeout=5,
        )
        mounts = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 6:
                mount = parts[5]
                if mount and os.path.exists(mount):
                    mounts.append(mount)
        return mounts
    except Exception:
        return []


def _get_common_mount_dirs():
    """
    Scan well-known directories where removable drives are mounted.
    Includes auto-detection of the current user's name.
    """
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "pi"
    scan_dirs = [
        Path(f"/media/{user}"),
        Path("/media"),
        Path("/mnt"),
        Path(f"/run/media/{user}"),
        Path("/run/media"),
    ]

    found = set()
    for base in scan_dirs:
        if base.exists():
            try:
                for item in base.iterdir():
                    if item.is_dir():
                        found.add(str(item.resolve()))
            except PermissionError:
                pass
    return list(found)


def _is_removable(path_str):
    """
    Heuristic: a mount point is probably a removable drive if it lives
    under ``/media``, ``/mnt``, ``/run/media``, or is NOT the root ``/``,
    NOT a system path like ``/boot``, ``/boot/firmware``, ``/proc``, etc.
    """
    SYSTEM_PATHS = {"/", "/boot", "/boot/firmware", "/efi", "/proc",
                    "/sys", "/dev", "/run", "/tmp"}

    path = path_str.strip()
    if not path or path in SYSTEM_PATHS:
        return False

    name = Path(path).name
    if name.startswith(".") or name.startswith("loop"):
        return False

    # Definite indicators of a removable drive
    if path.startswith("/media/") or path.startswith("/mnt/") or path.startswith("/run/media/"):
        return True

    # System paths that should not be treated as removable
    for sys_path in SYSTEM_PATHS:
        if path == sys_path:
            return False

    # If the path has a typical removable-storage structure (single subfolder
    # under /media), treat it as removable
    if path.count("/") >= 3:
        parent = Path(path).parent
        if parent.name in ("media", "mnt") or "media" in path.parents:
            return True

    return False


def _linux_drives():
    """
    Combine multiple detection methods to find all removable drives.
    Returns a deduplicated list of mount-point strings.
    """
    candidates = set()

    # Method 1: lsblk (most reliable on Raspberry Pi)
    for m in _get_all_mounts_via_lsblk():
        candidates.add(m)

    # Method 2: findmnt fallback
    if not candidates:
        for m in _get_all_mounts_via_findmnt():
            candidates.add(m)

    # Method 3: df fallback
    if not candidates:
        for m in _get_all_mounts_via_df():
            candidates.add(m)

    # Method 4: Always scan common mount directories
    for m in _get_common_mount_dirs():
        candidates.add(m)

    # Filter to removable-looking mounts
    drives = [m for m in candidates if _is_removable(m)]

    # Sort alphabetically for consistency
    drives.sort()
    return drives


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