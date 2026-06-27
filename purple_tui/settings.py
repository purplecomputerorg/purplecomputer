"""
Purple Computer - Persistent Settings

Settings that survive across app restarts (Littles Mode, etc.).
Stored in ~/.config/purple/settings.json alongside display.json.
"""

import json
from pathlib import Path

from .constants import VOLUME_DEFAULT

SETTINGS_FILE = Path.home() / ".config" / "purple" / "settings.json"

_defaults = {
    "littles_mode": None,        # None = off, "music", "music_noscreen", or "art"
    "code_panel": True,          # Whether the code panel can be opened (space hold)
    "music_looping": True,       # Whether music room loop recording can be triggered (enter hold)
    "music_key_switching": True, # Whether music room key switching (arrows) is enabled
    "all_caps": False,           # Whether all rendered text is uppercased at render time
    "volume_level": VOLUME_DEFAULT, # Last volume the kid set (0-100), restored on restart
    "volume_lock": None,         # Parent lock: None = unlocked, 0-100 = pin playback at that level (0 = silent); volume keys disabled while set
    "parent_pin": None,          # Optional 4-digit PIN gating the parent menu; None = no PIN
    "kid_letters": False,        # Use the recorded kid-voice clips for A-Z letter names (gated behind the secret menu)
    "secret_unlocked": False,    # Family secret menu revealed via the Ctrl+codeword gesture
}


def load_settings() -> dict:
    """Load settings from disk, falling back to defaults.

    Migrates the legacy `silent_mode: True` field to `volume_lock: 0`,
    since silence is just a lock pinned at zero in the unified model.
    """
    settings = dict(_defaults)
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            for key in _defaults:
                if key in data:
                    settings[key] = data[key]
            if data.get("silent_mode") and settings["volume_lock"] is None:
                settings["volume_lock"] = 0
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


def get_music_key_switching() -> bool:
    """Whether music room key switching (arrows) is enabled."""
    return load_settings()["music_key_switching"]


def set_music_key_switching(enabled: bool) -> None:
    settings = load_settings()
    settings["music_key_switching"] = enabled
    save_settings(settings)


def get_all_caps() -> bool:
    """Whether all rendered text is uppercased."""
    return load_settings()["all_caps"]


def set_all_caps(enabled: bool) -> None:
    settings = load_settings()
    settings["all_caps"] = enabled
    save_settings(settings)


def get_volume_level() -> int:
    """Last volume level the kid set (0-100)."""
    return load_settings()["volume_level"]


def set_volume_level(level: int) -> None:
    settings = load_settings()
    settings["volume_level"] = level
    save_settings(settings)


def get_volume_lock() -> int | None:
    """Locked playback volume (0-100), or None if not locked. 0 means Silent."""
    return load_settings()["volume_lock"]


def set_volume_lock(level: int | None) -> None:
    settings = load_settings()
    settings["volume_lock"] = level
    save_settings(settings)


def get_kid_letters() -> bool:
    """Whether the recorded kid-voice clips are used for A-Z letter names."""
    return load_settings()["kid_letters"]


def set_kid_letters(enabled: bool) -> None:
    settings = load_settings()
    settings["kid_letters"] = enabled
    save_settings(settings)


def get_secret_unlocked() -> bool:
    """Whether the family secret menu has been unlocked."""
    return load_settings()["secret_unlocked"]


def set_secret_unlocked(enabled: bool) -> None:
    settings = load_settings()
    settings["secret_unlocked"] = enabled
    save_settings(settings)


def get_parent_pin() -> str | None:
    """Optional 4-digit parent menu PIN, or None if unset."""
    return load_settings()["parent_pin"]


def set_parent_pin(pin: str | None) -> None:
    settings = load_settings()
    settings["parent_pin"] = pin
    save_settings(settings)


