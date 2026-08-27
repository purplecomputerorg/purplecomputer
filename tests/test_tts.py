"""TTS unit tests (no audio device required)."""

import os

os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from purple_tui import tts


class TestCache:
    def test_long_text_is_cached(self, tmp_path, monkeypatch):
        # Enter-Enter recall repeats long utterances exactly; they must not
        # re-synthesize every time
        import wave

        monkeypatch.setattr(tts, "_CACHE_DIR", tmp_path)
        wav = tmp_path / "src.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 2205)

        long_text = " ".join(["divided by"] * 24) + " 2"
        assert tts._store_cache(long_text, str(wav)) is not None
        assert tts._get_cached(long_text) is not None


class TestVoiceClipLookup:
    def test_short_text(self):
        # Just must not raise; clip may or may not exist locally
        tts._get_voice_clip("hello")

    def test_long_text_returns_none(self):
        # A long utterance builds a filename over the 255-byte filesystem cap;
        # Path.exists() raises ENAMETOOLONG, which used to kill the speech
        # thread silently (say + long keymash inputs never spoke)
        long_text = " ".join(["divided by"] * 24) + " 2"
        assert tts._get_voice_clip(long_text) is None


def test_preload_loads_once_and_warms(monkeypatch, tmp_path):
    """One model load, one throwaway synthesis, nothing left on disk, timing logged."""
    import threading
    loads, synths, logged = [], [], []

    class _Voice:
        pass

    monkeypatch.setattr(tts, "_piper_voice", None)
    monkeypatch.setattr(tts, "_piper_available", None)
    monkeypatch.setattr(tts, "load_voice", lambda: loads.append(1) or _Voice())
    monkeypatch.setattr(tts, "synthesize_to_file", lambda voice, text, path: synths.append(path) or True)
    from purple_tui import audio
    monkeypatch.setattr(audio, "_log", logged.append)

    tts.preload()
    for t in threading.enumerate():
        if t.name == "piper-preload":
            t.join(timeout=5)
    assert loads == [1] and len(synths) == 1
    assert not os.path.exists(synths[0])
    assert tts._get_piper_voice() is not None and loads == [1]
    assert any(line.startswith("piper preload: model") for line in logged)
