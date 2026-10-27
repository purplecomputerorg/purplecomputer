"""The Esc menu, sized by what matters: the rooms as big cards, family rooms as
small pills under them, then what you can do in the room you're in, led by a
wide Code card (colors, Time Travel, Save, Open, Print, Clear follow, only the
ones it has). The computer's Volume and printer sit in the top corners."""

import pygame

from .. import palette as P
from .. import printing
from ..constants import ICON_BROOM, ICON_ROBOT, ICON_TIME_TRAVEL, ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from . import color_wheel, key_save
from .paper import can_print
from .rooms.family_room import ICON_FAMILY
from .library import ICON_OPEN, ICON_SAVE
from .ui import DOWN, LEFT, RIGHT, UP, Dialog, Overlay, Picker, arrow_keys_size, draw_arrow_keys, draw_scrim

ICON_PRINTER = "\U000F042A"  # nf-md-printer
KEYS = {"volume": "v", "clear": "c", "time_travel": "t", "save": "s", "open": "o", "print": "p",
        "colors": color_wheel.OPEN_KEY}
PRINTER_LABELS = {printing.NONE: "No Printer", printing.SETTING_UP: "Starting Up", printing.BROKEN: "Can't Print"}
VOLUME, ROWS, FAMILY, HERE = "volume", "rooms", "family", "here"
FAMILY_KEYS = "67890"  # fixed, so turning a built-in room off never renumbers a family room
MAX_FAMILY_ROOMS = len(FAMILY_KEYS)
FAMILY_LABEL_CHARS = 12
# Geometry in em, (width, gap): rooms are the biggest cards, Code the widest tool.
ROOM_CARD, TOOL_CARD, FAMILY_PILL = (10.6, 1.1), (7.8, 0.8), (12.0, 1.0)
CARD_H, TOOL_H, PILL_H, CODE_W = 7.8, 7.0, 2.6, 15.6
MAX_TOOLS = 7
PILL_W = 17.0


def family_rooms() -> list:
    """Rooms from installed packs that a parent turned on, unchanged since."""
    from ..content import get_content
    from ..settings import get_rooms_on
    on = get_rooms_on()
    return [r for r in get_content().rooms if on.get(r.key) == r.digest][:MAX_FAMILY_ROOMS]


def short_title(title: str) -> str:
    return title if len(title) <= FAMILY_LABEL_CHARS else title[:FAMILY_LABEL_CHARS - 1] + "…"


def cards(n: int, card) -> tuple:
    """(widths, gap) for a row of n same-size cards."""
    return [card[0]] * n, card[1]


def row_width(widths: list, gap: float) -> float:
    return sum(widths) + max(0, len(widths) - 1) * gap


def row_centers(widths: list, gap: float, inner_w: float) -> list:
    """Each card's center x in em from the inner left edge, so up and down land on the card nearest above or below."""
    x, centers = (inner_w - row_width(widths, gap)) / 2, []
    for w in widths:
        centers.append(x + w / 2)
        x += w + gap
    return centers


def nearest(centers: list, x: float) -> int:
    return min(range(len(centers)), key=lambda c: abs(centers[c] - x))


def draw_card(g, r, icon, label, lines=(), selected=False, dim=False, lit=False, badge=""):
    """Glyph above name, short lines beneath. Selected is filled, lit is outlined and shaded, dim is quiet.
    Rows sit where they would on a room card, scaled to this card's height; a wide card puts the glyph beside them."""
    em = g.em
    if selected:
        g.rect(P.PRIMARY, r, radius=em(0.6))
    elif lit:
        g.rect(P.FIELD, r, radius=em(0.6))
    if not selected:
        g.rect(P.LINE if lit else P.HAIR, r, width=1, radius=em(0.6))
    fg = P.ON_PRIMARY if selected else (P.DIM if dim else P.TEXT)
    ink = fg if (selected or dim) else P.ACCENT
    rows = [(label, em(1.0), "mono-bold", fg)] + [(t, em(0.9), "mono", fg if selected else P.DIM) for t in lines]
    if r.w > 2 * r.h:
        return _draw_beside(g, r, icon, ink, rows)
    at = lambda v: r.y + round(em(v) * r.h / em(CARD_H))
    if icon == "colors":
        dot = color_wheel.disc(round(em(1.75)))
        g.surface.blit(dot, dot.get_rect(center=(r.centerx, at(2.0))))
    else:
        g.draw_text(icon, em(1.75), r.centerx, at(2.0), "nerd", ink, anchor="center")
    if badge:
        g.draw_text(badge, em(1.1), r.right - em(1.0), r.y + em(1.0), "nerd", fg if selected else P.ACCENT, anchor="center")
    for i, (text, px, face, color) in enumerate(rows):
        g.draw_text(text, px, r.centerx, at((4.1, 5.6, 6.7)[i]), face, color, anchor="center")


def _draw_beside(g, r, icon, ink, rows):
    """A wide card: the glyph, then its rows left-aligned beside it, centered as one group."""
    em = g.em
    icon_w = g.measure(icon, em(2.2), "nerd")[0]
    text_w = max(g.measure(t, px, face)[0] for t, px, face, _ in rows)
    x = r.centerx - (icon_w + em(1.1) + text_w) // 2
    g.draw_text(icon, em(2.2), x, r.centery, "nerd", ink, anchor="midleft")
    y = r.centery - em(1.25) * (len(rows) - 1) // 2
    for i, (text, px, face, color) in enumerate(rows):
        g.draw_text(text, px, x + icon_w + em(1.1), y + i * em(1.25), face, color, anchor="midleft")


def draw_section(g, icon, label, x0, x1, cy):
    """A hairline with a glyph and name in its middle."""
    em = g.em
    icon_w = g.measure(icon, em(1.1), "nerd")[0]
    text_w = g.measure(label, em(0.95), "mono-bold")[0]
    left = (x0 + x1 - icon_w - em(0.5) - text_w) // 2
    g.draw_text(icon, em(1.1), left, cy, "nerd", P.ACCENT, anchor="midleft")
    right = g.draw_text(label, em(0.95), left + icon_w + em(0.5), cy, "mono-bold", P.MUTED, anchor="midleft").right
    g.rect(P.HAIR, pygame.Rect(x0, cy, left - em(1.0) - x0, 1))
    g.rect(P.HAIR, pygame.Rect(right + em(1.0), cy, x1 - right - em(1.0), 1))


def draw_pill(g, r, parts, on):
    """One line in a rounded pill: (text, px, face, color) parts, color None for the default
    (accent glyph, text label). Picked fills it, like a picked card."""
    if on:
        g.rect(P.PRIMARY, r, radius=r.h // 2)
    else:
        g.rect(P.HAIR, r, width=1, radius=r.h // 2)
    parts = [(t, px, face, P.ON_PRIMARY if on else color or (P.ACCENT if face == "nerd" else P.TEXT))
             for t, px, face, color in parts if t]
    space = g.em(0.7)
    x = r.centerx - (sum(g.measure(t, px, face)[0] for t, px, face, _ in parts) + space * (len(parts) - 1)) // 2
    label_drop = g.cap_drop(g.em(0.95), "mono-bold")
    for text, px, face, color in parts:
        y = r.centery if face == "nerd" else round(r.centery + label_drop - g.cap_drop(px, face))
        x = g.draw_text(text, px, x, y, face, color, anchor="midleft").right + space


class RoomPicker(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.options = [app.rooms[r] for r in app.kid_rooms]
        self.family = family_rooms()
        here = app.family_room
        names = [r.name for r in self.family]
        if here and here.room.name in names:
            self.row, self.col = FAMILY, names.index(here.room.name)
        else:
            self.row, self.col = ROWS, app.kid_rooms.index(app.active_room)
        code = app.room.has_code_panel and (app._code_panel_active or app._code_panel_enabled)
        self.tools = [] if here else (["code"] if code else []) + (["colors"] if color_wheel.can_open(app.room) else []) \
            + ["time_travel", "save", "open"] + (["print"] if self._printable() else []) + ["clear"]
        self.rows = [VOLUME, ROWS] + ([FAMILY] if self.family else []) + ([HERE] if self.tools else [])
        self.inner_w = max(row_width(*self._widths(r)) for r in (ROWS, FAMILY))
        self.inner_w = max(self.inner_w, row_width([CODE_W] + [TOOL_CARD[0]] * (MAX_TOOLS - 1), TOOL_CARD[1]))

    def _printable(self) -> bool:
        return printing.status() == printing.READY and can_print(self.app.room)

    def _items(self, row) -> list:
        return {VOLUME: ["volume"], ROWS: self.options, FAMILY: self.family, HERE: self.tools}[row]

    def _widths(self, row):
        """(card widths, gap) in em for a row."""
        if row == HERE:
            return [CODE_W if t == "code" else TOOL_CARD[0] for t in self.tools], TOOL_CARD[1]
        return cards(len(self._items(row)), FAMILY_PILL if row == FAMILY else ROOM_CARD)

    def _centers(self, row) -> list:
        if row == VOLUME:
            return [self.inner_w - PILL_W / 2]
        return row_centers(*self._widths(row), self.inner_w)

    def _disabled_volume(self):
        """Icon + label for the Volume pill when the keys are dead: Silent Mode or no audio."""
        if self.app._volume_lock == 0:
            icon, _, label = self.app._volume_badge()
            return icon, label
        if self.app.audio_ok is False:
            return ICON_VOLUME_OFF, "No Sound"
        return None

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if not action.is_repeat:
                self._move(action.direction)
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            ch = action.char.lower()
            if ch.isdigit() and 0 < int(ch) <= len(self.options):
                return self.close({"room": self.options[int(ch) - 1].name})
            if ch in FAMILY_KEYS[:len(self.family)]:
                return self.close({"family": self.family[FAMILY_KEYS.index(ch)].name})
            if ch == KEYS["print"] and "print" not in self.tools:
                return self._print()
            item = next((k for k, v in KEYS.items() if v == ch and k in self.tools + ["volume"]), None)
            if item:
                self.row = VOLUME if item == "volume" else HERE
                self.col = self._items(self.row).index(item)
                return self._activate()
            return self.close(None)
        if isinstance(action, ControlAction):
            a = action.action
            if a in ("volume_mute", "volume_down", "volume_up") and action.is_down:
                getattr(self.app, f"action_{a}")()
            elif a == "escape" and not action.is_down:
                self.close(None)  # on release, so a hold falls through to the app's timer
            elif a == "space" and action.is_down and not action.is_repeat and "code" in self.tools:
                self._toggle_code()
            elif a == "enter" and action.is_down and not action.is_repeat:
                self._activate()

    def _move(self, d):
        if d in ("left", "right"):
            self.col = max(0, min(len(self._items(self.row)) - 1, self.col + (1 if d == "right" else -1)))
        else:
            x = self._centers(self.row)[self.col]
            i = self.rows.index(self.row) + (1 if d == "down" else -1)
            self.row = self.rows[max(0, min(len(self.rows) - 1, i))]
            self.col = nearest(self._centers(self.row), x)
        self.app.invalidate()

    def _activate(self):
        if self.row == ROWS:
            return self.close({"room": self.options[self.col].name})
        if self.row == FAMILY:
            return self.close({"family": self.family[self.col].name})
        {"volume": self._open_volume, "clear": self._confirm_clear, "code": self._toggle_code,
         "colors": lambda: self.close({"colors": True}),
         "time_travel": lambda: self.close({"time_travel": True}),
         "save": self._save,
         "open": lambda: self.close({"open": True}),
         "print": self._print}[self._items(self.row)[self.col]]()

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
        """A modal over the dimmed room: room cards under the title, family pills
        under them, a labelled section of this room's tools, then the Parent Menu
        hint and the arrow keys. Volume and the printer take the top corners."""
        draw_scrim(g)
        em = g.em
        pad = em(2.0)
        head_h = g.line_height(em(1.15), "mono-bold")
        section_h = g.line_height(em(0.95), "mono-bold")
        arrows_h = arrow_keys_size(g, em(0.9))[1]
        family_h = em(1.2) + em(PILL_H) if self.family else 0
        tools_h = em(1.6) + section_h + em(1.0) + em(TOOL_H) if self.tools else 0
        box = pygame.Rect(0, 0, em(self.inner_w) + 2 * pad, pad + head_h + em(1.5) + em(CARD_H) + family_h
                          + tools_h + em(1.6) + arrows_h + pad)
        box.center = (g.w // 2, g.h // 2)
        g.rect(P.SURFACE, box, radius=em(1.0))
        g.rect(P.LINE, box, width=1, radius=em(1.0))
        y = box.y + pad
        g.draw_text("Pick a room", em(1.15), box.centerx, y, "mono-bold", P.TEXT, anchor="midtop", track=0.06)
        self._volume_pill(g, box.x + pad, y + head_h // 2)
        self._printer_status(g, box.x + pad, y + head_h // 2)
        y += head_h + em(1.5)
        self._card_row(g, ROWS, [(r.icon, r.label, str(i + 1), False) for i, r in enumerate(self.options)],
                       box.x + pad, y, CARD_H)
        y += em(CARD_H)
        if self.family:
            y += em(1.2)
            for col, (center, room) in enumerate(zip(self._centers(FAMILY), self.family)):
                r = pygame.Rect(0, y, em(FAMILY_PILL[0]), em(PILL_H))
                r.centerx = box.x + pad + em(center)
                on = (self.row, self.col) == (FAMILY, col)
                draw_pill(g, r, [(ICON_FAMILY, em(1.1), "nerd", None), (short_title(room.title), em(0.95), "mono-bold", None),
                                 (FAMILY_KEYS[col], em(0.85), "mono", P.DIM)], on)
            y += em(PILL_H)
        if self.tools:
            y += em(1.6)
            here = self.app.rooms[self.app.active_room]
            draw_section(g, here.icon, f"In {here.label}", box.x + pad, box.right - pad, y + section_h // 2)
            y += section_h + em(1.0)
            self._card_row(g, HERE, [self._tool(t) for t in self.tools], box.x + pad, y, TOOL_H)
        self._draw_footer(g, box.centerx, box.bottom - pad - arrows_h // 4)

    def _card_row(self, g, row, cells, x0, y, h):
        em = g.em
        for col, (center, w, cell) in enumerate(zip(self._centers(row), self._widths(row)[0], cells)):
            r = pygame.Rect(0, y, em(w), em(h))
            r.centerx = x0 + em(center)
            self._cell(g, r, *cell, on=(self.row, self.col) == (row, col))

    def _cell(self, g, r, icon, label, key, disabled, lit=False, on=False):
        """The key beneath the name, "or Enter" on the picked one. Lit (code that's on) says the key closes it."""
        enter = ("or Enter" if key else "" if disabled else "Press Enter") if on else ""
        press = key and (f"{key} closes it" if lit else f"Press {key}")
        draw_card(g, r, icon, label, [t for t in (press, enter) if t], on, disabled, lit)

    def _tool(self, tool):
        """Icon, label, key, disabled (and lit, for Code) for one of this room's tools."""
        if tool == "code":
            on = self.app._code_panel_active
            return ICON_ROBOT, "Code is on" if on else "Code", "Space", False, on
        if tool == "save":
            why = key_save.unavailable()
            return (ICON_SAVE, why, "", True) if why else (ICON_SAVE, "Save", "S", False)
        return {"colors": ("colors", "Colors", KEYS["colors"], False),
                "time_travel": (ICON_TIME_TRAVEL, "Time Travel", "T", False),
                "open": (ICON_OPEN, "Open", "O", False),
                "print": (ICON_PRINTER, "Print", "P", False),
                "clear": (ICON_BROOM, "Clear", "C", False)}[tool]

    def _printer_status(self, g, x0, cy):
        """Quiet text in the corner while there's no printer to use: what the printer is doing."""
        now = printing.status()
        if now == printing.READY:
            return
        x = g.draw_text(ICON_PRINTER, g.em(1.1), x0 + g.em(0.4), cy, "nerd", P.DIM, anchor="midleft").right + g.em(0.6)
        g.draw_text(PRINTER_LABELS[now], g.em(0.9), x, cy, "mono", P.DIM, anchor="midleft")

    def _volume_pill(self, g, x0, cy):
        """The computer's Volume, apart from the rooms: icon, name and key on one line."""
        em = g.em
        on = self.row == VOLUME
        locked = self._disabled_volume()
        icon, label = locked or (ICON_VOLUME_HIGH, "Volume")
        r = pygame.Rect(0, 0, em(PILL_W), em(PILL_H))
        r.center = (x0 + em(self._centers(VOLUME)[0]), cy)
        hint = "" if locked else ("Press V or Enter" if on else "Press V")
        draw_pill(g, r, [(icon, em(1.2), "nerd", P.DIM if locked else None), (label, em(0.95), "mono-bold", P.DIM if locked else None),
                         (hint, em(0.85), "mono", P.DIM)], on)

    def _draw_footer(self, g, cx, y):
        px = g.em(0.9)
        label = "Hold Esc for Parent Menu   ·   Arrows move"
        label_w = g.measure(label, px, "mono")[0]
        x = cx - (label_w + g.em(0.9) + arrow_keys_size(g, px)[0]) // 2
        x = g.draw_text(label, px, x, y, "mono", P.MUTED, anchor="midleft").right + g.em(0.9)
        draw_arrow_keys(g, px, x, y, color=P.ACCENT)


class VolumeModal(Dialog):
    title = "Volume"
    hint = f"{LEFT} {RIGHT} {UP} {DOWN} adjust   Enter close"
    width_pct = 48

    def body_height(self, g):
        return g.vh(6)

    def draw_body(self, g, rect):
        self.app.draw_volume(g, g.em(1.3), *rect.center)

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
