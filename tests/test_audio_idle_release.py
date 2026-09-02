"""Mixer idle-release state machine.

After a quiet period the mixer is quit so Pulse's sink can suspend (an open
SDL stream mixes silence forever). The next play must re-init inline via the
fast path (no subprocess probe) and behave exactly as before the release.
The quit runs outside _MIXER_LOCK so a wedged backend can never block the
main thread, transient re-init failures retry instead of latching audio off,
and Sound caches reload after any quit (they are tied to the closed device).
"""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from purple_tui import audio
from purple_tui.purple_tui import PurpleApp, Room
from purple_tui.rooms import music_room
from purple_tui.rooms.music_room import MusicGrid


class _FakeMixer:
    def __init__(self):
        self.inited = True
        self.busy = False
        self.init_calls = 0
        self.quit_calls = 0

    def init(self, **kwargs):
        self.inited = True
        self.init_calls += 1

    def quit(self):
        self.inited = False
        self.quit_calls += 1

    def get_init(self):
        return self.inited

    def get_busy(self):
        return self.busy

    def set_num_channels(self, n):
        pass


class _FakePygame:
    class error(Exception):
        pass

    def __init__(self):
        self.mixer = _FakeMixer()


class _FakeTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def _ready_mixer(monkeypatch):
    pg = _FakePygame()
    monkeypatch.setattr(music_room, "pygame", pg)
    monkeypatch.setattr(music_room, "_MIXER_READY", True)
    monkeypatch.setattr(music_room, "_PROBE_TIMED_OUT", False)
    monkeypatch.setattr(music_room, "_KNOWN_SILENT", False)
    monkeypatch.setattr(music_room, "_IDLE_RELEASED", False)
    monkeypatch.setattr(music_room, "_RELEASING", False)
    return pg


def _release_and_wait(quiet=0.0):
    music_room.request_idle_release(quiet)
    deadline = time.monotonic() + 2
    while music_room._IDLE_RELEASED is not True and time.monotonic() < deadline:
        time.sleep(0.01)


def test_release_quits_after_quiet_period(monkeypatch):
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)

    _release_and_wait()

    assert pg.mixer.quit_calls == 1
    assert music_room._MIXER_READY is None
    assert music_room._IDLE_RELEASED is True
    assert music_room._RELEASING is False


def test_no_release_while_playing_or_recent(monkeypatch):
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", time.monotonic())
    music_room.request_idle_release(60.0)  # recent play vetoes
    pg.mixer.busy = True
    monkeypatch.setattr(audio, "_last_play", 0.0)
    music_room.request_idle_release(0.0)  # busy channel vetoes
    time.sleep(0.05)

    assert pg.mixer.quit_calls == 0
    assert music_room._MIXER_READY is True


def test_release_aborts_if_play_lands_before_lock(monkeypatch):
    """The quiet period is re-checked under the lock: a play stamped after
    the cheap pre-check but before the release thread runs must veto."""
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", time.monotonic())

    music_room._release_for_idle(60.0)

    assert pg.mixer.quit_calls == 0
    assert music_room._MIXER_READY is True


def test_wedged_quit_never_blocks_the_main_thread(monkeypatch):
    """mixer.quit() can wedge on a dying backend. It runs outside
    _MIXER_LOCK, so every mixer gate must return promptly (and False)
    while the quit is stuck, instead of deadlocking warm_mixer."""
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)
    unwedge = threading.Event()

    def wedged_quit():
        unwedge.wait(5)
        pg.mixer.inited = False
        pg.mixer.quit_calls += 1

    monkeypatch.setattr(pg.mixer, "quit", wedged_quit)
    music_room.request_idle_release(0.0)
    deadline = time.monotonic() + 2
    while not music_room._RELEASING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert music_room._RELEASING is True

    start = time.monotonic()
    assert music_room.mixer_ready_for_play() is False
    assert music_room.should_attempt_play() is False
    assert music_room.warm_mixer() is False
    assert audio.play_safe(SimpleNamespace()) is None
    assert time.monotonic() - start < 1.0  # nothing blocked on the wedge

    unwedge.set()
    _release_and_wait()
    assert music_room._IDLE_RELEASED is True


def test_play_reinits_via_fast_path_after_release(monkeypatch):
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)
    _release_and_wait()

    assert music_room.mixer_ready_for_play() is True
    assert pg.mixer.init_calls == 1  # direct init, no probe subprocess
    assert music_room._MIXER_READY is True
    assert music_room._IDLE_RELEASED is False


def test_transient_reinit_failure_retries_on_next_play(monkeypatch):
    """One failed fast re-init must not latch audio off for the session."""
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)
    _release_and_wait()
    real_init = pg.mixer.init
    calls = {"n": 0}

    def flaky_init(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakePygame.error("pulse restarting")
        real_init(**kwargs)

    monkeypatch.setattr(pg.mixer, "init", flaky_init)

    assert music_room.mixer_ready_for_play() is False  # transient failure
    assert music_room._MIXER_READY is None  # not latched to False
    assert music_room._IDLE_RELEASED is True
    assert music_room.mixer_ready_for_play() is True  # next play retries


def test_not_ready_states_still_refuse_play(monkeypatch):
    _ready_mixer(monkeypatch)
    monkeypatch.setattr(music_room, "_MIXER_READY", False)
    assert music_room.mixer_ready_for_play() is False
    monkeypatch.setattr(music_room, "_MIXER_READY", None)
    assert music_room.mixer_ready_for_play() is False  # untested, no fast path


def test_should_attempt_play_states(monkeypatch):
    """play_safe's gate: permissive while a hotplug re-probe is in flight
    (the raise-reinit-retry path recovers the sound), strict otherwise."""
    _ready_mixer(monkeypatch)
    assert music_room.should_attempt_play() is True  # ready
    monkeypatch.setattr(music_room, "_MIXER_READY", False)
    assert music_room.should_attempt_play() is False  # known-broken output
    monkeypatch.setattr(music_room, "_MIXER_READY", None)
    assert music_room.should_attempt_play() is True  # probe in flight: retry path decides
    monkeypatch.setattr(music_room, "_RELEASING", True)
    assert music_room.should_attempt_play() is False  # quit in flight


def test_hotplug_reset_clears_fast_path(monkeypatch):
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)
    _release_and_wait()
    monkeypatch.setattr(music_room, "warm_mixer", lambda *a, **k: True)

    music_room.reinit_mixer_after_hotplug()

    assert music_room._IDLE_RELEASED is False
    assert pg.mixer.quit_calls == 1  # already released; no double quit


def test_sound_caches_reload_after_mixer_quit(monkeypatch):
    """Sounds are tied to the device they were decoded for: any quit bumps
    the generation and stale caches must clear on next load."""
    _ready_mixer(monkeypatch)

    class GridStub:
        _drop_stale_sounds = MusicGrid._drop_stale_sounds
        _clear_sound_caches = MusicGrid._clear_sound_caches

        def __init__(self):
            self._instrument_sounds = {"glockenspiel": {"c5": object()}}
            self._percussion_sounds = {"1": object()}
            self._percussion_loaded = True
            self._letter_sounds = {"a": object()}
            self._letter_sounds_loaded = True
            self._sounds_generation = music_room.mixer_generation()

    grid = GridStub()
    grid._drop_stale_sounds()
    assert grid._instrument_sounds  # same generation: untouched

    music_room._quit_mixer()
    grid._drop_stale_sounds()

    assert grid._instrument_sounds == {}
    assert grid._percussion_sounds == {} and not grid._percussion_loaded
    assert grid._letter_sounds == {} and not grid._letter_sounds_loaded
    assert grid._sounds_generation == music_room.mixer_generation()


class _PlayableSound:
    def play(self, *a, **k):
        return "channel"


class _UnplayableSound:
    def play(self, *a, **k):
        raise AssertionError("play attempted with mixer unavailable")


def test_play_safe_refuses_when_output_known_broken(monkeypatch):
    _ready_mixer(monkeypatch)
    monkeypatch.setattr(music_room, "_MIXER_READY", False)
    monkeypatch.setattr(audio, "_last_play", 0.0)

    assert audio.play_safe(_UnplayableSound()) is None
    assert audio.seconds_since_last_play() > 60  # refused play isn't stamped


def test_play_safe_attempts_during_hotplug_reprobe(monkeypatch):
    """While _MIXER_READY is None mid-probe, play_safe must still attempt
    the play so its reinit-and-retry path can recover the sound."""
    _ready_mixer(monkeypatch)
    monkeypatch.setattr(music_room, "_MIXER_READY", None)

    assert audio.play_safe(_PlayableSound()) == "channel"


def test_play_safe_stamps_last_play_and_reinits_after_release(monkeypatch):
    pg = _ready_mixer(monkeypatch)
    monkeypatch.setattr(audio, "_last_play", 0.0)
    _release_and_wait()

    assert audio.play_safe(_PlayableSound()) == "channel"
    assert pg.mixer.init_calls == 1  # fast re-init happened inside play_safe
    assert audio.seconds_since_last_play() < 5


def test_play_clip_clears_channel_on_exception(monkeypatch):
    """A stale tts._current_channel would veto idle release forever."""
    from purple_tui import tts

    class BadChannel:
        def get_busy(self):
            raise RuntimeError("mixer died mid-clip")

    monkeypatch.setattr(tts, "pygame", SimpleNamespace(
        mixer=SimpleNamespace(Sound=lambda p: SimpleNamespace(get_length=lambda: 0.0)),
        time=SimpleNamespace(wait=lambda ms: None),
    ))
    monkeypatch.setattr(audio, "play_safe", lambda s: BadChannel())
    tts._current_channel = None

    assert tts._play_clip(Path("/nonexistent.wav"), tts._speech_id) is False
    assert tts._current_channel is None


class _FakeAppForIdleCheck:
    """Drives PurpleApp._check_audio_idle in isolation."""

    _check_audio_idle = PurpleApp._check_audio_idle

    def __init__(self, room):
        self.active_room = room
        self._audio_idle_timer = _FakeTimer()


def _idle_check_setup(monkeypatch, idle_seconds):
    from purple_tui import tts, power_manager
    calls = []
    monkeypatch.setattr(music_room, "_MIXER_READY", True)
    monkeypatch.setattr(tts, "_current_channel", None)
    monkeypatch.setattr(
        power_manager, "get_power_manager",
        lambda: type("PM", (), {"get_idle_seconds": lambda self: idle_seconds})())
    monkeypatch.setattr(music_room, "request_idle_release", lambda *a: calls.append(a))
    return calls


def test_idle_check_releases_when_everything_quiet(monkeypatch):
    calls = _idle_check_setup(monkeypatch, idle_seconds=999)
    _FakeAppForIdleCheck(Room.PLAY)._check_audio_idle()
    assert len(calls) == 1


def test_idle_check_vetoes(monkeypatch):
    from purple_tui import tts

    calls = _idle_check_setup(monkeypatch, idle_seconds=999)
    _FakeAppForIdleCheck(Room.MUSIC)._check_audio_idle()  # music room veto
    assert calls == []

    calls = _idle_check_setup(monkeypatch, idle_seconds=999)
    monkeypatch.setattr(tts, "_current_channel", object())  # speech veto
    _FakeAppForIdleCheck(Room.PLAY)._check_audio_idle()
    assert calls == []

    calls = _idle_check_setup(monkeypatch, idle_seconds=5)  # recent input veto
    _FakeAppForIdleCheck(Room.PLAY)._check_audio_idle()
    assert calls == []


def test_idle_check_stops_polling_once_mixer_closed(monkeypatch):
    """After a release (or on audio-less machines) the 30s poll must stop;
    the next keystroke re-arms it via _record_user_activity."""
    calls = _idle_check_setup(monkeypatch, idle_seconds=999)
    monkeypatch.setattr(music_room, "_MIXER_READY", None)
    app = _FakeAppForIdleCheck(Room.PLAY)
    timer = app._audio_idle_timer

    app._check_audio_idle()

    assert timer.stopped
    assert app._audio_idle_timer is None
    assert calls == []


def test_audio_idle_timer_rearm_respects_audio_ok():
    app = SimpleNamespace(
        _audio_idle_timer=None, audio_ok=True,
        _check_audio_idle=lambda: None,
        set_interval=lambda *a, **k: "timer",
    )
    PurpleApp._arm_audio_idle_timer(app)
    assert app._audio_idle_timer == "timer"

    app.audio_ok = False
    app._audio_idle_timer = None
    PurpleApp._arm_audio_idle_timer(app)
    assert app._audio_idle_timer is None  # no polling on audio-less machines
