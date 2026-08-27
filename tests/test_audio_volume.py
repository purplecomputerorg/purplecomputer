"""System volume path (purple_tui/audio.py): backend selection, the commands
it issues, and the badge tables it derives from VOLUME_LEVELS."""

import pytest

from purple_tui import audio
from purple_tui.constants import VOLUME_ICONS, VOLUME_LABELS, VOLUME_LEVELS


@pytest.fixture
def backend(monkeypatch):
    def _set(present: bool):
        monkeypatch.setattr(audio, "_backend", None)
        monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/pactl" if present else None)
    return _set


def test_pactl_preferred_when_present(backend):
    backend(True)
    cmds = audio.system_volume_argv(80)
    assert cmds == [
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "80%"],
    ]


def test_amixer_fallback_uses_db_mapping(backend):
    backend(False)
    assert audio.system_volume_argv(40) == [["amixer", "-M", "sset", "Master", "40%", "unmute"]]


@pytest.mark.parametrize("present", [True, False])
def test_zero_mutes(backend, present):
    backend(present)
    flat = sum(audio.system_volume_argv(0), [])
    assert "mute" in flat or "1" in flat
    assert "unmute" not in flat


def test_set_system_volume_runs_commands_and_logs_failures(backend, monkeypatch):
    backend(True)
    ran, logged = [], []

    class _Proc:
        def __init__(self, rc):
            self.returncode = rc

    monkeypatch.setattr(audio.subprocess, "run", lambda argv, **kw: ran.append(argv) or _Proc(len(ran) - 1))
    monkeypatch.setattr(audio.boot_log, "heartbeat", logged.append)
    audio.set_system_volume(60, wait=True)
    assert ran == audio.system_volume_argv(60)
    failures = [line for line in logged if line.startswith("volume:")]
    assert len(failures) == 1 and "set-sink-volume" in failures[0] and "-> 1" in failures[0]


def test_step_tables_are_parallel():
    assert len(VOLUME_LEVELS) == len(VOLUME_LABELS) == len(VOLUME_ICONS)
    assert VOLUME_LEVELS[0] == 0 and VOLUME_LEVELS[-1] == 100


def test_every_step_has_a_distinct_badge():
    badges = [audio.volume_badge(v) for v in VOLUME_LEVELS]
    assert len({b[2] for b in badges}) == len(VOLUME_LEVELS)
    assert len({b[1] for b in badges}) == len(VOLUME_LEVELS)
    assert all(len(b[1]) == audio.BADGE_CELLS for b in badges)
    assert badges[0] == (VOLUME_ICONS[0], "░" * audio.BADGE_CELLS, "Sound Off")
    assert badges[-1][1] == "█" * audio.BADGE_CELLS


@pytest.mark.parametrize("legacy,label", [(15, "Whisper"), (35, "Quiet"), (85, "Loud")])
def test_levels_saved_under_old_steps_snap_to_nearest(legacy, label):
    assert audio.volume_badge(legacy)[2] == label


def test_adjacent_volume_walks_steps_and_clamps():
    assert audio.adjacent_volume(0, up=False) == 0
    assert audio.adjacent_volume(100, up=True) == 100
    assert audio.adjacent_volume(60, up=True) == 80
    assert audio.adjacent_volume(60, up=False) == 40
    assert audio.adjacent_volume(85, up=False) == 60
