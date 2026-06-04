"""
DriveSync - Language Detection Module
Detects the language of song titles using langid and stores results
in MP3 ID3 tags (TLAN frame) for persistence.
Falls back to a JSON cache file if TLAN is not set.
"""

import json
from pathlib import Path

from config import MUSIC_DIR
from mutagen.mp3 import MP3
from mutagen.id3 import TLAN, TIT2, TPE1

# Cache file path (stored in music dir alongside thumbnails) - fallback when TLAN not set
LANGUAGE_CACHE_FILE = MUSIC_DIR / ".language_cache.json"
# langid is loaded lazily to avoid import overhead when not needed
_langid_available = False


def _ensure_langid():
    """Lazy-import langid (first call loads the model)."""
    global _langid_available
    if not _langid_available:
        try:
            import langid
            langid.set_languages([
                'en', 'af', 'sq', 'ar', 'hy', 'az', 'eu', 'be', 'bn', 'bg',
                'ca', 'zh', 'hr', 'cs', 'da', 'nl', 'eo', 'et', 'fi', 'fr',
                'gl', 'ka', 'de', 'el', 'gu', 'ht', 'ha', 'iw', 'hi', 'hu',
                'is', 'id', 'ga', 'it', 'ja', 'kn', 'kk', 'rw', 'ky', 'ko',
                'lo', 'la', 'lv', 'lt', 'lb', 'mk', 'mg', 'ms', 'ml', 'mt',
                'mi', 'mr', 'mn', 'ne', 'no', 'oc', 'or', 'ps', 'fa', 'pl',
                'pt', 'pa', 'ro', 'ru', 'sm', 'gd', 'sr', 'st', 'sn', 'sk',
                'sl', 'so', 'es', 'sw', 'sv', 'tl', 'tg', 'ta', 'tt', 'te',
                'th', 'bo', 'tr', 'tk', 'uk', 'ur', 'uz', 'vi', 'cy', 'xh',
                'yi', 'yo', 'zu',
            ])
            _langid_available = True
        except Exception:
            _langid_available = False


# Language code to human-readable name mapping
LANGUAGE_NAMES = {
    'en': 'English', 'af': 'Afrikaans', 'sq': 'Albanian', 'ar': 'Arabic',
    'hy': 'Armenian', 'az': 'Azerbaijani', 'eu': 'Basque', 'be': 'Belarusian',
    'bn': 'Bengali', 'bg': 'Bulgarian', 'ca': 'Catalan', 'zh': 'Chinese',
    'hr': 'Croatian', 'cs': 'Czech', 'da': 'Danish', 'nl': 'Dutch',
    'eo': 'Esperanto', 'et': 'Estonian', 'fi': 'Finnish', 'fr': 'French',
    'gl': 'Galician', 'ka': 'Georgian', 'de': 'German', 'el': 'Greek',
    'gu': 'Gujarati', 'ht': 'Haitian', 'ha': 'Hausa', 'iw': 'Hebrew',
    'hi': 'Hindi', 'hu': 'Hungarian', 'is': 'Icelandic', 'id': 'Indonesian',
    'ga': 'Irish', 'it': 'Italian', 'ja': 'Japanese', 'kn': 'Kannada',
    'kk': 'Kazakh', 'rw': 'Kinyarwanda', 'ky': 'Kyrgyz', 'ko': 'Korean',
    'lo': 'Lao', 'la': 'Latin', 'lv': 'Latvian', 'lt': 'Lithuanian',
    'lb': 'Luxembourgish', 'mk': 'Macedonian', 'mg': 'Malagasy', 'ms': 'Malay',
    'ml': 'Malayalam', 'mt': 'Maltese', 'mi': 'Maori', 'mr': 'Marathi',
    'mn': 'Mongolian', 'ne': 'Nepali', 'no': 'Norwegian', 'oc': 'Occitan',
    'or': 'Oriya', 'ps': 'Pashto', 'fa': 'Persian', 'pl': 'Polish',
    'pt': 'Portuguese', 'pa': 'Punjabi', 'ro': 'Romanian', 'ru': 'Russian',
    'sm': 'Samoan', 'gd': 'Scots Gaelic', 'sr': 'Serbian', 'st': 'Sesotho',
    'sn': 'Shona', 'sk': 'Slovak', 'sl': 'Slovenian', 'so': 'Somali',
    'es': 'Spanish', 'sw': 'Swahili', 'sv': 'Swedish', 'tl': 'Tagalog',
    'tg': 'Tajik', 'ta': 'Tamil', 'tt': 'Tatar', 'te': 'Telugu',
    'th': 'Thai', 'bo': 'Tibetan', 'tr': 'Turkish', 'tk': 'Turkmen',
    'uk': 'Ukrainian', 'ur': 'Urdu', 'uz': 'Uzbek', 'vi': 'Vietnamese',
    'cy': 'Welsh', 'xh': 'Xhosa', 'yi': 'Yiddish', 'yo': 'Yoruba', 'zu': 'Zulu',
}


def _get_language_from_id3(filepath):
    """Read language from MP3 ID3 TLAN frame. Returns None if not set."""
    try:
        audio = MP3(filepath)
        if audio.tags and "TLAN" in audio.tags:
            lang = str(audio.tags["TLAN"]).strip().lower()
            if lang and lang != "XXX":
                return lang
    except Exception:
        pass
    return None


def _set_language_in_id3(filepath, lang_code):
    """Write language code to MP3 ID3 TLAN frame."""
    try:
        audio = MP3(filepath)
        if audio.tags is None:
            audio.add_tags()
        # Remove any existing TLAN
        if "TLAN:" in audio.tags:
            del audio.tags["TLAN:"]
        audio.tags.add(TLAN(encoding=3, text=lang_code))
        audio.save()
        return True
    except Exception:
        return False


def get_song_language_from_file(filepath):
    """
    Get the language for a song, checking ID3 TLAN first.
    If not set, falls back to JSON cache.
    Returns language code string or 'en' as default.
    """
    # Try ID3 tag first (authoritative)
    lang = _get_language_from_id3(filepath)
    if lang:
        return lang
    # Fall back to JSON cache
    cache = load_language_cache()
    stem = Path(filepath).stem
    return cache.get(stem, 'en')


def set_song_language(filepath, lang_code):
    """
    Set the language for a song by writing to ID3 TLAN frame.
    Also updates the JSON cache for consistency.
    Returns True on success.
    """
    lang_code = lang_code.strip().lower()[:3]
    success = _set_language_in_id3(filepath, lang_code)
    if success:
        # Also update JSON cache
        cache = load_language_cache()
        stem = Path(filepath).stem
        cache[stem] = lang_code
        save_language_cache(cache)
    return success


def detect_and_set_language_from_metadata(filepath, title=None, artist=None):
    """
    Detect language from song metadata (title + artist) and set it in ID3 TLAN tag.
    If title/artist not provided, reads them from the file's ID3 tags.
    Returns the detected language code.
    """
    # Read title and artist from ID3 if not provided
    if not title or not artist:
        try:
            audio = MP3(filepath)
            if audio.tags:
                title = title or str(audio.tags.get("TIT2", "Unknown Title"))
                artist = artist or str(audio.tags.get("TPE1", "Unknown Artist"))
        except Exception:
            pass
    
    # Detect language using both title and artist
    lang_code = detect_language(title, artist)
    
    # Set the detected language in ID3
    set_song_language(filepath, lang_code)
    
    return lang_code


def detect_language(title, artist=None):
    """
    Detect the language of a song title, optionally using artist name for better detection.
    Returns a language code string (e.g. 'en', 'af', 'ko').
    Falls back to 'en' if detection fails.
    
    Args:
        title: Song title to detect language from
        artist: Optional artist name to combine with title for better detection
    """
    if not title or title == "Unknown Title":
        return 'en'

    _ensure_langid()
    if not _langid_available:
        return 'en'

    try:
        import langid
        # Combine title and artist for more text to analyze if artist is provided
        text_to_analyze = title
        if artist and artist != "Unknown Artist":
            text_to_analyze = f"{title} {artist}"
        
        lang, conf = langid.classify(text_to_analyze)
        if conf > 0.3:
            return lang
        return 'en'
    except Exception:
        return 'en'


def scan_and_cache_languages():
    """
    Scan all MP3 files in the library, detect language from title,
    and store in ID3 TLAN tag. Also saves JSON cache as backup.
    Skips songs that already have a TLAN tag set.
    Returns dict of song_id -> language_code.
    """
    _ensure_langid()
    results = {}

    for f in MUSIC_DIR.glob("*.mp3"):
        # Skip if already has TLAN tag
        existing = _get_language_from_id3(f)
        if existing:
            results[f.stem] = existing
            continue

        # Read title
        try:
            audio = MP3(f)
            tags = audio.tags
            title = str(tags.get("TIT2", f.stem)) if tags else f.stem
        except Exception:
            title = f.stem

        # Detect and store
        lang = detect_language(title)
        _set_language_in_id3(f, lang)
        results[f.stem] = lang

    # Save JSON cache as backup
    save_language_cache(results)
    return results


def save_language_cache(cache_dict):
    """Save language cache to JSON file."""
    try:
        with open(LANGUAGE_CACHE_FILE, 'w', encoding='utf-8') as cf:
            json.dump(cache_dict, cf, indent=2)
    except Exception:
        pass


def load_language_cache():
    """
    Load the language cache from disk.
    Returns dict of song_id -> language_code, or empty dict if no cache.
    """
    if not LANGUAGE_CACHE_FILE.exists():
        return {}
    try:
        with open(LANGUAGE_CACHE_FILE, 'r', encoding='utf-8') as cf:
            return json.load(cf)
    except Exception:
        return {}


def get_available_languages():
    """
    Return sorted list of language codes and names that exist in the library.
    Returns list of dicts: [{"code": "en", "name": "English"}, ...]
    """
    cache = load_language_cache()
    codes = set(cache.values())
    # Also scan ID3 tags for any languages not in cache
    for f in MUSIC_DIR.glob("*.mp3"):
        lang = _get_language_from_id3(f)
        if lang:
            codes.add(lang)
    result = []
    for code in sorted(codes):
        name = LANGUAGE_NAMES.get(code, code.upper())
        result.append({"code": code, "name": name})
    return result


def get_songs_by_language(language_code=None):
    """
    Return set of song_ids that match the given language code.
    If language_code is None, returns all song IDs.
    """
    cache = load_language_cache()
    # Also include songs that have TLAN set but might not be in cache
    for f in MUSIC_DIR.glob("*.mp3"):
        if f.stem not in cache:
            lang = _get_language_from_id3(f)
            if lang:
                cache[f.stem] = lang

    if not language_code or language_code == 'all':
        return set(cache.keys())
    return {sid for sid, lang in cache.items() if lang == language_code}