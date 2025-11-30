"""
Text-to-Speech module using Piper TTS

Piper is a fast, local, neural TTS system.
https://github.com/OHF-Voice/piper1-gpl
"""

import subprocess
import tempfile
from pathlib import Path
import os

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame.mixer


# Piper configuration
PIPER_PATH = "/opt/piper/piper"
VOICE_MODEL = "/opt/piper/en_US-lessac-medium.onnx"

# Fallback paths for development/testing
DEV_PIPER_PATHS = [
    Path.home() / ".local" / "bin" / "piper",
    Path("/usr/local/bin/piper"),
    Path("/usr/bin/piper"),
]


def _find_piper() -> str | None:
    """Find the Piper executable"""
    # Check production path first
    if Path(PIPER_PATH).exists():
        return PIPER_PATH

    # Check development paths
    for path in DEV_PIPER_PATHS:
        if path.exists():
            return str(path)

    return None


def _find_voice() -> str | None:
    """Find the voice model"""
    if Path(VOICE_MODEL).exists():
        return VOICE_MODEL

    # Check common locations
    voice_locations = [
        Path.home() / ".local" / "share" / "piper" / "en_US-lessac-medium.onnx",
        Path("/usr/share/piper/voices/en_US-lessac-medium.onnx"),
    ]

    for path in voice_locations:
        if path.exists():
            return str(path)

    return None


def speak(text: str) -> bool:
    """
    Speak the given text using Piper TTS.

    Args:
        text: The text to speak

    Returns:
        True if speech was successful, False otherwise
    """
    if not text or not text.strip():
        return False

    piper_path = _find_piper()
    voice_path = _find_voice()

    if not piper_path:
        # Fall back to espeak-ng if Piper not available
        return _speak_espeak(text)

    if not voice_path:
        return _speak_espeak(text)

    try:
        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        # Run Piper to generate audio
        process = subprocess.run(
            [piper_path, '--model', voice_path, '--output_file', wav_path],
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=10,
        )

        if process.returncode != 0:
            Path(wav_path).unlink(missing_ok=True)
            return _speak_espeak(text)

        # Play the audio
        _play_audio(wav_path)

        # Clean up
        Path(wav_path).unlink(missing_ok=True)
        return True

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return _speak_espeak(text)


def _speak_espeak(text: str) -> bool:
    """Fallback to espeak-ng for TTS"""
    try:
        subprocess.run(
            ['espeak-ng', '-s', '140', text],
            capture_output=True,
            timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


_mixer_initialized = False


def _ensure_mixer() -> bool:
    """Initialize pygame mixer if needed"""
    global _mixer_initialized
    if _mixer_initialized:
        return True
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        _mixer_initialized = True
        return True
    except pygame.error:
        return False


def _play_audio(wav_path: str) -> None:
    """Play a WAV file using pygame mixer"""
    if not _ensure_mixer():
        return

    try:
        sound = pygame.mixer.Sound(wav_path)
        sound.play()
    except pygame.error:
        pass


def is_available() -> bool:
    """Check if TTS is available"""
    return _find_piper() is not None or _check_espeak()


def _check_espeak() -> bool:
    """Check if espeak-ng is available"""
    try:
        subprocess.run(
            ['espeak-ng', '--version'],
            capture_output=True,
            timeout=2,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
