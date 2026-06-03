// ===== DriveSync – Playlist Module =====

async function loadPlaylists() {
    const container = document.getElementById('playlistsList');
    try {
        const res = await fetch('/api/playlists');
        const playlists = await res.json();
        if (playlists.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>No playlists yet.</p></div>';
            return;
        }
        let html = '<div class="playlist-grid">';
        playlists.forEach(p => {
            const shuff = p.shuffled ? '🔀 ' : '';
            const created = p.created ? p.created.slice(0, 10) : '';
            html += `<div class="playlist-card" onclick="viewPlaylist('${p.id}')">
                <div class="icon">${shuff}📁</div>
                <div class="name">${escHtml(p.name)}</div>
                <div class="count">${p.song_count} songs${created ? ' · ' + created : ''}</div>
            </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>Error loading playlists</p></div>';
    }
}

function showCreatePlaylist() {
    document.getElementById('newPlaylistName').value = '';
    document.getElementById('createPlaylistModal').classList.add('show');
}

function closeModal() {
    document.getElementById('createPlaylistModal').classList.remove('show');
}

async function createPlaylist() {
    const name = document.getElementById('newPlaylistName').value.trim();
    if (!name) { alert('Please enter a name'); return; }
    try {
        const res = await fetch('/api/playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.success) { closeModal(); loadPlaylists(); }
        else { alert('Error: ' + (data.error || 'Unknown')); }
    } catch (e) { alert('Error creating playlist'); }
}

async function viewPlaylist(id) {
    DS.currentPlaylistId = id;
    document.getElementById('playlistsView').style.display = 'none';
    document.getElementById('playlistDetail').style.display = 'block';

    try {
        const res = await fetch(`/api/playlists/${id}`);
        const data = await res.json();
        document.getElementById('playlistDetailName').textContent = data.name + (data.shuffled ? ' 🔀' : '');

        document.getElementById('shuffleBtn').style.display = 'inline-flex';
        document.getElementById('unshuffleBtn').style.display = data.shuffled && data.original_order ? 'inline-flex' : 'none';

        const songsContainer = document.getElementById('playlistSongs');
        if (data.songs_info && data.songs_info.length > 0) {
            let html = '<div class="song-grid">';
            data.songs_info.forEach((s, idx) => {
                const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
                const playing = DS.currentPlayingId === s.id;
                const escapedTitle = escHtml(s.title).replace(/'/g, "\\'");
                html += `<div class="song-card ${playing ? 'playing' : ''}" data-song-id="${s.id}">
                    <span style="color:var(--text-muted);font-weight:700;width:20px;flex-shrink:0;font-size:12px;">${idx+1}</span>
                    <div class="song-thumb" onclick="event.stopPropagation();togglePlay('${s.id}','${escapedTitle}')">
                        ${thumb ? `<img src="${thumb}" loading="lazy">` : '🎵'}
                        <div class="play-overlay ${playing ? 'playing' : ''}">${playing ? '⏸' : '▶️'}</div>
                    </div>
                    <div class="song-info">
                        <div class="title">${escHtml(s.title)}</div>
                        <div class="artist">${escHtml(s.artist)}</div>
                    </div>
                    <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();removeFromPlaylist('${encodeURIComponent(s.filename)}')">✕</button>
                </div>`;
            });
            html += '</div>';
            songsContainer.innerHTML = html;
        } else {
            songsContainer.innerHTML = '<div class="empty-state"><p>No songs in this playlist yet</p></div>';
        }
        showPlaylistAddSongs();
        loadArtistsForBatch();
    } catch (e) { alert('Error loading playlist'); }
}

function backToPlaylists() {
    DS.currentPlaylistId = null;
    document.getElementById('playlistsView').style.display = 'block';
    document.getElementById('playlistDetail').style.display = 'none';
    loadPlaylists();
}

async function showPlaylistAddSongs() {
    if (!DS.currentPlaylistId) return;
    const container = document.getElementById('playlistAddSongs');
    const search = document.getElementById('playlistSearch').value;

    try {
        const url = search ? `/api/songs?search=${encodeURIComponent(search)}` : '/api/songs';
        const res = await fetch(url);
        const songs = await res.json();
        const plRes = await fetch(`/api/playlists/${DS.currentPlaylistId}`);
        const plData = await plRes.json();
        const existing = plData.songs_info ? plData.songs_info.map(s => s.filename) : [];
        const available = songs.filter(s => !existing.includes(s.filename));

        if (available.length === 0) { container.innerHTML = '<p class="text-muted">No more songs to add</p>'; return; }

        let html = '<div class="song-grid scrollable-songs">';
        available.forEach(s => {
            const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
            html += `<div class="song-card" onclick="addToCurrentPlaylist('${s.id}')">
                <div class="song-thumb">${thumb ? `<img src="${thumb}" loading="lazy">` : '🎵'}</div>
                <div class="song-info">
                    <div class="title">${escHtml(s.title)}</div>
                    <div class="artist">${escHtml(s.artist)}</div>
                </div>
                <span style="color:var(--success);font-size:18px;flex-shrink:0;">+</span>
            </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch(e) {}
}

async function addToCurrentPlaylist(songId) {
    if (!DS.currentPlaylistId) return;
    try {
        await fetch(`/api/playlists/${DS.currentPlaylistId}/songs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ song_id: songId })
        });
        viewPlaylist(DS.currentPlaylistId);
    } catch(e) { alert('Error adding song'); }
}

async function removeFromPlaylist(filename) {
    if (!DS.currentPlaylistId) return;
    if (!confirm('Remove from playlist?')) return;
    try {
        await fetch(`/api/playlists/${DS.currentPlaylistId}/songs/${filename}`, { method: 'DELETE' });
        viewPlaylist(DS.currentPlaylistId);
    } catch(e) { alert('Error removing song'); }
}

async function shufflePlaylist() {
    if (!DS.currentPlaylistId) return;
    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}/shuffle`, { method: 'POST' });
        const data = await res.json();
        if (data.success) viewPlaylist(DS.currentPlaylistId);
    } catch(e) { alert('Error shuffling'); }
}

async function unshufflePlaylist() {
    if (!DS.currentPlaylistId) return;
    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}/unshuffle`, { method: 'POST' });
        const data = await res.json();
        if (data.success) viewPlaylist(DS.currentPlaylistId);
    } catch(e) { alert('Error unshuffling'); }
}

async function deleteCurrentPlaylist() {
    if (!DS.currentPlaylistId) return;
    if (!confirm('Delete this playlist?')) return;
    try {
        await fetch(`/api/playlists/${DS.currentPlaylistId}`, { method: 'DELETE' });
        backToPlaylists();
    } catch(e) { alert('Error deleting playlist'); }
}

// ── Batch Add by Artist ──────────────────────────────────────────────

async function loadArtistsForBatch() {
    const select = document.getElementById('batchArtistSelect');
    try {
        const res = await fetch('/api/artists');
        const artists = await res.json();
        let html = '<option value="">-- Select an artist --</option>';
        artists.forEach(a => {
			console.log(a);
            const safe = escHtml(a);
            html += `<option value="${safe}">${safe}</option>`;
        });
        select.innerHTML = html;
    } catch(e) {
        select.innerHTML = '<option value="">Error loading artists</option>';
    }
}

async function batchAddByArtist() {
    if (!DS.currentPlaylistId) return;
    const select = document.getElementById('batchArtistSelect');
    const artist = select.value;
    if (!artist) { alert('Please select an artist'); return; }

    if (!confirm(`Add all songs by "${artist}" to this playlist?`)) return;

    const statusEl = document.getElementById('batchStatus');
    statusEl.textContent = 'Adding songs...';

    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}/songs/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist })
        });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = `✅ Added ${data.added} songs by "${artist}"`;
            viewPlaylist(DS.currentPlaylistId);
        } else {
            statusEl.textContent = '❌ Error: ' + (data.error || 'Unknown');
        }
    } catch(e) {
        statusEl.textContent = '❌ Error adding songs';
    }
}
