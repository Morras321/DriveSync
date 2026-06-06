"""
DriveSync - Flask Routes Module
Maps HTTP endpoints to the library, YouTube, playlist and SD-card modules.
"""

import re
import json
import time
import shutil
from pathlib import Path

from flask import Blueprint, request, jsonify, send_from_directory, send_file, Response, stream_with_context

from config import MUSIC_DIR, THUMBNAIL_DIR, FRONTEND_DIR, download_progress
from library import get_all_songs, get_song_info, import_file, delete_song, find_song_by_id
from languages import scan_and_cache_languages, get_available_languages, set_song_language, LANGUAGE_NAMES
from youtube import start_download, cancel_download, check_missing_songs
from playlist import (
    get_all_playlists,
    get_playlist_with_info,
    create_playlist,
    delete_playlist,
    add_song,
    add_songs_by_artist,
    add_songs_by_artists_batch,
    add_all_artists,
    get_artists,
    remove_song,
    shuffle_playlist,
    unshuffle_playlist,
    reorder_playlist,
)
from sdcard import (get_drive_info, export_playlist, list_playlist_folders,
                    delete_playlist_folder, list_folder_songs, add_song_to_folder)
from config import get_storage_info

api = Blueprint("api", __name__)


# ═══════════════════════════════════════════════════════════════════════
#  Music Library
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/songs")
def list_songs():
    search = request.args.get("search", "").lower()
    language = request.args.get("language", "all")
    
    songs = get_all_songs(language_filter=language)
    if search:
        songs = [s for s in songs
                 if search in s["title"].lower() or search in s["artist"].lower()]
    return jsonify(songs)


@api.route("/api/songs/<song_id>")
def get_song(song_id):
    for f in MUSIC_DIR.glob("*.mp3"):
        if f.stem == song_id:
            return jsonify(get_song_info(f))
    return jsonify({"error": "Not found"}), 404


@api.route("/api/songs/<song_id>/delete", methods=["DELETE"])
def remove_song(song_id):
    ok = delete_song(song_id)
    print(ok)
    return jsonify({"success": ok})


# ═══════════════════════════════════════════════════════════════════════
#  Audio Streaming (Preview)
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/songs/<song_id>/stream")
def stream_song(song_id):
    for f in MUSIC_DIR.glob("*.mp3"):
        if f.stem == song_id:
            file_size = f.stat().st_size

            # Range request support (seeking)
            range_header = request.headers.get("Range")
            if range_header:
                match = re.search(r"bytes=(\d+)-(\d*)", range_header)
                if match:
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else file_size - 1
                    length = end - start + 1

                    with open(f, "rb") as af:
                        af.seek(start)
                        data = af.read(length)

                    resp = Response(data, 206, mimetype="audio/mpeg")
                    resp.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                    resp.headers["Accept-Ranges"] = "bytes"
                    resp.headers["Content-Length"] = str(length)
                    return resp

            # Full stream
            def generate():
                with open(f, "rb") as af:
                    while chunk := af.read(8192):
                        yield chunk

            return Response(
                stream_with_context(generate()),
                mimetype="audio/mpeg",
                headers={
                    "Content-Type": "audio/mpeg",
                    "Accept-Ranges": "bytes",
                },
            )

    return jsonify({"error": "Not found"}), 404


# ═══════════════════════════════════════════════════════════════════════
#  Thumbnails
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/thumbnails/<filename>")
def get_thumbnail(filename):
    safe = Path(filename).name
    path = THUMBNAIL_DIR / safe
    if path.exists():
        return send_file(str(path), mimetype="image/jpeg")
    return "", 404


# ═══════════════════════════════════════════════════════════════════════
#  YouTube Download
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    result = start_download(url)
    return jsonify(result)


@api.route("/api/download/progress")
def download_progress_route():
    return jsonify(download_progress)


@api.route("/api/download/cancel", methods=["POST"])
def download_cancel():
    cancel_download()
    return jsonify({"success": True, "message": "Cancelling…"})


@api.route("/api/download/check-missing", methods=["POST"])
def check_missing_route():
    """Check which songs from a URL are not yet in the library (no download)."""
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    result = check_missing_songs(url)
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
#  YouTube Import to Playlist
# ═══════════════════════════════════════════════════════════════════════

import_progress = {
    "status": "idle",
    "total": 0,
    "existing_count": 0,
    "missing_count": 0,
    "downloaded": 0,
    "playlist_id": None,
    "playlist_name": None,
    "added": 0,
    "not_found": [],
    "error": None,
}


@api.route("/api/playlists/import-youtube", methods=["POST"])
def import_youtube_playlist():
    """
    Import a YouTube playlist: check missing songs, download them, then create a playlist.
    Returns immediately. Poll /api/playlists/import-youtube-progress for status.
    """
    from youtube import _extract_playlist_entries, _song_exists_in_library, clean_url
    from youtube import _download_playlist, _reset_progress, _download_cancel_event

    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    clean = clean_url(url)

    # Extract entries
    entries, pl_title = _extract_playlist_entries(clean)
    if not entries:
        return jsonify({"error": "No entries found in playlist"}), 400

    # Separate existing vs missing
    existing_titles = []
    existing_ids = set()
    missing = []
    for video_id, title in entries:
        if _song_exists_in_library(title):
            existing_titles.append(title)
        else:
            missing.append({"video_id": video_id, "title": title})

    all_titles = [t for _, t in entries]
    all_video_ids = [vid for vid, _ in entries]

    # Reset progress
    import_progress["status"] = "checking"
    import_progress["total"] = len(all_titles)
    import_progress["existing_count"] = len(existing_titles)
    import_progress["missing_count"] = len(missing)
    import_progress["downloaded"] = 0
    import_progress["playlist_id"] = None
    import_progress["playlist_name"] = None
    import_progress["added"] = 0
    import_progress["not_found"] = []
    import_progress["error"] = None

    import threading

    def _create_playlist_from_results():
        """Create playlist using all song files that now exist in the library."""
        pl_name = pl_title[:80] + " (YouTube)" if pl_title else "YouTube Import"

        pid = create_playlist(pl_name)

        # Find all matching songs in library by scanning filenames
        from library import get_all_songs
        all_songs = get_all_songs()
        
        # Build a lookup: sanitized stem -> song info
        import re
        from config import MUSIC_DIR
        title_to_song = {}
        for s in all_songs:
            clean_title = re.sub(r'[<>:"/\\|?*]', "_", s["title"])[:100]
            title_to_song[clean_title.lower()] = s
            title_to_song[s["title"].lower()] = s
            title_to_song[s["id"].lower()] = s

        added = 0
        not_found = []
        for video_id, title in entries:
            found = False
            # Try matching by sanitized title (matches download logic)
            safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:100]
            if safe_title.lower() in title_to_song:
                s = title_to_song[safe_title.lower()]
                add_song(pid, s["id"])
                added += 1
                found = True
            elif title.lower() in title_to_song:
                s = title_to_song[title.lower()]
                add_song(pid, s["id"])
                added += 1
                found = True
            elif title.lower()[:50] in {k[:50] for k in title_to_song}:
                # Fuzzy match first 50 chars
                for key, s in title_to_song.items():
                    if key[:50] == title.lower()[:50]:
                        add_song(pid, s["id"])
                        added += 1
                        found = True
                        break
            if not found:
                not_found.append(title)

        import_progress["status"] = "completed"
        import_progress["playlist_id"] = pid
        import_progress["playlist_name"] = pl_name
        import_progress["added"] = added
        import_progress["not_found"] = not_found

    if missing:
        import_progress["status"] = "downloading"
        download_progress["url"] = clean
        download_progress["action"] = "import_youtube"
        download_progress["import_total"] = len(missing)
        download_progress["import_existing"] = len(existing_titles)

        def _download_task():
            _reset_progress("starting")
            _download_cancel_event.clear()
            # _download_playlist is synchronous -- it will block until done
            _download_playlist(clean)
            # After download finishes (or fails), create the playlist
            import time as ttime
            ttime.sleep(1)  # brief pause to let progress settle
            _create_playlist_from_results()

        threading.Thread(target=_download_task, daemon=True).start()
    else:
        # All songs already exist, create playlist immediately
        _create_playlist_from_results()

    return jsonify({"status": "started", "total": len(entries), "missing": len(missing)})


@api.route("/api/playlists/import-youtube-progress")
def import_youtube_progress():
    """Poll import progress."""
    result = dict(import_progress)
    if download_progress["status"] in ("starting", "downloading", "processing", "cancelling"):
        result["download_status"] = download_progress["status"]
        result["download_percent"] = download_progress["percent"]
        result["downloaded"] = download_progress.get("downloaded_count", 0)
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
#  File Import
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/import", methods=["POST"])
def import_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    custom_title = request.form.get("title", "").strip() or None
    custom_artist = request.form.get("artist", "").strip() or None
    thumbnail_file = request.files.get("thumbnail", None)

    temp = MUSIC_DIR / "_temp_upload" / file.filename
    temp.parent.mkdir(exist_ok=True)
    file.save(str(temp))

    custom_thumbnail = None
    if thumbnail_file and thumbnail_file.filename:
        custom_thumbnail = thumbnail_file.read()

    result = import_file(str(temp), custom_title=custom_title, custom_artist=custom_artist, custom_thumbnail=custom_thumbnail)
    shutil.rmtree(str(temp.parent), ignore_errors=True)
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
#  Playlists
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/playlists")
def list_playlists():
    return jsonify(get_all_playlists())


@api.route("/api/playlists", methods=["POST"])
def create_playlist_route():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    pid = create_playlist(name)
    return jsonify({"success": True, "id": pid})


@api.route("/api/playlists/<playlist_id>")
def get_playlist_route(playlist_id):
    playlist = get_playlist_with_info(playlist_id)
    if not playlist:
        return jsonify({"error": "Not found"}), 404
    return jsonify(playlist)


@api.route("/api/playlists/<playlist_id>", methods=["DELETE"])
def delete_playlist_route(playlist_id):
    ok = delete_playlist(playlist_id)
    return jsonify({"success": ok})


@api.route("/api/playlists/<playlist_id>/songs", methods=["POST"])
def add_song_route(playlist_id):
    song_id = (request.json or {}).get("song_id", "")
    ok = add_song(playlist_id, song_id)
    return jsonify({"success": ok})


@api.route("/api/playlists/<playlist_id>/songs/<path:song_filename>", methods=["DELETE"])
def remove_song_route(playlist_id, song_filename):
    ok = remove_song(playlist_id, song_filename)
    return jsonify({"success": ok})


@api.route("/api/artists")
def list_artists():
    """Return a sorted list of unique artist names from the library."""
    return jsonify(get_artists())


@api.route("/api/playlists/<playlist_id>/songs/batch", methods=["POST"])
def add_songs_batch_route(playlist_id):
    """Batch-add songs to a playlist by artist name."""
    data = request.json or {}
    artist = data.get("artist", "").strip()
    if not artist:
        return jsonify({"error": "Artist name required"}), 400
    count = add_songs_by_artist(playlist_id, artist)
    return jsonify({"success": True, "added": count})


@api.route("/api/playlists/<playlist_id>/songs/batch-multi", methods=["POST"])
def add_songs_batch_multi_route(playlist_id):
    """Batch-add songs by multiple artists at once."""
    data = request.json or {}
    artists = data.get("artists", [])
    if not artists:
        return jsonify({"error": "Artists list required"}), 400
    result = add_songs_by_artists_batch(playlist_id, artists)
    return jsonify({"success": True, **result})


@api.route("/api/playlists/<playlist_id>/songs/batch-all", methods=["POST"])
def add_all_songs_route(playlist_id):
    """Add ALL songs from library to a playlist at once."""
    count = add_all_artists(playlist_id)
    return jsonify({"success": True, "added": count})


@api.route("/api/playlists/<playlist_id>/shuffle", methods=["POST"])
def shuffle_route(playlist_id):
    ok = shuffle_playlist(playlist_id)
    return jsonify({"success": ok})


@api.route("/api/playlists/<playlist_id>/unshuffle", methods=["POST"])
def unshuffle_route(playlist_id):
    ok = unshuffle_playlist(playlist_id)
    if not ok:
        return jsonify({"error": "No original order to restore"}), 400
    return jsonify({"success": True})


@api.route("/api/playlists/<playlist_id>/order", methods=["POST"])
def reorder_route(playlist_id):
    new_order = (request.json or {}).get("songs", [])
    ok, err = reorder_playlist(playlist_id, new_order)
    if not ok:
        return jsonify({"error": err or "Reorder failed"}), 400
    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════════════
#  SD Card
# ═══════════════════════════════════════════════════════════════════════

@api.route("/api/languages")
def list_languages():
    """Return available languages in the library."""
    return jsonify(get_available_languages())


@api.route("/api/languages/scan", methods=["POST"])
def scan_languages():
    """Scan all songs and detect their language (one-time operation)."""
    result = scan_and_cache_languages()
    return jsonify({"success": True, "detected": len(result)})


@api.route("/api/songs/<song_id>/language", methods=["POST"])
def set_song_language_route(song_id):
    """Manually set/override the language for a song."""
    data = request.json or {}
    language = data.get("language", "").strip().lower()
    if not language:
        return jsonify({"error": "Language code required"}), 400
    if language not in LANGUAGE_NAMES and len(language) != 2:
        return jsonify({"error": f"Invalid language code: {language}"}), 400
    
    path = find_song_by_id(song_id)
    if not path:
        return jsonify({"error": "Song not found"}), 404
    
    ok = set_song_language(path, language)
    if ok:
        return jsonify({"success": True, "language": language})
    return jsonify({"error": "Failed to set language tag"}), 500


@api.route("/api/storage")
def storage_info():
    """Return disk usage info for all music directories."""
    return jsonify(get_storage_info())


@api.route("/api/sdcard")
def sdcard_info():
    return jsonify(get_drive_info())


@api.route("/api/sdcard/export", methods=["POST"])
def sdcard_export():
    data = request.json or {}
    playlist_id = data.get("playlist_id")
    sd_drive = data.get("sd_drive")
    subfolder = data.get("subfolder", "")
    shuffle_prefix = data.get("shuffle_prefix", False)

    if not playlist_id or not sd_drive:
        return jsonify({"error": "Playlist ID and SD drive required"}), 400

    result = export_playlist(playlist_id, sd_drive, subfolder, shuffle_prefix)
    return jsonify(result)


@api.route("/api/sdcard/folders", methods=["POST"])
def sdcard_list_folders():
    """List existing playlist folders on a drive/subfolder."""
    data = request.json or {}
    drive_path = data.get("drive_path")
    subfolder = data.get("subfolder", "")
    if not drive_path:
        return jsonify({"error": "Drive path required"}), 400
    folders = list_playlist_folders(drive_path, subfolder)
    return jsonify(folders)


@api.route("/api/sdcard/folders/songs", methods=["POST"])
def sdcard_folder_songs():
    """List all songs in a specific folder on the drive."""
    data = request.json or {}
    folder_path = data.get("folder_path")
    if not folder_path:
        return jsonify({"error": "Folder path required"}), 400
    songs = list_folder_songs(folder_path)
    return jsonify(songs)


@api.route("/api/sdcard/folders/add-song", methods=["POST"])
def sdcard_folder_add_song():
    """Add a song to a folder on the drive (by song_id or file path)."""
    data = request.json or {}
    folder_path = data.get("folder_path")
    song_source = data.get("song_source")
    if not folder_path or not song_source:
        return jsonify({"error": "folder_path and song_source required"}), 400
    result = add_song_to_folder(folder_path, song_source)
    return jsonify(result)


@api.route("/api/sdcard/folders/delete", methods=["POST"])
def sdcard_delete_folder():
    """Delete a playlist folder from the drive."""
    data = request.json or {}
    folder_path = data.get("folder_path")
    if not folder_path:
        return jsonify({"error": "Folder path required"}), 400
    ok = delete_playlist_folder(folder_path)
    return jsonify({"success": ok})


# ═══════════════════════════════════════════════════════════════════════
#  Frontend
# ═══════════════════════════════════════════════════════════════════════

@api.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@api.route("/<path:path>")
def frontend_static(path):
    return send_from_directory(str(FRONTEND_DIR), path)