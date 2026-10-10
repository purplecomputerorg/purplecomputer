"""What every canvas room is. The app, the Esc menu, the status strip, and the
save wall read a room's identity from these attributes; adding a room is one
subclass plus a line in rooms/__init__.py. guides/canvas-architecture.md."""


class Room:
    name = ""
    label = ""
    icon = ""
    arrow_hint = ""
    LANDSCAPE = False
    has_code_panel = False
    shows_legend = True
    keeps_audio_awake = False

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

    def hold_progress(self):
        return None

    def timeline_state(self) -> dict:
        return {}

    def restore_timeline_state(self, state: dict):
        pass

    def clear(self):
        self.restore_timeline_state({})

    async def handle(self, action):
        pass

    def draw(self, g, rect):
        pass
