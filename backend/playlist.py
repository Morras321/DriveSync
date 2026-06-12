"""
DriveSync - Playlist Management Module
CRUD operations for playlists stored as JSON files.
Supports shuffle (with original-order preservation) and unshuffle.
"""

import json
import random
import re
import time
from pathlib import Path

from config import PLAYLIST_DIR
from library import get_song_info, MUSIC_DIR


# ── Query ──────────────────────────────────────────────────────────────

def get_all_playlists():
    """Return a list of summary dicts for every playlist."""
    playlists = []
    for f in sorted(PLAYLIST_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            playlists.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "song_count": len(data.get("songs", [])),
                "created": data.get("created", ""),
                "shuffled": data.get("shuffled", False),
                "original_order": data.get("original_order", None),
            })
        except Exception:
            pass
    return playlists


def get_playlist(playlist_id):
    """Return the full playlist dict, or None."""
    path = PLAYLIST_DIR / f"{playlist_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_playlist(playlist_id, data):
    """Persist a playlist dict to disk."""
    path = PLAYLIST_DIR / f"{playlist_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _new_id(name):
    """Generate a filesystem-safe ID from a playlist name."""
    base = re.sub(r'[<>:"/\\|?*]', "_", name).replace(" ", "_")
    path = PLAYLIST_DIR / f"{base}.json"
    if path.exists():
        base = f"{base}_{int(time.time())}"
    return base


# ── CRUD ───────────────────────────────────────────────────────────────

def create_playlist(name):
    """Create a new empty playlist. Returns the playlist id."""
    pid = _new_id(name)
    data = {
        "name": name,
        "songs": [],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "shuffled": False,
        "original_order": None,
    }
    save_playlist(pid, data)
    return pid


def delete_playlist(playlist_id):
    """Remove a playlist file. Returns True if deleted."""
    path = PLAYLIST_DIR / f"{playlist_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def rename_playlist(playlist_id, new_name):
    """Rename a playlist. Returns True on success."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return False
    playlist["name"] = new_name.strip() or playlist["name"]
    save_playlist(playlist_id, playlist)
    return True


# ── Song manipulation ─────────────────────────────────────────────────

def add_song(playlist_id, song_id):
    """Add a song (by its stem) to a playlist. No-op if already present."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return False

    for f in MUSIC_DIR.glob("*.mp3"):
        if f.stem == song_id and f.name not in playlist["songs"]:
            playlist["songs"].append(f.name)
            save_playlist(playlist_id, playlist)
            return True
    return False


# ── Artist splitting ──────────────────────────────────────────────────

# Regex pattern to split multi-artist strings
# Matches separators: comma (incl. fullwidth), semicolon, slash, feat., ft.,
# &, and, with, vs., duet, along with whitespace variants
_ARTIST_SEP_PATTERN = re.compile(
    r'\s*(?:'
    r'[,，;；/]'                    # Commas (both ASCII and fullwidth), semicolons, slashes
    r'|feat\.|ft\.|featuring'      # feat/ft variations
    r'|&'                          # ampersand
    r'|\band\b'
    r'|\bwith\b'
    r'|\bvs\.?\b'
    r'|\bduet\b'
    r'|\bduet with\b'
    r'|\(feat\.[^)]*\)'            # (feat. ...) patterns
    r'|\(with[^)]*\)'              # (with ...) patterns
    r'|\(ft\.[^)]*\)'              # (ft. ...) patterns
    r')\s*',
    re.IGNORECASE
)


def _split_artists(artist_string):
    """
    Parse an artist string into individual base artists.
    Handles various separators and Unicode characters.
    Returns a set of cleaned artist names.
    """
    if not artist_string:
        return set()
    # First, strip common parenthetical suffixes like (feat. Artist) that might remain
    cleaned = re.sub(r'\([^)]*\)', '', artist_string).strip()
    if not cleaned:
        return set()
    # Split using the regex pattern
    parts = _ARTIST_SEP_PATTERN.split(cleaned)
    result = set()
    for part in parts:
        p = part.strip().strip('"\'')
        # Skip empty parts or parts that look like remnants of separators
        if p and len(p) > 1 and not p.startswith('('):
            result.add(p)
    return result


def get_artists():
    """Return a sorted list of unique base artist names from all MP3 files.
    For songs with multiple artists (e.g. "Artist A, Artist B"), each individual
    artist is returned separately so the user sees only the base artists."""
    artists = set()
    for f in MUSIC_DIR.glob("*.mp3"):
        try:
            from mutagen.mp3 import MP3
            audio = MP3(f)
            artist_str = str(audio.tags.get("TPE1", "")).strip() if audio.tags else ""
            if artist_str:
                individual_artists = _split_artists(artist_str)
                artists.update(individual_artists)
        except Exception:
            pass
    return sorted(artists, key=lambda x: x.lower())


def add_songs_by_artist(playlist_id, artist_name):
    """
    Add all songs matching an artist name to a playlist.
    Matches if the selected base artist appears anywhere in a song's artist metadata,
    even if the song has multiple artists.
    Returns the count of songs added.
    """
    playlist = get_playlist(playlist_id)
    if not playlist:
        return 0

    added = 0
    artist_lower = artist_name.strip().lower()
    existing = set(playlist["songs"])

    for f in MUSIC_DIR.glob("*.mp3"):
        if f.name in existing:
            continue
        # Check artist via ID3 tags
        try:
            from mutagen.mp3 import MP3
            audio = MP3(f)
            artist = str(audio.tags.get("TPE1", "")).lower() if audio.tags else ""
        except Exception:
            artist = ""

        # Check if the selected artist appears in the song's individual artist list
        individual_artists = _split_artists(artist)
        if artist_lower in [a.lower() for a in individual_artists]:
            playlist["songs"].append(f.name)
            existing.add(f.name)
            added += 1
        else:
            # Also check filename for artist prefix (e.g. "Artist - Title.mp3")
            name_artist = ""
            if " - " in f.stem:
                name_artist = f.stem.split(" - ", 1)[0].lower()
            if artist_lower in name_artist:
                playlist["songs"].append(f.name)
                existing.add(f.name)
                added += 1

    if added > 0:
        save_playlist(playlist_id, playlist)

    return added


def add_songs_by_artists_batch(playlist_id, artist_names):
    """
    Add all songs matching ANY of the given artist names to a playlist.
    artist_names: list of artist name strings.
    Returns dict with counts per artist and total added.
    """
    playlist = get_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found", "total_added": 0, "per_artist": {}}

    if not artist_names:
        return {"error": "No artists provided", "total_added": 0, "per_artist": {}}

    # Normalize all artist names to lowercase for matching
    artist_lower_set = set(a.strip().lower() for a in artist_names if a.strip())
    existing = set(playlist["songs"])
    per_artist = {a: 0 for a in artist_names}
    total_added = 0

    for f in MUSIC_DIR.glob("*.mp3"):
        if f.name in existing:
            continue
        # Check artist via ID3 tags
        try:
            from mutagen.mp3 import MP3
            audio = MP3(f)
            artist = str(audio.tags.get("TPE1", "")).lower() if audio.tags else ""
        except Exception:
            artist = ""

        # Check if ANY of the selected artists appear in the song's artist list
        individual_artists = _split_artists(artist)
        individual_lower = [a.lower() for a in individual_artists]

        matched = False
        for a_lower, a_orig in zip(
            [a.lower() for a in artist_names if a.strip()],
            [a for a in artist_names if a.strip()]
        ):
            if a_lower in individual_lower:
                per_artist[a_orig] = per_artist.get(a_orig, 0) + 1
                matched = True
            else:
                # Also check filename
                name_artist = ""
                if " - " in f.stem:
                    name_artist = f.stem.split(" - ", 1)[0].lower()
                if a_lower in name_artist:
                    per_artist[a_orig] = per_artist.get(a_orig, 0) + 1
                    matched = True

        if matched:
            playlist["songs"].append(f.name)
            existing.add(f.name)
            total_added += 1

    if total_added > 0:
        save_playlist(playlist_id, playlist)

    return {"total_added": total_added, "per_artist": per_artist}


def add_all_artists(playlist_id):
    """
    Add ALL songs that are not already in the playlist.
    Returns the count of songs added.
    """
    playlist = get_playlist(playlist_id)
    if not playlist:
        return 0

    added = 0
    existing = set(playlist["songs"])

    for f in MUSIC_DIR.glob("*.mp3"):
        if f.name not in existing:
            playlist["songs"].append(f.name)
            existing.add(f.name)
            added += 1

    if added > 0:
        save_playlist(playlist_id, playlist)

    return added


def remove_song(playlist_id, song_filename):
    """Remove a song from a playlist by its filename."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return False

    from urllib.parse import unquote
    song_filename = unquote(song_filename)
    if song_filename in playlist["songs"]:
        playlist["songs"].remove(song_filename)
        save_playlist(playlist_id, playlist)
        return True
    return False


# ── Ordering ───────────────────────────────────────────────────────────

def shuffle_playlist(playlist_id):
    """Randomise song order, preserving original order for unshuffle."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return False

    # Save original order on first shuffle
    if not playlist.get("original_order"):
        playlist["original_order"] = list(playlist["songs"])

    random.shuffle(playlist["songs"])
    playlist["shuffled"] = True
    save_playlist(playlist_id, playlist)
    return True


def unshuffle_playlist(playlist_id):
    """Restore the original song order."""
    playlist = get_playlist(playlist_id)
    if not playlist or not playlist.get("original_order"):
        return False

    playlist["songs"] = list(playlist["original_order"])
    playlist["original_order"] = None
    playlist["shuffled"] = False
    save_playlist(playlist_id, playlist)
    return True


def reorder_playlist(playlist_id, new_order):
    """Apply a manual song order (list of filenames)."""
    playlist = get_playlist(playlist_id)
    if not playlist:
        return False, "Playlist not found"

    existing = set(playlist["songs"])
    for s in new_order:
        if s not in existing:
            return False, f"'{s}' is not in the playlist"

    playlist["songs"] = new_order
    playlist["shuffled"] = False
    playlist["original_order"] = None
    save_playlist(playlist_id, playlist)
    return True, None


# ── Resolve song info for UI ──────────────────────────────────────────

def get_playlist_with_info(playlist_id):
    """
    Return a playlist dict with an extra ``songs_info`` list
    containing full metadata for each song reference.
    """
    playlist = get_playlist(playlist_id)
    if not playlist:
        return None

    songs_info = []
    for ref in playlist.get("songs", []):
        path = MUSIC_DIR / ref
        if path.exists():
            songs_info.append(get_song_info(path))
    playlist["songs_info"] = songs_info
    return playlist