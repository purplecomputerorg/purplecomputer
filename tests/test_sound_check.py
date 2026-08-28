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


def _heard(loop_gain_db: float, **fields) -> sound_check.SoundCheck:
    sent = sound_check._sent_tone_db()
    return sound_check.SoundCheck(heard=True, floor_db=-60, tone_db=tuple(t + loop_gain_db for t in sent), **fields)


def test_loop_gain_is_referenced_to_the_mic_base_volume():
    analog = _heard(-20, sink_db=-14.0, source_db=-42.0, source_base_db=-66.0)
    digital = _heard(-20, sink_db=-14.0, source_db=-42.0, source_base_db=-20.0)
    assert analog.loop_gain_db == pytest.approx(-20 + 14 + 42 - 66, abs=0.01)
    assert digital.loop_gain_db - analog.loop_gain_db == pytest.approx(46, abs=0.01)
    assert "mic base -66 dB" in analog.summary()


def test_default_volume_only_ever_turns_a_loud_machine_down():
    hp15, surface, stream, air = 7, -11, -34, -35  # measured; the Air is louder than the Stream by ear
    assert sound_check.default_volume(_heard(hp15)) == 28  # volume 4
    assert sound_check.default_volume(_heard(hp15, clipped=99)) == 28  # a lower bound still says loud
    assert sound_check.default_volume(_heard(40)) == 28
    for quiet in (surface, stream, air, -60):
        assert sound_check.default_volume(_heard(quiet)) is None
    hot_and_clipped = sound_check.analyze(_recording(+12))
    assert not hot_and_clipped.clean and sound_check.default_volume(hot_and_clipped) == 28


def test_default_volume_when_nothing_was_heard():
    not_heard = sound_check.analyze(_recording(-95))
    assert not not_heard.heard and sound_check.default_volume(not_heard) is None
    assert sound_check.default_volume(sound_check.SoundCheck(note="no microphone")) is None


@pytest.fixture
def pulse(monkeypatch):
    """Fake pactl with a working sink and mic; records every call."""
    calls = []
    outputs = {
        "get-default-sink": "spk\n", "get-default-source": "mic\n",
        "get-sink-volume": "Volume: mono: 52428 / 80% / -5.81 dB\n", "get-sink-mute": "Mute: no\n",
        "get-source-volume": "Volume: mono: 65536 / 100% / 0.00 dB\n", "get-source-mute": "Mute: no\n",
        "list": ("Source #0\n\tName: spk.monitor\n\tBase Volume: 65536 / 100% / 0.00 dB\n"
                 "Source #1\n\tName: mic\n\tVolume: mono: 65536 / 100% / 0.00 dB\n\tBase Volume: 6554 / 10% / -60.00 dB\n"),
    }

    def fake_pactl(*args):
        calls.append(args)
        return outputs.get(args[0], "")

    monkeypatch.setattr(sound_check, "_pactl", fake_pactl)
    monkeypatch.setattr(sound_check.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    return calls, outputs


def _source_pct(calls):
    return next(int(a[2].rstrip("%")) for a in reversed(calls) if a[0] == "set-source-volume")


def test_run_plays_once_by_default_and_restores_state(pulse, monkeypatch):
    calls, _ = pulse
    monkeypatch.setattr(sound_check, "_capture", lambda sink, source, wav: _recording(+12))
    details = []
    r = sound_check.run(log=details.append)
    assert r.source_pct == sound_check.SOURCE_PCT and r.source_base_db == -60.0 and not r.clean and len(details) == 1
    assert ("set-sink-volume", "spk", f"{sound_check.SINK_PCT}%") in calls
    assert calls[-4:] == [("set-sink-volume", "spk", "80%"), ("set-sink-mute", "spk", "0"),
                          ("set-source-volume", "mic", "100%"), ("set-source-mute", "mic", "0")]


def test_probe_ladder_steps_the_mic_gain_down_until_clean(pulse, monkeypatch):
    calls, _ = pulse
    monkeypatch.setattr(sound_check, "_capture", lambda sink, source, wav: _recording(+12 if _source_pct(calls) == sound_check.SOURCE_PCT else -20))
    details = []
    r = sound_check.run(ladder=sound_check.PROBE_LADDER, log=details.append)
    assert r.source_pct == 12 and r.clean and len(details) == 2
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


def test_run_waits_for_a_card_that_enumerates_late_only_when_asked(pulse, monkeypatch):
    calls, outputs = pulse
    outputs["get-default-sink"] = "\n"
    fake = sound_check._pactl

    def late_card(*args):
        if args[0] == "get-default-sink" and sum(a[0] == "get-default-sink" for a in calls) == 2:
            outputs["get-default-sink"] = "spk\n"
        return fake(*args)

    monkeypatch.setattr(sound_check, "_pactl", late_card)
    monkeypatch.setattr(sound_check, "READY_POLL", 0)
    monkeypatch.setattr(sound_check, "_capture", lambda sink, source, wav: _recording(-20))
    assert sound_check.run().note == "no speaker"
    r = sound_check.run(wait=1.0)
    assert r.heard and r.clean and r.source_pct == sound_check.SOURCE_PCT


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
