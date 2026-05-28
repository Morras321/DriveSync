// ===== DriveSync – Application State =====
const DS = {
    currentPlaylistId: null,
    sdCards: [],
    allSongs: [],
    currentAudio: null,
    currentPlayingId: null,
    downloadPollInterval: null,
};

// ===== Initialisation – ensure library loads on first visit =====
document.addEventListener('DOMContentLoaded', () => {
    loadLibrary();
    checkSdCards();
    loadStorageInfo();
});
