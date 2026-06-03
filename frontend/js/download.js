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