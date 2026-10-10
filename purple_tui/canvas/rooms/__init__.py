"""Rooms: the kid-facing rooms in tab order, and the parent-facing screens."""

from .art_room import ArtRoom
from .blocks_room import BlocksRoom
from .music_room import MusicRoom
from .play_room import PlayRoom

ROOM_CLASSES = (PlayRoom, MusicRoom, ArtRoom, BlocksRoom)
ROOM_NAMES = tuple(c.name for c in ROOM_CLASSES)
