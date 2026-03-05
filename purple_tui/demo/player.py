"""Backward-compatible re-export from purple_tui.playback.player.

The player now lives in purple_tui.playback.player. This module
re-exports it so existing demo code continues to work unchanged.
DemoPlayer is an alias for PlaybackPlayer.
"""

from ..playback.player import PlaybackPlayer as DemoPlayer

__all__ = ["DemoPlayer"]
