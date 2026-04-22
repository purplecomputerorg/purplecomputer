"""Resilient pygame.mixer playback helper.

All sound playback in Purple goes through `play_safe`, which retries once
after a mixer reinit if the first attempt raises. This catches the
"Pulse server restarted / SDL stream went stale" case that otherwise
leaves sound silently broken until Purple is restarted.

Keeps playback sites (music_room, tts) free of try/except boilerplate.
"""

from __future__ import annotations

from typing import Any, Optional


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
    try:
        return sound.play(*args, **kwargs)
    except Exception:
        pass
    try:
        from .rooms.music_room import reinit_mixer
        reinit_mixer()
    except Exception:
        return None
    try:
        return sound.play(*args, **kwargs)
    except Exception:
        return None
