// ===== DriveSync – Library Module =====

async function loadLibrary() {
    const container = document.getElementById('librarySongs');
    const search = document.getElementById('librarySearch').value;
    try {
        const url = search ? `/api/songs?search=${encodeURIComponent(search)}` : '/api/songs';
        const res = await fetch(url);
        const songs = await res.json();
        DS.allSongs = songs;

        if (songs.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">🎶</div><p>No songs in library. Download or import some music!</p></div>';
            return;
        }

        let html = '<div class="song-grid">';
        songs.forEach(s => {
            const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
            const dur = formatDuration(s.duration);
            const size = formatSize(s.size);
            const playing = DS.currentPlayingId === s.id;
            const escapedTitle = escHtml(s.title).replace(/'/g, "\\'");

            html += `
                <div class="song-card ${playing ? 'playing' : ''}" data-song-id="${s.id}">
                    <div class="song-thumb" onclick="event.stopPropagation();togglePlay('${s.id}','${escapedTitle}')">
                        ${thumb ? `<img src="${thumb}" alt="" loading="lazy">` : '🎵'}
                        <div class="play-overlay ${playing ? 'playing' : ''}">${playing ? '⏸' : '▶️'}</div>
                    </div>
                    <div class="song-info">
                        <div class="title">${escHtml(s.title)}</div>
                        <div class="artist">${escHtml(s.artist)}</div>
                        <div class="meta">${dur} · ${size}</div>
                    </div>
                    <div class="song-actions">
                        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation();openPlaylistPicker('${s.id}')" title="Add to playlist">+</button>
                        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteSong('${s.id}')" title="Delete">🗑️</button>
                    </div>
                </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><div class="icon">❌</div><p>Error loading library</p></div>';
    }
}

async function deleteSong(id) {
    if (!confirm('Delete this song from the library?')) return;
    try {
        const res = await fetch(`/api/songs/${id}/delete`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) loadLibrary();
    } catch (e) {
        alert('Error deleting song');
    }
}

// ── Playlist Picker Modal ────────────────────────────────────────────

let _pendingSongId = null;

async function openPlaylistPicker(songId) {
    _pendingSongId = songId;
    const container = document.getElementById('playlistPickerList');
    const overlay = document.getElementById('playlistPickerModal');

    try {
        const res = await fetch('/api/playlists');
        const playlists = await res.json();

        if (playlists.length === 0) {
            alert('No playlists. Create one first!');
            return;
        }

        container.innerHTML = playlists.map(p =>
            `<div class="playlist-picker-item" onclick="addToPickedPlaylist('${p.id}')">
                <span class="picker-icon">📁</span>
                <span class="picker-name">${escHtml(p.name)}</span>
                <span class="picker-count">${p.song_count} songs</span>
            </div>`
        ).join('');

        overlay.classList.add('show');
        document.getElementById('playlistPickerSearch').value = '';
        document.getElementById('playlistPickerSearch').focus();
    } catch (e) {
        alert('Error loading playlists');
    }
}

function filterPlaylistPicker() {
    const q = document.getElementById('playlistPickerSearch').value.toLowerCase();
    document.querySelectorAll('.playlist-picker-item').forEach(el => {
        const name = el.querySelector('.picker-name').textContent.toLowerCase();
        el.style.display = name.includes(q) ? 'flex' : 'none';
    });
}

async function addToPickedPlaylist(playlistId) {
    if (!_pendingSongId) return;
    try {
        const res = await fetch(`/api/playlists/${playlistId}/songs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ song_id: _pendingSongId })
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('playlistPickerModal').classList.remove('show');
        }
    } catch (e) {
        alert('Error adding to playlist');
    }
}

function closePlaylistPicker() {
    document.getElementById('playlistPickerModal').classList.remove('show');
    _pendingSongId = null;
}