// ===== DriveSync – Drive/Disk Export Module =====

// ── Storage info for library ──────────────────────────────────────────

async function loadStorageInfo() {
    const container = document.getElementById('storageInfo');
    try {
        const res = await fetch('/api/storage');
        const dirs = await res.json();
        if (dirs.length === 0) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'flex';
        container.innerHTML = dirs.map(d => {
            const freeGb = (d.free / 1024 / 1024 / 1024).toFixed(1);
            const totalGb = (d.total / 1024 / 1024 / 1024).toFixed(1);
            const usedGb = (d.used / 1024 / 1024 / 1024).toFixed(1);
            const pct = d.total > 0 ? Math.round((d.used / d.total) * 100) : 0;
            const label = d.path.split(/[/\\]/).pop() || d.path;
            return `<div class="storage-item" title="${escHtml(d.path)}">
                <span class="storage-label">💾 ${escHtml(label)}</span>
                <span class="storage-bar"><span class="storage-fill" style="width:${pct}%"></span></span>
                <span class="storage-text">${freeGb}GB free / ${totalGb}GB</span>
                <span class="storage-songs">${d.song_count} songs</span>
            </div>`;
        }).join('');
    } catch(e) {
        container.style.display = 'none';
    }
}

// ── Drive scanning ────────────────────────────────────────────────────

async function checkSdCards() {
    const statusEl = document.getElementById('sdStatus');
    statusEl.innerHTML = '<span class="spinner"></span>';
    try {
        const res = await fetch('/api/sdcard');
        DS.sdCards = await res.json();
        const select = document.getElementById('sdDriveSelect');
        select.innerHTML = '';

        if (DS.sdCards.length === 0) {
            select.innerHTML = '<option value="">-- No drives detected --</option>';
            statusEl.textContent = '❌ No drives';
        } else {
            DS.sdCards.forEach(c => {
                const freeGb = (c.free / 1024 / 1024 / 1024).toFixed(1);
                const totalGb = (c.total / 1024 / 1024 / 1024).toFixed(1);
                select.innerHTML += `<option value="${c.drive}">${c.drive} (${freeGb}GB free / ${totalGb}GB)</option>`;
            });
            statusEl.textContent = `✅ ${DS.sdCards.length} drive(s)`;
        }

        updateDriveInfoDisplay();
        loadExportPlaylists();
        refreshDriveFolders();
    } catch(e) {
        statusEl.textContent = '❌ Error';
        const container = document.getElementById('sdCardInfo');
        container.innerHTML = '<div class="empty-state"><p>⚠️ Could not scan drives. On Linux make sure your user has permission to access <code>/media</code> and <code>/mnt</code>.<br><br>Try: <code>sudo usermod -aG plugdev $USER</code> then reboot.</p></div>';
    }
}

function updateDriveInfoDisplay() {
    const container = document.getElementById('sdCardInfo');
    if (DS.sdCards.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No drives detected. Insert a drive and tap "Scan".</p></div>';
        return;
    }
    let html = '<div class="sd-card-info">';
    DS.sdCards.forEach(c => {
        const freeGb = (c.free / 1024 / 1024 / 1024).toFixed(1);
        const totalGb = (c.total / 1024 / 1024 / 1024).toFixed(1);
        const pct = c.total > 0 ? Math.round((c.free / c.total) * 100) : 0;
        html += `<div class="sd-stat">
            <div style="font-size:11px;color:var(--text-muted);">${c.drive}</div>
            <div class="value">${freeGb} GB</div>
            <div class="label">Free of ${totalGb} GB (${pct}%)</div>
        </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

// ── Drive path management (subfolder outside export) ──────────────────

let _selectedDrive = '';
let _selectedSubfolder = '';

function drivePathChanged() {
    _selectedDrive = document.getElementById('sdDriveSelect').value;
    _selectedSubfolder = document.getElementById('sdSubfolderInput').value.trim();
    document.getElementById('sdPathDisplay').textContent = _selectedDrive
        ? (_selectedDrive + (_selectedSubfolder ? _selectedSubfolder + '/' : ''))
        : '(select a drive)';
    refreshDriveFolders();
    closeFolderDetail();
}

function updateSubfolderHint() {
    drivePathChanged();
}

// ── Folder listing ────────────────────────────────────────────────────

async function refreshDriveFolders() {
    const drivePath = _selectedDrive;
    const subfolder = _selectedSubfolder;
    const container = document.getElementById('driveFoldersList');

    if (!drivePath) {
        container.innerHTML = '<p class="text-muted">Select a drive above to see existing playlist folders.</p>';
        return;
    }

    try {
        const res = await fetch('/api/sdcard/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ drive_path: drivePath, subfolder: subfolder })
        });
        const folders = await res.json();

        if (folders.length === 0) {
            container.innerHTML = '<p class="text-muted">No playlist folders found here yet.</p>';
            return;
        }

        container.innerHTML = '<div class="drive-folder-grid">' +
            folders.map(f => {
                const sizeMb = (f.size / 1024 / 1024).toFixed(1);
                const safePath = escHtml(f.path);
                return `<div class="drive-folder-card">
                    <div class="folder-info" data-path="${safePath}" onclick="viewFolderSongs(this)">
                        <span class="folder-icon">📁</span>
                        <div>
                            <div class="folder-name">${escHtml(f.name)}</div>
                            <div class="folder-meta">${f.song_count} songs · ${sizeMb} MB</div>
                        </div>
                    </div>
                    <button class="btn btn-danger btn-sm" data-path="${safePath}" onclick="event.stopPropagation();deleteDriveFolder(this)">🗑️</button>
                </div>`;
            }).join('') +
        '</div>';
    } catch(e) {
        container.innerHTML = '<p class="text-muted">Error loading folders.</p>';
    }
}

// ── View songs inside a folder ────────────────────────────────────────

let _currentFolderPath = null;

async function viewFolderSongs(buttonElement) {
	const folderPath = buttonElement.getAttribute('data-path');
    _currentFolderPath = folderPath;
    const container = document.getElementById('folderSongsContainer');
    const detail = document.getElementById('folderDetail');
    detail.style.display = 'block';
    document.getElementById('folderDetailName').textContent = '📂 ' + folderPath.split(/[/\\]/).pop();
    document.getElementById('folderDetailPath').textContent = folderPath;
    container.innerHTML = '<p class="text-muted">Loading songs...</p>';
    document.getElementById('folderSongsStatus').className = 'status';

    try {
        const res = await fetch('/api/sdcard/folders/songs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath })
        });
        const songs = await res.json();

        if (songs.length === 0) {
            container.innerHTML = '<p class="text-muted">No songs in this folder.</p>';
            return;
        }

        container.innerHTML = '<div class="song-grid">' +
            songs.map(s => {
                const sizeMb = (s.size / 1024 / 1024).toFixed(1);
                return `<div class="song-card">
                    <div class="song-thumb">🎵</div>
                    <div class="song-info">
                        <div class="title">${escHtml(s.title)}</div>
                        <div class="artist">${escHtml(s.artist)}</div>
                        <div class="meta">${escHtml(s.filename)} · ${sizeMb} MB</div>
                    </div>
                </div>`;
            }).join('') +
        '</div>';
    } catch(e) {
        container.innerHTML = '<p class="text-muted">Error loading songs.</p>';
    }
}

function closeFolderDetail() {
    document.getElementById('folderDetail').style.display = 'none';
    _currentFolderPath = null;
}

async function addSongToCurrentFolder() {
    if (!_currentFolderPath) { alert('No folder selected'); return; }

    const statusEl = document.getElementById('folderSongsStatus');
    clearStatus(statusEl);
    showStatus(statusEl, 'Select a song from library to add...', 'info');

    // Use the playlist picker approach: show library songs to pick from
    try {
        const res = await fetch('/api/songs');
        const songs = await res.json();
        if (songs.length === 0) {
            showStatus(statusEl, 'No songs in library to add.', 'error');
            return;
        }

        const names = songs.map(s => `${s.title} - ${s.artist}`);
        // Simple prompt for now (we can make a full modal later)
        const choice = prompt(
            `Add a song to ${_currentFolderPath.split(/[/\\]/).pop()}\n\n` +
            names.map((n, i) => `${i+1}. ${n}`).join('\n') +
            '\n\nEnter number or song name:'
        );
        if (!choice) { clearStatus(statusEl); return; }

        let songId = null;
        const idx = parseInt(choice) - 1;
        if (idx >= 0 && idx < songs.length) {
            songId = songs[idx].id;
        } else {
            const match = songs.find(s =>
                s.title.toLowerCase().includes(choice.toLowerCase()) ||
                s.artist.toLowerCase().includes(choice.toLowerCase())
            );
            if (match) songId = match.id;
        }

        if (!songId) { showStatus(statusEl, 'Song not found.', 'error'); return; }

        const addRes = await fetch('/api/sdcard/folders/add-song', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: _currentFolderPath, song_source: songId })
        });
        const data = await addRes.json();
        if (data.success) {
            showStatus(statusEl, `✅ Added "${data.filename}"`, 'success');
            viewFolderSongs(_currentFolderPath);
            refreshDriveFolders();
        } else {
            showStatus(statusEl, 'Error: ' + (data.error || 'Unknown'), 'error');
        }
    } catch(e) {
        showStatus(statusEl, 'Error: ' + e.message, 'error');
    }
}

async function deleteDriveFolder(buttonElement) {
	const folderPath = buttonElement.getAttribute('data-path');
    if (!confirm('Delete this playlist folder from the drive?\n\n' + folderPath)) return;
    try {
        const res = await fetch('/api/sdcard/folders/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath })
        });
        const data = await res.json();
        if (data.success) {
            if (_currentFolderPath === folderPath) closeFolderDetail();
            refreshDriveFolders();
        } else {
            alert('Failed to delete folder.');
        }
    } catch(e) {
        alert('Error deleting folder');
    }
}

// ── Export ────────────────────────────────────────────────────────────

async function loadExportPlaylists() {
    try {
        const res = await fetch('/api/playlists');
        const playlists = await res.json();
        const select = document.getElementById('exportPlaylistSelect');
        select.innerHTML = '<option value="">-- Select a playlist --</option>';
        playlists.forEach(p => {
            select.innerHTML += `<option value="${p.id}">${escHtml(p.name)} (${p.song_count})</option>`;
        });
    } catch(e) {}
}

async function loadExportData() {
    await checkSdCards();
    await loadExportPlaylists();
}

async function exportToSd() {
    const playlistId = document.getElementById('exportPlaylistSelect').value;
    const shufflePrefix = document.getElementById('shufflePrefix').checked;

    if (!playlistId) { alert('Please select a playlist'); return; }
    if (!_selectedDrive) { alert('Please select a drive'); return; }

    const statusEl = document.getElementById('exportStatus');
    clearStatus(statusEl);
    showStatus(statusEl, 'Exporting...', 'info');

    try {
        const res = await fetch('/api/sdcard/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_id: playlistId,
                sd_drive: _selectedDrive,
                subfolder: _selectedSubfolder,
                shuffle_prefix: shufflePrefix
            })
        });
        const data = await res.json();

        if (data.error) {
            showStatus(statusEl, 'Error: ' + data.error, 'error');
        } else if (data.success) {
            const shuffleMsg = shufflePrefix ? ' (with prefixes)' : '';
            const subMsg = _selectedSubfolder ? ` in "${_selectedSubfolder}"` : '';
            let msg = `✅ Exported "${data.playlist}" to ${data.sd_path}${subMsg}${shuffleMsg}. ${data.copied}/${data.total} songs.`;
            if (data.errors && data.errors.length) msg += ` Errors: ${data.errors.join(', ')}`;
            showStatus(statusEl, msg, 'success');
            checkSdCards();
            refreshDriveFolders();
        }
    } catch (e) {
        showStatus(statusEl, 'Error: ' + e.message, 'error');
    }
}