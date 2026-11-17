"""What every canvas room is. The app, the Esc menu, the status strip, and the
Open library read a room's identity from these attributes; adding a room is one
subclass plus a line in rooms/__init__.py. guides/canvas-architecture.md."""

import pygame

from ..ui import arrow_chip_width, hint_row_h


class Room:
    name = ""
    label = ""
    icon = ""
    LANDSCAPE = False
    has_code_panel = False
    shows_legend = True
    keeps_audio_awake = False
    STARTS_OFF = False   # hidden from the Esc menu until a parent turns it on
    about = ""           # the Parent Menu's line about it
    edits_text = False   # gets Ctrl or Cmd letters, Home and End, and = / * as typed
    keys_word = None     # the code word that puts keys back in the room's first mode, while they're in another

    def __init__(self, app):
        self.app = app
        self._toast = None

    def announce(self, text: str, picture: str | None = None):
        """A switch's toast, with an images/ picture, for kids who can't read the header; replaces the last
        so quick switches don't stack."""
        pic = picture and self.app.g.image(picture, self.app.g.vh(3.4))
        self._toast = self.app.notify(text, picture=pic, replaces=self._toast)

    def on_enter(self):
        pass

    def on_leave(self):
        pass

    def stop_sound(self):
        pass

    def open_code_panel(self):
        pass

    def close_code_panel(self):
        pass

    async def run_shown(self, runner, *args, **kwargs):
        """Run code-panel code with the panel's hint following the runner's corrections as they're made."""
        field = getattr(self, "code_panel", None) and self.code_panel.field
        if field:
            field.live = runner.corrections
        try:
            await runner.run(*args, **kwargs)
        finally:
            if field and field.live is runner.corrections:
                field.live = None
        if field and runner.corrections:
            field.set_correction(*runner.corrections[-1])

    header_row = None   # set by draw: the arrow hint sits at its right end

    def header_band(self, g, rect) -> pygame.Rect:
        """The toolbar row along the top of rect, which the arrow hint ends."""
        pad = g.em(0.7)
        self.header_row = pygame.Rect(rect.x + pad, rect.y + pad, rect.w - 2 * pad, hint_row_h(g))
        return self.header_row

    def header_reserve(self, g) -> int:
        """How much of the header row's right end the arrow hint takes, with a gap."""
        hint = self.app.arrow_chip_hint()
        return arrow_chip_width(g, hint) + g.em(1.2) if hint else 0

    def arrow_hint(self) -> str:
        return ""

    def hold_progress(self):
        return None

    def footer_h(self, g) -> int:
        """Height under the room's canvas: the hold bar covers exactly this."""
        return hint_row_h(g) + g.em(1.1)   # Art and Blocks: pad, hint row, gap

    def timeline_state(self) -> dict:
        return {}

    def restore_timeline_state(self, state: dict):
        pass

    def save_extras(self) -> dict:
        """What a save keeps beyond the Time Travel state."""
        return {}

    def on_open_save(self):
        pass

    def plain_text(self) -> str:
        """The work as text, copied to a USB drive beside its picture; empty for rooms without words."""
        return ""

    def clear(self):
        self.restore_timeline_state({})

    async def handle(self, action):
        pass

    def draw(self, g, rect):
        pass
