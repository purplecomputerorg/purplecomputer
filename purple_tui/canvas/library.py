"""Open (Esc, O): this room's saves, newest first, and in Art the pictures the
family added from Purple Studio. Enter opens one, P prints it, holding
Backspace removes a save."""

import time

import pygame

from .. import palette as P
from .. import printing
from ..constants import ICON_ROBOT
from ..content import get_content
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from . import saves
from .saves import fit
from .secret_doodle import paint_picture
from .ui import Overlay, draw_bar, draw_label, draw_scrim, draw_window

ICON_SAVE = "\U000F0193"  # nf-md-content_save
ICON_OPEN = "\U000F0770"  # nf-md-folder_open
ICON_HOME = "\U000F02DC"  # nf-md-home
COLS, ROWS_SHOWN = 4, 2
DELETE_HOLD_S = 1.2
FILL_BUDGET_S = 0.03  # drawing new pictures stops for the frame after this, so Open shows at once and fills in
LABEL_CHARS = 14


class PictureTile:
    """A pack picture as the library sees a save: its Art state is the picture painted on a fresh canvas."""
    room = "art"
    landscape = True
    has_code = False

    def __init__(self, app, picture):
        self.app = app
        self.picture = picture
        self.id = f"picture-{picture.name}"
        self._state = None

    @property
    def state(self) -> dict:
        if self._state is None:
            art = self.app.offscreen("art")
            paint_picture(art, self.picture.ops, self.picture.letters)
            self._state = art.timeline_state()
        return self._state

    def when(self) -> str:
        name = self.picture.title
        return f"{ICON_HOME} {name if len(name) <= LABEL_CHARS else name[:LABEL_CHARS - 1] + '…'}"


class Library(Overlay):
    def __init__(self, app):
        super().__init__(app)
        pictures = get_content().pictures if app.active_room == "art" else []
        self.tiles = saves.list_saves(app.active_room) + [PictureTile(app, p) for p in pictures]
        self.selected = 0
        self.top_row = 0
        self._thumbs = app.save_pictures
        self._deadline, self._filling = None, False
        self._deleting = None   # (save, started) while Backspace is held on it
        self._hold_timers: list = []
        self.can_print = printing.status() == printing.READY

    def on_close(self):
        self._stop_delete()

    # ---------------------------------------------------------------- keys
    async def handle(self, action):
        if isinstance(action, NavigationAction):
            step = {"left": -1, "right": 1, "up": -COLS, "down": COLS}[action.direction]
            self._select(self.selected + step)
        elif isinstance(action, ControlAction) and action.action == "backspace":
            if not action.is_down:
                self._stop_delete()
            elif not action.is_repeat and self._removable(self._tile()):
                self._start_delete(self._tile())
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == "escape":
                self.close()
            elif action.action == "enter" and self.tiles:
                self.close()
                self.app.open_save(self._tile())
        elif isinstance(action, CharacterAction) and not action.is_repeat and action.char.lower() == "p":
            self._print()

    def _tile(self):
        return self.tiles[self.selected] if self.tiles else None

    @staticmethod
    def _removable(tile) -> bool:
        return isinstance(tile, saves.Save)

    def _select(self, index: int):
        self._stop_delete()
        self.selected = max(0, min(len(self.tiles) - 1, index))
        row = self.selected // COLS
        self.top_row = min(max(self.top_row, row - ROWS_SHOWN + 1), row)
        self.app.invalidate()

    def _print(self):
        why = printing.why_not()
        if why:
            return self.app.notify(why, timeout=4)
        if self.tiles:
            self.close()
            self.app.print_save(self._tile())

    def _start_delete(self, save):
        self._stop_delete()
        self._deleting = (save, time.monotonic())
        self._hold_timers = [self.app.timers.after(DELETE_HOLD_S, self._finish_delete),
                             self.app.timers.every(1 / 30, self.app.invalidate)]

    def _stop_delete(self):
        for t in self._hold_timers:
            t.stop()
        self._hold_timers, self._deleting = [], None
        self.app.invalidate()

    def _finish_delete(self):
        save = self._deleting[0]
        self._stop_delete()
        self.app.delete_save(save)
        self.tiles.remove(save)
        self._select(self.selected)

    def _delete_progress(self, tile) -> float:
        if self._deleting is None or self._deleting[0] is not tile:
            return 0.0
        return min(1.0, (time.monotonic() - self._deleting[1]) / DELETE_HOLD_S)

    # ---------------------------------------------------------------- drawing
    def _thumb(self, tile, w: int, h: int):
        key = (tile.id, w, h)
        if key not in self._thumbs:
            now = time.monotonic()
            self._deadline = self._deadline or now + FILL_BUDGET_S   # the frame's first new picture always draws
            if now > self._deadline:
                self._filling = True
                return None
        return self._thumbs.get_or(key, lambda: self._picture(tile, w, h)) or None

    def _picture(self, tile, w: int, h: int):
        source = self.app.save_artwork(tile, on_screen=True)
        return False if source is None else fit(source, w, h)  # False is cached, None would be redrawn

    def draw(self, g):
        self._deadline, self._filling = None, False
        self._draw(g)
        if self._filling:
            self.app.timers.after(0, self.app.invalidate)   # a draw's own invalidate is cleared when the frame lands

    def _draw(self, g):
        draw_scrim(g)
        em = g.em
        tw, ih, label_h, gap, pad = em(12.5), em(9.4), em(2.6), em(1.1), em(1.8)
        hint_h = g.line_height(em(0.92), "mono")
        th = ih + label_h
        box = pygame.Rect(0, 0, COLS * tw + (COLS - 1) * gap + 2 * pad, 0)
        box.h = em(3.0) + pad + ROWS_SHOWN * th + (ROWS_SHOWN - 1) * gap + em(1.2) + hint_h + pad
        box.center = (g.w // 2, g.h // 2)
        y0 = draw_window(g, box, f"{ICON_OPEN}  Open  ·  {self.app.room.icon} {self.app.room.label}") + pad
        first = self.top_row * COLS
        for i, tile in enumerate(self.tiles[first:first + COLS * ROWS_SHOWN], start=first):
            row, col = divmod(i - first, COLS)
            self._draw_tile(g, pygame.Rect(box.x + pad + col * (tw + gap), y0 + row * (th + gap), tw, ih), i, tile)
        if not self.tiles:
            g.draw_markup("[dim]Nothing saved yet.\nSave something from the Esc menu and it shows up here.[/]", em(0.95),
                          box.x + pad, y0 + th - em(1.3), "mono", P.MUTED, box.w - 2 * pad, "center", P.SURFACE)
        self._draw_hint(g, box, box.bottom - pad - hint_h, hint_h)

    def _draw_tile(self, g, r: pygame.Rect, i: int, tile):
        em = g.em
        on = i == self.selected
        if on:
            g.rect(P.PRIMARY, r.inflate(em(0.6), em(0.6)), radius=em(0.7))
        g.rect(P.BG, r, radius=em(0.5))
        thumb = self._thumb(tile, r.w - em(0.8), r.h - em(0.8))
        if thumb is not None:
            g.surface.blit(thumb, thumb.get_rect(center=r.center))
        label = tile.when() + (f"  {ICON_ROBOT}" if tile.has_code else "")
        draw_label(g, label, em(0.92), r.centerx, r.bottom + em(1.4), P.MUTED, anchor="center", on=on)
        progress = self._delete_progress(tile)
        if progress > 0:
            draw_bar(g, r.x + em(0.6), r.bottom - em(1.2), r.w - em(1.2), em(0.6), progress, P.DANGER)

    def _draw_hint(self, g, box, y, h):
        hint = "Enter: open" if self.tiles else ""
        if self._removable(self._tile()):
            hint += "    Hold ⌫: remove"
        if self.can_print and self.tiles:
            hint += "    P: print"
        rows = (len(self.tiles) + COLS - 1) // COLS
        more = ("▲ " if self.top_row > 0 else "") + ("▼ more" if self.top_row + ROWS_SHOWN < rows else "")
        g.draw_text(f"{hint}    Esc: close".strip(), g.em(0.92), box.centerx, y + h // 2, "mono", P.DIM, anchor="center")
        if more:
            g.draw_text(more.strip(), g.em(0.92), box.right - g.em(1.8), y + h // 2, "mono", P.DIM, anchor="midright")
