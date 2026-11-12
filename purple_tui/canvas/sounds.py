"""Sound files the canvas rooms play, cached per mixer generation: instrument
notes, number-row percussion, and letter names. Family packs come first:
a pack instrument's samples replace or join the core ones, and a pack's
letter recordings play after Purple's own clip or in its place."""

from pathlib import Path

import pygame

from ..mixer import mixer_generation, mixer_ready_for_play
from ..music_constants import ALL_KEYS, PERCUSSION

# Every grid key can have a recording; the ones that can't be a file name are spelled out.
CLIP_NAMES = {k: {";": "semicolon", ",": "comma", ".": "period", "/": "slash"}.get(k, k.lower()) for k in ALL_KEYS}
DRUM_KEYS = {name: digit for digit, name in PERCUSSION.items()}
SAMPLE_VOLUME = 0.4


def core_sounds() -> Path:
    paths = [Path(__file__).parents[2] / "packs" / "core-sounds" / "content",
             Path.home() / ".purple" / "packs" / "core-sounds" / "content"]
    return next((p for p in paths if p.exists()), paths[0])


def find_sound(base: Path, name: str):
    return next((p for ext in (".ogg", ".wav") if (p := base / f"{name}{ext}").exists()), None)


def _load(path) -> pygame.mixer.Sound | None:
    try:
        s = pygame.mixer.Sound(str(path))
        s.set_volume(SAMPLE_VOLUME)
        return s
    except pygame.error:
        return None


def _load_dir(base: Path, names) -> dict:
    return {n: s for n in names if (p := find_sound(base, n)) and (s := _load(p)) is not None}


class SoundBank:
    def __init__(self):
        self._cache: dict = {}
        self._generation = None

    def clear(self):
        self._cache.clear()

    def _get(self, key, load) -> dict:
        if self._generation != mixer_generation():
            self._cache.clear()
            self._generation = mixer_generation()
        if key not in self._cache:
            if not mixer_ready_for_play():
                return {}
            self._cache[key] = load()
        return self._cache[key]

    def file(self, path: Path):
        return self._get(("file", path), lambda: {"sound": _load(path)}).get("sound")

    def instrument(self, instrument_id: str) -> dict:
        """Samples keyed by pitch stem ('c4', 'cs5')."""
        def load():
            from ..content import get_content
            base = get_content().instrument_dir(instrument_id) or core_sounds() / instrument_id
            paths = sorted(base.glob("*.wav")) + sorted(base.glob("*.ogg")) if base.exists() else []
            return {p.stem: s for p in paths if (s := _load(p)) is not None}
        return self._get(("instrument", instrument_id), load)

    def percussion(self) -> dict:
        """Keyed by digit."""
        return self._get("percussion", lambda: _load_dir(core_sounds(), [k for k in ALL_KEYS if k.isdigit()]))

    def drum(self, name: str):
        return self.percussion().get(DRUM_KEYS.get(name.lower(), ""))

    def letters(self, sounds: bool = False) -> dict:
        """Keyed by key, the clips it plays in turn: Purple's own (with sounds, a letter's
        phonics sound; digits keep their names), then a pack's recording, which plays
        alone unless the pack lists it under "after" in content/letters.json."""
        def load():
            core = core_sounds()
            own = _first_found(([core / "letter-sounds"] if sounds else []) + [core / "letters"])
            family = _family_letters()

            def plays(name):
                mine, after = family.get(name, (None, True))
                return [s for s in (own.get(name) if after else None, mine) if s is not None]
            return {k: p for k, n in CLIP_NAMES.items() if (p := plays(n))}
        return self._get(("letters", sounds), load)


def _first_found(dirs: list) -> dict:
    """Clip name -> Sound, from the first directory that has it."""
    found = {}
    for d in reversed([d for d in dirs if d.exists()]):
        found.update(_load_dir(d, CLIP_NAMES.values()))
    return found


def _family_letters() -> dict:
    """Clip name -> (Sound, after), from the last installed pack that recorded it."""
    from ..content import get_content
    found = {}
    for d in reversed(get_content().pack_dirs("letters")):
        after = _after(d.parent)
        found.update({n: (s, n in after) for n, s in _load_dir(d, CLIP_NAMES.values()).items()})
    return found


def _after(content_dir: Path) -> set:
    from ..content import _read_json
    data = _read_json(content_dir / "letters.json")
    names = data.get("after") if isinstance(data, dict) else None
    return {n for n in names if isinstance(n, str)} if isinstance(names, list) else set()
