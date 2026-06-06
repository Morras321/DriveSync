// ===== DriveSync – Utility Functions =====

/** HTML-escape a string */
function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}

/** Escape a string for use in an HTML attribute (inside double quotes) */
function escAttr(str) {
    return (str || '').replace(/&/g, '\x26amp;').replace(/"/g, '\x26quot;').replace(/'/g, '\x26#39;').replace(/</g, '\x26lt;').replace(/>/g, '\x26gt;');
}

/** Show a status message in an element */
function showStatus(el, msg, type) {
    el.textContent = msg;
    el.className = 'status show status-' + type;
}

/** Clear a status element */
function clearStatus(el) {
    el.className = 'status';
}

/** Switch between tabs */
function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.querySelector(`.tab-btn[onclick*="'${name}'"]`).classList.add('active');

    if (name === 'library') loadLibrary();
    if (name === 'playlists') loadPlaylists();
    if (name === 'export') loadExportData();
}

/** Format seconds to mm:ss */
function formatDuration(sec) {
    if (!sec) return '--:--';
    const m = Math.floor(sec / 60);
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

/** Format bytes to human-readable */
function formatSize(bytes) {
    if (!bytes) return '';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function switchStyles() {
	document.getElementById('style').href = 'css/drivesync_glass2.css';
}