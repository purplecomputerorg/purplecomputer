"""
Text-to-Speech module using Piper TTS

Piper is a fast, local, neural TTS system.
https://github.com/rhasspy/piper
"""

import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path
import os

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame.mixer

# Voice model configuration
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006

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


def _get_piper_voice():
    """Get or create the Piper voice instance"""
    global _piper_voice, _piper_available

    if _piper_available is False:
        return None

    if _piper_voice is not None:
        return _piper_voice

    try:
        from piper import PiperVoice

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
    """Check if pygame mixer is available (don't initialize - let play mode do it)"""
    global _mixer_initialized
    if _mixer_initialized:
        return True
    # Check if mixer is already initialized (by play mode)
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
    """Initialize in background thread"""
    _get_piper_voice()
    _ensure_mixer()


_current_channel = None
_speech_id = 0  # Incremented on each speak() call to cancel stale requests


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


def speak(text: str) -> bool:
    """
    Speak the given text using Piper TTS.
    Runs in a background thread to not block the UI.
    Cancels any currently playing or generating speech first.

    Args:
        text: The text to speak

    Returns:
        True if speech was started, False otherwise
    """
    global _speech_id
    if not text or not text.strip():
        return False

    # Stop any previous speech and get new ID
    stop()
    my_id = _speech_id

    # Run TTS in background thread
    thread = threading.Thread(target=_speak_sync, args=(text, my_id), daemon=True)
    thread.start()
    return True


def _speak_sync(text: str, speech_id: int) -> bool:
    """Synchronous speech - called from background thread"""
    global _current_channel, _speech_id

    # Check cancellation first
    if speech_id != _speech_id:
        return False

    if not _ensure_mixer():
        return False

    # Check for pre-generated voice clip first
    clip_path = _get_voice_clip(text)
    if clip_path:
        return _play_clip(clip_path, speech_id)

    # Fall back to Piper TTS for dynamic content
    voice = _get_piper_voice()
    if voice is None:
        return False

    # Check again after potentially slow voice load
    if speech_id != _speech_id:
        return False

    wav_path = None
    try:
        # Check if we've been cancelled before generating
        if speech_id != _speech_id:
            return False

        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        # Generate audio with Piper
        # Pad with pauses before and after to prevent clipping on short words
        from piper.config import SynthesisConfig
        config = SynthesisConfig(speaker_id=VOICE_SPEAKER)

        # Collect audio chunks from generator
        audio_chunks = list(voice.synthesize(f"... {text} ...", config))
        if not audio_chunks:
            Path(wav_path).unlink(missing_ok=True)
            return False

        # Write WAV file from chunks
        first_chunk = audio_chunks[0]
        with wave.open(wav_path, 'wb') as wav_file:
            wav_file.setnchannels(first_chunk.sample_channels)
            wav_file.setsampwidth(first_chunk.sample_width)
            wav_file.setframerate(first_chunk.sample_rate)
            for chunk in audio_chunks:
                wav_file.writeframes(chunk.audio_int16_bytes)

        # Check if we've been cancelled after generating
        if speech_id != _speech_id:
            Path(wav_path).unlink(missing_ok=True)
            return False

        # Play the audio
        sound = pygame.mixer.Sound(wav_path)
        channel = sound.play()
        _current_channel = channel

        # Wait for playback to finish (non-blocking check loop)
        if channel:
            while channel.get_busy():
                # Check for cancellation during playback
                if speech_id != _speech_id:
                    try:
                        channel.stop()
                    except Exception:
                        pass
                    break
                pygame.time.wait(50)

        # Clean up
        _current_channel = None
        if wav_path:
            Path(wav_path).unlink(missing_ok=True)
        return True

    except Exception:
        if wav_path:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass
        return False


def _play_clip(clip_path: Path, speech_id: int) -> bool:
    """Play a pre-generated voice clip."""
    global _current_channel, _speech_id

    try:
        if speech_id != _speech_id:
            return False

        sound = pygame.mixer.Sound(str(clip_path))
        channel = sound.play()
        _current_channel = channel

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
