"""
DriveSync - Music Library Module
Scanning MP3 files, reading metadata, and importing audio files.
Supports multiple music directories (local + external drives).
"""

import re
import shutil
import subprocess
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1

from config import MUSIC_DIR, THUMBNAIL_DIR, VALID_AUDIO_EXTENSIONS, get_all_music_dirs
from languages import get_song_language_from_file, load_language_cache

# Cache of which dir a song_id belongs to
_song_location_cache = {}
# Cache for full song info (keyed by resolved filepath) for performance
_song_info_cache = {}
# Track last known file count to invalidate cache
_last_file_count = 0


def _rebuild_cache():
    """Scan all music dirs and build song_id -> path mapping. Also checks if cache needs invalidating."""
    global _last_file_count, _song_info_cache
    
    # Count total files to detect changes
    total_files = 0
    for d in get_all_music_dirs():
        if d.exists():
            total_files += len(list(d.glob("*.mp3")))
    
    # If file count changed, clear all caches
    if total_files != _last_file_count:
        _song_location_cache.clear()
        _song_info_cache.clear()
        _last_file_count = total_files
    
    # Rebuild location cache if needed
    if not _song_location_cache:
        for d in get_all_music_dirs():
            if d.exists():
                for f in d.glob("*.mp3"):
                    _song_location_cache[f.stem] = f


# ── Query ──────────────────────────────────────────────────────────────

def get_all_songs(language_filter=None):
    """Return a list of song-info dicts for every MP3 across all music dirs.
    Uses caching for fast repeated access (e.g. when searching).
    
    Args:
        language_filter: optional language code (e.g. 'ko', 'ja') to filter by.
                         'all' or None returns all songs.
    """
    _rebuild_cache()
    songs = []
    seen = set()
    
    # If filtering by language, get the set of matching song IDs
    lang_filtered_ids = None
    if language_filter and language_filter != 'all':
        from languages import get_songs_by_language
        lang_filtered_ids = get_songs_by_language(language_filter)
    
    for d in get_all_music_dirs():
        if not d.exists():
            continue
        for f in sorted(d.glob("*.mp3")):
            resolved = str(f.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            
            # Apply language filter
            if lang_filtered_ids is not None and f.stem not in lang_filtered_ids:
                continue
            
            # Use cached info if available
            if resolved in _song_info_cache:
                info = _song_info_cache[resolved]
                # Make sure language is cached (it's fast from the JSON lookup)
                if info and 'language' not in info:
                    info['language'] = get_song_language_from_file(f)
                    _song_info_cache[resolved] = info
            else:
                info = get_song_info(f)
                if info:
                    _song_info_cache[resolved] = info
            if info:
                songs.append(info)
    return songs


def get_song_info(filepath):
    """Read ID3 metadata from an MP3 file and return a dict with language detection."""
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

        # Get language from ID3 TLAN tag (or cache fallback)
        language = get_song_language_from_file(filepath)

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
            "language": language,
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
            "language": "en",
        }


def find_song_by_id(song_id):
    """Return the full Path to the first MP3 matching song_id, or None."""
    _rebuild_cache()
    return _song_location_cache.get(song_id)


# ── Import ─────────────────────────────────────────────────────────────

def _check_duplicate(filename):
    """Check if a file with the given name already exists in any music dir. Returns the existing path or None."""
    for d in get_all_music_dirs():
        if not d.exists():
            continue
        candidate = d / filename
        if candidate.exists():
            return candidate
    return None


def import_file(src_path, delete_original=False, target_dir=None, custom_title=None, custom_artist=None, custom_thumbnail=None):
    """
    Copy *src_path* into the music library (first available dir, or target_dir).
    If the source isn't MP3, attempt conversion via ffmpeg.
    Returns a dict with success / filename / error.
    If custom_title is provided, renames the file and updates ID3 title tag.
    If custom_artist is provided, sets the ID3 artist tag.
    If custom_thumbnail is provided (binary data), embeds it as album art.
    """
    src = Path(src_path)
    if not src.exists():
        return {"error": "File not found"}

    if src.suffix.lower() not in VALID_AUDIO_EXTENSIONS:
        return {"error": f"Unsupported format: {src.suffix}"}

    # Determine final filename (use custom_title if given)
    if custom_title:
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", custom_title)[:100]
        dest_name = f"{safe_title}.mp3"
    else:
        dest_name = src.stem[:100] + src.suffix

    # Check for duplicate
    existing = _check_duplicate(dest_name)
    if existing:
        return {"error": f"Already imported: {existing.name}", "filename": existing.name}

    dest_dir = target_dir if target_dir else MUSIC_DIR
    dest = dest_dir / dest_name

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

    # Apply custom ID3 metadata if provided
    if custom_title or custom_artist or custom_thumbnail:
        try:
            audio = MP3(dest)
            if audio.tags is None:
                audio.add_tags()
            if custom_title:
                audio.tags.add(TIT2(encoding=3, text=custom_title))
            if custom_artist:
                # Remove existing TPE1 tags first
                for key in list(audio.tags.keys()):
                    if key.startswith("TPE1"):
                        del audio.tags[key]
                audio.tags.add(TPE1(encoding=3, text=custom_artist))
            if custom_thumbnail:
                # Remove existing APIC tags
                for key in list(audio.tags.keys()):
                    if key.startswith("APIC:"):
                        del audio.tags[key]
                audio.tags.add(
                    APIC(encoding=3, mime="image/jpeg",
                         type=3, desc="Cover",
                         data=custom_thumbnail)
                )
                # Also save thumbnail to thumbnails dir
                thumb_path = THUMBNAIL_DIR / f"{dest.stem}.jpg"
                with open(thumb_path, "wb") as tf:
                    tf.write(custom_thumbnail)
            audio.save()
        except Exception as exc:
            print(f"Custom metadata apply failed: {exc}")

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
    for d in get_all_music_dirs():
        for f in d.glob(f"{song_id}.*"):
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