// ===== DriveSync – Full Queue-Based Player & Preview =====

/** Toggle play/pause for a song (quick preview from library/playlists) */
function togglePlay(id, title) {
    // Check if this song is playing in the player queue
    if (Player.currentIndex >= 0 && Player.queue[Player.currentIndex]?.id === id) {
        playerTogglePlay();
        return;
    }

    if (DS.currentAudio && DS.currentPlayingId === id) {
        if (DS.currentAudio.paused) {
            document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
                el.textContent = '⏸';
            });
            DS.currentAudio.play();
        } else {
            document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
                el.textContent = '▶️';
            });
            DS.currentAudio.pause();
        }
        return;
    }
    stopAudio();
    DS.currentPlayingId = id;

    const url = `/api/songs/${encodeURIComponent(id)}/stream`;
    const audioEl = document.getElementById('audioPlayer');
    document.getElementById('nowPlayingText').textContent = `🎵 ${title}`;
    document.getElementById('miniPlayer').classList.add('show');

    audioEl.src = url;
    audioEl.play().catch(() => {});
    audioEl.onended = () => stopAudio();
    DS.currentAudio = audioEl;

    // Highlight the playing card
    document.querySelectorAll('.song-card.playing, .play-overlay.playing').forEach(el => el.classList.remove('playing'));
    document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
        el.classList.add('playing');
        el.textContent = '⏸';
    });
    document.querySelectorAll(`[data-song-id="${id}"]`).forEach(el => el.classList.add('playing'));
}

/** Stop playback and hide the mini-player */
function stopAudio() {
    if (DS.currentAudio) { DS.currentAudio.pause(); DS.currentAudio = null; }
    const audioEl = document.getElementById('audioPlayer');
    audioEl.pause();
    audioEl.src = '';
    DS.currentPlayingId = null;
    document.getElementById('miniPlayer').classList.remove('show');

    document.querySelectorAll('.song-card.playing, .play-overlay.playing').forEach(el => {
        el.classList.remove('playing');
        if (el.classList.contains('play-overlay')) el.textContent = '▶️';
    });
}

// ===== DriveSync – Full Queue-Based Player =====

// Player state
const Player = {
    queue: [],
    currentIndex: -1,
    autoplay: false,
    audio: null,
    isPlaying: false,
    _usedForAutoplay: new Set(),
};

/** Initialize the player audio (shared with mini-player via #audioPlayer) */
function playerInit() {
    Player.audio = document.getElementById('audioPlayer');
    Player.audio.addEventListener('timeupdate', playerUpdateProgress);
    Player.audio.addEventListener('ended', playerOnEnded);
    Player.audio.addEventListener('play', () => { Player.isPlaying = true; playerUpdatePlayBtn(); });
    Player.audio.addEventListener('pause', () => { Player.isPlaying = false; playerUpdatePlayBtn(); });

    // Autoplay toggle
    document.getElementById('playerAutoplayToggle').addEventListener('change', function() {
        Player.autoplay = this.checked;
    });

    // Load playlist modal
    loadPlaylistPickerForPlayer();
}

/** Add a song to the end of the queue */
function playerAddToQueue(song) {
    Player.queue.push(song);
    playerRenderQueue();
    if (Player.queue.length === 1 && Player.currentIndex === -1) {
        playerPlayIndex(0);
    }
}

/** Play a specific index in the queue */
function playerPlayIndex(idx) {
    if (idx < 0 || idx >= Player.queue.length) return;
    Player.currentIndex = idx;
    const song = Player.queue[idx];

    // Stop the mini-player preview if it was playing something else
    stopAudio();

    // Use the same audio element
    const audioEl = Player.audio;
    const url = `/api/songs/${encodeURIComponent(song.id)}/stream`;
    audioEl.src = url;
    audioEl.play().catch(() => {});
    Player.isPlaying = true;
    DS.currentPlayingId = song.id;

    // Update UI
    playerUpdateNowPlaying(song);
    playerUpdatePlayBtn();
    playerRenderQueue();

    // Update library highlight
    document.querySelectorAll('.song-card.playing, .play-overlay.playing').forEach(el => el.classList.remove('playing'));
    document.querySelectorAll(`[data-song-id="${song.id}"]`).forEach(el => el.classList.add('playing'));
}

/** Update the now-playing display */
function playerUpdateNowPlaying(song) {
    document.getElementById('playerSongTitle').textContent = song.title || 'Unknown';
    document.getElementById('playerSongArtist').textContent = song.artist || '—';

    // Thumbnail
    const img = document.getElementById('playerThumbImg');
    const placeholder = document.getElementById('playerThumbPlaceholder');
    if (song.has_thumbnail) {
        img.src = `/api/thumbnails/${song.id}.jpg`;
        img.style.display = 'block';
        placeholder.style.display = 'none';
    } else {
        img.style.display = 'none';
        placeholder.style.display = 'inline';
    }

    // Media Session API - Update lockscreen / notification with song info & thumbnail
    if ('mediaSession' in navigator) {
        const artwork = [];
        if (song.has_thumbnail) {
            // Use the thumbnail as album art
            artwork.push({
                src: `/api/thumbnails/${song.id}.jpg`,
                sizes: '300x300',
                type: 'image/jpeg'
            });
        }
        navigator.mediaSession.metadata = new MediaMetadata({
            title: song.title || 'Unknown',
            artist: song.artist || '—',
            album: 'DriveSync',
            artwork: artwork
        });

        // Set up action handlers (only need to set once)
        if (!navigator.mediaSession._handlersSet) {
            navigator.mediaSession._handlersSet = true;
            navigator.mediaSession.setActionHandler('play', () => playerTogglePlay());
            navigator.mediaSession.setActionHandler('pause', () => playerTogglePlay());
            navigator.mediaSession.setActionHandler('previoustrack', () => playerPrev());
            navigator.mediaSession.setActionHandler('nexttrack', () => playerNext());
            navigator.mediaSession.setActionHandler('seekto', (details) => {
                if (Player.audio && Player.audio.duration) {
                    Player.audio.currentTime = details.seekTime;
                }
            });
        }
    }
}

/** Toggle play/pause for the player */
function playerTogglePlay() {
    if (Player.queue.length === 0 || Player.currentIndex === -1) return;
    const audioEl = Player.audio;
    if (audioEl.paused) {
        audioEl.play().catch(() => {});
    } else {
        audioEl.pause();
    }
}

/** Next song in queue */
async function playerNext() {
    if (Player.queue.length === 0) return;
    if (Player.currentIndex < Player.queue.length - 1) {
        playerPlayIndex(Player.currentIndex + 1);
    } else {
        // Queue ended
        if (Player.autoplay) {
            await playerAddAutoplaySong();
            if (Player.currentIndex + 1 < Player.queue.length) {
                playerPlayIndex(Player.currentIndex + 1);
            }
        } else {
            Player.currentIndex = -1;
            Player.isPlaying = false;
            playerUpdatePlayBtn();
        }
    }
}

/** Previous song in queue */
function playerPrev() {
    if (Player.queue.length === 0 || Player.currentIndex <= 0) return;
    playerPlayIndex(Player.currentIndex - 1);
}

/** Called when a song ends */
async function playerOnEnded() {
    if (Player.currentIndex < Player.queue.length - 1) {
        playerPlayIndex(Player.currentIndex + 1);
    } else if (Player.autoplay) {
        await playerAddAutoplaySong();
        if (Player.currentIndex + 1 < Player.queue.length) {
            playerPlayIndex(Player.currentIndex + 1);
        }
    } else {
        Player.isPlaying = false;
        playerUpdatePlayBtn();
        playerRenderQueue();
    }
}

/** Add a random song from the library for autoplay */
async function playerAddAutoplaySong() {
    try {
        const res = await fetch('/api/songs');
        const songs = await res.json();
        if (songs.length === 0) return;

        // Pick a song not recently used for autoplay
        const available = songs.filter(s => !Player._usedForAutoplay.has(s.id));
        const pool = available.length > 0 ? available : songs;
        const picked = pool[Math.floor(Math.random() * pool.length)];

        Player._usedForAutoplay.add(picked.id);
        if (Player._usedForAutoplay.size > 50) Player._usedForAutoplay.clear();

        Player.queue.push(picked);
        playerRenderQueue();
    } catch(e) {}
}

/** Remove a song from the queue */
function playerRemoveFromQueue(idx) {
    Player.queue.splice(idx, 1);
    if (idx < Player.currentIndex) {
        Player.currentIndex--;
    } else if (idx === Player.currentIndex) {
        // Currently playing song was removed
        if (Player.queue.length > 0) {
            const nextIdx = Math.min(Player.currentIndex, Player.queue.length - 1);
            playerPlayIndex(nextIdx);
        } else {
            Player.currentIndex = -1;
            Player.isPlaying = false;
            Player.audio.pause();
            Player.audio.src = '';
            playerUpdateNowPlaying({ title: 'No song playing', artist: '—' });
            playerUpdatePlayBtn();
        }
    }
    playerRenderQueue();
}

/** Clear the entire queue */
function playerClearQueue() {
    Player.queue = [];
    Player.currentIndex = -1;
    Player.isPlaying = false;
    Player.audio.pause();
    Player.audio.src = '';
    DS.currentPlayingId = null;
    Player._usedForAutoplay.clear();
    playerUpdateNowPlaying({ title: 'No song playing', artist: '—' });
    playerUpdatePlayBtn();
    playerRenderQueue();
    document.getElementById('playerProgress').value = 0;
    document.getElementById('playerTimeCurrent').textContent = '0:00';
    document.getElementById('playerTimeTotal').textContent = '0:00';
}

/** Save the current queue as a playlist */
async function playerSaveQueue() {
    if (Player.queue.length === 0) { alert('Queue is empty'); return; }
    const name = prompt('Enter a name for the new playlist:', 'My Queue');
    if (!name) return;

    try {
        const res = await fetch('/api/playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (!data.success) { alert('Error creating playlist'); return; }

        const pid = data.id;
        for (const song of Player.queue) {
            await fetch(`/api/playlists/${pid}/songs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ song_id: song.id })
            });
        }
        alert(`✅ Queue saved as "${name}"!`);
    } catch(e) {
        alert('Error saving queue');
    }
}

/** Load a playlist into the queue */
async function playerLoadPlaylist() {
    // Show the playlist picker modal
    document.getElementById('playlistPickerModal').classList.add('show');
    await loadPlaylistPickerForPlayer();
}

/** Load a specific playlist into the queue */
async function playerLoadPlaylistById(playlistId) {
    closePlaylistPicker();
    try {
        const res = await fetch(`/api/playlists/${playlistId}`);
        const data = await res.json();
        if (!data.songs_info || data.songs_info.length === 0) {
            alert('Playlist is empty');
            return;
        }
        // Replace queue with playlist songs
        Player.queue = data.songs_info.map(s => ({
            id: s.id,
            title: s.title,
            artist: s.artist,
            has_thumbnail: s.has_thumbnail,
            duration: s.duration,
        }));
        Player.currentIndex = -1;
        Player._usedForAutoplay.clear();
        playerRenderQueue();
        if (Player.queue.length > 0) {
            playerPlayIndex(0);
        }
    } catch(e) {
        alert('Error loading playlist');
    }
}

/** Load playlist picker for the player */
async function loadPlaylistPickerForPlayer() {
    const list = document.getElementById('playlistPickerList');
    try {
        const res = await fetch('/api/playlists');
        const playlists = await res.json();
        if (playlists.length === 0) {
            list.innerHTML = '<p class="text-muted">No playlists available</p>';
            return;
        }
        let html = '';
        playlists.forEach(p => {
            html += `<div class="playlist-picker-item" onclick="playerLoadPlaylistById('${p.id}')">
                📁 ${escHtml(p.name)} <span class="text-muted">(${p.song_count} songs)</span>
            </div>`;
        });
        list.innerHTML = html;
    } catch(e) {
        list.innerHTML = '<p class="text-muted">Error loading playlists</p>';
    }
}

/** Update the progress bar — only when player queue is active */
function playerUpdateProgress() {
    if (Player.currentIndex === -1 || !Player.audio || !Player.audio.duration) return;
    const pct = (Player.audio.currentTime / Player.audio.duration) * 100;
    document.getElementById('playerProgress').value = pct;
    document.getElementById('playerTimeCurrent').textContent = formatDuration(Math.floor(Player.audio.currentTime));
    document.getElementById('playerTimeTotal').textContent = formatDuration(Math.floor(Player.audio.duration));
}

/** Seek to a position in the current song */
function playerSeek(value) {
    if (!Player.audio || !Player.audio.duration) return;
    Player.audio.currentTime = (value / 100) * Player.audio.duration;
}

/** Update play button icon */
function playerUpdatePlayBtn() {
    const btn = document.getElementById('playerPlayBtn');
    btn.textContent = Player.isPlaying ? '⏸' : '▶️';
}

/** Render the queue list */
function playerRenderQueue() {
    const container = document.getElementById('playerQueue');
    if (Player.queue.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>Queue is empty. Add songs from the library!</p></div>';
        return;
    }
    let html = '';
    Player.queue.forEach((song, idx) => {
        const isCurrent = idx === Player.currentIndex;
        html += `<div class="player-queue-item ${isCurrent ? 'current' : ''}">
            <div class="player-queue-thumb">
                ${song.has_thumbnail ? `<img src="/api/thumbnails/${song.id}.jpg" alt="" loading="lazy">` : '🎵'}
            </div>
            <div class="player-queue-info" onclick="playerPlayIndex(${idx})">
                <div class="title">${isCurrent ? '🔊 ' : ''}${escHtml(song.title)}</div>
                <div class="artist text-muted">${escHtml(song.artist || 'Unknown')}</div>
            </div>
            <button class="player-queue-remove" onclick="event.stopPropagation();playerRemoveFromQueue(${idx})" title="Remove">✕</button>
        </div>`;
    });
    container.innerHTML = html;
}

// ===== YouTube Import =====

function showImportYoutubeModal() {
    const url = prompt('Enter YouTube playlist URL to import:');
    if (!url) return;

    const statusEl = document.getElementById('playlistsList');
    statusEl.innerHTML = '<div class="empty-state"><p>⏳ Checking YouTube playlist...</p></div>';

    // Start the import
    fetch('/api/playlists/import-youtube', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            statusEl.innerHTML = `<div class="empty-state"><p>❌ Error: ${escHtml(data.error)}</p></div>`;
            setTimeout(loadPlaylists, 3000);
            return;
        }
        // Start polling for progress
        statusEl.innerHTML = `<div class="empty-state"><p>⏳ Importing ${data.missing} missing songs (${data.total} total)...</p></div>`;
        playerPollImportProgress(data.total);
    })
    .catch(e => {
        statusEl.innerHTML = `<div class="empty-state"><p>❌ Error: ${escHtml(e.message)}</p></div>`;
        setTimeout(loadPlaylists, 3000);
    });
}

function playerPollImportProgress(total) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch('/api/playlists/import-youtube-progress');
            const data = await res.json();
            const statusEl = document.getElementById('playlistsList');

            if (data.download_status === 'downloading' || data.download_status === 'starting' || data.download_status === 'processing') {
                const pct = data.download_percent || 0;
                statusEl.innerHTML = `<div class="empty-state">
                    <p>⏳ Downloading missing songs... ${Math.round(pct)}%</p>
                    <div class="progress-bar" style="margin-top:8px;max-width:300px;"><div class="progress-fill" style="width:${pct}%"></div></div>
                </div>`;
            }

            if (data.status === 'completed') {
                clearInterval(interval);
                statusEl.innerHTML = `<div class="empty-state"><p>✅ Import complete! "${escHtml(data.playlist_name)}" created with ${data.added} songs.</p></div>`;
                setTimeout(loadPlaylists, 2000);
            } else if (data.error) {
                clearInterval(interval);
                statusEl.innerHTML = `<div class="empty-state"><p>❌ Error: ${escHtml(data.error)}</p></div>`;
                setTimeout(loadPlaylists, 3000);
            }
        } catch(e) {
            clearInterval(interval);
        }
    }, 1000);
}

// ===== Add to Queue from Library =====

// Add "Add to Queue" button to library songs via event delegation
document.addEventListener('click', function(e) {
    const grid = document.getElementById('librarySongGrid');
    if (!grid || !grid.contains(e.target)) return;

    const addQueueBtn = e.target.closest('[data-action="addtoqueue"]');
    if (addQueueBtn) {
        e.stopPropagation();
        const songCard = addQueueBtn.closest('.song-card');
        if (!songCard) return;
        const songId = songCard.dataset.songId;
        if (!songId) return;
        // Find song info from DS.allSongs
        const song = DS.allSongs.find(s => s.id === songId);
        if (song) {
            playerAddToQueue({
                id: song.id,
                title: song.title,
                artist: song.artist,
                has_thumbnail: song.has_thumbnail,
                duration: song.duration,
            });
        }
        return;
    }
});

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', playerInit);