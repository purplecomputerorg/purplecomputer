"""
Text-to-Speech module using Piper TTS

Piper is a fast, local, neural TTS system.
https://github.com/rhasspy/piper

Deterministic synthesis: noise_scale=0.3, noise_w=0.3, length_scale=1.0
ensures identical input always produces identical WAV output.
"""

import array
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path
import os

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
# Suppress ONNX Runtime warnings (e.g., "Unknown CPU vendor" in VMs)
os.environ['ORT_LOGGING_LEVEL'] = '3'
# Also suppress TensorFlow/transformers warnings if they leak through
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import pygame.mixer
from contextlib import contextmanager


@contextmanager
def _suppress_stderr():
    """Temporarily redirect stderr to suppress ONNX runtime warnings."""
    old_stderr = sys.stderr
    try:
        sys.stderr = open(os.devnull, 'w')
        yield
    finally:
        try:
            sys.stderr.close()
        except Exception:
            pass
        sys.stderr = old_stderr

# Voice model configuration
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006

# Deterministic synthesis parameters (no randomness between runs)
# Parameter names vary across piper-tts versions, so we try all known variants.
_SYNTH_PARAMS = {
    "noise_scale": 0.3,
    "noise_w": 0.3,         # some piper builds
    "noise_w_scale": 0.3,   # other piper builds
    "length_scale": 1.0,
}

# Pronunciation overrides: words Piper mispronounces -> phonetic respelling
PRONUNCIATION_MAP = {
    "dinos": "dyenoze",
}

# Single-character pronunciation map (letters and digits -> spoken form)
# Spellings chosen to avoid Piper treating them as abbreviations
# (e.g. "eff" gets spelled out as E.F.F., but "ef" is spoken as a word)
LETTER_PRONUNCIATION = {
    "A": "ay", "B": "bee", "C": "see", "D": "dee", "E": "ee",
    "F": "ef", "G": "jee", "H": "aitch", "I": "eye", "J": "jay",
    "K": "kay", "L": "el", "M": "em", "N": "en", "O": "oh",
    "P": "pee", "Q": "cue", "R": "ar", "S": "es", "T": "tee",
    "U": "you", "V": "vee", "W": "double you", "X": "ex",
    "Y": "why", "Z": "zee",
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Color words used in the system (for pre-generation)
SYSTEM_COLORS = [
    "red", "yellow", "blue", "orange", "green", "purple", "pink",
    "brown", "black", "white", "gray", "cyan", "magenta", "gold",
]


def _fix_pronunciation(text: str) -> str:
    """Replace words Piper mispronounces with phonetic respellings."""
    import re
    for word, replacement in PRONUNCIATION_MAP.items():
        text = re.sub(rf'\b{word}\b', replacement, text, flags=re.IGNORECASE)
    return text


def _normalize_for_cache(text: str) -> str:
    """Strip characters that don't affect TTS pronunciation.

    Piper ignores most punctuation, so "hello" and "hello!" sound identical.
    Normalizing before cache key generation ensures they share a cache entry.
    """
    # Keep letters, digits, spaces (whitespace affects pacing)
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    # Lowercase for consistent keys
    return text.lower()


def _prepare_text(text: str) -> str:
    """Prepare text for synthesis: letter expansion, pronunciation fixes, padding.

    1. If input is exactly one letter A-Z (upper or lower), replace with phonetic spelling.
    2. Apply pronunciation overrides.
    3. Normalize punctuation/case for cache consistency.
    4. If result is < 4 characters, append a period for prosody stability.
    """
    stripped = text.strip()

    # Single letter -> phonetic spelling
    if len(stripped) == 1 and stripped.upper() in LETTER_PRONUNCIATION:
        stripped = LETTER_PRONUNCIATION[stripped.upper()]

    # Pronunciation fixes
    stripped = _fix_pronunciation(stripped)

    # Normalize punctuation and case for cache consistency
    stripped = _normalize_for_cache(stripped)

    # Micro-context padding for very short utterances
    if len(stripped) < 4:
        stripped = stripped + "."

    return stripped


# --- WAV post-processing ---

def _trim_silence(samples: array.array, sample_rate: int, threshold_db: float = -40.0) -> array.array:
    """Trim leading and trailing silence below threshold_db.

    Uses windowed RMS (5ms windows) to avoid being fooled by single-sample
    spikes or brief static bursts from synthesis padding artifacts.

    Args:
        samples: array of signed 16-bit samples
        sample_rate: samples per second
        threshold_db: amplitude threshold in dB (relative to 16-bit full scale)
    """
    if not samples:
        return samples

    # Convert dB threshold to linear amplitude (16-bit full scale = 32767)
    threshold = 32767 * (10 ** (threshold_db / 20.0))
    threshold_sq = threshold * threshold

    # 5ms RMS window
    window = max(1, int(sample_rate * 0.005))

    def _rms_above(start_idx: int) -> bool:
        """Check if RMS of window starting at start_idx exceeds threshold."""
        end_idx = min(start_idx + window, len(samples))
        if end_idx <= start_idx:
            return False
        sum_sq = sum(s * s for s in samples[start_idx:end_idx])
        return (sum_sq / (end_idx - start_idx)) > threshold_sq

    # Find first window with RMS above threshold
    start = 0
    for i in range(0, len(samples) - window, window):
        if _rms_above(i):
            # Back up a tiny bit so we don't clip the attack
            start = max(0, i - int(sample_rate * 0.01))
            break

    # Find last window with RMS above threshold
    end = len(samples)
    for i in range(len(samples) - window, -1, -window):
        if _rms_above(i):
            # Keep a short tail
            end = min(len(samples), i + window + int(sample_rate * 0.02))
            break

    return samples[start:end]


def _apply_fade(samples: array.array, sample_rate: int, fade_ms: float = 10.0) -> array.array:
    """Apply fade-in and fade-out to eliminate clicks at audio boundaries."""
    if not samples:
        return samples

    fade_len = min(int(sample_rate * fade_ms / 1000.0), len(samples) // 2)
    if fade_len < 1:
        return samples

    result = array.array('h', samples)

    # Fade in
    for i in range(fade_len):
        scale = i / fade_len
        result[i] = int(result[i] * scale)

    # Fade out
    for i in range(fade_len):
        scale = i / fade_len
        result[-(i + 1)] = int(result[-(i + 1)] * scale)

    return result


def _normalize_peak(samples: array.array, target_db: float = -3.0) -> array.array:
    """Normalize peak amplitude to target_db.

    Args:
        samples: array of signed 16-bit samples
        target_db: target peak level in dB (relative to 16-bit full scale)
    """
    if not samples:
        return samples

    peak = max(abs(s) for s in samples)
    if peak == 0:
        return samples

    target_linear = 32767 * (10 ** (target_db / 20.0))
    scale = target_linear / peak

    result = array.array('h')
    for s in samples:
        result.append(max(-32768, min(32767, int(s * scale))))
    return result


def _postprocess_wav(wav_path: str) -> None:
    """Trim silence, fade edges, and normalize a WAV file in place."""
    with wave.open(wav_path, 'rb') as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    samples = array.array('h')
    samples.frombytes(raw)

    # Trim leading/trailing silence at -40 dB (windowed RMS)
    samples = _trim_silence(samples, sample_rate, threshold_db=-40.0)

    # Fade edges to eliminate clicks/pops
    samples = _apply_fade(samples, sample_rate, fade_ms=10.0)

    # Normalize peak to -3 dB
    samples = _normalize_peak(samples, target_db=-3.0)

    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


# --- Caching ---

_CACHE_DIR = Path(os.environ.get("PURPLE_TTS_CACHE")) if os.environ.get("PURPLE_TTS_CACHE") else Path.home() / ".purple" / "cache" / "tts"

# Don't cache text longer than this (unlikely to be retyped exactly)
_MAX_CACHE_TEXT_LEN = 60

# Cache size limit (bytes). Oldest-accessed files evicted when exceeded.
_MAX_CACHE_BYTES = 50 * 1024 * 1024  # 50 MB

def _wav_to_ogg(wav_path: str, ogg_path: str) -> None:
    """Convert WAV to OGG Vorbis using ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", wav_path, "-c:a", "libvorbis", "-q:a", "2", ogg_path],
        check=True, capture_output=True,
    )


def _cache_key(text: str) -> str:
    """Hash the prepared text to create a cache filename."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _get_cached(prepared_text: str) -> Path | None:
    """Return cached OGG path if it exists."""
    cache_path = _CACHE_DIR / f"{_cache_key(prepared_text)}.ogg"
    if cache_path.exists():
        try:
            cache_path.touch()
        except OSError:
            pass
        return cache_path
    return None


def _store_cache(prepared_text: str, wav_path: str) -> Path | None:
    """Store audio in cache as OGG (or WAV fallback). Returns cache path, or None on failure."""
    if len(prepared_text) > _MAX_CACHE_TEXT_LEN:
        return None

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = _cache_key(prepared_text)
        ogg_path = _CACHE_DIR / f"{key}.ogg"
        _wav_to_ogg(wav_path, str(ogg_path))
        _enforce_cache_limit()
        return ogg_path
    except Exception:
        return None


def _enforce_cache_limit() -> None:
    """Evict oldest-accessed cache files if total size exceeds the limit."""
    try:
        files = list(_CACHE_DIR.glob("*.*"))
        if not files:
            return

        total = sum(f.stat().st_size for f in files)
        if total <= _MAX_CACHE_BYTES:
            return

        # Sort by modification time (oldest first), evict until under limit
        files.sort(key=lambda f: f.stat().st_mtime)
        for f in files:
            if total <= _MAX_CACHE_BYTES:
                break
            size = f.stat().st_size
            f.unlink(missing_ok=True)
            total -= size
    except Exception:
        pass


def clear_cache() -> int:
    """Delete all cached TTS files. Returns number of files removed."""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.iterdir():
        if f.suffix == ".ogg":
            f.unlink()
            count += 1
    return count


# Pre-generated voice clips directory
VOICE_CLIPS_DIR = Path(__file__).parent.parent / "packs" / "core-sounds" / "content" / "voice"


def _get_voice_clip(text: str) -> Path | None:
    """Check if a pre-generated voice clip exists for this text."""
    # Convert text to filename (spaces to underscores)
    filename = text.strip().lower().replace(" ", "_") + ".wav"
    clip_path = VOICE_CLIPS_DIR / filename
    if clip_path.exists():
        return clip_path
    return None

def _get_voice_search_paths() -> list[Path]:
    """Get list of paths to search for voice model."""
    paths = [
        Path.home() / ".local" / "share" / "piper-voices",
        Path.home() / ".cache" / "piper",
        Path("/opt/purple/piper-voices"),  # USB/installed system
        Path("/opt/piper"),
    ]
    # On macOS/Linux, also check the actual user home (in case HOME is overridden)
    try:
        import pwd
        real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        paths.insert(0, real_home / ".local" / "share" / "piper-voices")
    except (ImportError, KeyError):
        pass
    return paths

# Piper voice instance (lazy loaded)
_piper_voice = None
_piper_available = None

# Serialize all Piper synthesis calls (espeak phonemizer is not thread-safe)
_synthesis_lock = threading.Lock()


def _get_piper_voice():
    """Get or create the Piper voice instance"""
    global _piper_voice, _piper_available

    if _piper_available is False:
        return None

    if _piper_voice is not None:
        return _piper_voice

    # In demo mode, skip piper entirely to avoid ONNX runtime warnings
    # Demo should use only pre-generated voice clips
    if os.environ.get("PURPLE_DEMO_AUTOSTART"):
        _piper_available = False
        return None

    try:
        # Suppress stderr during piper import (loads ONNX runtime)
        # This catches the "Unknown CPU vendor" warning from onnxruntime C code
        import sys
        old_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        try:
            from piper import PiperVoice
        finally:
            try:
                sys.stderr.close()
            except Exception:
                pass
            sys.stderr = old_stderr

        # Check for voice model in various locations
        model_path = None
        for base_path in _get_voice_search_paths():
            candidate = base_path / f"{VOICE_MODEL}.onnx"
            if candidate.exists():
                model_path = candidate
                break

        if model_path is None:
            _piper_available = False
            return None

        # Suppress stderr during model loading (ONNX session creation)
        with _suppress_stderr():
            _piper_voice = PiperVoice.load(str(model_path))
        _piper_available = True
        return _piper_voice

    except ImportError:
        _piper_available = False
        return None
    except Exception:
        _piper_available = False
        return None


_mixer_initialized = False


def _ensure_mixer() -> bool:
    """Check if pygame mixer is available (don't initialize, let music mode do it)"""
    global _mixer_initialized
    if _mixer_initialized:
        return True
    # Check if mixer is already initialized (by music mode)
    if pygame.mixer.get_init():
        _mixer_initialized = True
        return True
    # Try to initialize with standard settings
    # Use larger buffer (1024) to prevent audio clipping at start
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.set_num_channels(16)
        _mixer_initialized = True
        return True
    except pygame.error:
        return False


_init_done = False


def init() -> None:
    """Pre-initialize TTS (load voice model and mixer). Call when speech is enabled."""
    global _init_done
    if _init_done:
        return
    _init_done = True
    thread = threading.Thread(target=_init_sync, daemon=True)
    thread.start()


def _init_sync() -> None:
    """Initialize in background thread, then pre-generate common phrases."""
    _get_piper_voice()
    _ensure_mixer()
    # Pre-generate in a separate thread so init completes quickly
    thread = threading.Thread(target=_pregenerate_cache, daemon=True)
    thread.start()


def _pregenerate_cache() -> None:
    """Pre-generate cached audio for common utterances in the background.

    Covers letters, numbers, colors, all emoji words, and play mode words.
    Runs at low priority so it doesn't block normal usage.
    """
    voice = _get_piper_voice()
    if voice is None:
        return

    phrases = []

    # All 26 letters
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        phrases.append(letter)

    # Digits 0-20
    number_words = [
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    ]
    phrases.extend(number_words)

    # Math words
    phrases.extend(["plus", "equals", "times", "minus"])

    # System color words
    phrases.extend(SYSTEM_COLORS)

    # All emoji words (cat, dog, rocket, etc.)
    try:
        from .content import get_content
        content = get_content()
        for word in content.emojis:
            # Skip emoticon-style entries like ":)" or "<3"
            if word.isalpha() or " " in word:
                phrases.append(word)
    except Exception:
        pass

    # Music mode recognized words (cat, dog, mom, dad, etc.)
    try:
        from .music_words import WORDS
        phrases.extend(WORDS)
    except Exception:
        pass

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for phrase in phrases:
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            unique.append(phrase)

    for phrase in unique:
        prepared = _prepare_text(phrase)
        if _get_cached(prepared) is None:
            _synthesize_to_cache(voice, prepared)


def _make_synth_config():
    """Build a SynthesisConfig using only parameters the installed version accepts."""
    from piper.config import SynthesisConfig
    import dataclasses
    valid = {f.name for f in dataclasses.fields(SynthesisConfig)}
    kwargs = {k: v for k, v in _SYNTH_PARAMS.items() if k in valid}
    kwargs["speaker_id"] = VOICE_SPEAKER
    return SynthesisConfig(**kwargs)


def _synthesize_to_file(voice, prepared_text: str, wav_path: str) -> bool:
    """Synthesize prepared text to a WAV file. Returns True on success.

    Acquires _synthesis_lock to prevent concurrent Piper calls
    (espeak phonemizer is not thread-safe).
    """
    config = _make_synth_config()

    with _synthesis_lock:
        with _suppress_stderr():
            audio_chunks = list(voice.synthesize(prepared_text, config))

    if not audio_chunks:
        return False

    first_chunk = audio_chunks[0]
    with wave.open(wav_path, 'wb') as wav_file:
        wav_file.setnchannels(first_chunk.sample_channels)
        wav_file.setsampwidth(first_chunk.sample_width)
        wav_file.setframerate(first_chunk.sample_rate)
        for chunk in audio_chunks:
            wav_file.writeframes(chunk.audio_int16_bytes)

    # Post-process: trim silence, normalize
    _postprocess_wav(wav_path)
    return True


def _synthesize_to_cache(voice, prepared_text: str) -> Path | None:
    """Synthesize prepared text, post-process, and store in cache.

    Returns the path to play (cache path or temp file), or None on failure.
    """
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        if not _synthesize_to_file(voice, prepared_text, wav_path):
            Path(wav_path).unlink(missing_ok=True)
            return None

        # Try to cache (best effort, don't lose audio if caching fails)
        cache_path = _store_cache(prepared_text, wav_path)
        if cache_path:
            Path(wav_path).unlink(missing_ok=True)
            return cache_path

        # Caching failed, return temp file (caller must clean up)
        return Path(wav_path)

    except Exception:
        if wav_path:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass
        return None


_current_channel = None
_speech_id = 0  # Incremented on each speak() call to cancel stale requests
_muted = False  # Global mute state (controlled by app volume toggle)


def set_muted(muted: bool) -> None:
    """Set the global mute state. When muted, speak() does nothing."""
    global _muted
    _muted = muted
    if muted:
        stop()  # Stop any currently playing speech


def stop() -> None:
    """Stop any currently playing speech and cancel pending"""
    global _current_channel, _speech_id
    _speech_id += 1  # Invalidate any pending speech (atomic due to GIL)
    try:
        ch = _current_channel
        if ch:
            ch.stop()
    except Exception:
        pass
    _current_channel = None


def speak(text: str, on_playing: callable = None, on_done: callable = None) -> bool:
    """
    Speak the given text using Piper TTS.
    Runs in a background thread to not block the UI.
    Cancels any currently playing or generating speech first.

    Args:
        text: The text to speak
        on_playing: Called from background thread when audio starts playing
        on_done: Called from background thread when speech finishes (or fails)

    Returns:
        True if speech was started, False otherwise
    """
    global _speech_id
    if _muted:
        return False
    if not text or not text.strip():
        return False

    # Filter profanity
    from .speech_filter import filter_speech
    text = filter_speech(text)

    if not text or not text.strip():
        return False

    # Stop any previous speech and get new ID
    stop()
    my_id = _speech_id

    # Run TTS in background thread
    thread = threading.Thread(
        target=_speak_sync, args=(text, my_id, on_playing, on_done), daemon=True
    )
    thread.start()
    return True


def _speak_sync(text: str, speech_id: int,
                on_playing: callable = None, on_done: callable = None) -> bool:
    """Synchronous speech, called from background thread"""
    global _current_channel, _speech_id

    try:
        # Check cancellation first
        if speech_id != _speech_id:
            return False

        if not _ensure_mixer():
            return False

        # Check for pre-generated voice clip first (hand-curated clips take priority)
        clip_path = _get_voice_clip(text)
        if clip_path:
            return _play_clip(clip_path, speech_id, on_playing)

        # Prepare text (letter expansion, pronunciation, padding)
        prepared = _prepare_text(text)

        # Check cache
        cached_path = _get_cached(prepared)
        if cached_path:
            return _play_clip(cached_path, speech_id, on_playing)

        # Fall back to Piper TTS for dynamic content
        voice = _get_piper_voice()
        if voice is None:
            return False

        # Check again after potentially slow voice load
        if speech_id != _speech_id:
            return False

        # Synthesize, post-process, and cache (if short enough to be worth caching)
        result_path = _synthesize_to_cache(voice, prepared)
        if result_path is None:
            return False

        # Check if we've been cancelled after generating
        if speech_id != _speech_id:
            return False

        is_temp = not str(result_path).startswith(str(_CACHE_DIR))
        try:
            return _play_clip(result_path, speech_id, on_playing)
        finally:
            # Clean up temp files (uncached results)
            if is_temp:
                result_path.unlink(missing_ok=True)
    finally:
        if on_done:
            try:
                on_done()
            except Exception:
                pass


def _play_clip(clip_path: Path, speech_id: int, on_playing: callable = None) -> bool:
    """Play a pre-generated or cached voice clip."""
    global _current_channel, _speech_id

    try:
        if speech_id != _speech_id:
            return False

        sound = pygame.mixer.Sound(str(clip_path))
        channel = sound.play()
        _current_channel = channel

        if on_playing:
            try:
                on_playing()
            except Exception:
                pass

        if channel:
            while channel.get_busy():
                if speech_id != _speech_id:
                    try:
                        channel.stop()
                    except Exception:
                        pass
                    break
                pygame.time.wait(50)

        _current_channel = None
        return True

    except Exception:
        return False


def is_available() -> bool:
    """Check if TTS is available"""
    return _get_piper_voice() is not None
