"""
DriveSync - Music Library Module
Scanning MP3 files, reading metadata, and importing audio files.
"""

import shutil
import subprocess
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

from config import MUSIC_DIR, THUMBNAIL_DIR, VALID_AUDIO_EXTENSIONS


# ── Query ──────────────────────────────────────────────────────────────

def get_all_songs():
    """Return a list of song-info dicts for every MP3 in the library."""
    songs = []
    for f in sorted(MUSIC_DIR.glob("*.mp3")):
        info = get_song_info(f)
        if info:
            songs.append(info)
    return songs


def get_song_info(filepath):
    """Read ID3 metadata from an MP3 file and return a dict."""
    try:
        audio = MP3(filepath)
        tags = audio.tags

        title = str(tags.get("TIT2", "Unknown Title"))
        artist = str(tags.get("TPE1", "Unknown Artist"))
        album = str(tags.get("TALB", "Unknown Album"))
        year = str(tags.get("TYER", ""))
        duration = int(audio.info.length) if audio.info else 0

        # Extract embedded album art (APIC) to thumbnail cache
        has_thumb = False
        if tags:
            for tag in tags.values():
                if isinstance(tag, APIC):
                    thumb_path = THUMBNAIL_DIR / f"{filepath.stem}.jpg"
                    if not thumb_path.exists():
                        with open(thumb_path, "wb") as f:
                            f.write(tag.data)
                    has_thumb = True
                    break

        return {
            "id": filepath.stem,
            "filename": filepath.name,
            "title": title,
            "artist": artist,
            "album": album,
            "year": year,
            "duration": duration,
            "size": filepath.stat().st_size,
            "has_thumbnail": has_thumb,
            "filepath": str(filepath),
        }
    except Exception as exc:
        print(f"Error reading {filepath}: {exc}")
        return {
            "id": filepath.stem,
            "filename": filepath.name,
            "title": filepath.stem,
            "artist": "Unknown",
            "album": "Unknown",
            "year": "",
            "duration": 0,
            "size": filepath.stat().st_size,
            "has_thumbnail": False,
            "filepath": str(filepath),
        }


def find_song_by_id(song_id):
    """Return the Path to the first MP3 matching song_id stem, or None."""
    for f in MUSIC_DIR.glob("*.mp3"):
        if f.stem == song_id:
            return f
    return None


# ── Import ─────────────────────────────────────────────────────────────

def import_file(src_path, delete_original=False):
    """
    Copy *src_path* into the music library.
    If the source isn't MP3, attempt conversion via ffmpeg.
    Returns a dict with success / filename / error.
    """
    src = Path(src_path)
    if not src.exists():
        return {"error": "File not found"}

    if src.suffix.lower() not in VALID_AUDIO_EXTENSIONS:
        return {"error": f"Unsupported format: {src.suffix}"}

    dest = MUSIC_DIR / src.name
    counter = 1
    while dest.exists():
        dest = MUSIC_DIR / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    shutil.copy2(str(src), str(dest))

    # Convert to MP3
    if dest.suffix.lower() != ".mp3":
        mp3_dest = dest.with_suffix(".mp3")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(dest),
                 "-codec:a", "libmp3lame", "-qscale:a", "2",
                 "-map", "a", str(mp3_dest)],
                capture_output=True,
            )
            if mp3_dest.exists() and mp3_dest.stat().st_size > 0:
                dest.unlink()
                dest = mp3_dest
        except Exception:
            pass

    if delete_original:
        src.unlink()

    return {"success": True, "filename": dest.name}


# ── Deletion ──────────────────────────────────────────────────────────

def delete_song(song_id):
    """
    Remove a song from the library (MP3 file + thumbnail).
    Also removes the song reference from all playlists.
    Returns True if something was deleted.
    """
    removed = False
    for f in MUSIC_DIR.glob(f"{song_id}.*"):
        f.unlink()
        removed = True

    thumb = THUMBNAIL_DIR / f"{song_id}.jpg"
    if thumb.exists():
        thumb.unlink()

    # Remove from every playlist JSON
    from config import PLAYLIST_DIR
    for pl_file in PLAYLIST_DIR.glob("*.json"):
        try:
            import json
            data = json.loads(pl_file.read_text(encoding="utf-8"))
            to_remove = [s for s in data.get("songs", [])
                         if Path(s).stem == song_id or s == song_id]
            for s in to_remove:
                data["songs"].remove(s)
            pl_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return removed