// ===== DriveSync – Download Module =====
// Shared download state is polled from the server so all users see the same info.

let downloadPollInterval = null;

function showDownloadStatus(data) {
    const statusEl = document.getElementById('downloadStatus');
    const progressContainer = document.getElementById('progressContainer');
    const progressText = document.getElementById('progressText');
    const cancelBtn = document.getElementById('cancelDownloadBtn');

    const playlistSection = document.getElementById('playlistProgressSection');
    const songSection = document.getElementById('songProgressSection');
    const playlistFill = document.getElementById('playlistProgressFill');
    const songFill = document.getElementById('songProgressFill');
    const playlistCount = document.getElementById('playlistProgressCount');
    const songName = document.getElementById('songProgressName');

    const isActive = ['starting', 'downloading', 'processing', 'cancelling'].includes(data.status);

    if (isActive) {
        progressContainer.style.display = 'block';
        cancelBtn.style.display = 'inline-flex';

        // Show/hide playlist vs song sections
        if (data.is_playlist) {
            playlistSection.style.display = 'block';
            songSection.style.display = 'block';

            // Playlist progress
            const playlistPct = data.total_songs > 0
                ? Math.round(((data.downloaded_count + data.error_count) / data.total_songs) * 100)
                : 0;
            playlistFill.style.width = Math.min(playlistPct, 100) + '%';
            playlistCount.textContent = `${data.downloaded_count + data.error_count} / ${data.total_songs} songs`;

            // Current song progress
            songFill.style.width = Math.min(data.song_percent || 0, 100) + '%';
            songName.textContent = data.current_song_name
                ? `#${data.current_song_index}: ${data.current_song_name}`
                : '';
        } else {
            // Single song — hide playlist section, show song as main bar
            playlistSection.style.display = 'none';
            songSection.style.display = 'block';
            songFill.style.width = Math.min(data.percent || 0, 100) + '%';
            songName.textContent = data.current || '';
        }

        // Status text
        if (data.status === 'starting') {
            progressText.textContent = 'Starting download...';
        } else if (data.status === 'downloading') {
            let text = `Downloading... ${Math.round(data.percent)}%`;
            if (data.is_playlist && data.total_songs > 0) {
                text = `Song ${data.current_song_index}/${data.total_songs} — ${Math.round(data.percent)}%`;
            }
            progressText.textContent = text;
        } else if (data.status === 'processing') {
            progressText.textContent = 'Processing audio...';
        } else if (data.status === 'cancelling') {
            progressText.textContent = 'Cancelling...';
        }

        // Clear any status message
        clearStatus(statusEl);
    } else {
        progressContainer.style.display = 'none';
        cancelBtn.style.display = 'none';

        if (data.status === 'completed') {
            showStatus(statusEl, `✅ ${data.current || 'Download complete!'}`, 'success');
            loadLibrary();
        } else if (data.status === 'error') {
            showStatus(statusEl, `❌ Error: ${data.current || 'Download failed'}`, 'error');
        } else if (data.status === 'cancelled') {
            showStatus(statusEl, '⛔ Download cancelled', 'info');
        } else if (data.status === 'idle') {
            // Show nothing when idle
        }
    }
}


async function startDownload() {
    const url = document.getElementById('downloadUrl').value.trim();
    if (!url) { alert('Please enter a YouTube URL'); return; }

    const statusEl = document.getElementById('downloadStatus');
    clearStatus(statusEl);

    // Show immediate starting state
    showDownloadStatus({
        status: 'starting',
        percent: 0,
        is_playlist: false,
        current: url,
    });

    try {
        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.error) {
            showStatus(statusEl, 'Error: ' + data.error, 'error');
            document.getElementById('progressContainer').style.display = 'none';
            document.getElementById('cancelDownloadBtn').style.display = 'none';
            return;
        }

        // Start polling
        startProgressPolling();
    } catch (e) {
        showStatus(statusEl, 'Error: ' + e.message, 'error');
        document.getElementById('progressContainer').style.display = 'none';
        document.getElementById('cancelDownloadBtn').style.display = 'none';
    }
}


function startProgressPolling() {
    if (downloadPollInterval) clearInterval(downloadPollInterval);

    downloadPollInterval = setInterval(async () => {
        try {
            const pRes = await fetch('/api/download/progress');
            const pData = await pRes.json();
            showDownloadStatus(pData);

            // Stop polling on terminal states
            if (['completed', 'error', 'cancelled', 'idle'].includes(pData.status)) {
                clearInterval(downloadPollInterval);
                downloadPollInterval = null;
            }
        } catch(e) {}
    }, 1000);
}


async function cancelDownload() {
    try {
        await fetch('/api/download/cancel', { method: 'POST' });
        document.getElementById('cancelDownloadBtn').style.display = 'none';
        document.getElementById('progressText').textContent = 'Cancelling...';
    } catch(e) {}
}


async function startBatchDownload() {
    const urls = document.getElementById('batchUrls').value.trim().split('\n').filter(u => u.trim());
    if (urls.length === 0) { alert('Please enter at least one URL'); return; }
    const statusEl = document.getElementById('downloadStatus');
    showStatus(statusEl, `Starting batch: ${urls.length} songs...`, 'info');
    for (let i = 0; i < urls.length; i++) {
        document.getElementById('downloadUrl').value = urls[i].trim();
        showStatus(statusEl, `Downloading ${i+1}/${urls.length}...`, 'info');
        await startDownload();
        await new Promise(resolve => {
            const check = setInterval(async () => {
                try {
                    const pRes = await fetch('/api/download/progress');
                    const pData = await pRes.json();
                    if (['completed', 'error', 'idle', 'cancelled'].includes(pData.status)) {
                        clearInterval(check);
                        resolve();
                    }
                } catch(e) { clearInterval(check); resolve(); }
            }, 500);
        });
    }
    showStatus(statusEl, `✅ Batch complete! ${urls.length} songs.`, 'success');
    document.getElementById('batchUrls').value = '';
    loadLibrary();
}


async function checkMissingSongs() {
    const url = document.getElementById('downloadUrl').value.trim();
    if (!url) { alert('Please enter a YouTube URL'); return; }

    const resultsEl = document.getElementById('checkMissingResults');
    const statusEl = document.getElementById('downloadStatus');
    clearStatus(statusEl);
    resultsEl.style.display = 'block';
    resultsEl.innerHTML = '<p class="text-muted">Checking which songs are missing from your library...</p>';

    try {
        const res = await fetch('/api/download/check-missing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();

        if (data.error) {
            resultsEl.innerHTML = `<div class="status error">❌ Error: ${escHtml(data.error)}</div>`;
            return;
        }

        let html = '<div class="card" style="padding:12px;margin-top:8px;background:var(--bg);">';
        if (data.is_playlist) {
            html += `<h4>📋 Playlist Analysis</h4>`;
            html += `<p>Total songs in playlist: <strong>${data.total}</strong></p>`;
            html += `<p>✅ Already in library: <strong>${data.existing_count}</strong></p>`;
            html += `<p>⬇️ Need to download: <strong>${data.missing.length}</strong></p>`;
            
            if (data.existing_titles && data.existing_titles.length > 0) {
                html += '<details style="margin-top:8px;">';
                html += `<summary>Already downloaded (${data.existing_titles.length} songs)</summary>`;
                html += '<ul style="font-size:12px;max-height:200px;overflow-y:auto;">';
                data.existing_titles.forEach(t => {
                    html += `<li>✅ ${escHtml(t)}</li>`;
                });
                html += '</ul></details>';
            }
            
            if (data.missing.length > 0) {
                html += '<details style="margin-top:8px;">';
                html += `<summary>Songs to download (${data.missing.length} songs)</summary>`;
                html += '<ul style="font-size:12px;max-height:300px;overflow-y:auto;">';
                data.missing.forEach(s => {
                    html += `<li>⬇️ ${escHtml(s.title)}</li>`;
                });
                html += '</ul></details>';
                html += `<p style="margin-top:8px;"><button class="btn btn-primary btn-sm" onclick="downloadOnlyMissing()">⬇️ Download These ${data.missing.length} Songs</button></p>`;
                // Store missing entries for download
                window._missingPlaylistEntries = data.missing;
                window._missingPlaylistUrl = url;
            }
        } else {
            html += `<h4>🎵 Single Song Check</h4>`;
            if (data.missing.length > 0) {
                html += `<p>✅ This song is <strong>not</strong> in your library yet.</p>`;
                html += `<p><button class="btn btn-primary btn-sm" onclick="startDownload()">⬇️ Download It</button></p>`;
            } else {
                html += `<p>✅ This song is <strong>already</strong> in your library!</p>`;
            }
        }
        html += '</div>';
        resultsEl.innerHTML = html;
    } catch (e) {
        resultsEl.innerHTML = `<div class="status error">❌ Error: ${escHtml(e.message)}</div>`;
    }
}


async function downloadOnlyMissing() {
    if (!window._missingPlaylistEntries || window._missingPlaylistEntries.length === 0) {
        alert('No missing songs to download. Run "Check Missing" first.');
        return;
    }
    
    const url = window._missingPlaylistUrl || document.getElementById('downloadUrl').value.trim();
    if (!url) { alert('No URL'); return; }
    
    // Use the standard download but pass the pre-filtered flag
    // The server-side now filters automatically, but this gives visual feedback
    document.getElementById('downloadUrl').value = url;
    showStatus(document.getElementById('downloadStatus'), 
        `Starting download of ${window._missingPlaylistEntries.length} missing songs...`, 'info');
    await startDownload();
}


// ── Auto-poll when page loads (so all users see active downloads) ───
// Also listen for tab visibility to start/stop polling
document.addEventListener('DOMContentLoaded', () => {
    // Check initial state
    fetch('/api/download/progress')
        .then(r => r.json())
        .then(data => {
            if (['starting', 'downloading', 'processing', 'cancelling'].includes(data.status)) {
                showDownloadStatus(data);
                startProgressPolling();
            }
        })
        .catch(() => {});
});