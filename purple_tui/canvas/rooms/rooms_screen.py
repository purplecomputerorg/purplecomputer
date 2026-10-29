"""Parent Menu > Rooms: every room a kid can go to, built in or from a Purple Pack, on the
cards the Esc menu shows them on. Enter turns one on or off; Littles Mode sits on top."""

import pygame

from ... import palette as P
from ...keyboard import ControlAction, NavigationAction
from ..room_picker import (MAX_FAMILY_ROOMS, ROOM_CARD, cards, short_title, draw_card, draw_section, nearest, row_centers,
                           row_width)
from ..ui import CANCELLED, DOWN, LEFT, RIGHT, UP, Dialog
from .family_room import ICON_FAMILY, room_icon

ICON_CHECKED = "\U000F0132"  # nf-md-checkbox_marked
ICON_HOME = "\U000F02DC"     # nf-md-home
COLS = 6
MIN_W = 44.0
CARD_H = 6.9
PILL_W, PILL_H = 22.0, 2.6
LITTLES = ("littles", None)
NOTES = {"on": "On", "off": "Off", "changed": "Changed", "full": "Full"}


def room_state(room, on: dict) -> str:
    """A family room that changed after it was turned on (a new pack with the same name, say) waits off."""
    if on.get(room.key) == room.digest:
        return "on"
    return "changed" if room.key in on else "off"


def core_on(app) -> list:
    return [r for r in app.rooms if r not in app._rooms_off] or list(app.rooms)


def family_on(on: dict | None = None) -> int:
    from ...content import get_content
    from ...settings import get_rooms_on
    on = get_rooms_on() if on is None else on
    return sum(room_state(r, on) == "on" for r in get_content().rooms)


def rooms_label(app) -> str:
    from ...settings import get_littles_mode
    from .parent_menu import littles_name
    littles = get_littles_mode()
    return f"Rooms: Littles Mode, {littles_name(littles)}" if littles else f"Rooms: {len(core_on(app)) + family_on()} On"


def _pack_name(room) -> str:
    from ...content import read_manifest
    return (read_manifest(room.path.parents[2]) or {}).get("name", room.pack)


class RoomsScreen(Dialog):
    """Given packs, it opens on their rooms: the step right after a pack is added."""
    title = "Rooms"
    hint = f"{LEFT} {RIGHT} {UP} {DOWN} move   Enter on or off   Esc done"
    DESCRIPTION = "Lit up rooms show in the Esc menu."
    JUST_ADDED = "Pick the rooms to turn on now. You can change this later in the Parent Menu, under Rooms."
    LITTLES_ON = "Littles Mode is on, so there's no Esc menu. These rooms come back when it's off."

    def __init__(self, app, packs=None):
        super().__init__(app)
        self.packs = packs or set()
        self.rows, self.labels = self._rows()
        self.inner_w = max(MIN_W, row_width(*cards(max(map(len, self.rows)), ROOM_CARD)))
        self.row, self.col = 1, 0
        if packs:
            self.row = next((i for i, row in enumerate(self.rows) if row[0][0] == "family" and row[0][1].pack in packs), 1)
        self._first = 1

    def _rows(self) -> tuple:
        """Navigable rows, Littles Mode first, and the section label over each group's first row."""
        from ...content import get_content
        groups = {"": [("core", name) for name in self.app.rooms]}
        for r in get_content().rooms:
            groups.setdefault(r.pack, []).append(("family", r))
        rows, labels = [[LITTLES]], {}
        for pack, items in groups.items():
            name = pack and _pack_name(items[0][1])
            labels[len(rows)] = (ICON_FAMILY, f"New: {name}" if pack in self.packs else name) if pack else (ICON_HOME, "Built In")
            rows += [items[i:i + COLS] for i in range(0, len(items), COLS)]
        return rows, labels

    @property
    def description(self) -> str:
        from ...settings import get_littles_mode
        if get_littles_mode():
            return self.LITTLES_ON
        text = self.JUST_ADDED if self.packs else self.DESCRIPTION
        return text + (f" Family rooms on: {family_on()} of {MAX_FAMILY_ROOMS}." if len(self.labels) > 1 else "")

    def _state(self, item, on: dict) -> str:
        kind, x = item
        if kind == "core":
            return "on" if x in core_on(self.app) else "off"
        state = room_state(x, on)
        return "full" if state != "on" and family_on(on) >= MAX_FAMILY_ROOMS else state

    # --- keys ---

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if not action.is_repeat:
                self._move(action.direction)
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action in ("enter", "space"):
                self._activate(self.rows[self.row][self.col])
            elif action.action == "escape":
                self.close(True)

    def _centers(self, row) -> list:
        return row_centers(*cards(len(self.rows[row]), ROOM_CARD), self.inner_w)

    def _move(self, d):
        if d in ("left", "right"):
            self.col = max(0, min(len(self.rows[self.row]) - 1, self.col + (1 if d == "right" else -1)))
        else:
            x = self._centers(self.row)[self.col]
            self.row = max(0, min(len(self.rows) - 1, self.row + (1 if d == "down" else -1)))
            self.col = nearest(self._centers(self.row), x)
        self.app.invalidate()

    def _activate(self, item):
        kind, x = item
        if kind == "littles":
            from .parent_menu import LittlesModeScreen
            return self.app.push(LittlesModeScreen(self.app), on_close=lambda m: m is not CANCELLED and self.app._apply_littles_mode(m))
        if kind == "core":
            on = core_on(self.app)
            if on == [x]:
                return self.app.notify("One room always stays on", timeout=3)
            self.app.set_room_off(x, x in on)
        else:
            from ...settings import get_rooms_on, set_room_on
            state = self._state(item, get_rooms_on())
            if state == "full":
                return self.app.notify(f"The Esc menu holds {MAX_FAMILY_ROOMS} family rooms. Turn one off first.", timeout=4)
            set_room_on(x.key, None if state == "on" else x.digest)
        self.app.invalidate()

    # --- drawing ---

    def box_width(self, g) -> int:
        return g.em(self.inner_w) + 2 * g.vw(3)

    def _heights(self, g) -> tuple:
        """(description, pill row, card row) heights."""
        desc = g.markup_size(self.description, g.em(0.92), "mono", self.inner_width(g))[1] + g.em(0.8)
        return desc, g.em(PILL_H) + g.em(0.6), g.em(1.6) + g.em(CARD_H) + g.em(0.5)

    def _shown(self, g) -> int:
        """How many card rows fit on screen."""
        desc, pill, card = self._heights(g)
        return max(1, min(len(self.rows) - 1, (self.body_limit(g) - desc - pill) // card))

    def body_height(self, g) -> int:
        desc, pill, card = self._heights(g)
        return desc + pill + self._shown(g) * card

    def draw_body(self, g, rect):
        from ...settings import get_littles_mode, get_rooms_on
        from .parent_menu import littles_name
        desc_h, pill_h, card_h = self._heights(g)
        g.draw_markup(self.description, g.em(0.92), rect.x, rect.y, "mono", P.MUTED, rect.w, "center", P.SURFACE)
        y = rect.y + desc_h
        self._pill(g, rect.centerx, y + g.em(PILL_H) // 2, f"Littles Mode: {littles_name(get_littles_mode())}", self.row == 0)
        y += pill_h
        n = self._shown(g)
        row = max(self.row, 1)  # Littles Mode scrolls to the top
        self._first = min(max(self._first, row - n + 1), row)
        on = get_rooms_on()
        for i in range(self._first, self._first + n):
            self._card_row(g, i, rect, y, on)
            y += card_h

    def _card_row(self, g, i, rect, y, on):
        em = g.em
        label = self.labels.get(i)
        if label:
            draw_section(g, *label, rect.x, rect.right, y + em(0.7))
        more = UP if i == self._first > 1 else DOWN if i == self._first + self._shown(g) - 1 < len(self.rows) - 1 else None
        if more:
            g.draw_text(more, em(0.98), rect.right + em(1.1), y + em(1.6 + CARD_H / 2), "mono", P.MUTED, anchor="center")
        for col, (center, item) in enumerate(zip(self._centers(i), self.rows[i])):
            r = pygame.Rect(0, y + em(1.6), em(ROOM_CARD[0]), em(CARD_H))
            r.centerx = rect.x + em(center)
            state = self._state(item, on)
            kind, x = item
            icon, name = (self.app.rooms[x].icon, self.app.rooms[x].label) if kind == "core" else (room_icon(x), short_title(x.title))
            draw_card(g, r, icon, name, [NOTES[state]], (self.row, self.col) == (i, col),
                      dim=state != "on", lit=state == "on", badge=ICON_CHECKED if state == "on" else "")

    def _pill(self, g, cx, cy, text, selected):
        r = pygame.Rect(0, 0, g.em(PILL_W), g.em(PILL_H))
        r.center = (cx, cy)
        if selected:
            g.rect(P.PRIMARY, r, radius=r.h // 2)
        else:
            g.rect(P.LINE, r, width=1, radius=r.h // 2)
        g.draw_text(text, g.em(0.95), cx, cy, "mono-bold", P.ON_PRIMARY if selected else P.TEXT, anchor="center")
