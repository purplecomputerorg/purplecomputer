"""
Text-to-Speech module using Piper TTS

Piper is a fast, local, neural TTS system.
https://github.com/rhasspy/piper

Deterministic synthesis: fixed _SYNTH_PARAMS, so identical input produces identical WAV output.
"""

import array
import hashlib
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

from .audio import db_to_linear, normalize_loudness

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# Lazy: pygame.mixer drags in numpy (~120ms) and mixer.init() can block
# forever in C on broken audio hardware. Actual init happens via
# music_room.warm_mixer(), which runs a subprocess probe first. This module
# reuses whatever pygame module that call populated.
pygame = None  # populated by _ensure_mixer() after warm_mixer() succeeds


# TEMP diagnostic logging for the silent-speech bug; remove once captured
_DEBUG_LOG = "/tmp/purple-tts-debug.log"


def _dbg(msg: str) -> None:
    try:
        with open(_DEBUG_LOG, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


# Voice model configuration
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006

# Deterministic synthesis parameters (no randomness between runs)
# Parameter names vary across piper-tts versions, so we try all known variants.
_SYNTH_PARAMS = {
    "noise_scale": 0.3,
    "noise_w": 0.3,         # some piper builds
    "noise_w_scale": 0.3,   # other piper builds
    "length_scale": 1.15,  # 15% slower than the model default: kids follow it better
}

# Pronunciation overrides: words Piper mispronounces -> phonetic respelling
PRONUNCIATION_MAP = {
    "dinos": "dyenoze",
}

# Single-character pronunciation map (letters and digits -> spoken form)
# Spellings chosen to avoid Piper treating them as abbreviations
# (e.g. "eff" gets spelled out as E.F.F., but "ef" is spoken as a word)
LETTER_PRONUNCIATION = {
    "A": "ehh", "B": "bee", "C": "see", "D": "dee", "E": "ee",
    "F": "ef.", "G": "jee", "H": "aitch", "I": "eye", "J": "jay",
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
    threshold = db_to_linear(threshold_db)
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


SPEECH_RMS_DB = -12.0
SPEECH_CEILING_DB = -1.0


def postprocess_samples(samples: array.array, sample_rate: int) -> array.array:
    samples = _trim_silence(samples, sample_rate)
    samples = _apply_fade(samples, sample_rate)
    return normalize_loudness(samples, SPEECH_RMS_DB, SPEECH_CEILING_DB)


# --- Caching ---

_CACHE_DIR = Path(os.environ.get("PURPLE_TTS_CACHE")) if os.environ.get("PURPLE_TTS_CACHE") else Path.home() / ".purple" / "cache" / "tts"

# Don't cache text longer than this. Generous because Enter-Enter recall
# makes exact repeats common, and long utterances cost the most to synthesize.
# Keys are hashed and the 50MB LRU bounds disk use, so this is just a sanity cap.
_MAX_CACHE_TEXT_LEN = 500

# Cache size limit (bytes). Oldest-accessed files evicted when exceeded.
# Stored as raw WAV (~43 KB/s of speech, so ~500-1000 phrases fit): the image
# ships no encoder, and LRU eviction bounds disk use either way.
# History and rejected alternatives: guides/tts-caching.md
_MAX_CACHE_BYTES = 50 * 1024 * 1024  # 50 MB


_SYNTH_SIGNATURE = repr((VOICE_MODEL, VOICE_SPEAKER, sorted(_SYNTH_PARAMS.items()), SPEECH_RMS_DB, SPEECH_CEILING_DB))


def _cache_path(prepared_text: str) -> Path:
    """Keyed on text plus synthesis settings, so a voice or leveling change never replays stale WAVs."""
    key = f"{_SYNTH_SIGNATURE}\n{prepared_text}".encode('utf-8')
    return _CACHE_DIR / f"{hashlib.sha256(key).hexdigest()[:16]}.wav"


def _get_cached(prepared_text: str) -> Path | None:
    """Return cached WAV path if it exists."""
    cache_path = _cache_path(prepared_text)
    if cache_path.exists():
        try:
            cache_path.touch()
        except OSError:
            pass
        return cache_path
    return None


def _store_cache(prepared_text: str, wav_path: str) -> Path | None:
    """Move the WAV into the cache. Returns cache path, or None on failure
    (the temp file survives so the caller can still play it)."""
    if len(prepared_text) > _MAX_CACHE_TEXT_LEN:
        return None

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _cache_path(prepared_text)
        shutil.move(wav_path, cache_path)
        _enforce_cache_limit()
        return cache_path
    except Exception as e:
        _dbg(f"_store_cache failed: {type(e).__name__}: {e}")
        return None


def _enforce_cache_limit() -> None:
    """Evict oldest-accessed cache files if total size exceeds the limit."""
    try:
        with os.scandir(_CACHE_DIR) as entries:
            files = [(e.stat().st_mtime, e.stat().st_size, Path(e.path))
                     for e in entries if e.is_file()]

        total = sum(size for _, size, _ in files)
        if total <= _MAX_CACHE_BYTES:
            return

        # Evict oldest-accessed first until under limit
        for _, size, path in sorted(files):
            if total <= _MAX_CACHE_BYTES:
                break
            path.unlink(missing_ok=True)
            total -= size
    except Exception:
        pass


def clear_cache() -> int:
    """Delete all cached TTS files. Returns number of files removed."""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    return count


# Pre-generated voice clips directory
VOICE_CLIPS_DIR = Path(__file__).parent.parent / "packs" / "core-sounds" / "content" / "voice"


def voice_clip_filename(text: str) -> str:
    """Filename a phrase's pre-generated clip lives under.

    scripts/generate_voice_clips.py writes clips under this name, so the two
    must agree or the clip is generated and never found.
    """
    return text.strip().lower().replace(" ", "_") + ".wav"


def _get_voice_clip(text: str) -> Path | None:
    """Check if a pre-generated voice clip exists for this text."""
    filename = voice_clip_filename(text)
    # Clips are short curated phrases; a longer name would also make
    # Path.exists() raise ENAMETOOLONG (filesystem cap is 255 bytes)
    if len(filename.encode()) > 255:
        return None
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


def find_voice_model() -> Path | None:
    candidates = (p / f"{VOICE_MODEL}.onnx" for p in _get_voice_search_paths())
    return next((c for c in candidates if c.exists()), None)


def load_voice():
    """PiperVoice for the clip scripts. Raises ImportError or FileNotFoundError with the reason."""
    from piper import PiperVoice
    model_path = find_voice_model()
    if model_path is None:
        searched = "\n".join(f"  {p / f'{VOICE_MODEL}.onnx'}" for p in _get_voice_search_paths())
        raise FileNotFoundError(f"Piper voice model not found. Searched in:\n{searched}")
    return PiperVoice.load(str(model_path))

# Piper voice instance (lazy loaded)
_piper_voice = None
_piper_available = None

# Serialize all Piper synthesis calls (espeak phonemizer is not thread-safe)
_synthesis_lock = threading.Lock()
_preload_started = False


def _get_piper_voice():
    """Piper voice, loaded once. Serialized so a preload and a first speak can't both load."""
    global _piper_voice, _piper_available
    with _synthesis_lock:
        if _piper_available is False or _piper_voice is not None:
            return _piper_voice
        if os.environ.get("PURPLE_DEMO_AUTOSTART"):
            _piper_available = False  # the scripted demo plays only pre-generated clips
            return None
        try:
            _piper_voice = load_voice()
            _piper_available = True
        except Exception as e:
            _dbg(f"piper unavailable: {type(e).__name__}: {e}")
            _piper_available = False
        return _piper_voice


_worker: subprocess.Popen | None = None
_worker_ready = threading.Event()  # set once the worker is usable, or once it is known dead
_WORKER_READY_TIMEOUT = 90.0
_WORKER_REPLY_TIMEOUT = 30.0


def _worker_stderr():
    from .stderr_guard import LOG_PATH
    try:
        return open(LOG_PATH, "ab")
    except OSError:
        return subprocess.DEVNULL


def _drop_worker(proc) -> None:
    global _worker
    if _worker is proc:
        _worker = None
    try:
        proc.stdin.close()  # EOF: the worker exits on its own
    except Exception:
        pass
    _worker_ready.set()


def preload() -> threading.Thread | None:
    """Start the speech worker once per session. The model loads in its own
    process, so typing never stalls and the first word isn't cancelled mid-load."""
    global _preload_started, _worker
    if _preload_started or os.environ.get("PURPLE_DEMO_AUTOSTART") or find_voice_model() is None:
        return None
    _preload_started = True
    try:
        _worker = subprocess.Popen(
            [sys.executable, "-m", "purple_tui.tts_worker"],
            cwd=Path(__file__).resolve().parent.parent,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=_worker_stderr(),
            text=True, bufsize=1,
        )
    except Exception as e:
        _dbg(f"piper worker: spawn failed {type(e).__name__}: {e}")
        return None
    proc = _worker

    def _await_ready():
        from .audio import _log
        t0 = time.monotonic()
        if proc.stdout.readline().strip() == "ready":
            _worker_ready.set()
            _log(f"piper worker: ready in {time.monotonic() - t0:.1f}s")
        else:
            _log(f"piper worker: failed to start ({time.monotonic() - t0:.1f}s), speech loads in-process")
            _drop_worker(proc)

    thread = threading.Thread(target=_await_ready, daemon=True, name="piper-worker-ready")
    thread.start()
    return thread


def _worker_synthesize(prepared_text: str, wav_path: str) -> bool | None:
    """ok/fail from the worker, or None when there is no usable worker."""
    if _worker is None or not _worker_ready.wait(timeout=_WORKER_READY_TIMEOUT):
        return None
    proc = _worker
    if proc is None:
        return None
    with _synthesis_lock:
        try:
            proc.stdin.write(f"{wav_path}\t{prepared_text}\n")
            proc.stdin.flush()
            readable, _, _ = select.select([proc.stdout], [], [], _WORKER_REPLY_TIMEOUT)
            reply = proc.stdout.readline().strip() if readable else ""
        except (OSError, ValueError):
            reply = ""
    if reply in ("ok", "fail"):
        return reply == "ok"
    _dbg("piper worker: no reply, dropping it")
    _drop_worker(proc)
    return None


def _ensure_mixer() -> bool:
    """Return True iff the pygame mixer is safely available.

    Delegates to music_room.warm_mixer(), which runs the subprocess probe
    exactly once per session and caches the result. Never initializes
    pygame.mixer in-process directly — that call can hang forever in
    snd_pcm_open() on broken audio hardware while holding the GIL.
    """
    global pygame
    from .rooms.music_room import warm_mixer
    _dbg("ensure_mixer: calling warm_mixer")
    ok = warm_mixer()
    _dbg(f"ensure_mixer: warm_mixer -> {ok}")
    if not ok:
        return False
    if pygame is None:
        import pygame as _pg
        import pygame.mixer  # noqa: F401
        pygame = _pg
    return True


def _make_synth_config():
    """Build a SynthesisConfig using only parameters the installed version accepts."""
    from piper.config import SynthesisConfig
    import dataclasses
    valid = {f.name for f in dataclasses.fields(SynthesisConfig)}
    kwargs = {k: v for k, v in _SYNTH_PARAMS.items() if k in valid}
    kwargs["speaker_id"] = VOICE_SPEAKER
    return SynthesisConfig(**kwargs)


def synthesize_to_file(voice, prepared_text: str, wav_path: str) -> bool:
    """Shared by runtime speech and the clip scripts so the two can't drift. Serialized: espeak's phonemizer is not thread-safe."""
    config = _make_synth_config()
    with _synthesis_lock:
        audio_chunks = list(voice.synthesize(prepared_text, config))
    if not audio_chunks:
        return False
    first = audio_chunks[0]
    samples = array.array('h')
    samples.frombytes(b''.join(chunk.audio_int16_bytes for chunk in audio_chunks))
    samples = postprocess_samples(samples, first.sample_rate)
    with wave.open(wav_path, 'wb') as wav_file:
        wav_file.setnchannels(first.sample_channels)
        wav_file.setsampwidth(first.sample_width)
        wav_file.setframerate(first.sample_rate)
        wav_file.writeframes(samples.tobytes())
    return True


def _synthesize_to_cache(prepared_text: str) -> Path | None:
    """Synthesize prepared text (worker first, in-process if there is none),
    post-process, and store in cache. Returns the path to play, or None."""
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        ok = _worker_synthesize(prepared_text, wav_path)
        if ok is None:
            voice = _get_piper_voice()
            ok = voice is not None and synthesize_to_file(voice, prepared_text, wav_path)
        if not ok:
            Path(wav_path).unlink(missing_ok=True)
            return None

        # Try to cache (best effort, don't lose audio if caching fails)
        cache_path = _store_cache(prepared_text, wav_path)
        if cache_path:
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
    _dbg(f"stop() id {_speech_id} -> {_speech_id + 1}")
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
    wrapped = (lambda i: on_playing()) if on_playing else None
    return speak_many([text], on_playing=wrapped, on_done=on_done)


def speak_many(texts: list[str], gap: float = 0.5,
               on_playing: callable = None, on_done: callable = None) -> bool:
    """
    Speak texts in order with a pause between items.
    Cancels any currently playing or generating speech first; a later
    speak()/stop() cancels the rest of the sequence.

    Args:
        texts: The texts to speak, in order
        gap: Pause between items, in seconds
        on_playing: Called from background thread with the index into texts
            when that item starts playing
        on_done: Called from background thread when the sequence finishes
            (or is cancelled)

    Returns:
        True if speech was started, False otherwise
    """
    global _speech_id
    _dbg(f"speak_many n={len(texts)} muted={_muted} first={texts[0][:60]!r}" if texts else "speak_many empty")
    if _muted:
        return False

    from .speech_filter import filter_speech
    items = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        filtered = filter_speech(text)
        if filtered and filtered.strip():
            items.append((i, filtered))
    if not items:
        _dbg("speak_many: all filtered, not starting")
        return False

    # Stop any previous speech and get new ID
    stop()
    my_id = _speech_id

    thread = threading.Thread(
        target=_speak_seq, args=(items, my_id, gap, on_playing, on_done), daemon=True
    )
    thread.start()
    return True


def _speak_seq(items: list[tuple[int, str]], speech_id: int, gap: float,
               on_playing: callable = None, on_done: callable = None) -> None:
    """Speak a sequence of (index, text) items from a background thread."""
    try:
        for n, (index, text) in enumerate(items):
            if n:
                time.sleep(gap)
            if speech_id != _speech_id:
                _dbg(f"speak_seq: cancelled (id {speech_id} != {_speech_id})")
                return
            cb = (lambda idx=index: on_playing(idx)) if on_playing else None
            try:
                _speak_sync(text, speech_id, cb)
            except Exception as e:
                # A failed item must not silently kill the whole thread
                _dbg(f"speak_seq: item raised {type(e).__name__}: {e}")
    finally:
        if on_done:
            try:
                on_done()
            except Exception:
                pass


def _speak_sync(text: str, speech_id: int, on_playing: callable = None) -> bool:
    """Synchronous speech, called from background thread"""
    global _current_channel, _speech_id

    # Check cancellation first
    if speech_id != _speech_id:
        _dbg(f"speak_sync: cancelled before start (id {speech_id} != {_speech_id})")
        return False

    if not _ensure_mixer():
        _dbg("speak_sync: mixer unavailable")
        return False

    # Check for pre-generated voice clip first (hand-curated clips take priority)
    clip_path = _get_voice_clip(text)
    if clip_path:
        _dbg(f"speak_sync: voice clip {clip_path}")
        return _play_clip(clip_path, speech_id, on_playing)

    # Prepare text (letter expansion, pronunciation, padding)
    prepared = _prepare_text(text)

    # Check cache
    cached_path = _get_cached(prepared)
    if cached_path:
        _dbg("speak_sync: cache hit")
        return _play_clip(cached_path, speech_id, on_playing)

    _dbg(f"speak_sync: synthesizing len={len(prepared)}")
    result_path = _synthesize_to_cache(prepared)
    if result_path is None:
        _dbg("speak_sync: synthesis FAILED")
        return False

    # Check if we've been cancelled after generating
    if speech_id != _speech_id:
        _dbg("speak_sync: cancelled after synthesis")
        return False

    is_temp = not str(result_path).startswith(str(_CACHE_DIR))
    try:
        return _play_clip(result_path, speech_id, on_playing)
    finally:
        # Clean up temp files (uncached results)
        if is_temp:
            result_path.unlink(missing_ok=True)


def _play_clip(clip_path: Path, speech_id: int, on_playing: callable = None) -> bool:
    """Play a pre-generated or cached voice clip."""
    global _current_channel, _speech_id

    try:
        if speech_id != _speech_id:
            _dbg("play_clip: cancelled before play")
            return False

        sound = pygame.mixer.Sound(str(clip_path))
        from .audio import play_safe
        channel = play_safe(sound)
        _dbg(f"play_clip: dur={sound.get_length():.1f}s channel={'ok' if channel else 'NONE'}")
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

        _dbg("play_clip: finished")
        return True

    except Exception as e:
        _dbg(f"play_clip: exception {type(e).__name__}: {e}")
        return False
    finally:
        # Cleared even on exception: a stale channel here would veto the
        # app's mixer idle-release for the rest of the session.
        _current_channel = None


def is_available() -> bool:
    """Check if TTS is available"""
    return _get_piper_voice() is not None
