"""Demo player that executes demo scripts by dispatching keyboard actions.

The player converts demo script actions into KeyboardAction objects
and dispatches them to the app's keyboard handler at human-like pace.
"""

import asyncio
from typing import TYPE_CHECKING, Callable, Awaitable

from .script import (
    DemoAction,
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
    Clear,
    ClearAll,
    PlayKeys,
    DrawPath,
    MoveSequence,
    Comment,
)
from ..keyboard import (
    CharacterAction,
    NavigationAction,
    ModeAction,
    ControlAction,
)

if TYPE_CHECKING:
    from ..purple_tui import PurpleApp


class DemoPlayer:
    """Plays back a demo script by dispatching synthetic keyboard actions.

    Usage:
        player = DemoPlayer(app)
        await player.play(DEMO_SCRIPT)

    The player injects actions directly into the app's action dispatcher,
    bypassing evdev entirely. This works both on Linux and for testing.

    IMPORTANT: Understanding mode behaviors for demo scripts:

    Play Mode:
        - Keys CYCLE through colors on each press (purple → blue → red → off)
        - Colors PERSIST until cycled again
        - For demo "flash" effects, use set_play_key_color callback to
          explicitly turn keys on/off

    Doodle Mode:
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
        set_play_key_color: Callable[[str, int], None] | None = None,
        is_doodle_paint_mode: Callable[[], bool] | None = None,
    ):
        """Initialize the demo player.

        Args:
            dispatch_action: Async function to dispatch keyboard actions
                (typically app._dispatch_keyboard_action)
            speed_multiplier: Speed up (>1) or slow down (<1) the demo
            clear_all: Optional function to clear all state at demo start
            set_play_key_color: Optional function to set a Play mode key's
                color index directly (0=purple, 1=blue, 2=red, -1=off)
            is_doodle_paint_mode: Optional function to check if Doodle mode
                is in paint mode (vs text mode)
        """
        self._dispatch = dispatch_action
        self._speed = speed_multiplier
        self._clear_all = clear_all
        self._set_play_key_color = set_play_key_color
        self._is_doodle_paint_mode = is_doodle_paint_mode
        self._running = False
        self._cancelled = False

    async def play(self, script: list[DemoAction]) -> None:
        """Play a demo script from start to finish.

        Args:
            script: List of DemoAction objects to execute
        """
        self._running = True
        self._cancelled = False

        try:
            for action in script:
                if self._cancelled:
                    break
                await self._execute_action(action)
        finally:
            self._running = False

    def cancel(self) -> None:
        """Cancel the currently playing demo."""
        self._cancelled = True

    @property
    def is_running(self) -> bool:
        """Check if a demo is currently playing."""
        return self._running

    async def _sleep(self, duration: float) -> None:
        """Sleep with speed multiplier applied."""
        await asyncio.sleep(duration / self._speed)

    async def _execute_action(self, action: DemoAction) -> None:
        """Execute a single demo action."""
        if isinstance(action, Comment):
            # Comments do nothing
            return

        elif isinstance(action, TypeText):
            await self._type_text(action)

        elif isinstance(action, PressKey):
            await self._press_key(action)

        elif isinstance(action, SwitchMode):
            await self._switch_mode(action)

        elif isinstance(action, Pause):
            await self._sleep(action.duration)

        elif isinstance(action, Clear):
            await self._clear(action)

        elif isinstance(action, ClearAll):
            await self._clear_all_state(action)

        elif isinstance(action, PlayKeys):
            await self._play_keys(action)

        elif isinstance(action, DrawPath):
            await self._draw_path(action)

        elif isinstance(action, MoveSequence):
            await self._move_sequence(action)

    async def _type_text(self, action: TypeText) -> None:
        """Type text character by character."""
        for char in action.text:
            if self._cancelled:
                return

            # Determine if shift is needed
            shifted = char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~'

            # Dispatch character action
            await self._dispatch(CharacterAction(
                char=char,
                shifted=shifted,
                shift_held=shifted,
            ))

            await self._sleep(action.delay_per_char)

        await self._sleep(action.final_pause)

    async def _press_key(self, action: PressKey) -> None:
        """Press a special key."""
        key = action.key.lower()

        if key in ('up', 'down', 'left', 'right'):
            # Navigation action
            await self._dispatch(NavigationAction(direction=key))

        elif key in ('enter', 'backspace', 'escape', 'tab', 'space'):
            # Control action (key down)
            await self._dispatch(ControlAction(action=key, is_down=True))

            # If there's a hold duration, wait then release
            if action.hold_duration > 0:
                await self._sleep(action.hold_duration)
                await self._dispatch(ControlAction(action=key, is_down=False))

        await self._sleep(action.pause_after)

    async def _switch_mode(self, action: SwitchMode) -> None:
        """Switch to a different mode."""
        await self._dispatch(ModeAction(mode=action.mode))
        await self._sleep(action.pause_after)

    async def _clear(self, action: Clear) -> None:
        """Clear the current mode's content.

        In Ask mode, escape clears input.
        For a full clear, we could add a special action.
        """
        # Press escape to clear current input
        await self._dispatch(ControlAction(action='escape', is_down=True))
        await self._sleep(action.pause_after)

    async def _clear_all_state(self, action: ClearAll) -> None:
        """Clear all state across all modes."""
        if self._clear_all:
            self._clear_all()
        await self._sleep(action.pause_after)

    async def _play_keys(self, action: PlayKeys) -> None:
        """Play a sequence of keys with musical timing.

        Each key press cycles the key's color (purple → blue → red → off → ...).
        Colors PERSIST after being set. This is intentional: by pressing keys
        in strategic patterns, you can "draw" pictures on the keyboard grid
        while playing music.

        For example, pressing 'e', 'i', 'c', 'v', 'b', 'n' creates a smiley face
        (eyes + smile) that stays visible.
        """
        beat_duration = 60.0 / action.tempo_bpm

        for item in action.sequence:
            if self._cancelled:
                return

            if item is None:
                # Rest (silence, no key press)
                await self._sleep(beat_duration)
            elif isinstance(item, list):
                # Chord: multiple keys pressed together
                for key in item:
                    await self._dispatch(CharacterAction(char=key))
                await self._sleep(beat_duration)
            else:
                # Single key
                await self._dispatch(CharacterAction(char=item))
                await self._sleep(beat_duration)

        await self._sleep(action.pause_after)

    async def _draw_path(self, action: DrawPath) -> None:
        """Draw a path in Doodle mode's paint mode.

        IMPORTANT: Doodle mode starts in TEXT mode by default. This method
        automatically switches to PAINT mode (via Tab) before drawing.
        In paint mode, letter keys select brush colors and stamp.
        """
        # Ensure we're in paint mode (Tab toggles between text/paint mode)
        # Check if we're already in paint mode to avoid toggling out of it
        in_paint_mode = (
            self._is_doodle_paint_mode and self._is_doodle_paint_mode()
        )
        if not in_paint_mode:
            await self._dispatch(ControlAction(action='tab', is_down=True))
            await self._sleep(0.1)

        # Select color by pressing the color key (in paint mode, this selects brush)
        # Use shift to select without stamping
        if action.color_key:
            await self._dispatch(CharacterAction(
                char=action.color_key,
                shift_held=True,  # Shift = select color only, don't stamp
            ))
            await self._sleep(0.1)

        # Hold space down for line drawing
        await self._dispatch(ControlAction(action='space', is_down=True))
        await self._sleep(0.05)

        # Move in each direction (space_held=True tells canvas to paint)
        for direction in action.directions:
            for _ in range(action.steps_per_direction):
                if self._cancelled:
                    # Release space before cancelling
                    await self._dispatch(ControlAction(action='space', is_down=False))
                    return

                await self._dispatch(NavigationAction(
                    direction=direction,
                    space_held=True,
                ))
                await self._sleep(action.delay_per_step)

        # Release space
        await self._dispatch(ControlAction(action='space', is_down=False))
        await self._sleep(action.pause_after)

    async def _move_sequence(self, action: MoveSequence) -> None:
        """Move cursor without painting (just arrow keys).

        Unlike DrawPath, this does NOT hold space, so no painting occurs.
        Use this for repositioning the cursor between paint operations.
        """
        for direction in action.directions:
            if self._cancelled:
                return

            await self._dispatch(NavigationAction(
                direction=direction,
                space_held=False,
            ))
            await self._sleep(action.delay_per_step)

        await self._sleep(action.pause_after)
