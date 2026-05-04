"""
Purple Computer - Persistent Settings

Settings that survive across app restarts (Littles Mode, etc.).
Stored in ~/.config/purple/settings.json alongside display.json.
"""

import json
from pathlib import Path

SETTINGS_FILE = Path.home() / ".config" / "purple" / "settings.json"

_defaults = {
    "littles_mode": None,        # None = off, "music", "music_noscreen", or "art"
    "code_panel": True,          # Whether the code panel can be opened (space hold)
    "music_looping": True,       # Whether music room loop recording can be triggered (enter hold)
}


def load_settings() -> dict:
    """Load settings from disk, falling back to defaults."""
    settings = dict(_defaults)
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            for key in _defaults:
                if key in data:
                    settings[key] = data[key]
    except Exception:
        pass
    return settings


def save_settings(settings: dict) -> bool:
    """Save settings to disk."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False



def get_littles_mode() -> str | None:
    """Get current Littles Mode setting. None = off, 'music' or 'art'."""
    return load_settings()["littles_mode"]


def set_littles_mode(mode: str | None) -> None:
    """Set Littles Mode. None to disable, 'music' or 'art' to enable."""
    settings = load_settings()
    settings["littles_mode"] = mode
    save_settings(settings)


def get_code_panel() -> bool:
    """Whether the code panel is enabled."""
    return load_settings()["code_panel"]


def set_code_panel(enabled: bool) -> None:
    settings = load_settings()
    settings["code_panel"] = enabled
    save_settings(settings)


def get_music_looping() -> bool:
    """Whether music room looping is enabled."""
    return load_settings()["music_looping"]


def set_music_looping(enabled: bool) -> None:
    settings = load_settings()
    settings["music_looping"] = enabled
    save_settings(settings)


