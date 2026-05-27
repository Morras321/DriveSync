// ===== DriveSync – Drive/Disk Export Module =====

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

function updateSubfolderHint() {
    const drive = document.getElementById('sdDriveSelect').value;
    const folderCheck = document.getElementById('driveFolderCheck');
    const hint = document.getElementById('subfolderHint');
    if (drive) {
        folderCheck.innerHTML = `Checking Folder: ${drive}${document.getElementById('subfolderInput').value ? document.getElementById('subfolderInput').value + '\\' : ''}`;
        hint.textContent = `Playlists will be saved to: ${drive}${document.getElementById('subfolderInput').value ? document.getElementById('subfolderInput').value + '\\' : ''}[Playlist Name]`;
    } else {
        folderCheck.innerHTML = "Checking Root Folder";
        hint.textContent = 'Select a drive above';
    }
	refreshDriveFolders();
}

async function refreshDriveFolders() {
    const drivePath = document.getElementById('sdDriveSelect').value;
    const subfolder = document.getElementById('subfolderInput').value.trim();
    const container = document.getElementById('driveFoldersList');

    if (!drivePath) {
        container.innerHTML = '<p class="text-muted">Select a drive to see existing playlists.</p>';
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
            container.innerHTML = '<p class="text-muted">No playlist folders found on this drive yet.</p>';
            return;
        }

        container.innerHTML = '<div class="drive-folder-grid">' +
            folders.map(f => {
                const sizeMb = (f.size / 1024 / 1024).toFixed(1);
                return `<div class="drive-folder-card">
                    <div class="folder-info">
                        <span class="folder-icon">📁</span>
                        <div>
                            <div class="folder-name">${escHtml(f.name)}</div>
                            <div class="folder-meta">${f.song_count} songs · ${sizeMb} MB</div>
                        </div>
                    </div>
                    <button class="btn btn-danger btn-sm" data-path="${escHtml(f.path)}" onclick="handleDeleteClick(this)">🗑️</button>
                </div>`;
            }).join('') +
        '</div>';
    } catch(e) {
        container.innerHTML = '<p class="text-muted">Error loading folders.</p>';
    }
}

async function handleDeleteClick(buttonElement) {
    const folderPath = buttonElement.getAttribute('data-path');
    await deleteDriveFolder(folderPath);
}

async function deleteDriveFolder(folderPath) {
    if (!confirm('Delete this playlist folder from the drive?')) return;
    try {
        const res = await fetch('/api/sdcard/folders/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath })
        });
        const data = await res.json();
        if (data.success) {
            refreshDriveFolders();
        } else {
            alert('Backend failed to delete the folder. Check path permissions.');
        }
    } catch(e) {
        alert('Error deleting folder');
    }
}

async function exportToSd() {
    const playlistId = document.getElementById('exportPlaylistSelect').value;
    const sdDrive = document.getElementById('sdDriveSelect').value;
    const subfolder = document.getElementById('subfolderInput').value.trim();
    const shufflePrefix = document.getElementById('shufflePrefix').checked;

    if (!playlistId) { alert('Please select a playlist'); return; }
    if (!sdDrive) { alert('Please select a drive'); return; }

    const statusEl = document.getElementById('exportStatus');
    clearStatus(statusEl);
    showStatus(statusEl, 'Exporting...', 'info');

    try {
        const res = await fetch('/api/sdcard/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_id: playlistId,
                sd_drive: sdDrive,
                subfolder: subfolder,
                shuffle_prefix: shufflePrefix
            })
        });
        const data = await res.json();

        if (data.error) {
            showStatus(statusEl, 'Error: ' + data.error, 'error');
        } else if (data.success) {
            const shuffleMsg = shufflePrefix ? ' (with prefixes)' : '';
            const subMsg = subfolder ? ` in "${subfolder}"` : '';
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