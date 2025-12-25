"""
Purple Computer Modes

Executable Textual widgets for each mode. These are curated, reviewed code -
NOT user-installable.

Content (emojis, definitions, sounds) comes from purplepacks, which are
content-only and safe for parents to install.
"""

from .ask_mode import AskMode
from .play_mode import PlayMode
from .write_mode import WriteMode

__all__ = ["AskMode", "PlayMode", "WriteMode"]
