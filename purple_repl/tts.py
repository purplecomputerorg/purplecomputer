"""
Purple Computer Text-to-Speech Wrapper
Provides a simple interface for speaking text aloud
"""

import os
import sys
import subprocess
from pathlib import Path


class TTSEngine:
    """Base class for TTS engines"""

    def speak(self, text, wait=True):
        """Speak the given text"""
        raise NotImplementedError

    def set_voice(self, voice):
        """Set the voice to use"""
        pass

    def set_rate(self, rate):
        """Set speech rate (words per minute)"""
        pass

    def stop(self):
        """Stop current speech"""
        pass


class PiperTTS(TTSEngine):
    """
    Piper TTS engine - high quality offline synthesis
    https://github.com/rhasspy/piper
    """

    def __init__(self):
        self.piper_path = self._find_piper()
        self.model_path = None
        self.rate = 1.0

        if self.piper_path:
            self._find_model()

    def _find_piper(self):
        """Find piper executable"""
        piper = subprocess.run(['which', 'piper'], capture_output=True, text=True)
        if piper.returncode == 0:
            return piper.stdout.strip()
        return None

    def _find_model(self):
        """Find a piper model to use"""
        # Common model locations
        model_dirs = [
            Path.home() / '.local/share/piper/models',
            Path('/usr/share/piper/models'),
            Path('/usr/local/share/piper/models'),
        ]

        for model_dir in model_dirs:
            if model_dir.exists():
                models = list(model_dir.glob('*.onnx'))
                if models:
                    self.model_path = str(models[0])
                    return

    def speak(self, text, wait=True):
        """Speak text using Piper"""
        if not self.piper_path or not self.model_path:
            return False

        try:
            # Piper reads from stdin and outputs audio
            cmd = [
                self.piper_path,
                '--model', self.model_path,
                '--output-raw'
            ]

            # Pipe to aplay for audio output
            piper = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )

            aplay = subprocess.Popen(
                ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
                stdin=piper.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            piper.stdin.write(text.encode())
            piper.stdin.close()

            if wait:
                aplay.wait()

            return True

        except Exception as e:
            return False


class EspeakTTS(TTSEngine):
    """
    Espeak-ng TTS engine - lightweight fallback
    """

    def __init__(self):
        self.espeak_path = self._find_espeak()
        self.voice = 'en'
        self.rate = 150

    def _find_espeak(self):
        """Find espeak-ng executable"""
        for cmd in ['espeak-ng', 'espeak']:
            result = subprocess.run(['which', cmd], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        return None

    def speak(self, text, wait=True):
        """Speak text using espeak"""
        if not self.espeak_path:
            return False

        try:
            cmd = [
                self.espeak_path,
                '-v', self.voice,
                '-s', str(self.rate),
                text
            ]

            if wait:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return True

        except Exception:
            return False

    def set_voice(self, voice):
        """Set voice (e.g., 'en', 'en-us', 'en-gb')"""
        self.voice = voice

    def set_rate(self, rate):
        """Set speech rate in words per minute"""
        self.rate = max(80, min(400, rate))


class Pyttsx3TTS(TTSEngine):
    """
    Pyttsx3 TTS engine - Python wrapper for system TTS
    """

    def __init__(self):
        self.engine = None
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 0.9)
        except Exception:
            pass

    def speak(self, text, wait=True):
        """Speak text using pyttsx3"""
        if not self.engine:
            return False

        try:
            self.engine.say(text)
            if wait:
                self.engine.runAndWait()
            return True
        except Exception:
            return False

    def set_rate(self, rate):
        """Set speech rate"""
        if self.engine:
            self.engine.setProperty('rate', rate)


# Global TTS engine instance
_tts_engine = None


def _get_engine():
    """Get or create the TTS engine"""
    global _tts_engine

    if _tts_engine is not None:
        return _tts_engine

    # Try engines in order of preference
    # 1. Piper (best quality)
    piper = PiperTTS()
    if piper.piper_path and piper.model_path:
        _tts_engine = piper
        return _tts_engine

    # 2. Espeak (good fallback)
    espeak = EspeakTTS()
    if espeak.espeak_path:
        _tts_engine = espeak
        return _tts_engine

    # 3. Pyttsx3 (last resort)
    pyttsx = Pyttsx3TTS()
    if pyttsx.engine:
        _tts_engine = pyttsx
        return _tts_engine

    # No TTS available
    return None


def speak(text, wait=True):
    """
    Speak the given text aloud

    Args:
        text: Text to speak
        wait: If True, wait for speech to complete
    """
    if not text or not isinstance(text, str):
        return

    engine = _get_engine()
    if engine:
        engine.speak(text, wait)
    else:
        # Silent fallback - print to console
        print(f"🔊 {text}")


def set_voice(voice):
    """Set the TTS voice"""
    engine = _get_engine()
    if engine:
        engine.set_voice(voice)


def set_rate(rate):
    """Set speech rate (words per minute)"""
    engine = _get_engine()
    if engine:
        engine.set_rate(rate)


def is_available():
    """Check if TTS is available"""
    return _get_engine() is not None


# Export public API
__all__ = ['speak', 'set_voice', 'set_rate', 'is_available']
