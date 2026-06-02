"""
DriveSync - YouTube Download Module
URL cleaning, audio downloading, metadata enhancement, and cancel support.
"""

import os
import re
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import Thread, Event
from urllib.parse import urlparse, parse_qs, urlencode

import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TYER

from config import MUSIC_DIR, THUMBNAIL_DIR, download_progress

# ---------------------------
# Cancel Support
# ---------------------------
_download_cancel_event = Event()


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


def _progress_hook(d):
    """yt-dlp progress hook – checks cancel flag."""
    if _download_cancel_event.is_set():
        raise Exception("Download cancelled by user")

    if d["status"] == "downloading":
        try:
            pct = d.get("_percent_str", "0%").strip().replace("%", "")
            download_progress["percent"] = float(pct)
        except Exception:
            download_progress["percent"] = 0
        download_progress["status"] = "downloading"
        download_progress["current"] = d.get("filename", "unknown")
    elif d["status"] == "finished":
        download_progress["status"] = "processing"
        download_progress["percent"] = 100
    elif d["status"] == "error":
        download_progress["status"] = "error"


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
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
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


def enhance_metadata(mp3_path, info_dict):
    """Embed ID3 tags + album art into an MP3 file from yt-dlp info."""
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


def _download_single_video(video_url, temp_dir):
    """
    Download a single video URL to temp_dir, convert to MP3, and copy to the library.
    Creates its own YoutubeDL instance per video so output template is correct.
    Returns dict {success, filename, error} or raises on cancel.
    """
    if _download_cancel_event.is_set():
        return {"error": "cancelled"}

    template = os.path.join(temp_dir, "%(title)s.%(ext)s")
    opts = _build_ydl_opts(template)

    info = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
    except Exception as exc:
        err = str(exc)
        if "cancelled" in err.lower():
            return {"error": "cancelled"}
        print(f"Download attempt failed: {err}")
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
    return {"success": True, "filename": dest.name, "title": title}


def _download_playlist(clean_url):
    """Download all videos in a playlist one by one."""
    results = {"success": True, "downloaded": [], "errors": [], "total": 0}

    # First, extract playlist entries
    try:
        detect_opts = dict(_build_ydl_opts(""))
        detect_opts["extract_flat"] = False
        detect_opts["skip_download"] = True
        with yt_dlp.YoutubeDL(detect_opts) as ydl:
            playlist_info = ydl.extract_info(clean_url, download=False)
            if not playlist_info:
                results["error"] = "No playlist info returned"
                results["success"] = False
                return results

            entries = playlist_info.get("entries", [])
            if not entries:
                results["error"] = "Playlist is empty"
                results["success"] = False
                return results

            results["total"] = len(entries)

            for idx, entry in enumerate(entries):
                if _download_cancel_event.is_set():
                    results["status"] = "cancelled"
                    return results

                # Build the individual video URL
                video_id = entry.get("id")
                if not video_id:
                    results["errors"].append(f"Entry {idx+1}: Could not resolve video ID")
                    continue

                video_url = f"https://www.youtube.com/watch?v={video_id}"
                entry_title = entry.get("title", f"video_{video_id}")

                # Update progress
                download_progress["status"] = "downloading"
                download_progress["percent"] = int((idx / len(entries)) * 100)
                download_progress["current"] = f"[{idx+1}/{len(entries)}] {entry_title}"

                # Create a fresh temp dir for each video
                video_temp = tempfile.mkdtemp()
                try:
                    result = _download_single_video(video_url, video_temp)
                    if result.get("success"):
                        results["downloaded"].append(result["filename"])
                    elif result.get("error") == "cancelled":
                        results["status"] = "cancelled"
                        return results
                    else:
                        results["errors"].append(f"{entry_title}: {result.get('error', 'Unknown error')}")
                finally:
                    shutil.rmtree(video_temp, ignore_errors=True)

            results["downloaded_count"] = len(results["downloaded"])
            results["error_count"] = len(results["errors"])
            return results

    except Exception as exc:
        results["success"] = False
        results["error"] = str(exc)[:300]
        return results


def start_download(url):
    """
    Kick off a YouTube-to-MP3 download in a background thread.
    Supports single videos and playlists.
    Returns immediately; poll /api/download/progress for status.
    """
    clean = clean_url(url)
    if clean != url:
        print(f"URL cleaned: {url[:80]} -> {clean[:80]}")

    download_progress["status"] = "starting"
    download_progress["percent"] = 0
    download_progress["current"] = clean
    _download_cancel_event.clear()

    def _task():
        temp_dir = None
        try:
            # Determine if this is a playlist URL by checking the URL itself
            # Pure playlists have "/playlist" in path OR have "list=" with no "v" param
            parsed = urlparse(clean)
            params = parse_qs(parsed.query)
            has_list = "list" in params
            has_video = "v" in params
            is_playlist_path = "/playlist" in parsed.path

            # Treat as playlist if:
            # - Path is /playlist, OR
            # - Has list= param without a v= param (single video with list param is not a playlist)
            is_playlist = is_playlist_path or (has_list and not has_video)

            if is_playlist:
                download_progress["status"] = "starting"
                download_progress["current"] = "Downloading playlist..."
                result = _download_playlist(clean)

                if result.get("status") == "cancelled":
                    download_progress["status"] = "cancelled"
                elif result.get("success") and result.get("downloaded"):
                    download_progress["status"] = "completed"
                    count = result.get("downloaded_count", 0)
                    download_progress["current"] = f"Downloaded {count} songs"
                    download_progress["percent"] = 100
                    if result.get("errors"):
                        download_progress["current"] += f" ({len(result['errors'])} errors)"
                else:
                    download_progress["status"] = "error"
                    download_progress["current"] = result.get("error") or "Playlist download failed"
                return

            # Single video download
            temp_dir = tempfile.mkdtemp()

            if _download_cancel_event.is_set():
                download_progress["status"] = "cancelled"
                return

            result = _download_single_video(clean, temp_dir)

            if result.get("error") == "cancelled":
                download_progress["status"] = "cancelled"
            elif result.get("success"):
                download_progress["status"] = "completed"
                download_progress["current"] = result["filename"]
                download_progress["percent"] = 100
            else:
                download_progress["status"] = "error"
                download_progress["current"] = result.get("error", "Download failed")

        except Exception as exc:
            err = str(exc)
            if _download_cancel_event.is_set():
                download_progress["status"] = "cancelled"
            else:
                download_progress["status"] = "error"
                download_progress["current"] = err[:300]
                print(f"Download error: {err}")
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    Thread(target=_task, daemon=True).start()
    return {"status": "started", "message": "Download started"}


def cancel_download():
    """Signal the running download to stop."""
    _download_cancel_event.set()
    download_progress["status"] = "cancelling"