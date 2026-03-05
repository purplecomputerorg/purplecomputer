"""
Purple Computer Rooms

Executable Textual widgets for each room. These are curated, reviewed code,
NOT user-installable.

Content (emojis, definitions, sounds) comes from purplepacks, which are
content-only and safe for parents to install.
"""

from .explore_room import ExploreMode
from .play_room import PlayMode
from .doodle_room import DoodleMode

__all__ = ["ExploreMode", "PlayMode", "DoodleMode"]
