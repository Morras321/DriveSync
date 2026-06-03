"""
DriveSync - Flask Routes Module
Maps HTTP endpoints to the library, YouTube, playlist and SD-card modules.
"""

import re
import shutil
from pathlib import Path

from flask import Blueprint, request, jsonify, send_from_directory, send_file, Response, stream_with_context

from config import MUSIC_DIR, THUMBNAIL_DIR, FRONTEND_DIR, download_progress
from library import get_all_songs, get_song_info, import_file, delete_song
from youtube import start_download, cancel_download
from playlist import (
    get_all_playlists,
    get_playlist_with_info,
    create_playlist,
    delete_playlist,
    add_song,
    add_songs_by_artist,
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
    songs = get_all_songs()
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