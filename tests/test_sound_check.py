"""sound_check: the marimba chime is measurable through a noisy, DC-offset mic
path wherever the recording starts, clipping is caught, run() walks the mic-gain
ladder, restores state, and never plays or raises when the setup isn't right."""

import array
import math
import random

import pytest

from purple_tui import sound_check
from purple_tui.audio import FULL_SCALE

RATE = sound_check.RECORD_RATE


def _recording(gain_db: float, noise: int = 30, dc: int = 3000, lead: float = 0.93) -> bytes:
    """Chime through a noisy, DC-offset mic path, starting off the analysis window grid."""
    rng = random.Random(1)
    chime = sound_check.render_chime(RATE)
    gain = 10 ** (gain_db / 20)
    out = array.array("h")
    for i in range(int(RATE * lead) + len(chime) + int(RATE * 0.3)):
        c = chime[i - int(RATE * lead)] if 0 <= i - int(RATE * lead) < len(chime) else 0
        out.append(max(-FULL_SCALE, min(FULL_SCALE, int(c * gain) + dc + rng.randint(-noise, noise))))
    return out.tobytes()


def test_chime_is_a_soft_marimba_with_a_silent_lead_in():
    chime = sound_check.render_chime()
    assert 20 * math.log10(max(map(abs, chime)) / FULL_SCALE) == pytest.approx(sound_check.CHIME_PEAK_DB, abs=0.1)
    assert not any(chime[: int(sound_check.CHIME_RATE * 0.3)])
    assert 1.5 < len(chime) / sound_check.CHIME_RATE < 2.5


@pytest.mark.parametrize("lead", [0.9, 0.93, 0.97])
def test_analyze_recovers_loop_gain_wherever_the_recording_starts(lead):
    r = sound_check.analyze(_recording(-20, lead=lead))
    assert r.heard and r.clean
    assert r.loop_gain_db == pytest.approx(-20, abs=0.5)
    assert r.floor_db < -50  # DC offset must not read as noise
    assert "loop gain -20 dB" in r.summary()


def test_analyze_flags_clipping():
    r = sound_check.analyze(_recording(+12))
    assert r.heard and not r.clean
    assert r.summary().endswith("CLIP")


def test_analyze_needs_a_real_recording():
    assert sound_check.analyze(b"").note == "mic not delivering"
    quiet = sound_check.analyze(_recording(-95))
    assert not quiet.heard and "NOT HEARD" in quiet.summary()


def test_default_volume_only_caps_machines_heard_hot():
    loud, fine = sound_check.LOUD_LOOP_GAIN_DB + 5, sound_check.LOUD_LOOP_GAIN_DB - 5
    assert sound_check.default_volume(sound_check.analyze(_recording(loud - 30, dc=0))) is None  # clipped, bound too low
    hot = sound_check.SoundCheck(heard=True, tone_db=tuple(s + loud for s in sound_check._sent_tone_db()))
    assert sound_check.default_volume(hot) == sound_check.LOUD_MACHINE_VOLUME
    hot.heard = False
    assert sound_check.default_volume(hot) is None
    ok = sound_check.SoundCheck(heard=True, tone_db=tuple(s + fine for s in sound_check._sent_tone_db()))
    assert sound_check.default_volume(ok) is None


@pytest.fixture
def pulse(monkeypatch):
    """Fake pactl with a working sink and mic; records every call."""
    calls = []
    outputs = {
        "get-default-sink": "spk\n", "get-default-source": "mic\n",
        "get-sink-volume": "Volume: mono: 52428 / 80% / -5.81 dB\n", "get-sink-mute": "Mute: no\n",
        "get-source-volume": "Volume: mono: 65536 / 100% / 0.00 dB\n", "get-source-mute": "Mute: no\n",
    }

    def fake_pactl(*args):
        calls.append(args)
        return outputs.get(args[0], "")

    monkeypatch.setattr(sound_check, "_pactl", fake_pactl)
    monkeypatch.setattr(sound_check.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    return calls, outputs


def _source_pct(calls):
    return next(int(a[2].rstrip("%")) for a in reversed(calls) if a[0] == "set-source-volume")


def test_run_steps_the_mic_gain_down_until_clean_and_restores_state(pulse, monkeypatch):
    calls, _ = pulse
    monkeypatch.setattr(sound_check, "_capture", lambda sink, source, wav: _recording(+12 if _source_pct(calls) == 50 else -20))
    details = []
    r = sound_check.run(log=details.append)
    assert r.source_pct == 12 and r.clean and len(details) == 2
    assert ("set-sink-volume", "spk", "60%") in calls
    assert calls[-4:] == [("set-sink-volume", "spk", "80%"), ("set-sink-mute", "spk", "0"),
                          ("set-source-volume", "mic", "100%"), ("set-source-mute", "mic", "0")]


@pytest.mark.parametrize("change, note", [
    ({"get-default-source": "spk.monitor\n"}, "no microphone"),
    ({"get-default-source": "\n"}, "no microphone"),
    ({"get-default-sink": "auto_null\n"}, "no speaker"),
    ({"get-source-mute": "Mute: yes\n"}, "microphone muted"),
])
def test_run_does_not_play_without_a_working_speaker_and_mic(pulse, monkeypatch, change, note):
    calls, outputs = pulse
    outputs.update(change)
    monkeypatch.setattr(sound_check, "_capture", lambda *a: pytest.fail("must not play"))
    assert sound_check.run().summary() == f"sound check: {note}"
    assert not any(a[0].startswith("set-") for a in calls)


def test_run_without_pulse_tools(pulse, monkeypatch):
    monkeypatch.setattr(sound_check.shutil, "which", lambda tool: None)
    assert sound_check.run().note == "pulse tools missing"


def test_run_never_raises_and_still_restores(pulse, monkeypatch):
    calls, _ = pulse

    def boom(*a):
        raise OSError("parecord died")

    monkeypatch.setattr(sound_check, "_capture", boom)
    r = sound_check.run()
    assert r.note.startswith("failed (OSError") and not r.heard
    assert sound_check.default_volume(r) is None
    assert calls[-1] == ("set-source-mute", "mic", "0")
