# What a browser can't do that a Purple laptop can, made into quiet no-ops before Purple loads.
# Purple's threads are side work (mixer warmup, volume commands, power polling), so they don't start.
import threading

_skipped = set()


def _no_thread(self):
    if self.name not in _skipped:
        _skipped.add(self.name)
        print(f"[studio] skipped thread {self.name}")


threading.Thread.start = _no_thread


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


# SDL_ttf here can't draw Noto Color Emoji's bitmaps, so the page draws emoji with that same font
# file (see boot.ts, drawEmoji) and Purple gets the pixels back as a surface.
def _patch_emoji():
    import pygame
    from js import purpleDrawEmoji
    from purple_tui.canvas import gfx

    def emoji_run(self, text, px):
        img = purpleDrawEmoji(text, max(1, round(px * 1.2)))
        return pygame.image.frombuffer(bytes(img.data.to_py()), (img.width, img.height), "RGBA").convert_alpha()

    gfx.Gfx._emoji_run = emoji_run


_patch_emoji()


# The mixer probe runs a subprocess to catch audio hardware that hangs; a browser has neither, so
# the mixer opens in process (SDL plays through Web Audio).
def _patch_mixer():
    import pygame
    import pygame.mixer  # noqa: F401
    from purple_tui import mixer

    def warm(timeout_seconds=10.0):
        if mixer._MIXER_READY is None or mixer._IDLE_RELEASED:
            mixer._init_mixer()
        return mixer._MIXER_READY

    mixer.pygame = pygame
    mixer.warm_mixer = mixer._ensure_mixer = warm
    warm()
    print(f"[studio] mixer ready={mixer._MIXER_READY} {pygame.mixer.get_init()}")


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
        if voice is None:
            return None
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tts._write_wav(wav, tts.postprocess_samples(array.array("h", voice.pcm.to_bytes()), voice.rate), voice.rate)
        return tts._store_cache(prepared, wav, tts.VOICE_NATURAL) or wav

    async def say(text, speech_id, room_voice):
        clip = tts._get_voice_clip(text, room_voice) or await piper(text)
        if speech_id != tts._speech_id:
            return
        if not clip:
            return await purpleSay(text)
        channel = tts._current_channel = play_safe(pygame.mixer.Sound(str(clip)))
        while channel and channel.get_busy() and speech_id == tts._speech_id:
            await asyncio.sleep(0.05)
        if tts._current_channel is channel:
            tts._current_channel = None

    async def sequence(items, speech_id, gap, on_playing, on_done, room_voice):
        try:
            for n, (index, text) in enumerate(items):
                if n:
                    await asyncio.sleep(gap)
                if speech_id != tts._speech_id:
                    return
                if on_playing:
                    on_playing(index)
                await say(text, speech_id, room_voice)
        finally:
            if on_done:
                on_done()

    def speak_many(texts, gap=0.5, on_playing=None, on_done=None, room_voice=None):
        if tts._muted:
            return False
        items = [(i, f) for i, t in enumerate(texts) if t and t.strip() and (f := filter_speech(t)) and f.strip()]
        if not items:
            return False
        tts.stop()
        asyncio.ensure_future(sequence(items, tts._speech_id, gap, on_playing, on_done, room_voice))
        return True

    stop = tts.stop

    def hush():
        purpleHush()
        stop()

    tts.speak_many = speak_many
    tts.stop = hush


_patch_speech()


# Each finished frame is copied by the page onto the canvas people see, scaled down smoothly
# (frame.ts); the browser's own scaling of SDL's canvas leaves small text jagged.
def _patch_present():
    from js import purplePresented
    from purple_tui.canvas import gfx

    present = gfx.Gfx.present

    def presented(self):
        present(self)
        purplePresented()

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
