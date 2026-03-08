"""
Purple Computer Rooms

Executable Textual widgets for each room. These are curated, reviewed code,
NOT user-installable.

Content (emojis, definitions, sounds) comes from purplepacks, which are
content-only and safe for parents to install.
"""

from .play_room import PlayMode
from .music_room import MusicMode
from .art_room import ArtMode

__all__ = ["PlayMode", "MusicMode", "ArtMode"]
