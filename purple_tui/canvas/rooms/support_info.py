"""Support info: version, model, audio status, scrollable device and audio
reports a parent can read out to support, and a Sound check that plays the
startup chime and shows what first boot would decide."""

import threading

from ... import diagnostics
from ... import palette as P
from ...constants import SUPPORT_EMAIL
from ...keyboard import ControlAction, NavigationAction
from ..ui import Dialog, Picker

SCROLL_LINES = 5


class _ScrollablePage(Dialog):
    hint = "▲ ▼ scroll   Esc back"
    width_pct = 80

    def __init__(self, app):
        super().__init__(app)
        self.lines = self._collect_text().splitlines() or ["(nothing to show)"]
        self.offset = 0

    def _collect_text(self) -> str:
        raise NotImplementedError

    def body_height(self, g):
        return g.vh(60)

    def draw_body(self, g, rect):
        px = g.vh(2.1)
        lh = g.line_height(px, "mono")
        y = rect.y
        for line in self.lines[self.offset:self.offset + rect.h // lh]:
            g.draw_text(line or " ", px, rect.x, y, "mono", P.TEXT)
            y += lh

    async def handle(self, action):
        if isinstance(action, NavigationAction) and action.direction in ("up", "down"):
            step = -SCROLL_LINES if action.direction == "up" else SCROLL_LINES
            self.offset = max(0, min(max(0, len(self.lines) - 5), self.offset + step))
            self.app.invalidate()
        elif isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.close()


class DeviceInfoScreen(_ScrollablePage):
    title = "Device info"

    def _collect_text(self):
        return diagnostics.collect_device_info()


class AudioInfoScreen(_ScrollablePage):
    title = "Audio info"

    def _collect_text(self):
        return diagnostics.collect_audio_info(self.app.audio_ok)


class SoundCheckScreen(_ScrollablePage):
    title = "Sound check"

    def _collect_text(self):
        return "Playing the chime and listening through the microphone..."

    def on_open(self):
        if self.app._effective_volume() == 0:
            self._show("Sound is off, so the chime can't play. Turn the volume up first.")
            return
        threading.Thread(target=self._run, daemon=True, name="sound-check-menu").start()

    def _run(self):
        from ... import sound_check
        takes: list[str] = []
        result = sound_check.run(ladder=sound_check.PROBE_LADDER, log=takes.append)
        self.app._apply_volume_system()  # the check restored the sink to its pre-chime level; reassert ours
        self.app.call_from_thread(self._show, sound_check.report(result, takes))

    def _show(self, text: str):
        self.lines = text.splitlines()
        self.offset = 0
        self.app.invalidate()


class SupportInfoScreen(Picker):
    title = "Support info"
    hint = "▲ ▼ choose   Enter open   Esc back"
    OPTIONS = [(DeviceInfoScreen, "Device info"), (AudioInfoScreen, "Audio info"), (SoundCheckScreen, "Sound check")]

    def __init__(self, app):
        super().__init__(app)
        self.DESCRIPTION = "\n".join([
            diagnostics.get_version_label() or "Dev build",
            diagnostics.get_product_name(),
            diagnostics.get_audio_status_line(app.audio_ok),
            "",
            f"Contact: {SUPPORT_EMAIL}",
        ])

    def _on_confirm(self, value):
        screen = value(self.app)
        self.app.push(screen)
        if hasattr(screen, "on_open"):
            screen.on_open()
