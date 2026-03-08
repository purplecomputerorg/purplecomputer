"""Playback player that executes scripts by dispatching keyboard actions.

The player converts playback script actions into KeyboardAction objects
and dispatches them to the app's keyboard handler at human-like pace.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Awaitable

from .script import (
    PlaybackAction,
    TypeText,
    PressKey,
    SwitchRoom,
    SwitchTarget,
    Pause,
    Clear,
    ClearAll,
    ClearArt,
    PlayKeys,
    DrawPath,
    MoveSequence,
    SetSpeed,
    Comment,
    ZoomIn,
    ZoomOut,
    ZoomTarget,
)
from ..keyboard import (
    CharacterAction,
    NavigationAction,
    RoomAction,
    ControlAction,
)

if TYPE_CHECKING:
    pass


class PlaybackPlayer:
    """Plays back a script by dispatching synthetic keyboard actions.

    Usage:
        player = PlaybackPlayer(dispatch_action=app._dispatch_keyboard_action)
        await player.play(script)

    The player injects actions directly into the app's action dispatcher,
    bypassing evdev entirely. This works both on Linux and for testing.

    IMPORTANT: Understanding room behaviors for scripts:

    Music Mode:
        - Keys CYCLE through colors on each press (purple -> blue -> red -> off)
        - Colors PERSIST until cycled again
        - For demo "flash" effects, use set_play_key_color callback to
          explicitly turn keys on/off

    Art Mode:
        - Starts in TEXT MODE (typing letters)
        - Press Tab to enter PAINT MODE
        - In paint mode: letter keys select brush color and stamp
        - DrawPath automatically enters paint mode before drawing
    """

    def __init__(
        self,
        dispatch_action: Callable[[object], Awaitable[None]],
        speed_multiplier: float = 1.0,
        clear_all: Callable[[], None] | None = None,
        clear_art: Callable[[], None] | None = None,
        set_play_key_color: Callable[[str, int], None] | None = None,
        is_doodle_paint_mode: Callable[[], bool] | None = None,
        is_play_letters_mode: Callable[[], bool] | None = None,
        get_cursor_position: Callable[[], tuple[float, float] | None] | None = None,
        zoom_events_file: str | Path | None = None,
    ):
        """Initialize the playback player.

        Args:
            dispatch_action: Async function to dispatch keyboard actions
                (typically app._dispatch_keyboard_action)
            speed_multiplier: Speed up (>1) or slow down (<1) the playback
            clear_all: Optional function to clear all state at start
            clear_art: Optional function to clear doodle canvas and reset cursor
            set_play_key_color: Optional function to set a Music room key's
                color index directly (0=purple, 1=blue, 2=red, -1=off)
            is_doodle_paint_mode: Optional function to check if Art room
                is in paint mode (vs text mode)
            is_play_letters_mode: Optional function to check if Music room
                is in letters mode (vs music mode)
            get_cursor_position: Optional function returning (x_frac, y_frac)
                viewport fractions for the current cursor position. Used to
                emit cursor_at events for zoom post-processing.
            zoom_events_file: Optional path to write zoom events JSON for
                post-processing. If provided, zoom events are logged with
                timestamps relative to start.
        """
        self._dispatch = dispatch_action
        self._speed = speed_multiplier
        self._clear_all = clear_all
        self._clear_art = clear_art
        self._set_play_key_color = set_play_key_color
        self._is_doodle_paint_mode = is_doodle_paint_mode
        self._is_play_letters_mode = is_play_letters_mode
        self._get_cursor_position = get_cursor_position
        self._zoom_events_file = Path(zoom_events_file) if zoom_events_file else None
        self._running = False
        self._cancelled = False
        self._zoom_events: list[dict] = []
        self._start_time: float = 0.0
        self._zoomed_in = False

    async def play(self, script: list[PlaybackAction]) -> None:
        """Play a script from start to finish.

        Args:
            script: List of PlaybackAction objects to execute
        """
        self._running = True
        self._cancelled = False
        self._zoom_events = []
        self._start_time = time.monotonic()

        # Write wall-clock start time for recording sync
        sync_file = os.environ.get("PURPLE_DEMO_SYNC_FILE")
        if sync_file:
            try:
                Path(sync_file).write_text(str(time.time()))
            except OSError:
                pass

        try:
            for action in script:
                if self._cancelled:
                    break
                await self._execute_action(action)
        finally:
            self._running = False
            self._write_zoom_events()

    def cancel(self) -> None:
        """Cancel the currently playing script."""
        self._cancelled = True

    @property
    def is_running(self) -> bool:
        """Check if a script is currently playing."""
        return self._running

    async def _sleep(self, duration: float) -> None:
        """Sleep with speed multiplier applied."""
        await asyncio.sleep(duration / self._speed)

    async def _execute_action(self, action: PlaybackAction) -> None:
        """Execute a single playback action."""
        if isinstance(action, Comment):
            return

        elif isinstance(action, SetSpeed):
            self._speed = action.multiplier
            return

        elif isinstance(action, TypeText):
            await self._type_text(action)

        elif isinstance(action, PressKey):
            await self._press_key(action)

        elif isinstance(action, SwitchRoom):
            await self._switch_room(action)

        elif isinstance(action, SwitchTarget):
            await self._switch_target(action)

        elif isinstance(action, Pause):
            await self._sleep(action.duration)

        elif isinstance(action, Clear):
            await self._clear(action)

        elif isinstance(action, ClearAll):
            await self._clear_all_state(action)

        elif isinstance(action, ClearArt):
            await self._clear_art_canvas(action)

        elif isinstance(action, PlayKeys):
            await self._play_keys(action)

        elif isinstance(action, DrawPath):
            await self._draw_path(action)

        elif isinstance(action, MoveSequence):
            await self._move_sequence(action)

        elif isinstance(action, ZoomIn):
            await self._zoom_in(action)

        elif isinstance(action, ZoomOut):
            await self._zoom_out(action)

        elif isinstance(action, ZoomTarget):
            await self._zoom_target(action)

    async def _type_text(self, action: TypeText) -> None:
        """Type text character by character."""
        for char in action.text:
            if self._cancelled:
                return

            shifted = char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~'

            await self._dispatch(CharacterAction(
                char=char,
                shifted=shifted,
                shift_held=shifted,
            ))

            self._emit_cursor_at()

            await self._sleep(action.delay_per_char)

        await self._sleep(action.final_pause)

    async def _press_key(self, action: PressKey) -> None:
        """Press a special key."""
        key = action.key.lower()

        if key in ('up', 'down', 'left', 'right'):
            await self._dispatch(NavigationAction(direction=key))

        elif key in ('enter', 'backspace', 'escape', 'tab', 'space'):
            await self._dispatch(ControlAction(action=key, is_down=True))

            if action.hold_duration > 0:
                await self._sleep(action.hold_duration)
                await self._dispatch(ControlAction(action=key, is_down=False))

        elif len(key) == 1:
            await self._dispatch(CharacterAction(char=key))

        self._emit_cursor_at()

        await self._sleep(action.pause_after)

    async def _switch_room(self, action: SwitchRoom) -> None:
        """Switch to a different room."""
        await self._dispatch(RoomAction(room=action.room))
        await self._sleep(action.pause_after)

    async def _switch_target(self, action: SwitchTarget) -> None:
        """Switch to a specific room and mode.

        Parses target like "music.music" or "art.paint" into:
        1. Main room switch (via RoomAction)
        2. Sub-room toggle (via Tab) if needed
        """
        target = action.target
        parts = target.split(".", 1)
        main_room = parts[0]
        mode = parts[1] if len(parts) > 1 else ""

        await self._dispatch(RoomAction(room=main_room))
        await self._sleep(0.1)

        if main_room == "music" and mode == "letters":
            in_letters = (
                self._is_play_letters_mode and self._is_play_letters_mode()
            )
            if not in_letters:
                await self._dispatch(ControlAction(action='tab', is_down=True))
                await self._sleep(0.05)
        elif main_room == "music" and mode == "music":
            in_letters = (
                self._is_play_letters_mode and self._is_play_letters_mode()
            )
            if in_letters:
                await self._dispatch(ControlAction(action='tab', is_down=True))
                await self._sleep(0.05)
        elif main_room == "art" and mode == "paint":
            in_paint = (
                self._is_doodle_paint_mode and self._is_doodle_paint_mode()
            )
            if not in_paint:
                await self._dispatch(ControlAction(action='tab', is_down=True))
                await self._sleep(0.05)
        elif main_room == "art" and mode == "text":
            in_paint = (
                self._is_doodle_paint_mode and self._is_doodle_paint_mode()
            )
            if in_paint:
                await self._dispatch(ControlAction(action='tab', is_down=True))
                await self._sleep(0.05)

        await self._sleep(action.pause_after)

    async def _clear(self, action: Clear) -> None:
        """Clear the current room's content."""
        await self._dispatch(ControlAction(action='escape', is_down=True))
        await self._sleep(action.pause_after)

    async def _clear_all_state(self, action: ClearAll) -> None:
        """Clear all state across all modes."""
        if self._clear_all:
            self._clear_all()
        await self._sleep(action.pause_after)

    async def _clear_art_canvas(self, action: ClearArt) -> None:
        """Clear the art canvas and reset cursor to (0,0)."""
        if self._clear_art:
            self._clear_art()
        await self._sleep(action.pause_after)

    async def _play_keys(self, action: PlayKeys) -> None:
        """Play a sequence of keys in Music room with musical timing.

        Each key press cycles the key's color (purple -> blue -> red -> off).
        Colors PERSIST after being set.
        """
        for item in action.sequence:
            if self._cancelled:
                return

            if item is None:
                await self._sleep(action.seconds_between)
            elif isinstance(item, list):
                for key in item:
                    await self._dispatch(CharacterAction(char=key))
                await self._sleep(action.seconds_between)
            else:
                await self._dispatch(CharacterAction(char=item))
                await self._sleep(action.seconds_between)

        await self._sleep(action.pause_after)

    async def _draw_path(self, action: DrawPath) -> None:
        """Draw a path in Art room's paint mode.

        Automatically switches to PAINT mode (via Tab) before drawing.
        """
        in_paint_mode = (
            self._is_doodle_paint_mode and self._is_doodle_paint_mode()
        )
        if not in_paint_mode:
            await self._dispatch(ControlAction(action='tab', is_down=True))
            await self._sleep(0.1)

        if action.color_key:
            await self._dispatch(CharacterAction(
                char=action.color_key,
                shift_held=True,
            ))
            await self._sleep(0.1)

        await self._dispatch(ControlAction(action='space', is_down=True))
        await self._sleep(0.05)

        for direction in action.directions:
            for _ in range(action.steps_per_direction):
                if self._cancelled:
                    await self._dispatch(ControlAction(action='space', is_down=False))
                    return

                await self._dispatch(NavigationAction(
                    direction=direction,
                    space_held=True,
                ))
                await self._sleep(action.delay_per_step)

        await self._dispatch(ControlAction(action='space', is_down=False))
        await self._sleep(action.pause_after)

    async def _move_sequence(self, action: MoveSequence) -> None:
        """Move cursor without painting (just arrow keys)."""
        for direction in action.directions:
            if self._cancelled:
                return

            await self._dispatch(NavigationAction(
                direction=direction,
                space_held=False,
            ))
            await self._sleep(action.delay_per_step)

        await self._sleep(action.pause_after)

    def _emit_cursor_at(self) -> None:
        """Emit a cursor_at event if zoomed in and cursor position is available."""
        if not self._zoomed_in or not self._get_cursor_position:
            return
        pos = self._get_cursor_position()
        if pos is None:
            return
        x_frac, y_frac = pos
        elapsed = time.monotonic() - self._start_time
        self._zoom_events.append({
            "time": round(elapsed, 3),
            "action": "cursor_at",
            "x": round(x_frac, 4),
            "y": round(y_frac, 4),
        })

    async def _zoom_in(self, action: ZoomIn) -> None:
        """Record a zoom-in event for post-processing."""
        elapsed = time.monotonic() - self._start_time
        self._zoom_events.append({
            "time": round(elapsed, 3),
            "action": "zoom_in",
            "region": action.region,
            "zoom": action.zoom,
            "duration": action.duration,
        })
        self._zoomed_in = True
        await self._sleep(action.duration)
        self._emit_cursor_at()

    async def _zoom_out(self, action: ZoomOut) -> None:
        """Record a zoom-out event for post-processing."""
        self._zoomed_in = False
        elapsed = time.monotonic() - self._start_time
        self._zoom_events.append({
            "time": round(elapsed, 3),
            "action": "zoom_out",
            "duration": action.duration,
        })
        await self._sleep(action.duration)

    async def _zoom_target(self, action: ZoomTarget) -> None:
        """Record a pan event for post-processing."""
        elapsed = time.monotonic() - self._start_time
        event: dict = {
            "time": round(elapsed, 3),
            "action": "pan_to",
            "duration": action.duration,
        }
        if action.y is not None:
            event["y"] = action.y
        if action.x is not None:
            event["x"] = action.x
        self._zoom_events.append(event)
        await self._sleep(action.duration)

    def _write_zoom_events(self) -> None:
        """Write collected zoom events to JSON sidecar file."""
        if not self._zoom_events_file:
            return

        try:
            self._zoom_events_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._zoom_events_file, 'w') as f:
                json.dump(self._zoom_events, f, indent=2)
        except OSError:
            pass
