"""Tests for purple_tui.audio.play_safe.

Covers:
- Successful first play: retry path is not taken, reinit_mixer not called.
- First play raises, second succeeds after reinit: reinit_mixer called once,
  play called twice, return value from second attempt is returned.
- Both plays raise: returns None, reinit_mixer called once, no infinite loop.
- reinit_mixer itself raises: returns None, no crash.
"""

from unittest.mock import patch

from purple_tui.audio import play_safe


class _FakeSound:
    def __init__(self, plays):
        """plays is a list of callables (or return values); each call pops from front."""
        self._plays = list(plays)
        self.call_count = 0

    def play(self, *args, **kwargs):
        self.call_count += 1
        action = self._plays.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def test_play_safe_success_first_try():
    channel_sentinel = object()
    sound = _FakeSound([channel_sentinel])
    with patch("purple_tui.rooms.music_room.reinit_mixer") as reinit:
        result = play_safe(sound)
    assert result is channel_sentinel
    assert sound.call_count == 1
    reinit.assert_not_called()


def test_play_safe_retries_once_after_reinit():
    channel_sentinel = object()
    sound = _FakeSound([RuntimeError("stale"), channel_sentinel])
    with patch("purple_tui.rooms.music_room.reinit_mixer") as reinit:
        result = play_safe(sound)
    assert result is channel_sentinel
    assert sound.call_count == 2
    assert reinit.call_count == 1


def test_play_safe_gives_up_after_second_failure():
    sound = _FakeSound([RuntimeError("boom1"), RuntimeError("boom2")])
    with patch("purple_tui.rooms.music_room.reinit_mixer") as reinit:
        result = play_safe(sound)
    assert result is None
    assert sound.call_count == 2
    assert reinit.call_count == 1


def test_play_safe_does_not_loop_beyond_one_retry():
    """Even if we wire up a pathological Sound that would raise forever,
    play_safe must stop after exactly two total attempts."""
    sound = _FakeSound([RuntimeError()] * 10)
    with patch("purple_tui.rooms.music_room.reinit_mixer"):
        play_safe(sound)
    assert sound.call_count == 2


def test_play_safe_handles_reinit_failure():
    """If reinit itself raises, return None without crashing the caller."""
    sound = _FakeSound([RuntimeError("first"), RuntimeError("second")])
    with patch("purple_tui.rooms.music_room.reinit_mixer", side_effect=RuntimeError("reinit broken")):
        result = play_safe(sound)
    assert result is None
    # Sound.play was only called once because reinit failed before the retry.
    assert sound.call_count == 1
