"""The Esc menu: pick a room, or Volume, Clear, Time Travel, and the code toggle."""

import pygame

from . import palette as P
from .constants import (
    ICON_BROOM, ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_ROBOT, ICON_TIME_TRAVEL,
    ICON_VOLUME_HIGH, ICON_VOLUME_OFF,
)
from .keyboard import CharacterAction, ControlAction, NavigationAction
from .ui import TRACK, Dialog, Overlay, Picker, draw_scrim, draw_window, window_title_height

ROOM_OPTIONS = [("play", ICON_CHAT, "Play"), ("music", ICON_MUSIC, "Music"), ("art", ICON_PALETTE, "Art")]
NUMBER_KEY_ROOMS = {"1": "play", "2": "music", "3": "art"}
ROWS, EXTRAS, CODE = 0, 1, 2


def volume_badge(vol: int):
    steps = [(0, "Sound Off"), (15, "Whisper"), (35, "Quiet"), (60, "Medium"), (85, "Loud"), (100, "Full")]
    label = next(lbl for lvl, lbl in steps if vol <= lvl)
    filled = 0 if vol <= 0 else next(i for i, (lvl, _) in enumerate(steps) if vol <= lvl) * 2
    return (ICON_VOLUME_OFF if vol == 0 else ICON_VOLUME_HIGH), "█" * filled + "░" * (10 - filled), label


class RoomPicker(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.row = ROWS
        self.col = [o[0] for o in ROOM_OPTIONS].index(app.active_room)
        self.code_row = app.active_room in ("music", "art") and (app._code_panel_active or app._code_panel_enabled)

    def _locked_volume(self):
        lock = self.app._volume_lock
        if lock == 0:
            return ICON_VOLUME_OFF, "Silent Mode"
        if lock is not None:
            return ICON_VOLUME_HIGH, "Locked"
        if self.app.audio_ok is False:
            return ICON_VOLUME_OFF, "No Sound"
        return None

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if action.is_repeat:
                return
            d = action.direction
            if d in ("left", "right") and self.row != CODE:
                self.col = max(0, min(2, self.col + (1 if d == "right" else -1)))
            elif d == "up":
                self.row = max(ROWS, self.row - 1)
            elif d == "down":
                self.row = min(CODE if self.code_row else EXTRAS, self.row + 1)
            self.app.invalidate()
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            ch = action.char.lower()
            if ch in NUMBER_KEY_ROOMS:
                return self.close({"room": NUMBER_KEY_ROOMS[ch]})
            if ch == "v":
                self.row, self.col = EXTRAS, 0
                return self._open_volume()
            if ch == "c":
                self.row, self.col = EXTRAS, 1
                return self._confirm_clear()
            if ch == "t":
                return self.close({"time_travel": True})
            return self.close(None)
        if isinstance(action, ControlAction):
            a = action.action
            if a in ("volume_mute", "volume_down", "volume_up") and action.is_down:
                getattr(self.app, f"action_{a}")()
            elif a == "escape" and not action.is_down:
                self.close(None)  # on release, so a hold falls through to the app's timer
            elif a == "space" and action.is_down and not action.is_repeat and self.code_row:
                self._toggle_code()
            elif a == "enter" and action.is_down and not action.is_repeat:
                self._activate()

    def _activate(self):
        if self.row == ROWS:
            self.close({"room": ROOM_OPTIONS[self.col][0]})
        elif self.row == EXTRAS:
            (self._open_volume, self._confirm_clear, lambda: self.close({"time_travel": True}))[self.col]()
        else:
            self._toggle_code()

    def _toggle_code(self):
        self.close({"close_code": True} if self.app._code_panel_active else {"open_code": True})

    def _open_volume(self):
        if not self.app.volume_locked:
            self.app.push(VolumeModal(self.app))

    def _confirm_clear(self):
        self.app.push(ConfirmFresh(self.app, self.app.active_room), on_close=lambda r: r and self.close({"clear_room": r}))

    def draw(self, g):
        draw_scrim(g)
        tw, th, gap, eh = g.vw(22), g.vh(17), g.vw(1.5), g.vh(10)
        rows_h = th + gap + eh + (gap + eh if self.code_row else 0)
        box = pygame.Rect(0, 0, 3 * tw + 2 * gap + g.vw(8), window_title_height(g, "x") + g.vh(3) + rows_h + g.vh(9))
        box.center = (g.w // 2, g.h // 2)
        y = draw_window(g, box, "Pick a Room") + g.vh(3)
        x0 = box.centerx - (3 * tw + 2 * gap) // 2
        for i, (rid, icon, label) in enumerate(ROOM_OPTIONS):
            on = self.row == ROWS and self.col == i
            self._tile(g, pygame.Rect(x0 + i * (tw + gap), y, tw, th), on, label,
                       f"Press {i + 1}" + (" or Enter" if on else ""), icon=icon)
        y += th + gap
        locked = self._locked_volume()
        vol_label = f"{locked[0]}  {locked[1]}" if locked else f"{ICON_VOLUME_HIGH}  Volume"
        extras = [(vol_label, "" if locked else "Press V", locked is not None),
                  (f"{ICON_BROOM}  Clear", "Press C", False), (f"{ICON_TIME_TRAVEL}  Time Travel", "Press T", False)]
        for i, (label, key, disabled) in enumerate(extras):
            on = self.row == EXTRAS and self.col == i
            self._tile(g, pygame.Rect(x0 + i * (tw + gap), y, tw, eh), on, label,
                       "" if disabled else key + (" or Enter" if on else ""), disabled)
        if self.code_row:
            y += eh + gap
            label = f"{ICON_ROBOT}  Close Code" if self.app._code_panel_active else f"{ICON_ROBOT}  Open Code"
            self._tile(g, pygame.Rect(x0, y, 3 * tw + 2 * gap, eh), self.row == CODE, label,
                       "Space" + (" or Enter" if self.row == CODE else ""))
        g.draw_text("Enter picks   •   Hold Esc for grown-ups", g.vh(2.0), box.centerx, box.bottom - g.vh(5.5), "mono", P.MUTED, anchor="center")
        g.draw_text("Arrows move  ← ↑ ↓ →", g.vh(2.0), box.centerx, box.bottom - g.vh(2.5), "mono", P.DIM, anchor="center")

    def _tile(self, g, r, on, label, sub, disabled=False, icon=""):
        """icon (room tiles) draws large above the label; other tiles are one line."""
        g.rect(P.PRIMARY if on else P.TILE, r)
        if not on and not disabled:
            g.rect(P.LINE, r, width=1)
        fg = P.BG if on else (P.DIM if disabled else P.TEXT)
        cy = r.centery + (g.vh(2.0) if icon else 0)
        if icon:
            g.draw_text(icon, g.vh(3.8), r.centerx, cy - g.vh(4.3), "nerd", fg, anchor="center")
        g.draw_text(label.upper(), g.vh(2.4), r.centerx, cy - g.vh(1.6), "mono-bold", fg, anchor="center", track=TRACK)
        if sub:
            g.draw_text(sub, g.vh(1.9), r.centerx, cy + g.vh(1.6), "mono", fg if on else P.MUTED, anchor="center")


class VolumeModal(Dialog):
    title = "Volume"
    hint = "◀ ▶ ▲ ▼ adjust   Enter close"
    width_pct = 40

    def body_height(self, g):
        return g.vh(6)

    def draw_body(self, g, rect):
        icon, bars, label = volume_badge(self.app.volume_level)
        g.draw_text(f"{icon}  {bars}  {label}", g.vh(3), rect.centerx, rect.centery, "mono-bold", P.TEXT, anchor="center")

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if action.direction in ("up", "right"):
                self.app.action_volume_up()
            elif action.direction in ("down", "left"):
                self.app.action_volume_down()
            self.app.clear_notifications()
        elif isinstance(action, ControlAction) and action.is_down and action.action in ("enter", "escape", "tab"):
            self.close()
        elif isinstance(action, CharacterAction):
            self.close()


class ConfirmFresh(Picker):
    title = "Clear a Room"

    def __init__(self, app, room):
        name = {"play": "Play", "music": "Music", "art": "Art"}[room]
        super().__init__(app, [(room, f"Clear {name} Room"), (None, "Go Back")])
