"""
Purple Computer - Persistent Settings

Settings that survive across app restarts (Littles Mode, etc.).
Stored in ~/.config/purple/settings.json alongside display.json.
"""

import json
import shutil
from pathlib import Path

from .audio import snap_volume

SETTINGS_FILE = Path.home() / ".config" / "purple" / "settings.json"

_defaults = {
    "littles_mode": None,        # None = off, "music", "music_noscreen", or "art"
    "code_panel": True,          # Whether the code panel can be opened (space hold)
    "music_looping": True,       # Whether music room loop recording can be triggered (enter hold)
    "music_key_switching": True, # Whether music room key switching (arrows) is enabled
    "rooms_off": [],             # Built-in rooms a parent turned off, hidden from the Esc menu
    "rooms_turned_on": [],       # Built-in rooms a parent turned on, which matters for ones that start off (Write)
    "rooms_on": {},              # Family rooms a parent turned on: "pack/room" -> Room.digest of what they turned on
    "packs_added": {},           # Purple Packs someone pressed Add for: pack id -> sha256 of its .purplepack
    "all_caps": False,           # Whether all rendered text is uppercased at render time
    "volume_level": None,        # Last volume anyone set (0-100), restored on restart; None until then
    "volume_lock": None,         # Parent ceiling: None = no limit, 0-100 = loudest the kid can pick (0 = Silent Mode, keys disabled)
    "parent_pin": None,          # Optional 4-digit PIN gating the parent menu; None = no PIN
    "kid_letters": False,        # Use the recorded kid-voice clips for A-Z letter names (gated behind the secret menu)
    "secret_unlocked": False,    # Family secret menu revealed via the Ctrl+codeword gesture
    "voice": "natural",          # Which synthesizer speaks: "natural" (Piper) or "quick" (flite)
    "language": "en",            # Interface language code (a language pack), "en" = English
    "second_language": None,     # Language Play shows and says beside typed words; None = off
    "kids": [],                  # Kids added after the first, by folder name under kids/; the first kid is ""
    "kid": "",                   # Who's playing: "" or one of kids
    "pack_kids": {},             # Purple Packs just for one kid: pack id -> kid; the rest are for everyone
}

# Kept in SETTINGS_FILE for every kid; the rest is each kid's own (the first kid's also lives there).
SHARED = {"kids", "kid", "pack_kids", "packs_added", "rooms_on", "parent_pin", "volume_level", "volume_lock",
          "voice", "secret_unlocked"}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _kid_in(shared: dict) -> str:
    kid = shared.get("kid", "")
    return kid if kid in shared.get("kids", []) else ""


def get_kid() -> str:
    return _kid_in(_read(SETTINGS_FILE))


def kid_path(first: Path, kid: str | None = None) -> Path:
    """Where the first kid keeps something, or the same name in another kid's own folder."""
    kid = get_kid() if kid is None else kid
    return SETTINGS_FILE.parent / "kids" / kid / first.name if kid else first


def load_settings() -> dict:
    """Load settings from disk, falling back to defaults.

    Migrates the legacy `silent_mode: True` field to `volume_lock: 0`,
    since silence is just a lock pinned at zero in the unified model.
    """
    settings = dict(_defaults)
    try:
        shared = _read(SETTINGS_FILE)
        kid = _kid_in(shared)
        own = _read(kid_path(SETTINGS_FILE, kid)) if kid else shared
        for key in _defaults:
            data = shared if key in SHARED else own
            if key in data:
                settings[key] = data[key]
        if shared.get("silent_mode") and settings["volume_lock"] is None:
            settings["volume_lock"] = 0
        if settings["volume_level"] is not None:
            settings["volume_level"] = snap_volume(settings["volume_level"])
        if settings["volume_lock"] is not None:
            settings["volume_lock"] = snap_volume(settings["volume_lock"])
    except Exception:
        pass
    return settings


def save_settings(settings: dict) -> bool:
    """Save the shared settings, and the playing kid's own."""
    try:
        shared = _read(SETTINGS_FILE)
        kid = _kid_in(shared)
        if not kid:
            _write(SETTINGS_FILE, settings)
        else:
            _write(SETTINGS_FILE, shared | {k: v for k, v in settings.items() if k in SHARED})
            _write(kid_path(SETTINGS_FILE, kid), {k: v for k, v in settings.items() if k not in SHARED})
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


def _get_list(name: str) -> list:
    value = load_settings()[name]
    return value if isinstance(value, list) else []


def get_rooms_off(start_off=()) -> list:
    """Rooms a parent turned off, plus the start_off ones they never turned on."""
    off, on = _get_list("rooms_off"), _get_list("rooms_turned_on")
    return off + [r for r in start_off if r not in on and r not in off]


def set_room_off(name: str, off: bool) -> None:
    settings = load_settings()
    settings["rooms_off"] = [r for r in _get_list("rooms_off") if r != name] + ([name] if off else [])
    settings["rooms_turned_on"] = [r for r in _get_list("rooms_turned_on") if r != name] + ([] if off else [name])
    save_settings(settings)


def _get_map(name: str) -> dict:
    value = load_settings()[name]
    return value if isinstance(value, dict) else {}


def _set_in_map(name: str, key: str, value: str | None) -> None:
    settings = load_settings()
    settings[name] = {k: v for k, v in _get_map(name).items() if k != key} | ({key: value} if value is not None else {})
    save_settings(settings)


def get_rooms_on() -> dict:
    return _get_map("rooms_on")


def set_room_on(key: str, digest: str | None) -> None:
    """digest None turns the room off."""
    _set_in_map("rooms_on", key, digest)


def get_packs_added() -> dict:
    return _get_map("packs_added")


def set_pack_added(pack_id: str, sha: str | None) -> None:
    """sha None forgets it, so the next drive with it asks again."""
    _set_in_map("packs_added", pack_id, sha)


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


def get_volume_level() -> int | None:
    """Last volume level anyone set (0-100), or None if the volume has never been touched."""
    return load_settings()["volume_level"]


def set_volume_level(level: int) -> None:
    settings = load_settings()
    settings["volume_level"] = level
    save_settings(settings)


def get_volume_lock() -> int | None:
    """Parent ceiling on playback volume (0-100), or None if unlimited. 0 means Silent."""
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


def get_voice() -> str:
    """Which synthesizer speaks: "natural" (Piper) or "quick" (flite)."""
    return load_settings()["voice"]


def set_voice(pref: str) -> None:
    settings = load_settings()
    settings["voice"] = pref
    save_settings(settings)


def get_language() -> str:
    """The interface language's code; "en" is English, the built-in text."""
    return load_settings()["language"]


def set_language(code: str) -> None:
    settings = load_settings()
    settings["language"] = code
    save_settings(settings)


def get_second_language() -> str | None:
    """The language Play shows and says beside typed words ("en" when the interface isn't English), or None."""
    return load_settings()["second_language"]


def set_second_language(code: str | None) -> None:
    settings = load_settings()
    settings["second_language"] = code
    save_settings(settings)


def get_kids() -> list[str]:
    return [""] + _get_list("kids")


def set_kid(kid: str) -> None:
    settings = load_settings()
    settings["kid"] = kid
    save_settings(settings)


def add_kid() -> str:
    settings = load_settings()
    kid = str(1 + max((int(k) for k in _get_list("kids") if k.isdigit()), default=1))
    settings["kids"] = _get_list("kids") + [kid]
    save_settings(settings)
    return kid


def remove_kid(kid: str) -> None:
    """Never the first kid, whose things are the computer's own."""
    if not kid:
        return
    settings = load_settings()
    settings["kids"] = [k for k in _get_list("kids") if k != kid]
    settings["pack_kids"] = {p: k for p, k in _get_map("pack_kids").items() if k != kid}
    save_settings(settings)
    shutil.rmtree(SETTINGS_FILE.parent / "kids" / kid, ignore_errors=True)


def get_pack_kid(pack_id: str) -> str | None:
    """The one kid a pack is for, or None for everyone."""
    return _get_map("pack_kids").get(pack_id)


def set_pack_kid(pack_id: str, kid: str | None) -> None:
    _set_in_map("pack_kids", pack_id, kid)


def gets_pack(pack_id: str) -> bool:
    return get_pack_kid(pack_id) in (None, get_kid())
