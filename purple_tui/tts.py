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
VOICE_MODEL = "en_US-lessac-medium"

def _get_voice_search_paths() -> list[Path]:
    """Get list of paths to search for voice model."""
    paths = [
        Path.home() / ".local" / "share" / "piper-voices",
        Path.home() / ".cache" / "piper",
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
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
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


def speak(text: str) -> bool:
    """
    Speak the given text using Piper TTS.
    Runs in a background thread to not block the UI.

    Args:
        text: The text to speak

    Returns:
        True if speech was started, False otherwise
    """
    if not text or not text.strip():
        return False

    # Run TTS in background thread
    thread = threading.Thread(target=_speak_sync, args=(text,), daemon=True)
    thread.start()
    return True


def _speak_sync(text: str) -> bool:
    """Synchronous speech - called from background thread"""
    voice = _get_piper_voice()
    if voice is None:
        print(f"TTS: No voice available")
        return False

    if not _ensure_mixer():
        print(f"TTS: Mixer not available")
        return False

    try:
        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        # Generate audio with Piper (needs wave.Wave_write object)
        with wave.open(wav_path, 'wb') as wav_file:
            voice.synthesize_wav(text, wav_file)

        # Play the audio
        sound = pygame.mixer.Sound(wav_path)
        channel = sound.play()

        # Wait for playback to finish
        if channel:
            while channel.get_busy():
                pygame.time.wait(50)

        # Clean up
        Path(wav_path).unlink(missing_ok=True)
        return True

    except Exception as e:
        print(f"TTS error: {e}")
        return False


def is_available() -> bool:
    """Check if TTS is available"""
    return _get_piper_voice() is not None
