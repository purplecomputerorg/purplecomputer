"""A family-made room from a pack, run from its JSON program.

Opens from the room picker's "Your rooms" row as a screen over the current
room; Esc leaves. Keys fire the program's rules; the program can show and
add text, speak, play notes on any instrument, hit the percussion, wait, and
keep a few numbers. See room_program.py for the language.
"""

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ..constants import VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from ..modal import PurpleModal
from ..music_constants import PERCUSSION, pitch_filename
from ..room_program import LIMITS, Runner, parse_note

_DRUM_KEYS = {name: key for key, name in PERCUSSION.items()}
_DRUM_ALIASES = {"hat": "hi-hat", "hihat": "hi-hat", "bell": "cowbell", "wood": "woodblock", "tri": "triangle", "tamb": "tambourine"}


class PackRoomScreen(PurpleModal):
    """The room, the size of the viewport, with the program running behind it."""

    CSS = f"""
    #modal-dialog {{
        width: {VIEWPORT_WIDTH + 2};
        height: {VIEWPORT_HEIGHT + 2};
        padding: 0 1;
    }}

    #room-title {{
        width: 100%;
        height: 1;
        color: $text-muted;
    }}

    #room-show {{
        width: 100%;
        height: 1fr;
        content-align: center middle;
        text-align: center;
        text-style: bold;
    }}

    #room-line {{
        width: 100%;
        height: 8;
        text-align: center;
    }}

    #modal-hint {{
        margin-top: 0;
    }}
    """

    def __init__(self, program: dict, **kwargs):
        super().__init__(**kwargs)
        self.program = program
        self.runner = Runner(program, self)
        self._line: list[str] = []
        self._run: asyncio.Task | None = None
        self._every = []
        self._sounds: dict[str, dict] = {}
        self._drums: dict[str, object] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static(f"  {self.program.get('title', self.program['name'])}", id="room-title")
            yield Static("", id="room-show")
            yield Static("", id="room-line")
            yield Static("Press keys!   Esc to leave", id="modal-hint")

    def on_mount(self) -> None:
        if color := self.program.get("background"):
            self.background(color)
        self._start(self.runner.fire("start"))
        for seconds, rule in self.runner.every_rules():
            self._every.append(self.set_interval(seconds, lambda r=rule: asyncio.ensure_future(self.runner.run_rule(r))))

    def on_unmount(self) -> None:
        self._cancel()
        for timer in self._every:
            timer.stop()

    # Keyboard ---------------------------------------------------------------

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, ControlAction) and action.action == "escape":
            if not action.is_down:
                self.dismiss(None)
            return
        if isinstance(action, CharacterAction) and not action.is_repeat:
            self._press(action.char.lower())
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat and action.action in ("space", "enter"):
            self._press(action.action)
        elif isinstance(action, NavigationAction) and not action.is_repeat:
            self._press(action.direction)

    def _press(self, key: str) -> None:
        self._start(self.runner.fire("key", key))

    def _start(self, coro) -> None:
        """One run at a time: a new key cancels a run still waiting, so mashing
        never queues up seconds of stale actions."""
        self._cancel()
        self._run = asyncio.ensure_future(coro)

    def _cancel(self) -> None:
        if self._run and not self._run.done():
            self._run.cancel()
        self._run = None

    # Host -------------------------------------------------------------------

    def show(self, text: str) -> None:
        self.query_one("#room-show", Static).update(text)

    def add(self, text: str) -> None:
        self._line = (self._line + [text])[-LIMITS["line"]:]
        self.query_one("#room-line", Static).update("  ".join(self._line))

    def say(self, text: str) -> None:
        from .. import tts
        tts.speak(text)

    def play(self, note: str, instrument: str) -> None:
        from ..audio import play_safe
        from .music_room import load_instrument_sounds
        if self.app._effective_volume() == 0:
            return
        if instrument not in self._sounds:
            self._sounds[instrument] = load_instrument_sounds(instrument)
        parsed = parse_note(note)
        if parsed and (sound := self._sounds[instrument].get(pitch_filename(*parsed))):
            play_safe(sound)

    def drum(self, name: str) -> None:
        from ..audio import play_safe
        from .music_room import load_percussion_sounds
        if self.app._effective_volume() == 0:
            return
        if self._drums is None:
            self._drums = load_percussion_sounds()
        key = _DRUM_KEYS.get(_DRUM_ALIASES.get(name.lower(), name.lower()))
        if key and (sound := self._drums.get(key)):
            play_safe(sound)

    def clear(self) -> None:
        self._line = []
        self.show("")
        self.query_one("#room-line", Static).update("")

    def background(self, color: str) -> None:
        self.query_one("#modal-dialog").styles.background = color

    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
