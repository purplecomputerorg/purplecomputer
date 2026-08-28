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
