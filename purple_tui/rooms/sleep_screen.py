"""Sleep, shutdown confirm, bye, live-boot splash, and the first-boot power
cycle screen. Full-screen overlays; any key wakes or dismisses as noted."""

import os
import time

from .. import palette as P
from ..constants import (ICON_BATTERY_MED, ICON_HOURGLASS, ICON_LAPTOP, ICON_PLUG, ICON_USB,
                         ICON_VOLUME_OFF, LIVE_AUDIO_MARKER, is_live_boot)
from ..keyboard import ControlAction
from ..power_manager import LID_SHUTDOWN_DELAY, get_power_manager
from ..ui import Overlay

_FACE = ["---     ---", "", "   \\___/   ", "", "   z z z   "]
_BYE_FACE = ["---     ---", "", "   \\___/   ", "", "    Bye!   "]


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
    face: list = []
    message = ""
    hint = ""
    status = ""

    def draw(self, g):
        g.fill(self.bg)
        y = g.h // 2 - g.vh(14)
        for line in self.face:
            g.draw_text(line or " ", g.vh(4), g.w // 2, y, "mono-bold", P.PRIMARY, anchor="midtop")
            y += g.vh(5)
        if self.message:
            y += g.draw_markup(self.message, g.vh(2.8), g.vw(10), y, "sans-bold", P.PRIMARY, g.vw(80), "center", self.bg, g.vh(0.6))
        if self.hint:
            y += g.vh(3)
            y += g.draw_markup(self.hint, g.vh(2.4), g.vw(10), y, "sans", P.MUTED, g.vw(80), "center", self.bg)
        if self.status:
            y += g.vh(2)
            g.draw_markup(self.status, g.vh(2.2), g.vw(10), y, "sans", P.MUTED, g.vw(80), "center", self.bg, g.vh(0.4))


class SleepScreen(FullScreen):
    bg = "#140a22"
    face = _FACE
    hint = "Press any key to wake"

    def on_open(self):
        self._shutdown_initiated = False
        self._update_status()
        self._timer = self.app.timers.every(5.0, self._tick)

    def on_close(self):
        self._timer.stop()

    def _tick(self):
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
        else:
            remaining = max(0, pm.get_idle_shutdown_threshold() - pm.get_idle_seconds())
            icon = f"{ICON_PLUG} Plugged in." if pm.is_on_charger() is True else f"{ICON_BATTERY_MED} Battery."
            lines.append(f"{icon} Shuts off in {_friendly_time(remaining)}.")
        self.status = "\n".join(lines)

    def _check_idle_shutdown(self):
        from ..power_manager import _power_log
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
        if not get_power_manager().shutdown():
            self.hint = "Please turn off"

    async def handle(self, action):
        from ..power_manager import _power_log
        _power_log("WAKE UP: key pressed on sleep screen")
        get_power_manager().record_activity()
        self.app._lid_was_closed_for = 0
        self.close()


class ShutdownConfirmScreen(FullScreen):
    COUNTDOWN_SECONDS = 3
    face = _FACE

    def on_open(self):
        self._remaining = self.COUNTDOWN_SECONDS
        self._refresh()
        self._timer = self.app.timers.every(1.0, self._tick)

    def on_close(self):
        self._timer.stop()

    def _refresh(self):
        self.hint = f"Press power button again to shut down ({self._remaining})"

    def _tick(self):
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


class ByeScreen(FullScreen):
    face = _BYE_FACE
    hint = "Turning off..."

    def on_open(self):
        if not get_power_manager().shutdown():
            self.hint = "Please turn off"

    async def handle(self, action):
        pass


class LiveBootSplash(FullScreen):
    message = ("Welcome to Purple Computer!\n\n"
               "Purple is keyboard only, on purpose!\nKids explore by typing.\n\n"
               "You're running from USB. If the computer\nturns off, you'll need the USB to start again.\n\n"
               "To install Purple and keep it, hold the Esc\nkey to open the Parent Menu.")
    _AUDIO_WARNING = (f"{ICON_VOLUME_OFF} Sound is not working on this computer.\nPlug in a USB audio adapter, or open the\n"
                      "Parent Menu to see Support info.")
    hint = "Press any key to start"

    def on_open(self):
        self._timer = self.app.timers.every(0.25, self._refresh)

    def on_close(self):
        self._timer.stop()

    def _refresh(self):
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
    from ..mixer import _silence_reason
    return _silence_reason() == "no-card"


class FirstBootPowerCycleScreen(FullScreen):
    message = ("Almost done!\n\nPurple needs to turn off and on\none time to finish setting up.\n\n"
               "After it turns off, press the\npower button to start Purple.")
    hint = "Press ENTER to turn off"

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "enter" and action.is_down:
            self.app.push(ByeScreen(self.app))
