"""The Esc menu: pick a room, or Volume, Clear, Time Travel, and the code toggle."""

import pygame

from . import palette as P
from .constants import (
    ICON_BROOM, ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_ROBOT, ICON_TIME_TRAVEL,
    ICON_VOLUME_HIGH, ICON_VOLUME_OFF,
)
from .keyboard import CharacterAction, ControlAction, NavigationAction
from .ui import Dialog, Overlay, Picker, draw_scrim, volume_badge

ROOM_OPTIONS = [("play", ICON_CHAT, "Play"), ("music", ICON_MUSIC, "Music"), ("art", ICON_PALETTE, "Art")]
NUMBER_KEY_ROOMS = {"1": "play", "2": "music", "3": "art"}
ROWS, EXTRAS, CODE = 0, 1, 2


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
        """Centered card grid inside the frame, spaced in the mock's ems:
        glyph above name, the key beneath, one line of guidance."""
        draw_scrim(g, 240)
        g.rect(P.LINE, self.app._frame_rect(self.app._viewport_rect()), width=1, radius=g.em(0.6))
        em = g.em
        tw, th, gap = em(10.6), em(7.6), em(1.1)
        code_h = em(4.6) if self.code_row else 0
        head_h = g.line_height(em(1.15), "mono-bold")
        foot_h = g.line_height(em(0.92), "mono")
        total = head_h + em(1.5) + 2 * th + gap + (gap + code_h if self.code_row else 0) + em(1.5) + foot_h
        y = (g.h - total) // 2
        x0 = g.w // 2 - (3 * tw + 2 * gap) // 2
        g.draw_text("Pick a room", em(1.15), g.w // 2, y, "mono-bold", P.TEXT, anchor="midtop", track=0.06)
        y += head_h + em(1.5)
        locked = self._locked_volume()
        cards = [(ROWS, i, icon, label, str(i + 1), False) for i, (_, icon, label) in enumerate(ROOM_OPTIONS)]
        cards += [(EXTRAS, 0, *(locked + ("", True) if locked else (ICON_VOLUME_HIGH, "Volume", "V", False))),
                  (EXTRAS, 1, ICON_BROOM, "Clear", "C", False),
                  (EXTRAS, 2, ICON_TIME_TRAVEL, "Time Travel", "T", False)]
        for row, col, icon, label, key, disabled in cards:
            r = pygame.Rect(x0 + col * (tw + gap), y + row * (th + gap), tw, th)
            on = (self.row, self.col) == (row, col)
            self._card(g, r, on)
            fg = P.ON_PRIMARY if on else (P.DIM if disabled else P.TEXT)
            g.draw_text(icon, em(1.75), r.centerx, r.y + em(2.1), "nerd",
                        fg if (on or disabled) else P.ACCENT, anchor="center")
            g.draw_text(label, em(1.0), r.centerx, r.y + em(4.35), "mono-bold", fg, anchor="center")
            if key:
                g.draw_text(key, em(0.9), r.centerx, r.y + em(5.95), "mono",
                            fg if on else P.DIM, anchor="center")
        y += 2 * th + gap
        if self.code_row:
            y += gap
            r = pygame.Rect(x0, y, 3 * tw + 2 * gap, code_h)
            on = self.row == CODE
            self._card(g, r, on)
            label = "Close Code" if self.app._code_panel_active else "Open Code"
            fg = P.ON_PRIMARY if on else P.TEXT
            g.draw_text(f"{ICON_ROBOT}  {label}", em(1.0), r.centerx, r.centery - em(0.65), "mono-bold", fg, anchor="center")
            g.draw_text("Space", em(0.9), r.centerx, r.centery + em(0.95), "mono", fg if on else P.DIM, anchor="center")
            y += code_h
        g.draw_text("Enter to pick   ·   Hold Esc for grown-ups", em(0.92), g.w // 2, y + em(1.5), "mono", P.DIM, anchor="midtop")

    def _card(self, g, r, on):
        if on:
            g.rect(P.PRIMARY, r, radius=g.em(0.6))
        else:
            g.rect(P.HAIR, r, width=1, radius=g.em(0.6))


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
