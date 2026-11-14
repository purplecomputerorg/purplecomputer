"""Support info: version, model, audio status, scrollable device and audio
reports a parent can read out to support, a Sound check that plays the
startup chime and shows what first boot would decide, and a Printer check
laid out for a photo or a scrolling video sent to support."""

import textwrap
import threading

import pygame

from ... import diagnostics
from ... import palette as P
from ... import printing
from ...constants import SUPPORT_EMAIL
from ...keyboard import ControlAction, NavigationAction
from ...palette import rgb
from ..ui import DOWN, UP, Dialog, Picker

SCROLL_LINES = 5


def _wrap(text: str, cols: int) -> list:
    """Word-wrap each line to cols, continuing under its own indent plus two."""
    out = []
    for line in text.splitlines() or ["(nothing to show)"]:
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        out += textwrap.wrap(line, cols, subsequent_indent=indent, break_on_hyphens=False) or [""]
    return out


class _ScrollablePage(Dialog):
    hint = f"{UP} {DOWN} scroll   {{Esc}} back"
    width_pct = 80

    def __init__(self, app):
        super().__init__(app)
        self.text = self._collect_text()
        self.cols = 10_000  # until the first draw measures the box
        self.offset = 0

    @property
    def lines(self) -> list:
        return _wrap(self.text, self.cols)

    def _collect_text(self) -> str:
        raise NotImplementedError

    def body_height(self, g):
        return g.vh(60)

    def draw_body(self, g, rect):
        px = g.vh(2.1)
        lh = g.line_height(px, "mono")
        self.cols = max(20, rect.w // g.measure("M", px, "mono", tr=False)[0])
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
        self.text = text
        self.offset = 0
        self.app.invalidate()


def _test_page(g, computer_name: str):
    """A Purple circle and a line saying what it is, on a printed page."""
    from ..paper import INK, compose
    work = pygame.Surface((900, 700), pygame.SRCALPHA)
    pygame.draw.circle(work, rgb(P.PRIMARY), (450, 280), 260)
    label = g.text("Purple Computer printer test", 48, "sans", INK)
    work.blit(label, label.get_rect(midbottom=(450, 700)))
    return compose(work, True, g, computer_name)[0]


class PrinterCheckScreen(_ScrollablePage):
    title = "Printer check"
    hint = f"{{Enter}} print a test page   {UP} {DOWN} scroll   {{Esc}} back"

    def __init__(self, app):
        self.heard = []  # what the test page did, newest last
        super().__init__(app)

    def _collect_text(self):
        return "Checking the printer..."

    def on_open(self):
        threading.Thread(target=self._run, daemon=True, name="printer-check").start()

    def body_height(self, g):
        return self.body_limit(g)  # as much as fits in one photo

    def _run(self):
        report = "\n".join([diagnostics.get_version_label() or "Dev build", diagnostics.get_product_name(), "",
                            diagnostics.collect_printer_info(), "", f"Contact: {SUPPORT_EMAIL}"])
        self.app.call_from_thread(self._show, report)

    def _show(self, report: str):
        """Keeps the scroll where it is: the report refreshes while a test page prints."""
        self.text = "\n".join([printing.advice(SUPPORT_EMAIL), *(f"Test page: {line}" for line in self.heard), "", report])
        self.app.invalidate()

    def _hear(self, text: str):
        self.heard.append(text)
        self.on_open()  # the report changes with the job

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down and not action.is_repeat and action.action == "enter":
            why = printing.why_not()
            if why:
                return self._hear(why)
            self.app._print_pages(([_test_page(self.app.g, self.app.computer_name())], True), self._hear)
            return
        await super().handle(action)


class SupportInfoScreen(Picker):
    title = "Support info"
    hint = f"{UP} {DOWN} choose   {{Enter}} open   {{Esc}} back"
    OPTIONS = [(DeviceInfoScreen, "Device info"), (AudioInfoScreen, "Audio info"), (SoundCheckScreen, "Sound check"),
               (PrinterCheckScreen, "Printer check")]

    def __init__(self, app):
        super().__init__(app)
        self.DESCRIPTION = "\n".join([
            diagnostics.get_version_label() or "Dev build",
            diagnostics.get_product_name(),
            diagnostics.get_audio_status_line(app.audio_ok),
            printing.status_line(),
            "",
            f"Contact: {SUPPORT_EMAIL}",
        ])

    def _on_confirm(self, value):
        screen = value(self.app)
        self.app.push(screen)
        if hasattr(screen, "on_open"):
            screen.on_open()
