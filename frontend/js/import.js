// ===== DriveSync – Import Module =====

async function startImport() {
    const files = document.getElementById('importFiles').files;
    if (files.length === 0) { alert('Select files to import'); return; }

    const statusEl = document.getElementById('importStatus');
    clearStatus(statusEl);

    const customTitle = document.getElementById('importTitle').value.trim();
    const customArtist = document.getElementById('importArtist').value.trim();
    const thumbInput = document.getElementById('importThumbnail');

    let imported = 0;
    let errors = [];

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        showStatus(statusEl, `Importing ${i+1}/${files.length}: ${file.name}...`, 'info');

        const formData = new FormData();
        formData.append('file', file);

        // Send custom artist (same for all files)
        if (customArtist) {
            formData.append('artist', customArtist);
        }

        // Send custom title (with counter suffix for multiple files)
        if (customTitle) {
            const titleToUse = files.length > 1
                ? `${customTitle} (${i + 1})`
                : customTitle;
            formData.append('title', titleToUse);
        }
        if (thumbInput.files.length > 0) {
            formData.append('thumbnail', thumbInput.files[0]);
        }

        try {
            const res = await fetch('/api/import', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) imported++;
            else errors.push(`${file.name}: ${data.error}`);
        } catch (e) {
            errors.push(`${file.name}: Upload error`);
        }
    }

    let msg = `✅ Imported ${imported} of ${files.length}`;
    if (errors.length) msg += ` Errors: ${errors.join(', ')}`;
    showStatus(statusEl, msg, errors.length === 0 ? 'success' : 'error');
    loadLibrary();
}
