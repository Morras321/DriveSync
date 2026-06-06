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

        let html = '<div class="song-grid" id="librarySongGrid">';
        songs.forEach(s => {
            const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
            const dur = formatDuration(s.duration);
            const size = formatSize(s.size);
            const playing = DS.currentPlayingId === s.id;

            html += `
                <div class="song-card ${playing ? 'playing' : ''}" data-song-id="${s.id}">
                    <div class="song-thumb" data-song-id="${s.id}" data-song-title="${escAttr(s.title)}">
                        ${thumb ? `<img src="${thumb}" alt="" loading="lazy">` : '🎵'}
                        <div class="play-overlay ${playing ? 'playing' : ''}">${playing ? '⏸' : '▶'}</div>
                    </div>
                    <div class="song-info">
                        <div class="title" title="${escAttr(s.title)}">${escHtml(s.title)}</div>
                        <div class="artist">${escHtml(s.artist)}</div>
                        <div class="meta">${dur} · ${size}</div>
                    </div>
                    <div class="song-actions">
                        <button class="btn btn-primary btn-sm" data-action="addtoplaylist" data-song-id="${s.id}" title="Add to playlist">+</button>
                        <button class="btn btn-danger btn-sm" data-action="delete" data-song-id="${s.id}" title="Delete">🗑️</button>
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
        const res = await fetch(`/api/songs/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) { loadLibrary(); }
        else { alert('Error: ' + (data.error || 'Unknown')); }
    } catch (e) { alert('Error deleting song'); }
}

// ===== Event delegation for library song grid =====
document.addEventListener('click', function(e) {
    const grid = document.getElementById('librarySongGrid');
    if (!grid || !grid.contains(e.target)) return;

    // Play button / song thumb click
    const thumb = e.target.closest('.song-thumb');
    if (thumb) {
        e.stopPropagation();
        const id = thumb.dataset.songId;
        const title = thumb.dataset.songTitle;
        if (id && title) togglePlay(id, title);
        return;
    }

    // Add to playlist button
    const addBtn = e.target.closest('[data-action="addtoplaylist"]');
    if (addBtn) {
        e.stopPropagation();
        const id = addBtn.dataset.songId;
        if (id) openPlaylistPicker(id);
        return;
    }

    // Delete button
    const delBtn = e.target.closest('[data-action="delete"]');
    if (delBtn) {
        e.stopPropagation();
        const id = delBtn.dataset.songId;
        if (id) deleteSong(id);
        return;
    }
});