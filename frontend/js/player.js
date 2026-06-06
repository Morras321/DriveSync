// ===== DriveSync – Audio Preview Player =====

/** Toggle play/pause for a song */
function togglePlay(id, title) {
    if (DS.currentAudio && DS.currentPlayingId === id) {
        if (DS.currentAudio.paused) {
            document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
                el.textContent = '⏸';
            });
            DS.currentAudio.play();
        } else {
            document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
                el.textContent = '▶';
            });
            DS.currentAudio.pause();
        }
        return;
    }
    stopAudio();
    DS.currentPlayingId = id;

    const url = `/api/songs/${encodeURIComponent(id)}/stream`;
    const audioEl = document.getElementById('audioPlayer');
    document.getElementById('nowPlayingText').textContent = `🎵 ${title}`;
    document.getElementById('miniPlayer').classList.add('show');

    audioEl.src = url;
    audioEl.play().catch(() => {});
    audioEl.onended = () => stopAudio();
    DS.currentAudio = audioEl;

    // Highlight the playing card
    document.querySelectorAll('.song-card.playing, .play-overlay.playing').forEach(el => el.classList.remove('playing'));
    document.querySelectorAll(`[data-song-id="${id}"] .play-overlay`).forEach(el => {
        el.classList.add('playing');
        el.textContent = '⏸';
    });
    document.querySelectorAll(`[data-song-id="${id}"]`).forEach(el => el.classList.add('playing'));
}

/** Stop playback and hide the mini-player */
function stopAudio() {
    if (DS.currentAudio) { DS.currentAudio.pause(); DS.currentAudio = null; }
    const audioEl = document.getElementById('audioPlayer');
    audioEl.pause();
    audioEl.src = '';
    DS.currentPlayingId = null;
    document.getElementById('miniPlayer').classList.remove('show');

    document.querySelectorAll('.song-card.playing, .play-overlay.playing').forEach(el => {
        el.classList.remove('playing');
        if (el.classList.contains('play-overlay')) el.textContent = '▶️';
    });
}