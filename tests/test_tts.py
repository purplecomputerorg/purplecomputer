"""TTS unit tests (no audio device required)."""

import os

import pytest

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
        assert tts._store_cache(long_text, str(wav), tts.VOICE_NATURAL) is not None
        assert tts._get_cached(long_text, tts.VOICE_NATURAL) is not None
        assert tts._get_cached(long_text, tts.VOICE_QUICK) is None  # the two voices never share clips


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


def _write_tone(wav_path, seconds=0.2, rate=16000):
    import math
    import wave
    frames = b"".join(int(8000 * math.sin(i / 10)).to_bytes(2, "little", signed=True) for i in range(int(rate * seconds)))
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


class TestQuickVoice:
    @pytest.fixture
    def flite(self, tmp_path, monkeypatch):
        """A pretend flite on PATH whose voice file exists; records each command line."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            _write_tone(cmd[cmd.index("-o") + 1])
        monkeypatch.setattr(tts, "_CACHE_DIR", tmp_path)
        monkeypatch.setattr(tts, "find_flite_voice", lambda: tmp_path / "cmu_us_lnh.flitevox")
        monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/flite")
        monkeypatch.setattr(tts.subprocess, "run", fake_run)
        monkeypatch.setattr(tts, "_worker_stderr", lambda: None)
        return calls

    def test_quick_preference_skips_piper(self, flite, monkeypatch):
        monkeypatch.setattr(tts, "_voice_pref", tts.VOICE_QUICK)
        monkeypatch.setattr(tts, "_preload_started", False)
        monkeypatch.setattr(tts, "_worker_synthesize", lambda *a: pytest.fail("Piper must not run"))
        assert tts._engine() == tts.VOICE_QUICK
        assert tts.preload() is None  # no worker process, no model load at boot
        path = tts._synthesize_to_cache("apple.", tts.VOICE_QUICK)
        assert path == tts._cache_path("apple.", tts.VOICE_QUICK) and path.exists()
        cmd = flite[0]
        assert cmd[0] == "flite" and cmd[cmd.index("--setf") + 1] == "duration_stretch=1.15"
        assert cmd[cmd.index("-t") + 1] == "apple."

    def test_natural_without_piper_falls_through_to_flite(self, flite, monkeypatch):
        monkeypatch.setattr(tts, "_voice_pref", tts.VOICE_NATURAL)
        monkeypatch.setattr(tts, "_synthesize_piper", lambda text, path: False)
        path = tts._synthesize_to_cache("apple.", tts.VOICE_NATURAL)
        assert path == tts._cache_path("apple.", tts.VOICE_QUICK)
        assert len(flite) == 1

    def test_missing_piper_model_means_quick(self, monkeypatch):
        monkeypatch.setattr(tts, "_voice_pref", tts.VOICE_NATURAL)
        monkeypatch.setattr(tts, "find_voice_model", lambda: None)
        assert tts._engine() == tts.VOICE_QUICK

    def test_set_voice_persists_and_updates_engine(self, monkeypatch, tmp_path):
        from purple_tui import settings
        monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
        monkeypatch.setattr(tts, "_voice_pref", None)
        monkeypatch.setattr(tts, "preload", lambda: None)
        tts.set_voice(tts.VOICE_QUICK)
        assert settings.get_voice() == tts.VOICE_QUICK and tts.voice_preference() == tts.VOICE_QUICK


def _fake_voice(synths):

    class _Voice:
        def synthesize(self, text, config):
            synths.append(text)
            return iter(())
    return _Voice()


def test_worker_process_serves_requests(monkeypatch):
    import io
    from purple_tui import tts_worker
    synths, written = [], []
    monkeypatch.setattr(tts, "load_voice", lambda: _fake_voice(synths))
    monkeypatch.setattr(tts, "_make_synth_config", lambda: None)
    monkeypatch.setattr(tts, "synthesize_to_file", lambda voice, text, path: written.append((text, path)) or True)
    replies = io.StringIO()
    tts_worker.serve(io.StringIO("/tmp/a.wav\tapple.\n/tmp/b.wav\tbanana.\n"), replies)
    assert replies.getvalue() == "ready\nok\nok\n"
    assert synths == ["purple."] and written == [("apple.", "/tmp/a.wav"), ("banana.", "/tmp/b.wav")]


def test_preload_talks_to_the_worker_and_falls_back_when_it_dies(monkeypatch):
    r_req, w_req = os.pipe()
    r_rep, w_rep = os.pipe()

    class _Proc:
        stdin = os.fdopen(w_req, "w")
        stdout = os.fdopen(r_rep, "r")

    monkeypatch.setattr(tts.subprocess, "Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr(tts, "find_voice_model", lambda: "model.onnx")
    monkeypatch.setattr(tts, "_worker_stderr", lambda: None)
    monkeypatch.setattr(tts, "_preload_started", False)
    monkeypatch.setattr(tts, "_worker", None)
    tts._worker_ready.clear()
    from purple_tui import audio
    logged = []
    monkeypatch.setattr(audio, "_log", logged.append)

    os.write(w_rep, b"ready\n")
    tts.preload().join(timeout=5)
    assert tts._worker_ready.is_set() and any("ready in" in line for line in logged)
    assert tts.preload() is None  # once per session

    os.write(w_rep, b"ok\n")
    assert tts._worker_synthesize("apple.", "/tmp/x.wav") is True
    assert os.read(r_req, 100) == b"/tmp/x.wav\tapple.\n"

    os.close(w_rep)  # the worker died
    assert tts._worker_synthesize("banana.", "/tmp/y.wav") is None
    assert tts._worker is None
    os.close(r_req)
