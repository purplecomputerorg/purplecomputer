"""Rooms: the kid-facing rooms in tab order, and the parent-facing screens."""

from .art_room import ArtRoom
from .blocks_room import BlocksRoom
from .music_room import MusicRoom
from .play_room import PlayRoom
from .write_room import WriteRoom

ROOM_CLASSES = (ArtRoom, MusicRoom, PlayRoom, BlocksRoom, WriteRoom)
ROOM_NAMES = tuple(c.name for c in ROOM_CLASSES)
