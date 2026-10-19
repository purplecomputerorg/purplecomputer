"""What every canvas room is. The app, the Esc menu, the status strip, and the
Open library read a room's identity from these attributes; adding a room is one
subclass plus a line in rooms/__init__.py. guides/canvas-architecture.md."""


from ..ui import hint_row_h


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

    def __init__(self, app):
        self.app = app

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
