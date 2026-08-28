"""sound_check: the chord is measurable through a noisy, DC-offset mic path,
clipping is caught, and run() walks the mic-gain ladder and restores state."""

import array
import math
import random

import pytest

from purple_tui import sound_check
from purple_tui.audio import FULL_SCALE

RATE = sound_check.RECORD_RATE


def _recording(gain_db: float, noise: int = 30, dc: int = 3000, lead: float = 0.9) -> bytes:
    rng = random.Random(1)
    chime = sound_check.render_chime(RATE)
    gain = 10 ** (gain_db / 20)
    out = array.array("h")
    for i in range(int(RATE * lead) + len(chime) + int(RATE * 0.3)):
        c = chime[i - int(RATE * lead)] if 0 <= i - int(RATE * lead) < len(chime) else 0
        out.append(max(-FULL_SCALE, min(FULL_SCALE, int(c * gain) + dc + rng.randint(-noise, noise))))
    return out.tobytes()


def test_chime_peaks_under_the_ceiling_with_a_silent_lead_in():
    chime = sound_check.render_chime()
    assert -5 < 20 * math.log10(max(map(abs, chime)) / FULL_SCALE) < -2
    assert not any(chime[: int(sound_check.CHIME_RATE * 0.4)])


def test_analyze_recovers_loop_gain_through_noise_and_dc_offset():
    r = sound_check.analyze(_recording(-20))
    assert r.heard and r.clean
    assert r.loop_gain_db == pytest.approx(-20, abs=1)
    assert r.floor_db < -50  # DC offset must not read as noise
    assert r.snr_db > 30
    assert "loop gain -20 dB" in r.summary()


def test_analyze_flags_clipping():
    r = sound_check.analyze(_recording(+12))
    assert r.heard and not r.clean
    assert r.summary().endswith("CLIP")


def test_analyze_needs_a_real_recording():
    assert sound_check.analyze(b"").note == "mic not delivering"
    quiet = sound_check.analyze(_recording(-95))
    assert not quiet.heard and "NOT HEARD" in quiet.summary()


def test_run_steps_the_mic_gain_down_until_clean_and_restores_state(monkeypatch):
    calls = []
    outputs = {
        "get-default-sink": "spk\n", "get-default-source": "mic\n",
        "get-sink-volume": "Volume: mono: 52428 / 80% / -5.81 dB\n", "get-sink-mute": "Mute: no\n",
        "get-source-volume": "Volume: mono: 65536 / 100% / 0.00 dB\n", "get-source-mute": "Mute: yes\n",
    }

    def fake_pactl(*args):
        calls.append(args)
        return outputs.get(args[0], "")

    source_pct = lambda: next(int(a[2].rstrip("%")) for a in reversed(calls) if a[0] == "set-source-volume")
    monkeypatch.setattr(sound_check, "_pactl", fake_pactl)
    monkeypatch.setattr(sound_check, "_capture", lambda sink, source, wav: _recording(+12 if source_pct() == 100 else -20))
    details = []
    r = sound_check.run(log=details.append)
    assert r.source_pct == 50 and r.clean and len(details) == 2
    assert ("set-sink-volume", "spk", "60%") in calls
    assert calls[-4:] == [("set-sink-volume", "spk", "80%"), ("set-sink-mute", "spk", "0"),
                          ("set-source-volume", "mic", "100%"), ("set-source-mute", "mic", "1")]


def test_run_without_a_microphone(monkeypatch):
    monkeypatch.setattr(sound_check, "_pactl", lambda *a: "spk.monitor\n")
    assert sound_check.run().summary() == "sound check: no microphone"
