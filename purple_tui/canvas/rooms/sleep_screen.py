"""Sleep, shutdown confirm, bye, live-boot splash, and the first-boot power
cycle screen. Full-screen overlays; any key wakes or dismisses as noted."""

import os
import time

import pygame

from ... import backlight
from ... import palette as P
from ...constants import (ICON_BATTERY_MED, ICON_HARDDISK, ICON_HOURGLASS, ICON_KEYBOARD, ICON_LAPTOP, ICON_PLUG, ICON_USB,
                         ICON_VOLUME_OFF, LIVE_AUDIO_MARKER, is_live_boot)
from ...keyboard import ControlAction
from ...power_manager import LID_SHUTDOWN_DELAY, get_power_manager, manual_off_hint
from ..ui import Overlay


def _friendly_time(seconds: float) -> str:
    minutes = int(seconds / 60)
    if minutes >= 45:
        return "about 1 hr"
    if minutes >= 10:
        return f"about {minutes} min"
    if minutes >= 1:
        return f"{minutes} min"
    return "soon"


class FullScreen(Overlay):
    """Solid background, a face or message, and a hint underneath."""

    bg = P.BG
    image = ""
    face: list = []
    message = ""
    hint = ""
    status = ""
    tick_s = 0.0
    _timer = None

    def on_open(self):
        self._timer = self.app.timers.every(self.tick_s, self.tick) if self.tick_s else None

    def on_close(self):
        if self._timer:
            self._timer.stop()

    def tick(self):
        pass

    def draw(self, g):
        g.fill(self.bg)
        y = g.h // 2 - g.vh(14)
        if self.image:
            pic = g.image(self.image, g.vh(26))
            g.surface.blit(pic, pic.get_rect(midbottom=(g.w // 2, y + g.vh(14))))
            y += g.vh(16)
        for line in self.face:
            g.draw_text(line or " ", g.vh(4), g.w // 2, y, "mono-bold", P.PRIMARY, anchor="midtop")
            y += g.vh(5)
        if self.message:
            y += g.draw_markup(self.message, g.vh(2.8), g.vw(10), y, "mono-bold", P.PRIMARY, g.vw(80), "center", self.bg, g.vh(0.6))
        if self.hint:
            y += g.vh(3)
            y += g.draw_markup(self.hint, g.vh(2.4), g.vw(10), y, "mono", P.MUTED, g.vw(80), "center", self.bg)
        if self.status:
            y += g.vh(2)
            g.draw_markup(self.status, g.vh(2.2), g.vw(10), y, "mono", P.MUTED, g.vw(80), "center", self.bg, g.vh(0.4))


class AsleepBot(FullScreen):
    bg = "#140a22"
    image = "bot-asleep.png"
    face = ["z z z"]


class SleepScreen(AsleepBot):
    hint = "Press any key to wake"
    tick_s = 5.0

    def on_open(self):
        super().on_open()
        self._shutdown_initiated = False
        self._update_status()
        backlight.set_level(backlight.SLEEP_LEVEL)

    def on_close(self):
        super().on_close()
        from .parent_menu import load_display_settings
        backlight.set_level(load_display_settings()["brightness"])

    def tick(self):
        self._update_status()
        self._check_idle_shutdown()
        self.app.invalidate()

    def _update_status(self):
        pm = get_power_manager()
        lid_close_time = self.app._lid_close_time
        lines = []
        if lid_close_time is not None:
            closed_min = int((time.time() - lid_close_time) / 60)
            lines.append(f"{ICON_LAPTOP} Lid closed{f' {closed_min} min' if closed_min >= 1 else ''}.")
        elif self.app._lid_was_closed_for > 0:
            closed_min = int(self.app._lid_was_closed_for / 60)
            lines.append(f"{ICON_LAPTOP} Lid open{f' (closed {closed_min} min)' if closed_min >= 1 else ''}.")
        if is_live_boot():
            lines.append(f"{ICON_USB} USB. Need it to restart.")
        if lid_close_time is not None:
            remaining = max(0, LID_SHUTDOWN_DELAY - (time.time() - lid_close_time))
            lines.append(f"{ICON_HOURGLASS} Shuts off in {_friendly_time(remaining)}.")
        elif pm.get_idle_shutdown_threshold() != float("inf"):
            remaining = max(0, pm.get_idle_shutdown_threshold() - pm.get_idle_seconds())
            icon = f"{ICON_PLUG} Plugged in." if pm.is_on_charger() is True else f"{ICON_BATTERY_MED} Battery."
            lines.append(f"{icon} Shuts off in {_friendly_time(remaining)}.")
        self.status = "\n".join(lines)

    def _check_idle_shutdown(self):
        from ...power_manager import _power_log
        pm = get_power_manager()
        idle, threshold = pm.get_idle_seconds(), pm.get_idle_shutdown_threshold()
        if int(idle) % 30 == 0:
            _power_log(f"SLEEP_SCREEN TICK: idle={idle:.0f}s, shutdown_threshold={threshold}, charger={pm.is_on_charger()}")
        if idle >= threshold:
            _power_log(f"SLEEP_SCREEN SHUTDOWN: idle {idle:.0f}s >= {threshold}s")
            self._do_shutdown()

    def _do_shutdown(self):
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        if not power_off(self.app):
            self.hint = manual_off_hint()

    async def handle(self, action):
        from ...power_manager import _power_log
        _power_log("WAKE UP: key pressed on sleep screen")
        get_power_manager().record_activity()
        self.app._lid_was_closed_for = 0
        self.close()


def power_off(app) -> bool:
    """Every way the canvas UI turns the computer off: the Key gets the latest work first."""
    app.flush_for_power_off()
    return get_power_manager().shutdown()


class ShutdownConfirmScreen(AsleepBot):
    COUNTDOWN_SECONDS = 3
    tick_s = 1.0

    def on_open(self):
        super().on_open()
        self._remaining = self.COUNTDOWN_SECONDS
        self._refresh()

    def _refresh(self):
        self.hint = f"Press power button again to shut down ({self._remaining})"

    def tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            return self._cancel()
        self._refresh()
        self.app.invalidate()

    def _cancel(self):
        get_power_manager().record_activity()
        self.close()

    async def handle(self, action):
        self._cancel()


class ByeScreen(AsleepBot):
    face = ["Bye!"]
    hint = "Turning off..."

    def on_open(self):
        if not power_off(self.app):
            self.hint = manual_off_hint()

    async def handle(self, action):
        pass


class LiveBootSplash(FullScreen):
    _NOTES = [(ICON_KEYBOARD, "Purple is keyboard only, on purpose. Kids explore by typing."),
              (ICON_USB, "You're running from the Purple Key, so you'll need it to start Purple again."),
              (ICON_HARDDISK, "To install Purple and keep it, hold Esc to open the Parent Menu.")]
    _AUDIO_WARNING = (ICON_VOLUME_OFF, "Sound is not working on this computer. Plug in a USB audio adapter, "
                                       "or open the Parent Menu to see Support info.")
    hint = "Press any key to start"

    def draw(self, g):
        g.fill(self.bg)
        u = max(g.em(1), g.vh(2.3))  # g.em follows width alone, which leaves 4:3 screens with tiny text

        def em(n):
            return round(u * n)

        px, icon_w, gap, pad = em(1.0), em(2.4), em(1.0), em(1.6)
        notes = self._NOTES + ([self._AUDIO_WARNING] if self.status else [])
        sizes = [g.markup_size(text, px, "sans", min(g.vw(90), em(42)) - icon_w - 2 * pad) for _, text in notes]
        card = pygame.Rect(0, 0, icon_w + max(w for w, _ in sizes) + 2 * pad, sum(h for _, h in sizes) + gap * (len(notes) - 1) + 2 * pad)
        bot_h, title_px, hint_px = g.vh(15), em(1.8), em(1.0)
        title_h, hint_h = g.line_height(title_px, "sans-bold"), g.line_height(hint_px, "sans")
        y = max(em(1), (g.h - (bot_h + em(1.4) + title_h + em(1.8) + card.h + em(2.4) + hint_h)) // 2)
        bot = g.image("bot.png", bot_h)
        g.surface.blit(bot, bot.get_rect(midtop=(g.w // 2, y)))
        y += bot_h + em(1.4)
        g.draw_text("Welcome to Purple Computer!", title_px, g.w // 2, y, "sans-bold", P.ACCENT, anchor="midtop")
        card.midtop = (g.w // 2, y + title_h + em(1.8))
        g.rect(P.SURFACE, card, radius=em(0.8))
        y = card.y + pad
        for (icon, text), (w, h) in zip(notes, sizes):
            g.draw_text(icon, px, card.x + pad + icon_w // 2 - em(0.4), y + g.line_height(px, "sans") // 2, "nerd", P.ACCENT, anchor="center")
            g.draw_markup(text, px, card.x + pad + icon_w, y, "sans", P.TEXT, card.w - icon_w - 2 * pad)
            y += h + gap
        g.draw_text(self.hint, hint_px, g.w // 2, card.bottom + em(2.4), "sans", P.TEXT, anchor="midtop")

    tick_s = 0.25

    def tick(self):
        warn = self._AUDIO_WARNING if self.app.audio_ok is False else ""
        if warn != self.status:
            self.status = warn
            self.app.invalidate()

    async def handle(self, action):
        self.close()


def first_boot_power_cycle_needed(audio_ok) -> bool:
    """Audio worked in the live session but no card came up on this installed
    boot: the warm-reboot codec wedge a power off fixes."""
    if audio_ok is not False or is_live_boot() or not os.path.exists(LIVE_AUDIO_MARKER):
        return False
    from ...mixer import _silence_reason
    return _silence_reason() == "no-card"


class FirstBootPowerCycleScreen(FullScreen):
    message = ("Almost done!\n\nPurple needs to turn off and on\none time to finish setting up.\n\n"
               "After it turns off, press the\npower button to start Purple.")
    hint = "Press ENTER to turn off"

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "enter" and action.is_down:
            self.app.push(ByeScreen(self.app))
