"""Support info: version, model, audio status, scrollable device and audio
reports a parent can read out to support, a Sound check that plays the
startup chime and shows what first boot would decide, and a Printer check
laid out for a photo or a scrolling video sent to support."""

import textwrap
import threading

import pygame

from .. import diagnostics
from .. import palette as P
from .. import printing
from ..constants import SUPPORT_EMAIL
from ..keyboard import ControlAction, NavigationAction
from ..palette import rgb
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
        self.rows, self.fits = 1, True  # what the last draw showed

    @property
    def lines(self) -> list:
        return _wrap(self.text, self.cols)

    def _collect_text(self) -> str:
        raise NotImplementedError

    def body_height(self, g):
        return g.vh(60)

    text_vh = (2.1,)  # text sizes, largest first: the first that fits it all, else the largest to scroll

    def draw_body(self, g, rect):
        for vh in (*self.text_vh, self.text_vh[0]):
            px = g.vh(vh)
            lh = g.line_height(px, "mono")
            self.cols = max(20, rect.w // g.measure("M", px, "mono", tr=False)[0])
            if len(self.lines) * lh <= rect.h:
                break
        self.rows = max(1, rect.h // lh)
        self.fits = len(self.lines) <= self.rows
        y = rect.y
        for line in self.lines[self.offset:self.offset + self.rows]:
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
        from .. import sound_check
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


WAIT_CAP_S = 120  # longest the screen asks to wait before a photo, whatever the job is doing
WAITING = "Printing a test page. Please wait, don't take a photo yet."
PRINTED = "The printer finished the test page."
NOT_YET = "The test page hasn't printed yet."
PAGE_S = 5  # each page's time on screen while it pages itself for a video
SEND = " of this screen and send it to " + SUPPORT_EMAIL
NO_CIRCLE = "Didn't get a page with a purple circle? "


class PrinterCheckScreen(_ScrollablePage):
    """Tells the parent what to do at the top: press Enter, wait, or take the photo now.
    A report too long for one photo asks for a video and pages itself."""
    title = "Printer check"
    hint = f"{{Enter}} print a test page   {UP} {DOWN} scroll   {{Esc}} back"
    text_vh = (2.1, 1.9, 1.75, 1.6)  # shrinks so one photo holds the whole report

    def __init__(self, app):
        self.heard = []  # what the test page did, newest last
        self.printed = None  # None while no test page has ended
        self.waiting = None  # the cap's timer while a test page is on its way
        self.pager = None  # turns the pages for a video
        self.scrolled = False  # the arrows took over from the pager
        super().__init__(app)

    def _collect_text(self):
        return "Checking the printer..."

    def on_open(self):
        threading.Thread(target=self._run, daemon=True, name="printer-check").start()

    def on_close(self):
        for timer in (self.waiting, self.pager):
            timer and timer.stop()

    def body_height(self, g):
        return self.body_limit(g)  # as much as fits in one photo

    def _run(self):
        report = "\n".join([diagnostics.get_version_label() or "Dev build", diagnostics.get_product_name(), "",
                            diagnostics.collect_printer_info()])
        self.app.call_from_thread(self._show, report)

    def _show(self, report: str):
        """Keeps the scroll where it is: the report refreshes while a test page prints."""
        self.text = "\n".join([*(f"Test page: {line}" for line in self.heard), "", report]).lstrip("\n")
        self.app.invalidate()

    def headline(self) -> tuple:
        """(what to do now, the photo or video line or None)."""
        if self.waiting:
            return WAITING, None
        if self.printed:
            return PRINTED, NO_CIRCLE + self.send()
        if self.printed is False:
            return (self.heard[-1] if len(self.heard) > 1 else NOT_YET), self.send()
        return printing.advice(), self.send() if printing.status() == printing.BROKEN else None

    def send(self) -> str:
        if self.fits:
            return "Take a photo" + SEND
        pages = -(-(len(self.lines) - 1) // max(1, self.rows - 1))
        return f"Record a {pages * PAGE_S}-second video" + SEND

    def _hear(self, text: str):
        self.heard.append(text)
        self.on_open()  # the report changes with the job

    def _ended(self, printed: bool):
        self.waiting and self.waiting.stop()
        self.waiting, self.printed = None, printed
        self.on_open()

    def draw_body(self, g, rect):
        """The headline as a solid banner, so it reads as what to do rather than more report."""
        lines = [(text, px) for text, px in zip(self.headline(), (g.vh(3.6), g.vh(2.8))) if text]
        pad, inset = g.vh(1.6), g.vh(2.4)
        w = rect.w - 2 * inset
        h = sum(g.markup_size(text, px, "sans", w)[1] for text, px in lines) + 2 * pad
        g.rect(P.GOOD if self.printed else P.CARET if len(lines) > 1 else P.PRIMARY,
               pygame.Rect(rect.x, rect.y, rect.w, h), radius=g.vh(1.2))
        y = rect.y + pad
        for text, px in lines:
            y += g.draw_markup(text, px, rect.x + inset, y, "sans", P.ON_PRIMARY, w, "center")
        y = rect.y + h + g.vh(2.5)
        fitted = self.fits
        super().draw_body(g, pygame.Rect(rect.x, y, rect.w, rect.bottom - y))
        if self.fits != fitted:
            self.app.invalidate()  # the banner asks for a photo or a video by what fits
        self._page_for_video(len(lines) > 1 and not self.fits and not self.scrolled)

    def _page_for_video(self, wanted: bool):
        if wanted and not self.pager:
            self.pager = self.app.timers.every(PAGE_S, self._next_page)
        elif self.pager and not wanted:
            self.pager.stop()
            self.pager = None

    def _next_page(self):
        """Over and over from the top, so a video started at any moment gets every page."""
        self.offset += self.rows - 1  # one line repeats, so no line falls between two frames
        if self.offset >= len(self.lines) - 1:
            self.offset = 0
        self.app.invalidate()

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down and not action.is_repeat and action.action == "enter":
            return self._print_test_page()
        if isinstance(action, NavigationAction):
            self.scrolled = True
        await super().handle(action)

    def _print_test_page(self):
        if self.waiting:
            return
        why = printing.why_not()
        if why:
            return self._hear(why)
        self.heard, self.printed, self.offset = [], None, 0
        page = ([_test_page(self.app.g, self.app.computer_name())], True)
        if self.app._print_pages(page, self._hear, self._ended):
            self.waiting = self.waiting or self.app.timers.after(WAIT_CAP_S, lambda: self._ended(False))
        self.app.invalidate()


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
