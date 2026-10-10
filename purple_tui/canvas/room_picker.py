"""The Esc menu: pick a room, or Volume, Clear, Time Travel, Save, Print, and the code toggle."""

import pygame

from .. import palette as P
from .. import printing
from ..constants import ICON_BROOM, ICON_ROBOT, ICON_TIME_TRAVEL, ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from . import key_save
from .paper import can_print
from .rooms.family_room import ICON_FAMILY
from .save_wall import ICON_SAVE
from .ui import Dialog, Overlay, Picker, draw_keycap, draw_scrim

ICON_PRINTER = "\U000F042A"  # nf-md-printer
EXTRA_KEYS = {"volume": "v", "clear": "c", "time_travel": "t", "save": "s", "print": "p"}
PRINTER_LABELS = {printing.NONE: "No Printer", printing.SETTING_UP: "Starting Up", printing.BROKEN: "Can't Print"}
ROWS, FAMILY, EXTRAS, CODE = "rooms", "family", "extras", "code"
MAX_FAMILY_ROOMS = 6
FAMILY_LABEL_CHARS = 12


def family_rooms() -> list:
    """Rooms from installed packs, unless the parent turned them off."""
    from ..content import get_content
    from ..settings import get_family_rooms
    return get_content().rooms[:MAX_FAMILY_ROOMS] if get_family_rooms() else []


def _short(title: str) -> str:
    return title if len(title) <= FAMILY_LABEL_CHARS else title[:FAMILY_LABEL_CHARS - 1] + "…"


class RoomPicker(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.options = list(app.rooms.values())
        self.row = ROWS
        self.col = list(app.rooms).index(app.active_room)
        self.code_row = app.room.has_code_panel and (app._code_panel_active or app._code_panel_enabled)
        self.family = family_rooms()
        self.extras = ["volume", "clear", "time_travel", "save", "print"]
        self.card_rows = [ROWS] + ([FAMILY] if self.family else []) + [EXTRAS]
        self.rows = self.card_rows + ([CODE] if self.code_row else [])
        self.printer = printing.status()

    def _disabled_volume(self):
        """Icon + label for the Volume slot when the keys are dead: Silent Mode or no audio."""
        if self.app._volume_lock == 0:
            icon, _, label = self.app._volume_badge()
            return icon, label
        if self.app.audio_ok is False:
            return ICON_VOLUME_OFF, "No Sound"
        return None

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if action.is_repeat:
                return
            d = action.direction
            if d in ("left", "right") and self.row != CODE:
                self.col = max(0, min(self._row_len() - 1, self.col + (1 if d == "right" else -1)))
            elif d in ("up", "down"):
                i = self.rows.index(self.row) + (1 if d == "down" else -1)
                self.row = self.rows[max(0, min(len(self.rows) - 1, i))]
                if self.row != CODE:
                    self.col = min(self.col, self._row_len() - 1)
            self.app.invalidate()
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            ch = action.char.lower()
            if ch.isdigit() and 0 < int(ch) <= len(self.options):
                return self.close({"room": self.options[int(ch) - 1].name})
            extra = next((e for e in self.extras if EXTRA_KEYS[e] == ch), None)
            if extra:
                self.row, self.col = EXTRAS, self.extras.index(extra)
                return self._activate()
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

    def _row_len(self) -> int:
        return {ROWS: len(self.options), FAMILY: len(self.family), EXTRAS: len(self.extras)}[self.row]

    def _activate(self):
        if self.row == ROWS:
            self.close({"room": self.options[self.col].name})
        elif self.row == FAMILY:
            self.close({"family": self.family[self.col].name})
        elif self.row == EXTRAS:
            {"volume": self._open_volume, "clear": self._confirm_clear,
             "time_travel": lambda: self.close({"time_travel": True}),
             "save": self._save,
             "print": self._print}[self.extras[self.col]]()
        else:
            self._toggle_code()

    def _toggle_code(self):
        self.close({"close_code": True} if self.app._code_panel_active else {"open_code": True})

    def _open_volume(self):
        if not self.app.volume_disabled:
            self.app.push(VolumeModal(self.app))

    def _save(self):
        if not key_save.unavailable():
            self.close({"save": True})

    def _print(self):
        why = printing.why_not()
        if why:
            self.app.notify(why, timeout=4)
        elif can_print(self.app.room):
            self.close({"print": True})

    def _confirm_clear(self):
        self.app.push(ConfirmFresh(self.app, self.app.active_room), on_close=lambda r: r and self.close({"clear_room": r}))

    def draw(self, g):
        """A wide card grid in a modal over the dimmed room: glyph above name,
        the key beneath ("or Enter" on the picked one), a line of guidance and
        the arrow cluster at the foot."""
        draw_scrim(g)
        em = g.em
        tw, th, gap, pad = em(10.6), em(7.8), em(1.1), em(2.0)
        code_h = em(4.6) if self.code_row else 0
        head_h = g.line_height(em(1.15), "mono-bold")
        foot_h = g.line_height(em(0.92), "mono")
        arrows_h = em(3.6)
        n = len(self.card_rows)
        grid_h = n * th + (n - 1) * gap + (gap + code_h if self.code_row else 0)
        lengths = {ROWS: len(self.options), FAMILY: len(self.family), EXTRAS: len(self.extras)}
        cols = max(lengths.values())
        box = pygame.Rect(0, 0, cols * tw + (cols - 1) * gap + 2 * pad,
                          pad + head_h + em(1.5) + grid_h + em(1.5) + foot_h + em(0.9) + arrows_h + pad)
        box.center = (g.w // 2, g.h // 2)
        g.rect(P.SURFACE, box, radius=em(1.0))
        g.rect(P.LINE, box, width=1, radius=em(1.0))
        y = box.y + pad
        x0 = box.x + pad
        g.draw_text("Pick a room", em(1.15), box.centerx, y, "mono-bold", P.TEXT, anchor="midtop", track=0.06)
        y += head_h + em(1.5)
        locked = self._disabled_volume()
        cards = [(ROWS, i, r.icon, r.label, str(i + 1), False) for i, r in enumerate(self.options)]
        cards += [(FAMILY, i, ICON_FAMILY, _short(r.title), "", False) for i, r in enumerate(self.family)]
        extras = {"volume": locked + ("", True) if locked else (ICON_VOLUME_HIGH, "Volume", "V", False),
                  "clear": (ICON_BROOM, "Clear", "C", False),
                  "time_travel": (ICON_TIME_TRAVEL, "Time Travel", "T", False),
                  "save": self._save_card(),
                  "print": self._print_card()}
        cards += [(EXTRAS, i, *extras[e]) for i, e in enumerate(self.extras)]
        for row, col, icon, label, key, disabled in cards:
            inset = (cols - lengths[row]) * (tw + gap) // 2
            r = pygame.Rect(x0 + inset + col * (tw + gap), y + self.card_rows.index(row) * (th + gap), tw, th)
            on = (self.row, self.col) == (row, col)
            self._card(g, r, on)
            fg = P.ON_PRIMARY if on else (P.DIM if disabled else P.TEXT)
            g.draw_text(icon, em(1.75), r.centerx, r.y + em(2.0), "nerd",
                        fg if (on or disabled) else P.ACCENT, anchor="center")
            g.draw_text(label, em(1.0), r.centerx, r.y + em(4.1), "mono-bold", fg, anchor="center")
            if key:
                g.draw_text(f"Press {key}", em(0.9), r.centerx, r.y + em(5.6), "mono", fg if on else P.DIM, anchor="center")
            if key and on:
                g.draw_text("or Enter", em(0.9), r.centerx, r.y + em(6.7), "mono", fg, anchor="center")
            elif on and not disabled and not key:
                g.draw_text("Press Enter", em(0.9), r.centerx, r.y + em(5.6), "mono", fg, anchor="center")
        y += grid_h - (code_h + gap if self.code_row else 0)
        if self.code_row:
            y += gap
            r = pygame.Rect(x0, y, cols * tw + (cols - 1) * gap, code_h)
            on = self.row == CODE
            self._card(g, r, on)
            label = "Close Code" if self.app._code_panel_active else "Open Code"
            fg = P.ON_PRIMARY if on else P.TEXT
            g.draw_text(f"{ICON_ROBOT}  {label}", em(1.0), r.centerx, r.centery - em(0.65), "mono-bold", fg, anchor="center")
            g.draw_text("Press Space or Enter" if on else "Press Space", em(0.9), r.centerx, r.centery + em(0.95),
                        "mono", fg if on else P.DIM, anchor="center")
            y += code_h
        y += em(1.5)
        g.draw_text("Enter to pick   ·   Hold Esc for grown-ups", em(0.92), box.centerx, y, "mono", P.DIM, anchor="midtop")
        self._draw_arrow_cluster(g, box.centerx, y + foot_h + em(0.9) + arrows_h - em(0.9))

    def _save_card(self):
        why = key_save.unavailable()
        return (ICON_SAVE, why, "", True) if why else (ICON_SAVE, "Save", "S", False)

    def _print_card(self):
        """Icon, label, key, disabled: the card always says what the printer is doing."""
        if self.printer == printing.READY:
            ok = can_print(self.app.room)
            return ICON_PRINTER, "Print", "P" if ok else "", not ok
        return ICON_PRINTER, PRINTER_LABELS[self.printer], "", True

    def _draw_arrow_cluster(self, g, cx, y):
        """Inverted-T keycaps beside their label, [↑] floating over [↓]."""
        px, space = g.em(0.9), g.em(0.35)
        key_w = g.measure("↓", px, "mono")[0] + round(px * 1.4)
        label_w = g.measure("Arrows move", px, "mono")[0]
        x = cx - (label_w + g.em(0.9) + 3 * key_w + 2 * space) // 2
        x = g.draw_text("Arrows move", px, x, y, "mono", P.MUTED, anchor="midleft").right + g.em(0.9)
        boxes = []
        for glyph in "←↓→":
            boxes.append(draw_keycap(g, glyph, px, x, y, color=P.ACCENT))
            x = boxes[-1].right + space
        draw_keycap(g, "↑", px, boxes[1].centerx, y - boxes[1].h - space, anchor="center", color=P.ACCENT)

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
        icon, bars, label = self.app._volume_badge()
        g.draw_text(f"{icon}  {bars}  {label}", g.em(1.3), rect.centerx, rect.centery, "mono-bold", P.TEXT, anchor="center")

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
        name = app.rooms[room].label
        super().__init__(app, [(room, f"Clear {name} Room"), (None, "Go Back")])
