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
            html += `<div class="playlist-card" data-playlist-id="${p.id}">
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

        renderPlaylistSongs(data.songs_info);
        showPlaylistAddSongs();
        loadArtistsForBatch();
        // Clear playlist song search when opening
        document.getElementById('playlistSongSearch').value = '';
    } catch (e) { alert('Error loading playlist'); }
}

function renderPlaylistSongs(songsInfo) {
    const container = document.getElementById('playlistSongs');
    const searchVal = (document.getElementById('playlistSongSearch').value || '').toLowerCase();
    
    if (!songsInfo || songsInfo.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No songs in this playlist yet</p></div>';
        return;
    }

    let filtered = songsInfo;
    if (searchVal) {
        filtered = songsInfo.filter(s => 
            s.title.toLowerCase().includes(searchVal) || 
            s.artist.toLowerCase().includes(searchVal)
        );
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No songs match your search</p></div>';
        return;
    }

    let html = `<div class="text-muted" style="font-size:12px;margin-bottom:8px;">${filtered.length} of ${songsInfo.length} songs</div>`;
    html += '<div class="song-grid playlist-song-grid" id="playlistSongGrid">';
    filtered.forEach((s, idx) => {
        const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
        const playing = DS.currentPlayingId === s.id;
        html += `<div class="song-card ${playing ? 'playing' : ''}" data-song-id="${s.id}">
            <span style="color:var(--text-muted);font-weight:700;width:20px;flex-shrink:0;font-size:12px;">${idx+1}</span>
            <div class="song-thumb" data-song-id="${s.id}" data-song-title="${escAttr(s.title)}">
                ${thumb ? `<img src="${thumb}" loading="lazy">` : '🎵'}
                <div class="play-overlay ${playing ? 'playing' : ''}">${playing ? '⏸' : '▶️'}</div>
            </div>
            <div class="song-info">
                <div class="title">${escHtml(s.title)}</div>
                <div class="artist">${escHtml(s.artist)}</div>
            </div>
            <button class="btn btn-danger btn-sm" data-action="removefromplaylist" data-filename="${encodeURIComponent(s.filename)}">✕</button>
        </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
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
    const language = document.getElementById('playlistLanguageFilter').value;

    try {
        let url = '/api/songs?';
        if (search) url += `search=${encodeURIComponent(search)}&`;
        if (language && language !== 'all') url += `language=${encodeURIComponent(language)}&`;
        const res = await fetch(url);
        const songs = await res.json();
        const plRes = await fetch(`/api/playlists/${DS.currentPlaylistId}`);
        const plData = await plRes.json();
        const existing = plData.songs_info ? plData.songs_info.map(s => s.filename) : [];
        const available = songs.filter(s => !existing.includes(s.filename));

        if (available.length === 0) { container.innerHTML = '<p class="text-muted">No more songs to add</p>'; return; }

        // Show language info badge
        let langCounts = {};
        available.forEach(s => {
            const lang = s.language || 'en';
            langCounts[lang] = (langCounts[lang] || 0) + 1;
        });
        let langBadge = '<div class="text-muted" style="font-size:11px;margin-bottom:6px;">';
        for (const [code, count] of Object.entries(langCounts)) {
            langBadge += `<span style="margin-right:8px;">${_getLangFlag(code)} ${code.toUpperCase()}: ${count}</span>`;
        }
        langBadge += ` | ${available.length} songs available</div>`;

        let html = langBadge;
        html += '<div class="song-grid scrollable-songs" id="playlistAddSongGrid">';
        available.forEach(s => {
            const thumb = s.has_thumbnail ? `/api/thumbnails/${s.id}.jpg` : null;
            const lang = s.language || 'en';
            const langEmoji = _getLangFlag(lang);
            const langName = _getLangName(lang);
            html += `<div class="song-card" data-action="addtoplaylist" data-song-id="${s.id}">
                <div class="song-thumb">${thumb ? `<img src="${thumb}" loading="lazy">` : '🎵'}</div>
                <div class="song-info">
                    <div class="title">${escHtml(s.title)}</div>
                    <div class="artist">${escHtml(s.artist)} <span class="lang-badge" data-action="editlanguage" data-song-id="${s.id}" data-lang-name="${escAttr(langName)}" title="Click to change language (current: ${langName})" style="font-size:10px;color:var(--text-muted);margin-left:4px;cursor:pointer;border-bottom:1px dashed var(--text-muted);">${langEmoji} ${lang.toUpperCase()}</span></div>
                </div>
                <span style="color:var(--success);font-size:18px;flex-shrink:0;">+</span>
            </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch(e) {}
}

// Language flag emoji mapper for common languages
function _getLangFlag(code) {
    const flags = {
        'en': '🇬🇧', 'af': '🇿🇦', 'ko': '🇰🇷', 'ja': '🇯🇵', 'zh': '🇨🇳',
        'es': '🇪🇸', 'fr': '🇫🇷', 'de': '🇩🇪', 'pt': '🇧🇷', 'ru': '🇷🇺',
        'it': '🇮🇹', 'nl': '🇳🇱', 'pl': '🇵🇱', 'ar': '🇸🇦', 'tr': '🇹🇷',
        'sv': '🇸🇪', 'da': '🇩🇰', 'no': '🇳🇴', 'fi': '🇫🇮', 'hi': '🇮🇳',
        'th': '🇹🇭', 'vi': '🇻🇳', 'id': '🇮🇩', 'ms': '🇲🇾', 'he': '🇮🇱',
        'el': '🇬🇷', 'hu': '🇭🇺', 'cs': '🇨🇿', 'sk': '🇸🇰', 'ro': '🇷🇴',
    };
    return flags[code] || '🌐';
}

function _getLangName(code) {
    const names = {
        'en': 'English', 'af': 'Afrikaans', 'ko': 'Korean', 'ja': 'Japanese', 'zh': 'Chinese',
        'es': 'Spanish', 'fr': 'French', 'de': 'German', 'pt': 'Portuguese', 'ru': 'Russian',
        'it': 'Italian', 'nl': 'Dutch', 'pl': 'Polish', 'ar': 'Arabic', 'tr': 'Turkish',
        'sv': 'Swedish', 'da': 'Danish', 'no': 'Norwegian', 'fi': 'Finnish', 'hi': 'Hindi',
        'th': 'Thai', 'vi': 'Vietnamese', 'id': 'Indonesian', 'ms': 'Malay', 'he': 'Hebrew',
        'el': 'Greek', 'hu': 'Hungarian', 'cs': 'Czech', 'sk': 'Slovak', 'ro': 'Romanian',
    };
    return names[code] || code.toUpperCase();
}

async function editSongLanguage(songId, event) {
    event.stopPropagation();
    const currentLang = prompt('Enter the 2-letter language code for this song (e.g.: en, af, ko, ja):', '');
    if (!currentLang) return;
    
    const lang = currentLang.trim().toLowerCase();
    if (lang.length !== 2) {
        alert('Please enter a valid 2-letter language code (e.g.: en, af, ko)');
        return;
    }
    
    if (!confirm(`Change language of this song to "${_getLangName(lang)}" (${lang})?`)) return;
    
    try {
        const res = await fetch(`/api/songs/${songId}/language`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: lang })
        });
        const data = await res.json();
        if (data.success) {
            // Refresh the song list
            showPlaylistAddSongs();
            // Also refresh the language filter options
            loadLanguageFilter();
        } else {
            alert('Error: ' + (data.error || 'Failed to set language'));
        }
    } catch(e) {
        alert('Error updating language');
    }
}

async function loadLanguageFilter() {
    const select = document.getElementById('playlistLanguageFilter');
    const detectBtn = document.querySelector('.btn-outline[onclick*="loadLanguageFilter"]');
    
    try {
        // First check if languages are already cached
        let res = await fetch('/api/languages');
        let languages = await res.json();
        
        if (!languages || languages.length === 0) {
            // No cache yet, trigger a scan
            if (detectBtn) detectBtn.textContent = '⏳ Scanning...';
            await fetch('/api/languages/scan', { method: 'POST' });
            res = await fetch('/api/languages');
            languages = await res.json();
        }
        
        let html = '<option value="all">🌐 All Languages</option>';
        languages.forEach(l => {
            const flag = _getLangFlag(l.code);
            html += `<option value="${l.code}">${flag} ${l.name}</option>`;
        });
        select.innerHTML = html;
        if (detectBtn) detectBtn.textContent = '✅ Languages Detected';
        
        // Refresh the song list with the new filter
        showPlaylistAddSongs();
    } catch(e) {
        if (detectBtn) detectBtn.textContent = '❌ Scan Failed';
        select.innerHTML = '<option value="all">🌐 All Languages</option>';
    }
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

async function renameCurrentPlaylist() {
    if (!DS.currentPlaylistId) return;
    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}`);
        const data = await res.json();
        if (!data || data.error) { alert('Could not load playlist'); return; }
        const newName = prompt('Enter a new name for this playlist:', data.name);
        if (!newName || newName.trim() === data.name) return;
        const renameRes = await fetch(`/api/playlists/${DS.currentPlaylistId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });
        const renameData = await renameRes.json();
        if (renameData.success) {
            viewPlaylist(DS.currentPlaylistId);
        } else {
            alert('Error: ' + (renameData.error || 'Failed to rename'));
        }
    } catch(e) { alert('Error renaming playlist'); }
}

// ── Batch Add by Artist ──────────────────────────────────────────────

async function loadArtistsForBatch() {
    const select = document.getElementById('batchArtistSelect');
    const container = document.getElementById('batchArtistCheckboxes');
    try {
        const res = await fetch('/api/artists');
        const artists = await res.json();
        
        // Populate single select
        let html = '<option value="">-- Select an artist --</option>';
        artists.forEach(a => {
            const safe = escHtml(a);
            html += `<option value="${safe}">${safe}</option>`;
        });
        select.innerHTML = html;

        // Populate multi-select checkboxes (show first 50, rest expandable)
        let checkboxHtml = '<div style="max-height:250px;overflow-y:auto;border:1px solid var(--surface2);border-radius:6px;padding:4px;">';
        artists.forEach((a, idx) => {
            const safe = escHtml(a);
            checkboxHtml += `<label class="checkbox-label" style="display:flex;align-items:center;gap:6px;padding:2px 6px;font-size:12px;cursor:pointer;">
                <input type="checkbox" class="artist-checkbox" value="${safe}">
                <span>${safe}</span>
            </label>`;
        });
        checkboxHtml += '</div>';
        checkboxHtml += `<div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
            <button class="btn btn-sm btn-outline" onclick="selectAllArtists(true)">Select All</button>
            <button class="btn btn-sm btn-outline" onclick="selectAllArtists(false)">Deselect All</button>
            <button class="btn btn-sm btn-accent" onclick="batchAddSelectedArtists()">+ Add Selected</button>
            <button class="btn btn-sm btn-primary" onclick="batchAddAllSongs()">+ Add All Songs</button>
            <span id="batchMultiStatus" style="font-size:11px;color:var(--text-muted);margin-left:4px;"></span>
        </div>`;
        container.innerHTML = checkboxHtml;
    } catch(e) {
        select.innerHTML = '<option value="">Error loading artists</option>';
        container.innerHTML = '<p class="text-muted">Error loading artists</p>';
    }
}

function selectAllArtists(select) {
    document.querySelectorAll('.artist-checkbox').forEach(cb => cb.checked = select);
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

async function batchAddSelectedArtists() {
    if (!DS.currentPlaylistId) return;
    const checked = document.querySelectorAll('.artist-checkbox:checked');
    const artists = Array.from(checked).map(cb => cb.value);
    if (artists.length === 0) { alert('Please select at least one artist'); return; }

    if (!confirm(`Add all songs by ${artists.length} selected artist(s) to this playlist?`)) return;

    const statusEl = document.getElementById('batchMultiStatus');
    statusEl.textContent = 'Adding songs...';

    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}/songs/batch-multi`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artists })
        });
        const data = await res.json();
        if (data.success) {
            let detail = '';
            if (data.per_artist) {
                detail = ' (';
                const parts = [];
                for (const [artist, count] of Object.entries(data.per_artist)) {
                    if (count > 0) parts.push(`${artist}: ${count}`);
                }
                detail += parts.join(', ') + ')';
            }
            statusEl.textContent = `✅ Added ${data.total_added} songs${detail}`;
            viewPlaylist(DS.currentPlaylistId);
        } else {
            statusEl.textContent = '❌ Error: ' + (data.error || 'Unknown');
        }
    } catch(e) {
        statusEl.textContent = '❌ Error adding songs';
    }
}

async function batchAddAllSongs() {
    if (!DS.currentPlaylistId) return;
    if (!confirm('Add ALL songs from the library to this playlist?')) return;

    const statusEl = document.getElementById('batchMultiStatus');
    statusEl.textContent = 'Adding all songs...';

    try {
        const res = await fetch(`/api/playlists/${DS.currentPlaylistId}/songs/batch-all`, {
            method: 'POST'
        });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = `✅ Added ${data.added} songs to playlist`;
            viewPlaylist(DS.currentPlaylistId);
        } else {
            statusEl.textContent = '❌ Error: ' + (data.error || 'Unknown');
        }
    } catch(e) {
        statusEl.textContent = '❌ Error adding songs';
    }
}

// ===== Event delegation for playlist interactions =====

// Playlist card clicks
document.addEventListener('click', function(e) {
    const grid = document.querySelector('.playlist-grid');
    if (grid && grid.contains(e.target)) {
        const card = e.target.closest('.playlist-card');
        if (card && card.dataset.playlistId) {
            viewPlaylist(card.dataset.playlistId);
            return;
        }
    }
});

// Playlist detail song grid: play songs & remove songs
document.addEventListener('click', function(e) {
    const grid = document.getElementById('playlistSongGrid');
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

    // Remove from playlist button
    const rmBtn = e.target.closest('[data-action="removefromplaylist"]');
    if (rmBtn) {
        e.stopPropagation();
        const filename = rmBtn.dataset.filename;
        if (filename) removeFromPlaylist(filename);
        return;
    }
});

// Playlist add-song grid: add songs & edit language
document.addEventListener('click', function(e) {
    const grid = document.getElementById('playlistAddSongGrid');
    if (!grid || !grid.contains(e.target)) return;

    // Add to playlist card click
    const card = e.target.closest('[data-action="addtoplaylist"]');
    if (card) {
        e.stopPropagation();
        const id = card.dataset.songId;
        if (id) addToCurrentPlaylist(id);
        return;
    }

    // Edit language badge click
    const langBadge = e.target.closest('[data-action="editlanguage"]');
    if (langBadge) {
        e.stopPropagation();
        const id = langBadge.dataset.songId;
        if (id) editSongLanguage(id, e);
        return;
    }
});