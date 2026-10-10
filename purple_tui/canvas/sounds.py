"""Sound files the canvas rooms play, cached per mixer generation: instrument
notes, number-row percussion, and letter names. Family packs come first:
a pack instrument's samples replace or join the core ones, and a pack's
letter recordings win over Purple's own clips for the keys they cover."""

from pathlib import Path

import pygame

from ..mixer import mixer_generation, mixer_ready_for_play
from ..music_constants import ALL_KEYS, PERCUSSION

SPEAKABLE_KEYS = {k for k in ALL_KEYS if k.isalpha() or k.isdigit()}
DRUM_KEYS = {name: digit for digit, name in PERCUSSION.items()}


def core_sounds() -> Path:
    paths = [Path(__file__).parents[2] / "packs" / "core-sounds" / "content",
             Path.home() / ".purple" / "packs" / "core-sounds" / "content"]
    return next((p for p in paths if p.exists()), paths[0])


def find_sound(base: Path, name: str):
    return next((p for ext in (".ogg", ".wav") if (p := base / f"{name}{ext}").exists()), None)


def _load(path) -> pygame.mixer.Sound | None:
    try:
        s = pygame.mixer.Sound(str(path))
        s.set_volume(0.4)
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

    def letters(self) -> dict:
        """Keyed by key: pack recordings, then Kid Voice when on, then Purple's clips."""
        def load():
            from ..content import get_content
            from ..settings import get_kid_letters
            dirs = get_content().pack_dirs("letters")
            if get_kid_letters():
                dirs.append(core_sounds() / "letters-kid")
            dirs.append(core_sounds() / "letters")
            found = {}
            for d in reversed([d for d in dirs if d.exists()]):
                found.update(_load_dir(d, [k.lower() for k in SPEAKABLE_KEYS]))
            return {k: found[k.lower()] for k in SPEAKABLE_KEYS if k.lower() in found}
        return self._get("letters", load)
