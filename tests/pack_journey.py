"""A .purplepack's whole trip onto a Purple: on a USB drive, read, offered, added, its rooms turned on,
then each file it holds checked where a kid meets it (Play's answer, Art's Open, Music, the room).
Reads whatever the pack holds, so the same checks run on the SDK's fixture packs, a real Studio
download (studio/scripts/e2e-studio.ts) or a pack an AI tester built. CLI: scripts/e2e_pack.py."""

import asyncio
import json
import os
import tarfile
from dataclasses import dataclass
from pathlib import Path

from purple_tui import content, pack_arrivals, settings, tts
from purple_tui import palette as P
from purple_tui.canvas import sounds
from purple_tui.canvas.harness import press, type_text
from purple_tui.canvas.library import Library, PictureTile
from purple_tui.canvas.room_picker import family_rooms
from purple_tui.canvas.rooms.rooms_screen import RoomsScreen, room_state
from purple_tui.canvas.ui import Confirm
from purple_tui.content import MEANING_MAX, Picture, is_word_picture, typed_name
from purple_tui.music_constants import instruments, pitch_filename, reachable_pitches
from purple_tui.usb_updater import update_from


class _ThisProcess:
    """isolate()'s patcher outside pytest: a script's process is its own throwaway Purple."""
    setattr = staticmethod(setattr)

    @staticmethod
    def setenv(key, value):
        os.environ[key] = value


def isolate(root: Path, patch=_ThisProcess) -> None:
    """A fresh Purple's home under root; patch is pytest's monkeypatch in tests."""
    for key, sub in (("HOME", ""), ("PURPLE_SAVES_DIR", "saves"), ("PURPLE_ROOMS_DIR", "rooms-kept")):
        patch.setenv(key, str(root / sub))
    patch.setattr(settings, "SETTINGS_FILE", root / "settings.json")
    patch.setattr(pack_arrivals, "WAITING_DIR", root / "waiting")
    patch.setattr(pack_arrivals, "LATER_DIR", root / "waiting" / ".later")
    patch.setattr(content, "_content", None)


def said(screen) -> str:
    return " | ".join(filter(None, [type(screen).__name__, getattr(screen, "title", ""),
                                    getattr(screen, "description", None) or getattr(screen, "DESCRIPTION", "")]))


async def deliver(app, drive: Path, shots: Path | None = None) -> list[str]:
    """Plug in drive as udev would, then answer every screen the way a parent saying yes does:
    Add, OK, and check each new room. Returns what each screen said."""
    update_from(drive, pack_arrivals.WAITING_DIR)
    app._check_pack_arrivals()
    seen = []
    while app.top is not None and len(seen) < 12:
        screen = app.top
        seen.append(said(screen))
        shot(app, shots, f"deliver-{len(seen)}")
        if isinstance(screen, RoomsScreen):
            await _check_new_rooms(app, screen)
            await press(app, "escape")
            continue
        if isinstance(screen, Confirm) and screen.selected != 0:
            await press(app, "up")
        await press(app, "enter")
    return seen


async def _check_new_rooms(app, screen: RoomsScreen) -> None:
    for r, row in enumerate(screen.rows):
        for c, (kind, room) in enumerate(row):
            if kind == "family" and room.pack in screen.packs and room_state(room, settings.get_rooms_on()) != "on":
                screen.row, screen.col = r, c
                await press(app, "enter")


def shot(app, shots: Path | None, name: str) -> None:
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
        app.screenshot(str(shots / f"{name}.png"))


@dataclass
class Check:
    ok: bool
    what: str


def read_pack(pack: Path) -> dict[str, bytes]:
    with tarfile.open(pack) as tar:
        return {m.name.removeprefix("./"): tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


def _json(files: dict, path: str) -> dict:
    return json.loads(files[path]) if path in files else {}


def _stems(files: dict, folder: str, suffix: str) -> list[str]:
    return sorted(p[len(folder) + 1:-len(suffix)] for p in files if p.startswith(folder + "/") and p.endswith(suffix)
                  and "/" not in p[len(folder) + 1:])


async def play_answer(app, line: str) -> str:
    """What Play shows for a line typed on the keyboard and Entered."""
    app.action_switch_room("play")
    play = app.rooms["play"]
    before = len(play.history)
    await type_text(app, line)
    await press(app, "enter")
    return " ".join(e.markup.replace("\\[", "[") for e in play.history[before:] if e.kind == "answer")


def letter_clips(app) -> dict:
    """Music's Letters clips, key to the files it would play in turn (headless has no mixer to load them into)."""
    real = sounds._load, sounds.mixer_ready_for_play
    sounds._load, sounds.mixer_ready_for_play = (lambda path: path), (lambda: True)
    try:
        app.rooms["music"].sounds.clear()
        return app.rooms["music"].sounds.letters()
    finally:
        sounds._load, sounds.mixer_ready_for_play = real
        app.rooms["music"].sounds.clear()


async def open_art_library(app) -> Library:
    app.action_switch_room("art")
    await press(app, "escape")
    await press(app, "o")
    return app.top


async def until(check, timeout=5.0):
    for _ in range(int(timeout / 0.02)):
        if check():
            return True
        await asyncio.sleep(0.02)
    return False


async def check(app, pack: Path, shots: Path | None = None) -> list[Check]:
    """Each thing in pack, looked for where Purple shows or plays it."""
    files = read_pack(pack)
    manifest = json.loads(files["manifest.json"])
    pack_id = manifest["id"]
    installed = Path.home() / ".purple" / "packs" / pack_id
    cm = content.get_content()
    out: list[Check] = []

    def expect(ok, what):
        out.append(Check(bool(ok), what))

    def ours(path) -> bool:
        return path is not None and installed in Path(path).parents

    def any_ours(paths) -> bool:
        return any(ours(p) for p in paths or [])

    expect(pack_id in settings.get_packs_added(), f'"{manifest["name"]}" is added')

    for word, glyph in _json(files, "content/emoji.json").items():
        expect(glyph in await play_answer(app, word), f'Play answers "{word}" with {glyph}')
    for word, name in _json(files, "content/word-pictures.json").items():
        char = cm.get_emoji(word)
        expect(is_word_picture(char) and cm.word_pictures.get(char) == installed / "content" / "images" / f"{name}.png",
               f'"{word}" is the pack\'s picture {name}')
        expect(char and char in await play_answer(app, word), f'Play shows "{word}" as that picture')
    for word, meaning in _json(files, "content/meanings.json").items():
        expect(meaning.strip()[:MEANING_MAX] in await play_answer(app, f"who is {word}"), f'Play explains "{word}"')
    for alias, word in _json(files, "content/synonyms.json").items():
        expect(cm.get_emoji(alias) and cm.get_emoji(alias) == cm.get_emoji(word), f'"{alias}" means "{word}"')
    for word in files.get("content/rankings.txt", b"").decode().split():
        expect(word in [w for w, *_ in cm.search_words(word[:2])], f'"{word}" is suggested while typing')
    shot(app, shots, "play")

    clips = letter_clips(app)
    for name in _stems(files, "content/letters", ".wav"):
        key = next((k for k, n in sounds.CLIP_NAMES.items() if n == name), name)
        expect(any_ours(clips.get(key)), f"Music's Letters plays the pack's {key}")
    for stem in _stems(files, "content/voice", ".wav"):
        expect(ours(tts._get_voice_clip(stem.replace("_", " "))), f'Purple says "{stem.replace("_", " ")}" in the pack\'s recording')

    pictures = {Picture(n, [], typed_name(_json(files, f"content/pictures/{n}.json"), n)).title for n in _stems(files, "content/pictures", ".json")}
    if pictures:
        library = await open_art_library(app)
        tiles = {t.picture.title: t for t in getattr(library, "tiles", []) if isinstance(t, PictureTile)}
        shot(app, shots, "art-open")
        for title in sorted(pictures):
            expect(title in tiles and tiles[title].state, f'Art\'s Open has "{title}"')
        await press(app, "escape")

    for name in _stems(files, "content/instruments", ".json"):
        spec = _json(files, f"content/instruments/{name}.json")
        expect(any(i[0] == name for i in instruments()), f"Music lists the {name} instrument")
        folder = cm.instrument_dir(name)
        missing = [p for p in reachable_pitches() if not (folder and (folder / f"{pitch_filename(*p)}.wav").exists())]
        expect(not missing, f"{name} has every note the grid reaches" + (f" (missing {len(missing)})" if missing else ""))
        if spec.get("icon"):
            expect(cm.instrument_icon(name) == spec["icon"], f"{name} shows {spec['icon']}")

    on = {r.name: r for r in family_rooms() if r.pack == pack_id}
    for name in [s for s in _stems(files, "content/rooms", ".py") if s != "purple"]:
        expect(name in on, f"room {name} is turned on")
        if name in on:
            out += await _visit_room(app, on[name], files, shots)

    colors = _json(files, "content/theme.json").get("colors", {})
    if "bg" in colors:
        expect(P.BG.lower() == colors["bg"].lower(), f"the screen is the pack's {colors['bg']}")
    return out


async def _visit_room(app, room, files: dict, shots: Path | None) -> list[Check]:
    out = [Check(set(_stems(files, "content/images", ".png")) <= set(room.images), f"room {room.name} has the pack's pictures"),
           Check(set(_stems(files, "content/sounds", ".wav")) <= set(room.sounds), f"room {room.name} has the pack's sounds")]
    for stem in _stems(files, "content/room-voice", ".wav"):
        line = stem.replace("_", " ")
        clip = tts._get_voice_clip(line, room_voice=room.voice)
        out.append(Check(clip == room.voice / f"{stem}.wav", f'room {room.name} says "{line}" in Studio\'s voice'))
    app.open_family_room(room.name)
    guest = app.top
    await until(lambda: getattr(guest, "scene", None) or guest.fault)
    await press(app, "a")
    await asyncio.sleep(0.3)
    shot(app, shots, f"room-{room.name}")
    out.append(Check(guest.fault is None and bool(guest.scene), f"room {room.name} runs and answers a key"
                     + (f" (needs fixing: {guest.fault})" if guest.fault else "")))
    guest.close()
    return out
