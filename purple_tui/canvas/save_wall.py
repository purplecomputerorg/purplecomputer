"""The Save wall (Esc, S): the first tile saves what's on screen, the rest are
this room's saves, newest first. Enter opens one, P prints it, holding
Backspace removes it."""

import time

import pygame

from .. import palette as P
from .. import printing
from ..constants import ICON_ROBOT
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from . import saves
from .saves import fit
from .paper import artwork
from .ui import Overlay, draw_bar, draw_label, draw_scrim, draw_window

ICON_SAVE = "\U000F0193"  # nf-md-content_save
COLS, ROWS_SHOWN = 4, 2
DELETE_HOLD_S = 1.2
NOW = "now"


class SaveWall(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.saves = saves.list_saves(app.active_room)
        self.now_work = artwork(app.room, app.g)
        self.selected = 0
        self.top_row = 0
        self._thumbs: dict = {}
        self._deleting = None   # (save, started) while Backspace is held on it
        self._hold_timers: list = []
        self.can_print = printing.status() == printing.READY

    @property
    def tiles(self) -> list:
        return [NOW] + self.saves

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
            elif not action.is_repeat and self.selected > 0:
                self._start_delete(self.tiles[self.selected])
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == "escape":
                self.close()
            elif action.action == "enter":
                self._activate()
        elif isinstance(action, CharacterAction) and not action.is_repeat and action.char.lower() == "p":
            self._print()

    def _select(self, index: int):
        self._stop_delete()
        self.selected = max(0, min(len(self.tiles) - 1, index))
        row = self.selected // COLS
        self.top_row = min(max(self.top_row, row - ROWS_SHOWN + 1), row)
        self.app.invalidate()

    def _activate(self):
        if self.selected == 0:
            return self._save()
        self.close()
        self.app.open_save(self.tiles[self.selected])

    def _save(self):
        result = self.app.save_room()
        if result is False:
            return self.app.notify("Make something first, then save it", timeout=3)
        self.close()
        self.app.notify(f"{ICON_SAVE}  Saved" if result else f"{ICON_SAVE}  Already saved", timeout=2)

    def _print(self):
        why = printing.why_not()
        if why:
            return self.app.notify(why, timeout=4)
        tile = self.tiles[self.selected]
        self.close()
        self.app.action_print() if tile is NOW else self.app.print_save(tile)

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
        saves.delete(save)
        self.saves.remove(save)
        self._select(self.selected)

    def _delete_progress(self, tile) -> float:
        if self._deleting is None or self._deleting[0] is not tile:
            return 0.0
        return min(1.0, (time.monotonic() - self._deleting[1]) / DELETE_HOLD_S)

    # ---------------------------------------------------------------- drawing
    def _thumb(self, tile, w: int, h: int):
        key = (tile if tile is NOW else tile.id, w, h)
        if key not in self._thumbs:
            source = self.now_work if tile is NOW else tile.thumbnail()
            self._thumbs[key] = None if source is None else fit(source, w, h)
        return self._thumbs[key]

    def draw(self, g):
        draw_scrim(g)
        em = g.em
        tw, ih, label_h, gap, pad = em(12.5), em(9.4), em(2.6), em(1.1), em(1.8)
        hint_h = g.line_height(em(0.92), "mono")
        th = ih + label_h
        box = pygame.Rect(0, 0, COLS * tw + (COLS - 1) * gap + 2 * pad, 0)
        box.h = em(3.0) + pad + ROWS_SHOWN * th + (ROWS_SHOWN - 1) * gap + em(1.2) + hint_h + pad
        box.center = (g.w // 2, g.h // 2)
        from .app import ROOM_ICONS, ROOMS
        room = self.app.active_room
        y0 = draw_window(g, box, f"{ICON_SAVE}  Save  ·  {ROOM_ICONS[room]} {dict(ROOMS)[room]}") + pad
        first = self.top_row * COLS
        for i, tile in enumerate(self.tiles[first:first + COLS * ROWS_SHOWN], start=first):
            row, col = divmod(i - first, COLS)
            self._draw_tile(g, pygame.Rect(box.x + pad + col * (tw + gap), y0 + row * (th + gap), tw, ih), i, tile)
        if not self.saves:
            r = pygame.Rect(box.x + pad + tw + gap, y0, (COLS - 1) * (tw + gap) - gap, ih)
            g.draw_markup("[dim]What you save shows up here.\nCome back any time to open it again.[/]", em(0.95),
                          r.x, r.centery - em(1.3), "mono", P.MUTED, r.w, "center", P.SURFACE)
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
        else:
            g.draw_text("Nothing yet", em(0.9), r.centerx, r.centery, "mono", P.DIM, anchor="center")
        if tile is NOW:
            label = f"{ICON_SAVE} Save this"
        else:
            label = tile.when() + (f"  {ICON_ROBOT}" if tile.has_code else "")
        draw_label(g, label, em(0.92), r.centerx, r.bottom + em(1.4), P.TEXT if tile is NOW else P.MUTED,
                   anchor="center", on=on)
        progress = self._delete_progress(tile)
        if progress > 0:
            draw_bar(g, r.x + em(0.6), r.bottom - em(1.2), r.w - em(1.2), em(0.6), progress, P.DANGER)

    def _draw_hint(self, g, box, y, h):
        if self.selected == 0:
            hint = "Enter: save"
        else:
            hint = "Enter: open    Hold ⌫: remove"
        if self.can_print:
            hint += "    P: print"
        rows = (len(self.tiles) + COLS - 1) // COLS
        more = ("▲ " if self.top_row > 0 else "") + ("▼ more" if self.top_row + ROWS_SHOWN < rows else "")
        g.draw_text(f"{hint}    Esc: close", g.em(0.92), box.centerx, y + h // 2, "mono", P.DIM, anchor="center")
        if more:
            g.draw_text(more.strip(), g.em(0.92), box.right - g.em(1.8), y + h // 2, "mono", P.DIM, anchor="midright")
