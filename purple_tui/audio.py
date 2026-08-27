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
import math
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

from . import boot_log
from .constants import VOLUME_ICONS, VOLUME_LABELS, VOLUME_LEVELS

_last_play = 0.0
_backend: Optional[str] = None
_volume_lock = threading.Lock()
_latest_level = 0
BADGE_CELLS = 10
_FULL_SCALE = 32767


def volume_backend() -> str:
    global _backend
    if _backend is None:
        _backend = "pactl" if shutil.which("pactl") else "amixer"
        boot_log.heartbeat(f"volume backend: {_backend}")
    return _backend


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
                rc: Any = subprocess.run(
                    argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                ).returncode
            except Exception as e:
                rc = type(e).__name__
            if rc != 0:
                boot_log.heartbeat(f"volume: {' '.join(argv)} -> {rc}")


def set_system_volume(level: int, wait: bool = False) -> None:
    """Push `level` to the system mixer off the UI thread (a blocking call here
    once froze the volume keys). `wait` is for the parent menu's test tone."""
    global _latest_level
    _latest_level = level
    worker = threading.Thread(target=_run_volume_commands, args=(level,), daemon=True)
    worker.start()
    if wait:
        worker.join(timeout=3)


def volume_step(level: int) -> int:
    """Index of the VOLUME_LEVELS step nearest `level` (saved levels may predate the current steps)."""
    return min(range(len(VOLUME_LEVELS)), key=lambda i: abs(VOLUME_LEVELS[i] - level))


def adjacent_volume(level: int, up: bool) -> int:
    step = volume_step(level) + (1 if up else -1)
    return VOLUME_LEVELS[max(0, min(step, len(VOLUME_LEVELS) - 1))]


def volume_badge(level: int) -> tuple[str, str, str]:
    """(icon, bars, label) for a 0-100 level, derived from the step tables."""
    step = volume_step(level)
    filled = step * BADGE_CELLS // (len(VOLUME_LEVELS) - 1)
    return VOLUME_ICONS[step], "█" * filled + "░" * (BADGE_CELLS - filled), VOLUME_LABELS[step]


def normalize_loudness(samples: array.array, target_rms_db: float, ceiling_db: float) -> array.array:
    """Scale 16-bit samples so RMS lands on target_rms_db unless the peak would
    pass ceiling_db (both dBFS). Speech has a low crest factor so the RMS target
    binds; percussive material hits the ceiling first."""
    peak = max((abs(s) for s in samples), default=0)
    if not peak:
        return samples
    rms = math.sqrt(math.sumprod(samples, samples) / len(samples))
    gain = min(_FULL_SCALE * 10 ** (target_rms_db / 20) / rms,
               _FULL_SCALE * 10 ** (ceiling_db / 20) / peak)
    return array.array('h', (max(-32768, min(32767, int(s * gain))) for s in samples))


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
