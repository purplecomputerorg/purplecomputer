"""Saved work: what a kid chose to keep, one folder per room, newest first.

A save is <ms>-<digest>.json (the room's state, code lines included) beside
<ms>-<digest>.thumb.png, a small picture of it for the wall. Opening a save
loads the state; printing and copying to a USB stick redraw it at full size
(PurpleApp.save_artwork), which keeps a save small enough for the Key's
PURPLE-SAVE. The digest makes saving the same work twice a no-op.
"""

import hashlib
import json
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import pygame

from ..timeline import state_dir

THUMB_PX = 320  # longest side; wall tiles are about this wide on a 1920px screen
_ram_dir = None


def fit(surface, w: int, h: int):
    """Scaled to fit inside w x h, keeping its shape."""
    k = min(w / surface.get_width(), h / surface.get_height())
    size = (max(1, round(surface.get_width() * k)), max(1, round(surface.get_height() * k)))
    try:
        return pygame.transform.smoothscale(surface, size)
    except ValueError:
        return pygame.transform.scale(surface, size)


def saves_dir() -> Path:
    global _ram_dir
    base = state_dir("saves", "PURPLE_SAVES_DIR")
    if base is None:
        _ram_dir = _ram_dir or Path(tempfile.mkdtemp(prefix="purple-saves-"))
        base = _ram_dir
    return base


def _digest(state: dict) -> str:
    return hashlib.sha1(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


class Save:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.stem
        self._data = None

    @property
    def data(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                self._data = {}
        return self._data

    @property
    def state(self) -> dict:
        return self.data.get("state", {})

    @property
    def landscape(self) -> bool:
        return self.data.get("landscape", True)

    @property
    def has_code(self) -> bool:
        return any(k.startswith("code:") for k in self.state)

    @property
    def room(self) -> str:
        return self.path.parent.name

    def thumbnail(self):
        return _load(_thumb_path(self.path))

    @property
    def made(self) -> datetime:
        return datetime.fromtimestamp(int(self.id.split("-")[0]) / 1000)

    def when(self, today: date | None = None) -> str:
        today = today or date.today()
        days = (today - self.made.date()).days
        if days == 0:
            return "Today"
        if days == 1:
            return "Yesterday"
        return self.made.strftime("%A" if 0 < days < 7 else "%b %-d")


def _thumb_path(path: Path) -> Path:
    return path.with_suffix(".thumb.png")


def _load(path: Path):
    try:
        return pygame.image.load(str(path))
    except (pygame.error, OSError):
        return None


def list_saves(room: str) -> list[Save]:
    folder = saves_dir() / room
    return [Save(p) for p in sorted(folder.glob("*.json"), reverse=True)] if folder.is_dir() else []


def add(room: str, state: dict, image: pygame.Surface, landscape: bool) -> Save | None:
    """Write a new save with a thumbnail of image, or None when this exact work is already saved (or the disk refused)."""
    digest = _digest(state)
    folder = saves_dir() / room
    if any(folder.glob(f"*-{digest}.json")):
        return None
    path = folder / f"{int(time.time() * 1000)}-{digest}.json"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        pygame.image.save(fit(image, THUMB_PX, THUMB_PX), str(_thumb_path(path)))
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"state": state, "landscape": landscape}, separators=(",", ":")))
        tmp.replace(path)  # the .json landing is what makes the save exist
    except (OSError, pygame.error):
        return None
    return Save(path)


def delete(save: Save):
    for p in (save.path, _thumb_path(save.path)):
        try:
            p.unlink()
        except OSError:
            pass
