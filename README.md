# 🎵 DriveSync

**Download, manage, and sync music playlists to any USB drive or SD card — from any device on your network.**

DriveSync is a self-hosted web application that lets you download music from YouTube (with full metadata), import your own audio files, build playlists, and export them as folders to external drives. Perfect for car radios, standalone MP3 players, or any device that reads from SD cards.

---

## ✨ Features

| Feature | Description |
|---|---|
| **📚 Music Library** | Browse all your MP3s with album art, metadata, duration, and size. Search by song or artist. |
| **⬇️ YouTube Download** | Paste any YouTube URL — videos and playlists — and download as 320kbps MP3 with ID3 tags (title, artist, album, year, cover art). URLs are automatically cleaned of tracking parameters. |
| **📤 File Import** | Upload MP3, M4A, WAV, FLAC, OGG, AAC, WMA. Non-MP3 files are auto-converted via FFmpeg. |
| **📋 Playlists** | Create playlists, add songs from the library, shuffle/unshuffle with original-order restoration. |
| **💾 Drive Export** | Export any playlist as a folder to a USB drive, SD card, or external disk. Optionally add `001_`, `002_`… prefixes for playback order. Choose a subfolder (e.g. `Playlists/Music`) for organisation. View and delete existing playlist folders directly from the UI. |
| **🎧 Audio Preview** | Click any song thumbnail to preview playback with a built-in mini-player. |
| **🖥️ Cross-Platform** | Runs on **Windows** and **Linux** (including Raspberry Pi). Install scripts included. |
| **🌐 Network Access** | Access from any device on your LAN via any modern web browser. |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+**
- **FFmpeg** (for audio conversion) — [Download FFmpeg](https://ffmpeg.org/download.html)

### Windows

```powershell
# Run the installer (creates a virtual environment)
.\install.ps1

# Start the server
.\run.bat
```

### Linux / Raspberry Pi

```bash
# Make the installer executable
chmod +x install.sh

# Run the installer
./install.sh

# Start the server
./run.sh
```

### Manual Installation

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# Windows: venv\Scripts\activate
# Linux:   source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start DriveSync
python backend/main.py
```

### Open the Web UI

```
http://localhost:5000
```

Or find your machine's IP and access it from any device on your network:
```
http://192.168.x.x:5000
```

---

## 📁 Project Structure

```
DriveSync/
├── backend/
│   ├── __init__.py          # Package init
│   ├── config.py            # Paths, platform detection, runtime state
│   ├── library.py           # MP3 scanning, metadata reading, import/delete
│   ├── youtube.py           # YouTube URL cleaning, download, metadata embedding
│   ├── playlist.py          # Playlist CRUD, shuffle/unshuffle, reorder
│   ├── sdcard.py            # Removable drive detection, folder listing, export
│   ├── routes.py            # Flask Blueprint — all HTTP endpoints
│   └── main.py              # App entry point, CLI args, server start
├── frontend/
│   ├── index.html           # Minimal skeleton (no inline CSS/JS)
│   ├── css/
│   │   └── drivesync.css    # All styles (responsive, dark theme)
│   └── js/
│       ├── state.js         # Global application state & initialisation
│       ├── utils.js         # HTML escaping, status messages, tab switching
│       ├── player.js        # Audio preview (play/pause/stop)
│       ├── library.js       # Library listing, delete, playlist picker modal
│       ├── download.js      # Single/batch download, cancel, progress polling
│       ├── import.js        # File upload import
│       ├── playlists.js     # CRUD, shuffle/unshuffle, add/remove songs
│       └── sdcard.js        # Drive detection, folder management, export
├── music_downloads/         # Downloaded/imported MP3 files
│   └── .thumbnails/         # Cached album art thumbnails
├── playlists/               # Playlist data (JSON)
├── install.sh               # Linux installer (Debian/Raspberry Pi)
├── install.ps1              # Windows PowerShell installer
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## 🔧 Configuration

All configuration is in `backend/config.py`:

| Setting | Default | Description |
|---|---|---|
| `MUSIC_DIR` | `./music_downloads` | Where MP3 files are stored |
| `PLAYLIST_DIR` | `./playlists` | Where playlist JSON files are kept |
| `THUMBNAIL_DIR` | `./music_downloads/.thumbnails` | Cached album art |
| `PORT` | `5000` | Web server port (change via `--port`) |
| `HOST` | `0.0.0.0` | Bind address (change via `--host`) |

### CLI Options

```bash
python backend/main.py --host 0.0.0.0 --port 8080 --debug
```

---

## 📡 API Overview

| Endpoint | Method | Description |
|---|---|---|
| `/api/songs` | GET | List all songs (optional `?search=`) |
| `/api/songs/{id}/stream` | GET | Stream MP3 audio (range-request supported) |
| `/api/songs/{id}/delete` | DELETE | Remove a song from the library |
| `/api/download` | POST | Start a YouTube download |
| `/api/download/progress` | GET | Poll download progress |
| `/api/download/cancel` | POST | Cancel the current download |
| `/api/import` | POST | Upload audio files |
| `/api/playlists` | GET/POST | List / create playlists |
| `/api/playlists/{id}` | GET/DELETE | Get / delete a playlist |
| `/api/playlists/{id}/songs` | POST | Add a song to a playlist |
| `/api/playlists/{id}/songs/{filename}` | DELETE | Remove a song from a playlist |
| `/api/playlists/{id}/shuffle` | POST | Shuffle playlist (saves original order) |
| `/api/playlists/{id}/unshuffle` | POST | Restore original order |
| `/api/sdcard` | GET | List detected removable drives |
| `/api/sdcard/export` | POST | Export a playlist to a drive |
| `/api/sdcard/folders` | POST | List playlist folders on a drive |
| `/api/sdcard/folders/delete` | POST | Delete a playlist folder from a drive |

---

## 🛠️ Built With

- **[Flask](https://flask.palletsprojects.com/)** — Python web framework
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — YouTube audio download
- **[Mutagen](https://mutagen.readthedocs.io/)** — MP3 ID3 metadata editing
- **[FFmpeg](https://ffmpeg.org/)** — Audio conversion (non-MP3 formats)
- **Vanilla HTML/CSS/JS** — No frontend frameworks, no external dependencies

---

## 🐍 Raspberry Pi Setup

On a Raspberry Pi (Raspberry Pi OS):

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv ffmpeg

git clone https://github.com/YOUR_USER/DriveSync.git
cd DriveSync
chmod +x install.sh
./install.sh
./run.sh
```

For permanent background operation:
```bash
nohup ./run.sh > drivesync.log 2>&1 &
```

Or create a systemd service (`/etc/systemd/system/drivesync.service`).

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

## 🙋 FAQ

**Q: Can I download entire YouTube playlists?**  
A: Yes! Just paste the playlist URL (e.g. `https://www.youtube.com/playlist?list=...`).

**Q: Why is the download stuck / showing 403 errors?**  
A: yt-dlp uses modern User-Agent headers and client emulation. If issues persist, update yt-dlp: `pip install -U yt-dlp`.

**Q: How do I find my PC's IP address?**  
A: Run `ipconfig` (Windows) or `ip addr` (Linux) and look for your local network IP (usually starts with `192.168.` or `10.`).

**Q: Can I access DriveSync from my phone?**  
A: Yes — the web UI is fully responsive and works on mobile browsers.