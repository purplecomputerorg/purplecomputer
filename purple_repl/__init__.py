"""
Purple Computer REPL
A kid-friendly Python environment with emoji, speech, and creative modes
"""

__version__ = "0.1.0"
__author__ = "Purple Computer"
__license__ = "Purple Computer Source-Available License 1.0"

from . import emoji_lib
from . import tts
from . import modes

__all__ = ['emoji_lib', 'tts', 'modes']
