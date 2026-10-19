"""The Esc menu, in three parts: rooms to go to; what you can do in the room
you're in (code, colors, Time Travel, Save, Open, Print, Clear, only the ones
it has); and the computer's Volume, tucked in the corner."""

import pygame

from .. import palette as P
from .. import printing
from ..constants import ICON_BROOM, ICON_ROBOT, ICON_TIME_TRAVEL, ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from . import color_wheel, key_save
from .paper import can_print
from .rooms.family_room import ICON_FAMILY
from .library import ICON_OPEN, ICON_SAVE
from .ui import DOWN, LEFT, RIGHT, UP, Dialog, Overlay, Picker, arrow_keys_size, draw_arrow_keys, draw_key_hint, draw_scrim

ICON_PRINTER = "\U000F042A"  # nf-md-printer
KEYS = {"volume": "v", "clear": "c", "time_travel": "t", "save": "s", "open": "o", "print": "p",
        "colors": color_wheel.OPEN_KEY}
PRINTER_LABELS = {printing.NONE: "No Printer", printing.SETTING_UP: "Starting Up", printing.BROKEN: "Can't Print"}
VOLUME, ROWS, FAMILY, HERE = "volume", "rooms", "family", "here"
MAX_FAMILY_ROOMS = 6
FAMILY_LABEL_CHARS = 12
# Card geometry in em, (width, gap): room cards are wider than the tools under them.
ROOM_CARD, TOOL_CARD, CARD_H = (10.6, 1.1), (8.6, 0.9), 7.8
MAX_TOOLS = 7
PILL_W = 17.0
CLOSE_CODE_HINT = f"{ICON_ROBOT} Code is open.   {{Space}} closes it"


def family_rooms() -> list:
    """Rooms from installed packs that a parent turned on, unchanged since."""
    from ..content import get_content
    from ..settings import get_rooms_on
    on = get_rooms_on()
    return [r for r in get_content().rooms if on.get(r.key) == r.digest][:MAX_FAMILY_ROOMS]


def _short(title: str) -> str:
    return title if len(title) <= FAMILY_LABEL_CHARS else title[:FAMILY_LABEL_CHARS - 1] + "…"


def _row_width(n: int, card) -> float:
    w, gap = card
    return n * w + max(0, n - 1) * gap


class RoomPicker(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.options = [app.rooms[r] for r in app.kid_rooms]
        self.row = ROWS
        self.col = app.kid_rooms.index(app.active_room)
        code = app.room.has_code_panel and (app._code_panel_active or app._code_panel_enabled)
        self.tools = (["code"] if code else []) + (["colors"] if color_wheel.can_open(app.room) else []) \
            + ["time_travel", "save", "open", "print", "clear"]
        self.family = family_rooms()
        self.rows = [VOLUME, ROWS] + ([FAMILY] if self.family else []) + [HERE]
        self.printer = printing.status()
        self.inner_w = max(_row_width(len(self.options), ROOM_CARD), _row_width(len(self.family), ROOM_CARD),
                           _row_width(MAX_TOOLS, TOOL_CARD))

    def _items(self, row) -> list:
        return {VOLUME: ["volume"], ROWS: self.options, FAMILY: self.family, HERE: self.tools}[row]

    def _centers(self, row) -> list:
        """Each card's center x in em from the inner left edge, so up and down land on the card nearest above or below."""
        if row == VOLUME:
            return [self.inner_w - PILL_W / 2]
        n = len(self._items(row))
        w, gap = TOOL_CARD if row == HERE else ROOM_CARD
        return [self.inner_w / 2 + (i - (n - 1) / 2) * (w + gap) for i in range(n)]

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
            centers = self._centers(self.row)
            self.col = min(range(len(centers)), key=lambda c: abs(centers[c] - x))
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
        """A modal over the dimmed room: room cards under the title with Volume
        in the corner, a labelled section of this room's tools, then the
        Parent Menu hint and the arrow keys."""
        draw_scrim(g)
        em = g.em
        pad, card_h = em(2.0), em(CARD_H)
        head_h = g.line_height(em(1.15), "mono-bold")
        section_h = g.line_height(em(0.95), "mono-bold")
        arrows_h = arrow_keys_size(g, em(0.9))[1]
        room_rows = [r for r in (ROWS, FAMILY) if r in self.rows]
        grid_h = len(room_rows) * card_h + (len(room_rows) - 1) * em(ROOM_CARD[1])
        banner_h = em(4.2) if self.app._code_panel_active else 0
        box = pygame.Rect(0, 0, em(self.inner_w) + 2 * pad,
                          pad + head_h + em(1.5) + banner_h + grid_h + em(1.6) + section_h + em(1.0) + card_h + em(1.6) + arrows_h + pad)
        box.center = (g.w // 2, g.h // 2)
        g.rect(P.SURFACE, box, radius=em(1.0))
        g.rect(P.LINE, box, width=1, radius=em(1.0))
        y = box.y + pad
        g.draw_text("Pick a room", em(1.15), box.centerx, y, "mono-bold", P.TEXT, anchor="midtop", track=0.06)
        self._volume_pill(g, box.x + pad, y + head_h // 2)
        y += head_h + em(1.5)
        if banner_h:
            self._close_code_banner(g, pygame.Rect(box.x + pad, y, em(self.inner_w), banner_h - em(1.2)))
            y += banner_h
        for row in room_rows:
            if row == ROWS:
                cells = [(r.icon, r.label, str(i + 1), False) for i, r in enumerate(self.options)]
            else:
                cells = [(ICON_FAMILY, _short(r.title), "", False) for r in self.family]
            self._card_row(g, row, cells, box.x + pad, y, ROOM_CARD)
            y += card_h + em(ROOM_CARD[1])
        y += em(1.6) - em(ROOM_CARD[1])
        here = self.app.rooms[self.app.active_room]
        self._section(g, here.icon, f"In {here.label}", box.x + pad, box.right - pad, y + section_h // 2)
        y += section_h + em(1.0)
        self._card_row(g, HERE, [self._tool(t) for t in self.tools], box.x + pad, y, TOOL_CARD)
        self._draw_footer(g, box.centerx, box.bottom - pad - arrows_h // 4)

    def _close_code_banner(self, g, r):
        """Open code hides the room, so how to close it gets its own band, not just a card."""
        g.rect(P.FIELD, r, radius=g.em(0.6))
        g.rect(P.LINE, r, width=1, radius=g.em(0.6))
        draw_key_hint(g, CLOSE_CODE_HINT, g.em(1.15), r.centerx, r.centery, color=P.ACCENT, anchor="center")

    def _card_row(self, g, row, cells, x0, y, card):
        em = g.em
        for col, (center, cell) in enumerate(zip(self._centers(row), cells)):
            r = pygame.Rect(0, y, em(card[0]), em(CARD_H))
            r.centerx = x0 + em(center)
            self._cell(g, r, *cell, (self.row, self.col) == (row, col))

    def _cell(self, g, r, icon, label, key, disabled, on):
        """Glyph above name, the key beneath, "or Enter" on the picked one."""
        em = g.em
        self._card(g, r, on)
        fg = P.ON_PRIMARY if on else (P.DIM if disabled else P.TEXT)
        if icon == "colors":
            dot = color_wheel.disc(round(em(1.75)))
            g.surface.blit(dot, dot.get_rect(center=(r.centerx, r.y + em(2.0))))
        else:
            g.draw_text(icon, em(1.75), r.centerx, r.y + em(2.0), "nerd", fg if (on or disabled) else P.ACCENT, anchor="center")
        g.draw_text(label, em(1.0), r.centerx, r.y + em(4.1), "mono-bold", fg, anchor="center")
        if key:
            g.draw_text(f"Press {key}", em(0.9), r.centerx, r.y + em(5.6), "mono", fg if on else P.DIM, anchor="center")
        if key and on:
            g.draw_text("or Enter", em(0.9), r.centerx, r.y + em(6.7), "mono", fg, anchor="center")
        elif on and not disabled and not key:
            g.draw_text("Press Enter", em(0.9), r.centerx, r.y + em(5.6), "mono", fg, anchor="center")

    def _section(self, g, icon, label, x0, x1, cy):
        """A hairline with the room's glyph and name in its middle."""
        em = g.em
        icon_w = g.measure(icon, em(1.1), "nerd")[0]
        text_w = g.measure(label, em(0.95), "mono-bold")[0]
        left = (x0 + x1 - icon_w - em(0.5) - text_w) // 2
        g.draw_text(icon, em(1.1), left, cy, "nerd", P.ACCENT, anchor="midleft")
        right = g.draw_text(label, em(0.95), left + icon_w + em(0.5), cy, "mono-bold", P.MUTED, anchor="midleft").right
        g.rect(P.HAIR, pygame.Rect(x0, cy, left - em(1.0) - x0, 1))
        g.rect(P.HAIR, pygame.Rect(right + em(1.0), cy, x1 - right - em(1.0), 1))

    def _tool(self, tool):
        """Icon, label, key, disabled for one of this room's tools."""
        if tool == "code":
            return ICON_ROBOT, "Close Code" if self.app._code_panel_active else "Code", "Space", False
        if tool == "save":
            why = key_save.unavailable()
            return (ICON_SAVE, why, "", True) if why else (ICON_SAVE, "Save", "S", False)
        if tool == "print":
            return self._print_card()
        return {"colors": ("colors", "Colors", KEYS["colors"], False),
                "time_travel": (ICON_TIME_TRAVEL, "Time Travel", "T", False),
                "open": (ICON_OPEN, "Open", "O", False),
                "clear": (ICON_BROOM, "Clear", "C", False)}[tool]

    def _print_card(self):
        """The card always says what the printer is doing."""
        if self.printer == printing.READY:
            ok = can_print(self.app.room)
            return ICON_PRINTER, "Print", "P" if ok else "", not ok
        return ICON_PRINTER, PRINTER_LABELS[self.printer], "", True

    def _volume_pill(self, g, x0, cy):
        """The computer's Volume, apart from the rooms: icon, name and key on one line."""
        em = g.em
        on = self.row == VOLUME
        locked = self._disabled_volume()
        icon, label = locked or (ICON_VOLUME_HIGH, "Volume")
        r = pygame.Rect(0, 0, em(PILL_W), em(2.6))
        r.center = (x0 + em(self._centers(VOLUME)[0]), cy)
        if on:
            g.rect(P.PRIMARY, r, radius=r.h // 2)
        else:
            g.rect(P.HAIR, r, width=1, radius=r.h // 2)
        fg = P.ON_PRIMARY if on else (P.DIM if locked else P.TEXT)
        hint = "" if locked else ("Press V or Enter" if on else "Press V")
        parts = [p for p in [(icon, em(1.2), "nerd", fg if (on or locked) else P.ACCENT),
                             (label, em(0.95), "mono-bold", fg),
                             (hint, em(0.85), "mono", fg if on else P.DIM)] if p[0]]
        space = em(0.7)
        x = r.centerx - (sum(g.measure(t, px, face)[0] for t, px, face, _ in parts) + space * (len(parts) - 1)) // 2
        label_drop = g.cap_drop(em(0.95), "mono-bold")
        for text, px, face, color in parts:
            y = cy if face == "nerd" else round(cy + label_drop - g.cap_drop(px, face))
            x = g.draw_text(text, px, x, y, face, color, anchor="midleft").right + space

    def _draw_footer(self, g, cx, y):
        px = g.em(0.9)
        label = "Hold Esc for Parent Menu   ·   Arrows move"
        label_w = g.measure(label, px, "mono")[0]
        x = cx - (label_w + g.em(0.9) + arrow_keys_size(g, px)[0]) // 2
        x = g.draw_text(label, px, x, y, "mono", P.MUTED, anchor="midleft").right + g.em(0.9)
        draw_arrow_keys(g, px, x, y, color=P.ACCENT)

    def _card(self, g, r, on):
        if on:
            g.rect(P.PRIMARY, r, radius=g.em(0.6))
        else:
            g.rect(P.HAIR, r, width=1, radius=g.em(0.6))


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
