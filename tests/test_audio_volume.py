"""System volume path (purplecomputer/audio.py): backend selection, the commands
it issues, and the badge tables derived from VOLUME_LEVELS."""

import array
import math

import pytest

from purplecomputer import audio
from purplecomputer.constants import VOLUME_ICONS, VOLUME_LEVELS


@pytest.fixture
def backend(monkeypatch):
    def _set(present: bool):
        audio.volume_backend.cache_clear()
        monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/pactl" if present else None)
    yield _set
    audio.volume_backend.cache_clear()


def test_pactl_preferred_when_present(backend):
    backend(True)
    assert audio.system_volume_argv(80) == [
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "80%"],
    ]
    assert audio.system_volume_argv(0) == [
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"],
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "0%"],
    ]


def test_amixer_fallback_uses_db_mapping_and_mutes_at_zero(backend):
    backend(False)
    assert audio.system_volume_argv(40) == [["amixer", "-M", "sset", "Master", "40%", "unmute"]]
    assert audio.system_volume_argv(0) == [["amixer", "-M", "sset", "Master", "0%", "mute"]]


def test_set_system_volume_runs_commands_and_logs_failures(backend, monkeypatch):
    backend(True)
    ran, logged = [], []

    class _Proc:
        def __init__(self, rc):
            self.returncode = rc

    monkeypatch.setattr(audio.subprocess, "run", lambda argv, **kw: ran.append(argv) or _Proc(len(ran) - 1))
    monkeypatch.setattr(audio, "_log", logged.append)
    audio.set_system_volume(60, wait=True)
    assert ran == audio.system_volume_argv(60)
    failures = [line for line in logged if line.startswith("volume:")]
    assert len(failures) == 1 and "set-sink-volume" in failures[0] and "-> 1" in failures[0]


def test_step_tables_and_badges():
    assert len(VOLUME_LEVELS) == len(VOLUME_ICONS) == 11
    assert VOLUME_LEVELS == sorted(VOLUME_LEVELS)
    badges = [audio.volume_badge(v) for v in VOLUME_LEVELS]
    assert badges[0] == (VOLUME_ICONS[0], "░" * 10, "Sound Off")
    assert badges[1] == (VOLUME_ICONS[1], "█" + "░" * 9, "1")
    assert badges[-1] == (VOLUME_ICONS[-1], "█" * 10, "10")


def test_badge_under_a_ceiling():
    assert audio.volume_badge(23, 43)[2] == "3"
    assert audio.volume_badge(43, 43)[2] == "Max 6"
    assert audio.lock_badge(0)[2] == "Silent Mode"
    assert audio.lock_badge(53) == (*audio.volume_badge(53)[:2], "Max 7")


def test_ceiling_holds_the_kid_level_down_but_never_up():
    assert audio.effective_volume(81, None) == 81
    assert audio.effective_volume(81, 43) == 43
    assert audio.effective_volume(23, 43) == 23
    assert audio.effective_volume(81, 0) == 0


@pytest.mark.parametrize("legacy,snapped", [(10, 15), (26, 28), (58, 53), (76, 81), (85, 81)])
def test_levels_saved_under_old_steps_snap_to_nearest(legacy, snapped):
    assert audio.snap_volume(legacy) == snapped


def test_adjacent_volume_walks_steps_and_clamps():
    assert audio.adjacent_volume(0, up=False) == 0
    assert audio.adjacent_volume(15, up=False) == 0
    assert audio.adjacent_volume(100, up=True) == 100
    assert audio.adjacent_volume(53, up=True) == 66
    assert audio.adjacent_volume(53, up=False) == 43


def _stats(samples):
    db = lambda x: 20 * math.log10(x / audio.FULL_SCALE)  # noqa: E731
    return db(math.sqrt(sum(s * s for s in samples) / len(samples))), db(max(abs(s) for s in samples))


def test_normalize_loudness_hits_rms_target_when_peak_allows():
    tone = array.array('h', (int(8000 * math.sin(i / 7)) for i in range(4000)))
    rms, peak = _stats(audio.normalize_loudness(tone, target_rms_db=-12.0, ceiling_db=-1.0))
    assert abs(rms - (-12.0)) < 0.05
    assert peak < -1.0


def test_normalize_loudness_backs_off_to_ceiling_for_spiky_material():
    spiky = array.array('h', [30] * 4000)
    spiky[100] = 3000
    rms, peak = _stats(audio.normalize_loudness(spiky, target_rms_db=-12.0, ceiling_db=-1.0))
    assert abs(peak - (-1.0)) < 0.05
    assert rms < -12.0


def test_normalize_loudness_leaves_silence_alone():
    silence = array.array('h', [0] * 100)
    assert audio.normalize_loudness(silence, -12.0, -1.0) == silence
