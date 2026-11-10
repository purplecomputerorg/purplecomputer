# What a browser can't do that a Purple laptop can, made into quiet no-ops before Purple loads.
# Purple's threads are side work (mixer warmup, volume commands, power polling), so they don't start.
import threading

_said = set()


def _once(text):
    if text not in _said:
        _said.add(text)
        print(text)


def _no_thread(self):
    _once(f"[studio] skipped thread {self.name}")


threading.Thread.start = _no_thread


# Pyodide's event loop refuses a time that passed while it was being set, where CPython's runs it at once;
# a frame's idle wait that ends a hair early would otherwise stop Purple's frame loop for good.
def _patch_loop():
    from pyodide.webloop import WebLoop

    def call_at(self, when, callback, *args, context=None):
        return self.call_later(max(0, when - self.time()), callback, *args, context=context)

    WebLoop.call_at = call_at


_patch_loop()


# No users in a browser: tts looks up its own home directory.
def _stub_pwd():
    import sys
    import types
    pwd = types.ModuleType("pwd")

    def getpwnam(name):
        raise KeyError(name)

    pwd.getpwnam = pwd.getpwuid = getpwnam
    sys.modules["pwd"] = pwd


_stub_pwd()


# pygame.freetype doesn't initialize in Pyodide; Gfx only uses it to ask whether a face has a
# glyph, which the font's own character map answers.
def _patch_glyph_coverage():
    from fontTools.ttLib import TTFont
    from purple_tui.canvas import gfx
    cmaps = {}

    def covers(self, face, text):
        if face not in cmaps:
            cmaps[face] = set(TTFont(str(gfx.FONT_DIR / gfx.FACES[face]), lazy=True).getBestCmap())
        return all(ch.isspace() or ord(ch) in cmaps[face] for ch in text)

    gfx.Gfx._covers = covers


_patch_glyph_coverage()


# SDL_ttf here can't draw Noto Color Emoji's bitmaps, so Purple draws the same pictures from the
# ones studio_bundle.py pulled out of the ISO's font. purple.zip carries the ones Purple's own words
# use; any other is fetched from Studio the first time it's drawn, blank until it lands.
def _patch_emoji():
    import asyncio
    from pathlib import Path
    import pygame
    import purple_tui
    from js import URL, document
    from pyodide.http import pyfetch
    from purple_tui.canvas import gfx
    from purple_tui.canvas.emoji_pictures import EmojiPictures

    root = Path(purple_tui.__file__).parent.parent / "emoji"
    if not (root / "map.json").exists():
        return
    pictures = EmojiPictures(root)
    load = EmojiPictures._picture
    asked = set()

    async def fetch(gid):
        r = await pyfetch(URL.new(f"purple/emoji/{pictures.dir.name}/{gid}.png", document.baseURI).href)
        if not r.ok or not (app := globals().get("_app")):
            return
        (pictures.dir / f"{gid}.png").write_bytes(await r.bytes())
        for cache in (app.g._emoji, app.g._text, app.g._layouts):
            cache.clear()
        app.invalidate()

    def picture(self, gid):
        if gid in self._loaded or (self.dir / f"{gid}.png").exists():
            return load(self, gid)
        if gid not in asked:
            asked.add(gid)
            asyncio.ensure_future(fetch(gid))
        return pygame.Surface((1, 1), pygame.SRCALPHA)

    EmojiPictures._picture = picture
    gfx.Gfx._emoji_native = lambda self, text: pictures.render(text)


_patch_emoji()


# Purple's sounds play through the page's Web Audio (studio/src/live/sound.ts) instead of SDL's mixer:
# the browser decodes them off Python's thread. pygame.mixer keeps its names, as Purple uses them.
def _patch_mixer():
    import itertools
    from pathlib import Path
    import pygame
    import pygame.mixer
    from js import purpleSound
    from pyodide.ffi import to_js
    from purple_tui import mixer
    from purple_tui.canvas.sounds import core_sounds

    ids = itertools.count(1)
    core = core_sounds()
    # purple.zip's core sounds are empty files standing in for the ones Studio serves.
    url = lambda path: f"purple/core-sounds/{path.relative_to(core).as_posix()}"

    class Channel:
        def __init__(self, id, sound_volume):
            self.id, self.sound_volume = id, sound_volume

        def get_busy(self):
            return purpleSound.busy(self.id)

        def set_volume(self, volume, *_):  # pygame scales a channel by its sound's volume too
            purpleSound.volume(self.id, volume * self.sound_volume)

        def stop(self):
            purpleSound.end(self.id)

    class Sound:
        def __init__(self, file):
            path, self.id, self.volume = Path(file), next(ids), 1.0
            data = path.read_bytes()
            purpleSound.load(self.id, to_js(data) if data else url(path))

        def __del__(self):
            purpleSound.drop(self.id)

        def play(self, *_, **__):
            return Channel(purpleSound.play(self.id, self.volume), self.volume)

        def set_volume(self, volume):
            self.volume = volume

        def get_volume(self):
            return self.volume

        def stop(self):
            purpleSound.stopSound(self.id)

        def get_length(self):
            return purpleSound.length(self.id)

    m = pygame.mixer
    m.Sound, m.stop, m.get_busy = Sound, purpleSound.stopAll, purpleSound.anyBusy
    m.init = m.quit = m.set_num_channels = lambda *_, **__: None
    m.get_init = lambda: (48000, -16, 2)
    mixer.pygame = pygame
    mixer.warm_mixer = mixer._ensure_mixer = lambda timeout_seconds=10.0: mixer._MIXER_READY or mixer._init_mixer()
    mixer._init_mixer()
    purpleSound.warm(to_js([url(p) for p in sorted(core.rglob("*")) if p.suffix in (".ogg", ".wav") and not p.stat().st_size]))


_patch_mixer()


# Speech: Purple's own recorded clips when it has one for the words, else Piper as Purple runs it (the
# page's purplePiper, see piper.ts), cached and leveled by tts itself; the browser's voice while Piper
# loads. Run on the event loop instead of a thread, otherwise as tts.speak_many.
def _patch_speech():
    import array
    import asyncio
    import os
    import tempfile
    import pygame
    from js import purplePiper, purpleSay, purpleHush
    from purple_tui import tts
    from purple_tui.audio import play_safe
    from purple_tui.speech_filter import filter_speech

    async def piper(text):
        prepared = tts._prepare_text(text)
        if cached := tts._get_cached(prepared, tts.VOICE_NATURAL):
            return cached
        voice = await purplePiper(prepared)
        if not voice:  # JS null arrives as JsNull, which is falsy
            return None
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tts._write_wav(wav, tts.postprocess_samples(array.array("h", voice.pcm.to_bytes()), voice.rate), voice.rate)
        return tts._store_cache(prepared, wav, tts.VOICE_NATURAL) or wav

    async def say(text, speech_id, room_voice, family):
        clip = tts._get_voice_clip(text, room_voice, family) or await piper(text)
        if speech_id != tts._speech_id:
            return
        if not clip:
            return await purpleSay(text)
        channel = tts._current_channel = play_safe(pygame.mixer.Sound(str(clip)))
        while channel and channel.get_busy() and speech_id == tts._speech_id:
            await asyncio.sleep(0.05)
        if tts._current_channel is channel:
            tts._current_channel = None

    async def sequence(items, speech_id, gap, on_playing, on_done, room_voice, family):
        try:
            for n, (index, text) in enumerate(items):
                if n:
                    await asyncio.sleep(gap)
                if speech_id != tts._speech_id:
                    return
                if on_playing:
                    on_playing(index)
                await say(text, speech_id, room_voice, family)
        finally:
            if on_done:
                on_done()

    # tts.speak_many's signature: a text may come as (text, language), and the language goes unused here.
    def speak_many(texts, gap=0.5, on_playing=None, on_done=None, room_voice=None, family=True):
        if tts._muted:
            return False
        texts = [t[0] if isinstance(t, tuple) else t for t in texts]
        items = [(i, f) for i, t in enumerate(texts) if t and t.strip() and (f := filter_speech(t)) and f.strip()]
        if not items:
            return False
        tts.stop()
        asyncio.ensure_future(sequence(items, tts._speech_id, gap, on_playing, on_done, room_voice, family))
        return True

    stop = tts.stop

    def hush():
        purpleHush()
        stop()

    tts.speak_many = speak_many
    tts.stop = hush


_patch_speech()


# Each finished frame is copied by the page onto the canvas people see, scaled down smoothly
# (frame.ts); the browser's own scaling of SDL's canvas leaves small text jagged. Whenever a frame
# leaves Purple somewhere new, the page hears where (moved(), from live.py, run in these same globals).
# A report that fails is logged and skipped: raising here would stop Purple's frame loop for good.
def _patch_present():
    import json
    from js import purpleMoved, purplePresented
    from purple_tui.canvas import gfx

    present = gfx.Gfx.present

    def presented(self, *args, **kwargs):
        present(self, *args, **kwargs)
        purplePresented()
        try:
            if globals().get("_app") and (now := moved()):
                purpleMoved(json.dumps(now))
        except Exception as e:
            _once(f"[studio] couldn't say where Purple is: {e!r}")

    gfx.Gfx.present = presented


_patch_present()


# Family rooms: Purple's own FamilyRoom runs here, with the room in a Web Worker instead of a process
# (studio/src/rooms/guests.ts), and tells the Rooms page why a room stopped.
def _patch_family_rooms():
    from js import purpleRoomGuest, purpleRoomProblem
    from pyodide.ffi import create_proxy
    from purple_tui.canvas.rooms import family_room

    class JsGuest:
        def __init__(self, start, on_line):
            self._on_line = create_proxy(on_line)
            self._id = purpleRoomGuest.start(self._on_line)
            purpleRoomGuest.send(self._id, start)

        def send(self, line):
            purpleRoomGuest.send(self._id, line)

        def stop(self):
            purpleRoomGuest.stop(self._id)
            self._on_line.destroy()

    broken = family_room.FamilyRoom._broken

    def report(self, why, line=None):
        broken(self, why, line)
        purpleRoomProblem(why, line)

    family_room.Guest = JsGuest
    family_room.FamilyRoom._broken = report


_patch_family_rooms()
