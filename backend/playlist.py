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