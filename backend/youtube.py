"""
DriveSync - YouTube Download Module
URL cleaning, audio downloading, metadata enhancement, and cancel support.
Supports concurrent playlist downloads, dual progress bars,
and shared state across all users (no blocking).
"""

import os
import re
import json
import warnings
import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode

# Suppress yt-dlp's Python 3.9 deprecation warning on Raspberry Pi
warnings.filterwarnings("ignore", message=".*Python version 3.9.*deprecated.*")

import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TYER

from config import MUSIC_DIR, THUMBNAIL_DIR, download_progress, IS_WINDOWS
from languages import detect_and_set_language_from_metadata

# ---------------------------
# Cancel Support
# ---------------------------
_download_cancel_event = Event()
_progress_lock = Lock()

# Max concurrent downloads for playlist songs
# Windows (desktop): higher concurrency for faster downloads
# Linux (Raspberry Pi): lower concurrency to avoid overwhelming the CPU
PLAYLIST_CONCURRENCY = 5 if IS_WINDOWS else 2


def clean_url(url):
    """
    Strip tracking/playlist parameters from a YouTube URL.
    - Single video with list param -> keep only video
    - Playlist URL -> keep playlist param
    - Short youtu.be links -> keep video id
    """
    url = url.strip()

    # Short link: youtu.be/VIDEO_ID
    if "youtu.be" in url:
        match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', url)
        if match:
            return f"https://youtu.be/{match.group(1)}"
        return url

    if "youtube.com" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        video_id = params.get("v", [None])[0]
        list_id = params.get("list", [None])[0]
        is_playlist = "/playlist" in parsed.path

        if video_id and not is_playlist:
            return f"https://www.youtube.com/watch?v={video_id}"
        if list_id or is_playlist:
            return url  # keep playlist as-is

    return url


def _reset_progress(status="idle"):
    """Reset the shared download_progress dict."""
    with _progress_lock:
        download_progress["current"] = None
        download_progress["status"] = status
        download_progress["percent"] = 0
        download_progress["is_playlist"] = False
        download_progress["total_songs"] = 0
        download_progress["current_song_index"] = 0
        download_progress["current_song_name"] = ""
        download_progress["song_percent"] = 0
        download_progress["downloaded_count"] = 0
        download_progress["error_count"] = 0
        download_progress["errors"] = []
        download_progress["url"] = ""
        download_progress["action"] = None


def _update_progress(**kwargs):
    """Thread-safe update of progress dict fields."""
    with _progress_lock:
        for k, v in kwargs.items():
            if k in download_progress:
                download_progress[k] = v


def _build_ydl_opts(output_template):
    """Build yt-dlp options dict with sensible defaults."""
    return {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        },
        "extractor_args": {
            "youtube": {"player_client": ["android", "web"], "player_skip": ["webpage"]},
        },
        "writethumbnail": True,
        "embedthumbnail": True,
        "addmetadata": True,
        "progress_hooks": [],  # Set per-instance below
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "retries": 3,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
    }


def _find_downloaded_file(temp_dir):
    """Find the downloaded audio file in temp_dir (try MP3 first, then others)."""
    for ext in ["*.mp3", "*.m4a", "*.webm", "*.opus", "*.ogg", "*.aac", "*.wav"]:
        files = list(Path(temp_dir).glob(ext))
        if files:
            return files[0]
    # Fallback: any non-image file
    for f in Path(temp_dir).iterdir():
        if f.is_file() and f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            return f
    return None


def _convert_to_mp3(src_path):
    """Convert a non-MP3 audio file to MP3 via ffmpeg."""
    mp3_path = src_path.with_suffix(".mp3")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_path),
         "-codec:a", "libmp3lame", "-qscale:a", "2",
         "-map", "a", str(mp3_path)],
        capture_output=True, text=True,
    )
    if mp3_path.exists() and mp3_path.stat().st_size > 0:
        try:
            src_path.unlink()
        except OSError:
            pass
        return mp3_path
    return None


def _sanitise_filename(name):
    """Remove filesystem-unsafe characters and limit length."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    return safe[:100]


def _song_exists_in_library(title):
    """
    Check if a song with the given title already exists in any music directory.
    Matches by sanitised filename (same logic as _download_single_video_task).
    Returns True if found, False otherwise.
    """
    safe = _sanitise_filename(title)
    from config import get_all_music_dirs
    for d in get_all_music_dirs():
        if not d.exists():
            continue
        for ext in [".mp3", ".m4a", ".webm", ".opus"]:
            if (d / f"{safe}{ext}").exists():
                return True
    return False


def enhance_metadata(mp3_path, info_dict):
    """Embed ID3 tags + album art into an MP3 file from yt-dlp info."""
    if not info_dict:
        return
    try:
        audio = MP3(mp3_path)
        if audio.tags is None:
            audio.add_tags()

        title = str(info_dict.get("title", mp3_path.stem))
        artist = str(info_dict.get("artist")
                     or info_dict.get("channel")
                     or info_dict.get("uploader")
                     or "Unknown Artist")
        album = str(info_dict.get("album") or info_dict.get("channel") or "YouTube")
        upload_date = info_dict.get("upload_date", "")
        year = upload_date[:4] if len(upload_date) >= 4 else ""
        
        # Remove existing APIC tags
        for key in list(audio.tags.keys()):
            if key.startswith("APIC:"):
                del audio.tags[key]

        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TALB(encoding=3, text=album))
        if year:
            audio.tags.add(TYER(encoding=3, text=year))

        # Download & embed thumbnail
        thumb_url = info_dict.get("thumbnail")
        if thumb_url:
            try:
                import requests
                resp = requests.get(thumb_url, timeout=15,
                                    headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    audio.tags.add(APIC(encoding=3, mime="image/jpeg",
                                        type=3, desc="Cover", data=resp.content))
                    thumb_file = THUMBNAIL_DIR / f"{mp3_path.stem}.jpg"
                    with open(thumb_file, "wb") as f:
                        f.write(resp.content)
            except Exception as exc:
                print(f"Thumbnail download failed: {exc}")

        audio.save()
    except Exception as exc:
        print(f"Metadata enhancement failed: {exc}")


# ── Per-song progress hook ────────────────────────────────────────────

def _make_song_progress_hook(song_index, total_songs, song_name):
    """Create a progress hook that updates the per-song progress."""
    def _hook(d):
        if _download_cancel_event.is_set():
            raise Exception("Download cancelled by user")

        if d["status"] == "downloading":
            try:
                pct = d.get("_percent_str", "0%").strip().replace("%", "")
                song_pct = float(pct)
            except Exception:
                song_pct = 0
            _update_progress(
                status="downloading",
                song_percent=song_pct,
                current_song_name=song_name,
                current_song_index=song_index,
                total_songs=total_songs,
                percent=int(((song_index - 1) / total_songs) * 100 +
                            (song_pct / total_songs)) if total_songs > 1 else int(song_pct),
            )
        elif d["status"] == "finished":
            _update_progress(status="processing", song_percent=100)
        elif d["status"] == "error":
            _update_progress(status="error")
    return _hook


# ── Single video download task ───────────────────────────────────────

def _download_single_video_task(video_url, temp_dir, song_index=1, total_songs=1, song_name=""):
    """
    Download a single video URL to temp_dir, convert to MP3, and copy to the library.
    Returns dict {success, filename, error}.
    """
    if _download_cancel_event.is_set():
        return {"error": "cancelled"}

    template = os.path.join(temp_dir, "%(title)s.%(ext)s")
    opts = _build_ydl_opts(template)

    # Attach per-song progress hook
    opts["progress_hooks"] = [_make_song_progress_hook(song_index, total_songs, song_name)]

    info = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
    except Exception as exc:
        err = str(exc)
        if "cancelled" in err.lower():
            return {"error": "cancelled"}
        print(f"Download attempt failed for {video_url}: {err}")
        # Fallback: simpler options
        fallback_opts = dict(opts)
        fallback_opts["format"] = "worstaudio/worst"
        fallback_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
        fallback_opts.pop("embedthumbnail", None)
        fallback_opts.pop("writethumbnail", None)
        try:
            with yt_dlp.YoutubeDL(fallback_opts) as ydl2:
                info = ydl2.extract_info(video_url, download=True)
        except Exception as exc2:
            return {"error": str(exc2)[:300]}

    if info is None:
        return {"error": "No info returned from extractor"}

    title = info.get("title", "Unknown")
    src = _find_downloaded_file(Path(temp_dir))
    if src is None:
        return {"error": "No audio file found after download"}

    # Convert to MP3 if necessary
    if src.suffix.lower() != ".mp3":
        converted = _convert_to_mp3(src)
        if converted is None:
            return {"error": "FFmpeg conversion failed"}
        src = converted

    # Check for duplicate in library
    safe = _sanitise_filename(title)
    dest = MUSIC_DIR / f"{safe}{src.suffix}"
    if dest.exists():
        return {"error": f"Already downloaded: {safe}{src.suffix}", "filename": dest.name}

    shutil.copy2(str(src), str(dest))
    enhance_metadata(dest, info)
    
    # Detect and set language using title and artist from YouTube metadata
    artist = str(info.get("artist") or info.get("channel") or info.get("uploader") or "Unknown Artist")
    detect_and_set_language_from_metadata(dest, title, artist)
    
    return {"success": True, "filename": dest.name, "title": title}


# ── Playlist download with concurrency & batching ───────────────────

def _extract_playlist_entries(clean_url):
    """
    Extract all entries from a playlist URL.
    Handles pagination automatically via yt-dlp.
    Filters out None entries (unavailable/deleted videos).
    Returns list of (video_id, title) tuples.
    """
    entries = []
    try:
        detect_opts = dict(_build_ydl_opts(""))
        detect_opts.pop("extract_flat", None)
        detect_opts["extract_flat"] = "in_playlist"
        detect_opts["skip_download"] = True
        detect_opts["ignoreerrors"] = True

        with yt_dlp.YoutubeDL(detect_opts) as ydl:
            playlist_info = ydl.extract_info(clean_url, download=False)

        if not playlist_info:
            return entries

        raw_entries = playlist_info.get("entries", [])
        if not raw_entries:
            return entries

        for raw_entry in raw_entries:
            if raw_entry is None:
                continue  # Skip unavailable/deleted entries
            video_id = raw_entry.get("id")
            title = raw_entry.get("title")
            if video_id and title:
                entries.append((video_id, title))
            elif video_id:
                entries.append((video_id, f"video_{video_id}"))

        return entries

    except Exception as exc:
        print(f"Playlist extraction error: {exc}")
        return entries


def _download_playlist(clean_url):
    """Download all videos in a playlist with batching to avoid memory issues."""
    _update_progress(is_playlist=True, status="starting",
                     current="Extracting playlist entries...")

    # Extract entries with None-filtering
    all_entries = _extract_playlist_entries(clean_url)

    if not all_entries:
        _update_progress(status="error", current="No valid entries found in playlist")
        return

    # Filter out entries that already exist in the library
    _update_progress(status="starting",
                     current="Checking which songs already exist in the library...")
    entries = []
    skipped_count = 0
    for video_id, title in all_entries:
        if _song_exists_in_library(title):
            skipped_count += 1
        else:
            entries.append((video_id, title))

    total = len(entries)
    _update_progress(total_songs=total, status="starting",
                     current=f"Downloading {total} songs ({skipped_count} already in library)..." if skipped_count else f"Downloading {total} songs...")

    downloaded_count = 0
    error_count = 0
    errors_list = []

    # Use a bounded executor to limit memory usage
    # Process in chunks to avoid holding 2000 temp dirs in memory
    with ThreadPoolExecutor(max_workers=PLAYLIST_CONCURRENCY) as executor:
        # Process entries in batches
        batch_size = PLAYLIST_CONCURRENCY * 2  # Keep a small queue
        entry_queue = list(enumerate(entries))  # (original_index, (video_id, title))
        total_entries = len(entry_queue)
        processed_count = 0

        while entry_queue and not _download_cancel_event.is_set():
            # Take next batch
            batch = entry_queue[:batch_size]
            entry_queue = entry_queue[batch_size:]

            future_map = {}
            for idx, (video_id, title) in batch:
                if _download_cancel_event.is_set():
                    break
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                temp_dir = tempfile.mkdtemp()
                song_index = idx + 1
                future = executor.submit(
                    _download_single_video_task,
                    video_url, temp_dir, song_index, total, title
                )
                future_map[future] = (temp_dir, title)

            # Process this batch's results
            for future in as_completed(future_map):
                if _download_cancel_event.is_set():
                    # Cancel remaining futures
                    for f in future_map:
                        if not f.done():
                            f.cancel()
                    break

                temp_dir, song_name = future_map[future]
                try:
                    result = future.result(timeout=300)  # 5 min timeout per song
                    if result.get("success"):
                        downloaded_count += 1
                    elif result.get("error") == "cancelled":
                        _update_progress(status="cancelled")
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return
                    else:
                        error_count += 1
                        err_msg = result.get("error", "Unknown error")
                        # Don't flood the errors list with "Already downloaded" messages
                        if "Already downloaded" not in err_msg:
                            errors_list.append(f"{song_name}: {err_msg}")
                except Exception as exc:
                    error_count += 1
                    err_msg = str(exc)[:200]
                    errors_list.append(f"{song_name}: {err_msg}")
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    processed_count += 1

                # Update progress
                _update_progress(
                    downloaded_count=downloaded_count,
                    error_count=error_count,
                    errors=errors_list[-20:],  # Keep only last 20 errors
                    percent=int(processed_count / total * 100) if total > 0 else 0,
                )

            # Small delay between batches to let system breathe
            if entry_queue and not _download_cancel_event.is_set():
                import time
                time.sleep(1)

    # Final report
    if _download_cancel_event.is_set():
        _update_progress(status="cancelled")
    else:
        msg = f"Downloaded {downloaded_count} of {total} songs"
        if errors_list:
            msg += f" ({error_count} errors)"
        _update_progress(
            status="completed",
            current=msg,
            percent=100,
            downloaded_count=downloaded_count,
            error_count=error_count,
            errors=errors_list,
        )


def check_missing_songs(url):
    """
    Check which songs from a YouTube/playlist URL are NOT already in the library.
    Returns a dict with:
      - total: total number of songs in the source
      - missing: list of {video_id, title} that need downloading
      - existing_count: number of songs already in the library
    Does NOT download anything.
    """
    clean = clean_url(url)
    
    # Determine if this is a playlist URL
    parsed = urlparse(clean)
    params = parse_qs(parsed.query)
    has_list = "list" in params
    has_video = "v" in params
    is_playlist_path = "/playlist" in parsed.path
    
    is_playlist = is_playlist_path or (has_list and not has_video)
    
    if not is_playlist:
        # Single video - just check if it exists
        # We need the title, so extract info
        try:
            detect_opts = dict(_build_ydl_opts(""))
            detect_opts.pop("extract_flat", None)
            detect_opts["extract_flat"] = "in_playlist"
            detect_opts["skip_download"] = True
            detect_opts["ignoreerrors"] = True
            with yt_dlp.YoutubeDL(detect_opts) as ydl:
                info = ydl.extract_info(clean, download=False)
            if info:
                title = info.get("title", "Unknown")
                exists = _song_exists_in_library(title)
                return {
                    "total": 1,
                    "missing": [] if exists else [{"video_id": info.get("id"), "title": title}],
                    "existing_count": 1 if exists else 0,
                    "existing_titles": [title] if exists else [],
                    "is_playlist": False,
                }
        except Exception as exc:
            return {"error": str(exc)[:300], "total": 0, "missing": [], "existing_count": 0, "existing_titles": [], "is_playlist": False}
        return {"total": 0, "missing": [], "existing_count": 0, "existing_titles": [], "is_playlist": False}
    
    # Playlist - extract entries and check each
    entries = _extract_playlist_entries(clean)
    if not entries:
        return {"error": "No entries found in playlist", "total": 0, "missing": [], "existing_count": 0, "existing_titles": [], "is_playlist": True}
    
    missing = []
    existing_titles = []
    for video_id, title in entries:
        if _song_exists_in_library(title):
            existing_titles.append(title)
        else:
            missing.append({"video_id": video_id, "title": title})
    
    return {
        "total": len(entries),
        "missing": missing,
        "existing_count": len(existing_titles),
        "existing_titles": existing_titles,
        "is_playlist": True,
    }


# ── Public API ────────────────────────────────────────────────────────

def is_download_active():
    """Return True if a download is currently in progress."""
    with _progress_lock:
        return download_progress["status"] in ("starting", "downloading", "processing", "cancelling")


def start_download(url):
    """
    Kick off a YouTube-to-MP3 download in a background thread.
    Supports single videos and playlists.
    Returns immediately; poll /api/download/progress for status.
    """
    # Reject if another download is already running
    if is_download_active():
        return {"error": "A download is already in progress. Cancel it first or wait for it to complete."}

    clean = clean_url(url)
    if clean != url:
        print(f"URL cleaned: {url[:80]} -> {clean[:80]}")

    _reset_progress("starting")
    _update_progress(url=clean, current=clean)
    _download_cancel_event.clear()

    def _task():
        try:
            # Determine if this is a playlist URL
            parsed = urlparse(clean)
            params = parse_qs(parsed.query)
            has_list = "list" in params
            has_video = "v" in params
            is_playlist_path = "/playlist" in parsed.path

            is_playlist = is_playlist_path or (has_list and not has_video)

            if is_playlist:
                _update_progress(
                    status="starting",
                    current="Initializing playlist download...",
                    is_playlist=True,
                )
                _download_playlist(clean)
                return

            # Single video download
            temp_dir = tempfile.mkdtemp()
            try:
                result = _download_single_video_task(clean, temp_dir, 1, 1, clean)

                if _download_cancel_event.is_set():
                    _update_progress(status="cancelled")
                elif result.get("success"):
                    _update_progress(
                        status="completed",
                        current=result["filename"],
                        percent=100,
                        downloaded_count=1,
                    )
                else:
                    _update_progress(
                        status="error",
                        current=result.get("error", "Download failed"),
                    )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as exc:
            err = str(exc)
            if _download_cancel_event.is_set():
                _update_progress(status="cancelled")
            else:
                _update_progress(status="error", current=err[:300])
                print(f"Download error: {err}")

    Thread(target=_task, daemon=True).start()
    return {"status": "started", "message": "Download started"}


def cancel_download():
    """Signal the running download to stop."""
    _download_cancel_event.set()
    _update_progress(status="cancelling", action="cancel")