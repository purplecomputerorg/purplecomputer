"""Audio helpers: resilient playback, system volume, and the volume badge.

All sound playback in Purple goes through `play_safe`, which retries once
after a mixer reinit if the first attempt raises. This catches the
"Pulse server restarted / SDL stream went stale" case that otherwise
leaves sound silently broken until Purple is restarted.

System volume goes through `set_system_volume`: pactl when present (percent
maps onto perceived loudness and follows the default sink across hotplug),
`amixer -M` otherwise. Design and history: docs/PLAN-audio-volume.md.
"""

from __future__ import annotations

import array
import functools
import math
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

from .constants import VOLUME_ICONS, VOLUME_LEVELS

_last_play = 0.0
_volume_lock = threading.Lock()
_latest_level = 0
VOLUME_TOP = len(VOLUME_LEVELS) - 1
FULL_SCALE = 32767


def _log(line: str) -> None:
    from . import boot_log  # arms the boot watchdog on import; keep it out of scripts and tests
    boot_log.heartbeat(line)


@functools.cache
def volume_backend() -> str:
    backend = "pactl" if shutil.which("pactl") else "amixer"
    _log(f"volume backend: {backend}")
    return backend


def system_volume_argv(level: int) -> list[list[str]]:
    """Commands that set the system volume to `level` (0-100), muting at 0."""
    if volume_backend() == "pactl":
        return [
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0" if level else "1"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
        ]
    return [["amixer", "-M", "sset", "Master", f"{level}%", "unmute" if level else "mute"]]


def _run_volume_commands(level: int) -> None:
    with _volume_lock:
        if level != _latest_level:
            return  # a newer request is queued behind us
        for argv in system_volume_argv(level):
            try:
                rc = subprocess.run(
                    argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                ).returncode
            except Exception as e:
                rc = type(e).__name__
            if rc != 0:
                _log(f"volume: {' '.join(argv)} -> {rc}")


def set_system_volume(level: int, wait: bool = False) -> None:
    """Push `level` to the mixer off the UI thread: a blocking call here once froze the volume keys."""
    global _latest_level
    _latest_level = level
    worker = threading.Thread(target=_run_volume_commands, args=(level,), daemon=True)
    worker.start()
    if wait:
        worker.join(timeout=3)


def volume_step(level: int) -> int:
    return min(range(len(VOLUME_LEVELS)), key=lambda i: abs(VOLUME_LEVELS[i] - level))


def snap_volume(level: int) -> int:
    """Nearest step: settings saved under an older step table can sit between steps."""
    return VOLUME_LEVELS[volume_step(level)]


def adjacent_volume(level: int, up: bool) -> int:
    step = volume_step(level) + (1 if up else -1)
    return VOLUME_LEVELS[max(0, min(step, len(VOLUME_LEVELS) - 1))]


def effective_volume(level: int, ceiling: Optional[int]) -> int:
    """What playback gets: the kid's level, held under the parent's ceiling when one is set."""
    return level if ceiling is None else min(level, ceiling)


def volume_badge(level: int, ceiling: Optional[int] = None) -> tuple[str, str, str]:
    """(icon, bars, label) for an effective 0-100 level: one bar per step, labelled
    by its number. At the parent's ceiling the label reads Max 5; a ceiling of 0 is Silent Mode."""
    step = volume_step(level)
    label = "Sound Off" if step == 0 else str(step)
    if ceiling is not None and level >= ceiling:
        label = "Silent Mode" if ceiling == 0 else f"Max {label}"
    return VOLUME_ICONS[step], "█" * step + "░" * (VOLUME_TOP - step), label


def lock_badge(ceiling: int) -> tuple[str, str, str]:
    return volume_badge(ceiling, ceiling)


def db_to_linear(db: float) -> float:
    return FULL_SCALE * 10 ** (db / 20)


def normalize_loudness(samples: array.array, target_rms_db: float, ceiling_db: float) -> array.array:
    """Scale 16-bit samples so RMS lands on target_rms_db unless the peak would
    pass ceiling_db (both dBFS, ceiling at most 0). Speech has a low crest
    factor so the RMS target binds; percussive material hits the ceiling first."""
    peak = max(map(abs, samples), default=0)
    if not peak:
        return samples
    rms = math.sqrt(math.sumprod(samples, samples) / len(samples))
    gain = min(db_to_linear(target_rms_db) / rms, db_to_linear(ceiling_db) / peak)
    return array.array('h', (int(s * gain) for s in samples))


def seconds_since_last_play() -> float:
    """Seconds since the last play_safe call (any outcome). Used by the
    mixer idle-release to decide when the stream has gone quiet."""
    return time.monotonic() - _last_play


def play_safe(sound: Any, *args: Any, **kwargs: Any) -> Optional[Any]:
    """Play a pygame Sound, retrying once after a mixer reinit on failure.

    Returns the Channel from Sound.play() on success, or None if both the
    first play and the post-reinit retry failed. Callers that care about
    the Channel (tts.py tracks it to stop playback later) should handle
    None by treating it as "no channel, nothing to stop".

    The retry path calls reinit_mixer() (the lightweight VM-reconnect
    variant) rather than the full hotplug re-probe, because a stale
    connection only needs quit+init, not a fresh subprocess probe.
    """
    from .rooms.music_room import should_attempt_play
    if not should_attempt_play():
        return None
    global _last_play
    _last_play = time.monotonic()
    try:
        return sound.play(*args, **kwargs)
    except Exception as e:
        from .tts import _dbg
        _dbg(f"play_safe: play raised {type(e).__name__}: {e}, reiniting")
    try:
        from .rooms.music_room import reinit_mixer
        reinit_mixer()
    except Exception:
        return None
    try:
        return sound.play(*args, **kwargs)
    except Exception as e:
        from .tts import _dbg
        _dbg(f"play_safe: retry after reinit also raised {type(e).__name__}: {e}")
        return None
