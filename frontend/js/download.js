// ===== DriveSync – Download Module =====

async function startDownload() {
    const url = document.getElementById('downloadUrl').value.trim();
    if (!url) { alert('Please enter a YouTube URL'); return; }

    const statusEl = document.getElementById('downloadStatus');
    const progressContainer = document.getElementById('progressContainer');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const cancelBtn = document.getElementById('cancelDownloadBtn');

    clearStatus(statusEl);
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = 'Starting download...';
    cancelBtn.style.display = 'inline-flex';

    try {
        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.error) {
            showStatus(statusEl, 'Error: ' + data.error, 'error');
            progressContainer.style.display = 'none';
            cancelBtn.style.display = 'none';
            return;
        }

        if (DS.downloadPollInterval) clearInterval(DS.downloadPollInterval);

        DS.downloadPollInterval = setInterval(async () => {
            try {
                const pRes = await fetch('/api/download/progress');
                const pData = await pRes.json();

                if (pData.status === 'downloading' || pData.status === 'processing' || pData.status === 'starting') {
                    progressFill.style.width = pData.percent + '%';
                    progressText.textContent = `${pData.status}... ${Math.round(pData.percent)}%`;
                    cancelBtn.style.display = 'inline-flex';
                } else if (pData.status === 'completed') {
                    clearInterval(DS.downloadPollInterval);
                    DS.downloadPollInterval = null;
                    progressFill.style.width = '100%';
                    progressText.textContent = '✅ Complete!';
                    showStatus(statusEl, `Downloaded: ${pData.current}`, 'success');
                    cancelBtn.style.display = 'none';
                    setTimeout(() => { progressContainer.style.display = 'none'; }, 3000);
                    loadLibrary();
                } else if (pData.status === 'cancelled') {
                    clearInterval(DS.downloadPollInterval);
                    DS.downloadPollInterval = null;
                    cancelBtn.style.display = 'none';
                    progressContainer.style.display = 'none';
                    showStatus(statusEl, '⛔ Download cancelled', 'info');
                } else if (pData.status === 'error') {
                    clearInterval(DS.downloadPollInterval);
                    DS.downloadPollInterval = null;
                    cancelBtn.style.display = 'none';
                    showStatus(statusEl, 'Error: ' + pData.current, 'error');
                    progressContainer.style.display = 'none';
                }
            } catch(e) {}
        }, 1000);
    } catch (e) {
        showStatus(statusEl, 'Error: ' + e.message, 'error');
        progressContainer.style.display = 'none';
        cancelBtn.style.display = 'none';
    }
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
                    if (pData.status === 'completed' || pData.status === 'error' || pData.status === 'idle' || pData.status === 'cancelled') {
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