"""
DriveSync - Drive/Disk Export Module
Cross-platform detection of removable drives, playlist folder management,
and folder song listing/editing.
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
    Uses ``lsblk`` on Linux with a pragmatic fallback chain.
    """
    if IS_WINDOWS:
        return _windows_drives()
    return _linux_drives()


def _windows_drives():
    """Detect all non-system drives (not just removable) since USB HDDs may
    report as DRIVE_FIXED. We include any drive that isn't C:."""
    import string
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive) and drive.upper() != "C:\\":
            drives.append(drive)
    return drives


# ── Linux detection ────────────────────────────────────────────────────

def _get_lsblk_json():
    """
    Use ``lsblk --json`` to get structured data about all block devices.
    Returns a list of dicts with keys: name, mountpoint, fstype, type, label.
    """
    try:
        result = subprocess.run(
            ["lsblk", "--json", "-o", "NAME,MOUNTPOINT,FSTYPE,TYPE,LABEL"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []

        import json as json_mod
        data = json_mod.loads(result.stdout)
        devices = data.get("blockdevices", [])

        # Flatten children into the list
        def _flatten(items):
            out = []
            for item in items:
                children = item.pop("children", None)
                out.append(item)
                if children:
                    out.extend(_flatten(children))
            return out

        return _flatten(devices)
    except FileNotFoundError:
        return []
    except Exception as exc:
        print(f"lsblk --json failed: {exc}")
        return []


def _get_mounts_via_lsblk_text():
    """Fallback: lsblk without --json (some older systems)."""
    try:
        result = subprocess.run(
            ["lsblk", "-o", "MOUNTPOINT", "-l", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines()
                    if line.strip() and os.path.exists(line.strip())]
    except Exception:
        pass
    return []


def _probe_autofs_mounts():
    """
    Scan known autofs parent directories and try to trigger mounts
    by accessing each subdirectory. Returns paths that are confirmed
    mount points or contain real files (not empty autofs stubs).
    """
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "pi"
    autofs_bases = [
        Path(f"/media/{user}"),
        Path("/media"),
        Path("/media/usb"),
        Path("/mnt"),
        Path(f"/run/media/{user}"),
        Path("/run/media"),
    ]

    system_block = {"/", "/boot", "/boot/firmware", "/efi", "/proc",
                    "/sys", "/dev", "/run", "/tmp"}

    found = set()

    for base in autofs_bases:
        if not base.exists():
            continue
        try:
            for item in base.iterdir():
                if not item.is_dir():
                    continue
                resolved = str(item.resolve())

                # Skip system paths
                if resolved in system_block:
                    continue
                if any(resolved.startswith(s + "/") for s in ["/boot", "/proc", "/sys"]):
                    continue

                # Try to access the directory to trigger autofs mount
                try:
                    # List contents to trigger automount
                    contents = list(item.iterdir())
                except PermissionError:
                    # Can't access, skip
                    continue
                except OSError:
                    # Some other error, skip
                    continue

                # After trigger, check if it's a real mount or has content
                if os.path.ismount(resolved) or len(contents) > 0:
                    found.add(resolved)
        except PermissionError:
            continue

    return found


def _linux_drives():
    """
    Strategy:
    1. Try lsblk --json for structured data (best).
    2. Fall back to plain lsblk text output.
    3. Always scan /media, /mnt, /run/media regardless.
    4. Probe autofs mount points by accessing them to trigger mounts.

    Return list of mount-point strings that are *not* system paths.
    """
    candidates = set()
    system_block = {"/", "/boot", "/boot/firmware", "/efi", "/proc",
                     "/sys", "/dev", "/run", "/tmp"}

    # ── Method 1: lsblk --json (most reliable) ──
    for dev in _get_lsblk_json():
        mp = dev.get("mountpoint")
        dtype = dev.get("type", "")       # "part", "disk", "rom", "loop"
        fstype = dev.get("fstype", "") or ""

        if mp and mp.strip() and mp not in system_block:
            mp = mp.strip()
            # Skip loop devices and CDs
            if dtype == "loop" or dtype == "rom":
                continue
            # Skip paths we know are system
            if any(mp == s or mp.startswith(s + "/") for s in ["/boot", "/proc", "/sys"]):
                continue
            candidates.add(mp)

    # ── Method 2: plain lsblk ──
    if not candidates:
        for mp in _get_mounts_via_lsblk_text():
            if mp not in system_block:
                candidates.add(mp)

    # ── Method 3: scan common directories & trigger autofs mounts ──
    # This also handles autofs: accessing the directory triggers the automounter.
    autofs_mounts = _probe_autofs_mounts()
    candidates.update(autofs_mounts)

    result = sorted(c for c in candidates if c.strip())
    return result


# ── Info ───────────────────────────────────────────────────────────────

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


# ── Folder management ─────────────────────────────────────────────────

def list_playlist_folders(drive_path, subfolder=""):
    """
    List folders on the given drive that contain MP3 files.
    Returns [{name, path, song_count, size}].
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


def list_folder_songs(drive_path):
    """
    List all MP3 files inside a given folder (the folder itself, not recursive).
    Returns [{filename, path, size, title, artist}] with metadata.
    """
    folder = Path(drive_path)
    if not folder.exists() or not folder.is_dir():
        return []

    songs = []
    for f in sorted(folder.glob("*.mp3")):
        title, artist = _guess_metadata(f)
        songs.append({
            "filename": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "title": title,
            "artist": artist,
        })
    return songs


def _guess_metadata(mp3_path):
    """Try to read ID3 title/artist, fall back to filename heuristics."""
    try:
        from mutagen.mp3 import MP3 as MutagenMP3
        audio = MutagenMP3(mp3_path)
        tags = audio.tags
        title = str(tags.get("TIT2", "")) if tags else ""
        artist = str(tags.get("TPE1", "")) if tags else ""
        if title:
            return title, artist
    except Exception:
        pass

    # Fallback: parse filename  "Artist - Title.mp3" or just "Title.mp3"
    name = mp3_path.stem
    if " - " in name:
        parts = name.split(" - ", 1)
        return parts[1], parts[0]
    return name, "Unknown"


def add_song_to_folder(folder_path, song_source):
    """
    Copy a song into the given folder. song_source can be:
      - a path in the local library (by song id)
      - a full file path
    Returns {success, filename, error}.
    """
    folder = Path(folder_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)

    # Try to find the source
    src = Path(song_source)
    if not src.exists():
        # Maybe it's a song_id in our library
        from library import find_song_by_id
        found = find_song_by_id(song_source)
        if found:
            src = found
        else:
            return {"success": False, "error": f"Source not found: {song_source}"}

    dest = folder / src.name
    counter = 1
    while dest.exists():
        dest = folder / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    try:
        shutil.copy2(str(src), str(dest))
        return {"success": True, "filename": dest.name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def delete_playlist_folder(folder_path):
    """Delete a folder and its contents from the drive."""
    path = Path(folder_path)
    if path.exists() and path.is_dir():
        shutil.rmtree(str(path))
        return True
    return False


# ── Shuffle / Unshuffle exported folders ─────────────────────────────

def shuffle_folder(folder_path):
    """
    Add numeric prefixes to all MP3 files in a folder to set a shuffled order.
    If files already have numeric prefixes, they are stripped first then re-applied
    in random order. Does NOT copy/write songs — only renames.
    Returns {'success': bool, 'renamed': int, 'error': str or None}.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {"success": False, "renamed": 0, "error": "Folder not found"}

    mp3_files = sorted(folder.glob("*.mp3"))
    if not mp3_files:
        return {"success": False, "renamed": 0, "error": "No MP3 files in folder"}

    # Strip existing numeric prefixes first
    _strip_numeric_prefixes(mp3_files)
    # Re-list after potential rename
    mp3_files = sorted(folder.glob("*.mp3"))
    if not mp3_files:
        return {"success": False, "renamed": 0, "error": "No MP3 files after cleanup"}

    # Shuffle the list
    import random
    random.shuffle(mp3_files)

    renamed = _apply_numeric_prefixes(mp3_files)
    return {"success": True, "renamed": renamed, "error": None}


def unshuffle_folder(folder_path):
    """
    Remove all numeric prefixes from MP3 files in a folder (e.g. '001_Song.mp3' -> 'Song.mp3').
    Does NOT copy/write songs — only renames.
    Returns {'success': bool, 'renamed': int, 'error': str or None}.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {"success": False, "renamed": 0, "error": "Folder not found"}

    mp3_files = list(folder.glob("*.mp3"))
    if not mp3_files:
        return {"success": False, "renamed": 0, "error": "No MP3 files in folder"}

    renamed = 0
    for f in sorted(mp3_files):
        # Match prefix like "001_", "123_" etc.
        match = re.match(r'^(\d{3})_(.+)\.mp3$', f.name)
        if match:
            new_name = f"{match.group(2)}.mp3"
            # Avoid collision
            new_path = f.parent / new_name
            counter = 1
            while new_path.exists():
                stem = Path(new_name).stem
                new_path = f.parent / f"{stem}_{counter}.mp3"
                counter += 1
            try:
                f.rename(new_path)
                renamed += 1
            except Exception:
                pass
    return {"success": True, "renamed": renamed, "error": None}


def _strip_numeric_prefixes(mp3_files):
    """Remove numeric 'NNN_' prefixes from a list of MP3 file paths (in-place rename)."""
    for f in sorted(mp3_files):
        match = re.match(r'^(\d{3})_(.+)\.mp3$', f.name)
        if match:
            new_name = f"{match.group(2)}.mp3"
            new_path = f.parent / new_name
            counter = 1
            while new_path.exists():
                stem = Path(new_name).stem
                new_path = f.parent / f"{stem}_{counter}.mp3"
                counter += 1
            try:
                f.rename(new_path)
            except Exception:
                pass


def _apply_numeric_prefixes(mp3_files):
    """
    Rename MP3 files with 3-digit prefixes (001_, 002_, etc.) in the order given.
    Returns the count of renamed files.
    """
    renamed = 0
    for i, f in enumerate(mp3_files):
        prefix = f"{i+1:03d}_"
        if f.name.startswith(prefix):
            continue
        new_name = f"{prefix}{f.name}"
        new_path = f.parent / new_name
        try:
            f.rename(new_path)
            renamed += 1
        except Exception:
            pass
    return renamed


# ── Export ─────────────────────────────────────────────────────────────

def export_playlist(playlist_id, drive_path, subfolder="", shuffle_prefix=False):
    """Export a playlist as a folder to a drive."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found"}

    drives = find_removable_drives()
    if drive_path not in drives and not any(drive_path.startswith(d) for d in drives):
        return {"error": f"Drive not found at {drive_path}"}

    name = re.sub(r'[<>:"/\\|*\s]', "_", playlist["name"])
    dest = Path(drive_path)
    if subfolder:
        dest = dest / subfolder
    dest = dest / name

    dest.parent.mkdir(parents=True, exist_ok=True)
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