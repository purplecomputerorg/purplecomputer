"""Audio mixer lifecycle: probe, warm, idle release, hotplug reinit.

Moved out of the Music room unchanged; nothing here draws.
"""
from pathlib import Path
import os
import subprocess
import sys
import threading as _threading
# Suppress ALSA error/log messages before pygame imports ALSA.
# These corrupt Textual's stderr-based UI. Install null handlers for both paths.
def _suppress_alsa_output():
    try:
        import ctypes
        import ctypes.util

        # Find libasound
        path = ctypes.util.find_library('asound')
        if not path:
            for p in ('libasound.so.2', 'libasound.so'):
                try:
                    path = p
                    ctypes.CDLL(p)
                    break
                except OSError:
                    path = None
        if not path:
            return

        asound = ctypes.CDLL(path)

        # Handler types: error has int err, log has uint level
        HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
        LOG_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                       ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p)

        noop = lambda *_: None
        err_h, log_h = HANDLER(noop), LOG_HANDLER(noop)
        _suppress_alsa_output._refs = (err_h, log_h)  # prevent GC

        asound.snd_lib_error_set_handler(err_h)
        try:
            asound.snd_lib_log_set_handler(log_h)
        except AttributeError:
            pass
    except Exception:
        pass

# pygame.mixer.init() blocks in C code holding the GIL on broken audio hw
# (T2 Macs, some Surfaces/AMDs). A stuck call wedges the whole interpreter
# — Textual stops rendering, evdev grab stays held, only a power cycle
# recovers. So we probe in a subprocess first (subprocess wait releases the
# GIL; SIGKILL on timeout), and only init in-process after the probe passes.
# See guides/boot-hang-debugging.md.
pygame = None  # populated by warm_mixer() once pygame is safe to import
_MIXER_READY: bool | None = None  # None = untested, True/False = cached result
_PROBE_TIMED_OUT = False  # True = probe hung (hw is broken, don't retry)
_KNOWN_SILENT = False  # True = output codec opens fine but is inaudible (don't retry)
_IDLE_RELEASED = False  # True = mixer closed after a quiet period; re-init skips the probe
_RELEASING = False  # True = idle-release quit in flight; mixer unusable until it completes
_MIXER_GENERATION = 0  # bumped on every quit; stale Sound caches reload when it changes

# An open SDL stream makes Pulse mix silence forever (real CPU on weak
# machines), so the app releases the mixer after this many quiet seconds
# and lazily re-inits on the next play.
AUDIO_IDLE_SECONDS = 60.0

# Codecs that init cleanly but drive no speakers: the amp sits on an I2C
# side-channel the generic HDA driver never powers on, so ALSA accepts frames
# into a dead amp and mixer.init() "succeeds" while nothing is audible. No
# software probe (not even a test tone) can observe this, so we gate on codec
# identity. See guides/boot-hang-debugging.md.
_SILENT_HDA_CODECS = ("CS8409",)


def _is_usb_card(card: Path) -> bool:
    """A USB ALSA card is a real output Pulse can route to."""
    try:
        return "usb" in os.path.realpath(card / "device").lower()
    except OSError:
        return False


def _silence_reason(sound_root: str = "/sys/class/sound") -> str | None:
    """Why the output can't make sound, or None if it might.

    'no-card': no sound card at all (e.g. DSP firmware missing). Must be
    vetoed because Pulse's module-always-sink fabricates a dummy sink, so
    mixer.init() "succeeds" while everything plays into the void. Transient:
    the card may still probe late in boot, so callers keep retrying.
    'silent-codec': an HDA codec on the denylist. Permanent.
    A plugged-in USB device clears both: Pulse routes to it. The hotplug
    re-probe and retry poll re-evaluate this, so plugging in a speaker flips
    audio back on without a restart.
    """
    root = Path(sound_root)
    cards = list(root.glob("card*"))
    if any(_is_usb_card(c) for c in cards):
        return None
    if not cards:
        return "no-card"
    for chip in root.glob("hwC*D*/chip_name"):
        try:
            name = chip.read_text().strip()
        except OSError:
            continue
        if any(silent in name for silent in _SILENT_HDA_CODECS):
            return "silent-codec"
    return None


def output_is_known_silent(sound_root: str = "/sys/class/sound") -> bool:
    return _silence_reason(sound_root) is not None

_MIXER_LOCK = _threading.Lock()


def _reap_orphan(proc) -> None:
    """Block until an abandoned probe child dies, so it doesn't linger as a
    zombie if the kernel eventually releases its D-state. Daemon-threaded."""
    try:
        proc.wait()
    except Exception:
        pass

_PROBE_SCRIPT = (
    "import os; os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'; "
    "import pygame.mixer; "
    "pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048); "
    "pygame.mixer.quit()"
)


def _init_mixer() -> bool:
    """In-process mixer init. Caller must hold _MIXER_LOCK (or be a
    recovery path that owns the mixer). Updates _MIXER_READY."""
    global _MIXER_READY, _IDLE_RELEASED
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        pygame.mixer.set_num_channels(16)
        _MIXER_READY = True
        _IDLE_RELEASED = False
    except pygame.error:
        _MIXER_READY = False
    return _MIXER_READY


def warm_mixer(timeout_seconds: float = 10.0) -> bool:
    """Probe mixer in a subprocess, then init in-process if it passed.

    Timeout must cover cold Python startup + pygame/numpy import + mixer
    init, so 10s gives margin for older hardware. True hangs (CS8409)
    block forever, so 10s cleanly separates working from broken.

    Called from both the post-boot warmup thread and MusicMode.on_mount.
    The lock serialises them so the probe runs at most once per process;
    a late caller waits for the early caller's result.
    """
    global pygame, _MIXER_READY, _PROBE_TIMED_OUT, _KNOWN_SILENT
    from .tts import _dbg
    _dbg("warm_mixer: waiting for _MIXER_LOCK")
    with _MIXER_LOCK:
        _dbg(f"warm_mixer: got lock, ready={_MIXER_READY}")
        if _RELEASING:
            return False
        if _MIXER_READY is not None:
            return _MIXER_READY
        if _IDLE_RELEASED and pygame is not None:
            # Re-init after an idle release: the probe already passed this
            # session and pygame is imported, so a direct init is safe and
            # fast (no subprocess). A failed init here is transient (Pulse
            # restarting, sink waking from suspend), so reset to None
            # instead of latching False: the next play retries.
            if _init_mixer():
                return True
            _MIXER_READY = None
            return False
        reason = _silence_reason()
        if reason is not None:
            # Only the codec-identity veto is permanent. 'no-card' stays
            # retryable: the card may probe late (SOF firmware still loading).
            _KNOWN_SILENT = reason == "silent-codec"
            _MIXER_READY = False
            return False
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", _PROBE_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            _MIXER_READY = False
            return False
        try:
            probe_ok = proc.wait(timeout=timeout_seconds) == 0
        except subprocess.TimeoutExpired:
            # A truly wedged codec (CS8409 on a T1/T2 Mac) leaves the child in
            # uninterruptible D-state: SIGKILL can't reap it, and a blocking
            # wait() would hang us forever, which is the "Audio: checking..."
            # that never resolves. Signal and abandon it: it's a separate
            # process so it can't wedge us, and a daemon reaper collects it if
            # the kernel ever lets go. wait(timeout) polls, so it always returns
            # at the deadline regardless of D-state.
            _PROBE_TIMED_OUT = True
            probe_ok = False
            try:
                proc.kill()
            except Exception:
                pass
            _threading.Thread(target=_reap_orphan, args=(proc,), daemon=True).start()
        except Exception:
            probe_ok = False
        if not probe_ok:
            _MIXER_READY = False
            return False
        _suppress_alsa_output()
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        import pygame as _pg
        import pygame.mixer  # noqa: F401
        pygame = _pg
        return _init_mixer()


def _ensure_mixer() -> bool:
    """Backward-compatible alias for callers that don't pass a timeout."""
    return warm_mixer()


def _reset_mixer_state() -> bool:
    """Clear cached probe result so warm_mixer() retries on next call.

    Returns False if the probe timed out or the codec is known-silent
    (hardware can't produce sound, retrying won't help).
    """
    global _MIXER_READY
    if _PROBE_TIMED_OUT or _KNOWN_SILENT:
        return False
    _MIXER_READY = None
    return True


def reinit_mixer() -> None:
    """Quit and re-init the pygame mixer to recover from a dead audio backend.

    In VMs, PulseAudio/PipeWire can drop the connection and SDL2 won't reconnect
    on its own. This forces a fresh connection. All cached Sound objects become
    invalid after quit(), so callers must clear their sound caches.
    """
    from .tts import _dbg
    _dbg("reinit_mixer: start")
    if not _ensure_mixer():
        return
    try:
        _dbg("reinit_mixer: calling mixer.quit()")
        _quit_mixer()
        _dbg("reinit_mixer: quit returned")
    except Exception:
        pass
    _init_mixer()
    _dbg(f"reinit_mixer: done ready={_MIXER_READY}")
    from . import tts
    tts._current_channel = None


def reinit_mixer_after_hotplug() -> bool:
    """Full re-probe after audio hardware changed (USB plug/unplug).

    Unlike reinit_mixer() (which assumes the mixer was working and just lost
    its connection), this resets the timeout flag too so a machine that
    failed at boot gets a fresh chance when a USB adapter is plugged in.
    Returns True iff the mixer is working after reinit.
    """
    global _MIXER_READY, _PROBE_TIMED_OUT, _KNOWN_SILENT, _IDLE_RELEASED
    from .tts import _dbg
    _dbg("reinit_after_hotplug: waiting for _MIXER_LOCK")
    with _MIXER_LOCK:
        if pygame is not None:
            try:
                if pygame.mixer.get_init():
                    _dbg("reinit_after_hotplug: calling mixer.quit()")
                    _quit_mixer()
                    _dbg("reinit_after_hotplug: quit returned")
            except Exception:
                pass
        _MIXER_READY = None
        _PROBE_TIMED_OUT = False
        _KNOWN_SILENT = False
        # Hardware changed: the old probe result no longer applies, so the
        # idle fast-path must not skip the fresh probe below.
        _IDLE_RELEASED = False
    try:
        from . import tts
        tts._current_channel = None
    except Exception:
        pass
    return warm_mixer()


def mixer_is_open() -> bool:
    """True while an SDL stream is open (Pulse's sink can't suspend)."""
    return bool(_MIXER_READY)


def mixer_generation() -> int:
    """Bumped on every mixer quit. Sound objects are tied to the device
    they were decoded for, so caches stamped with an older generation
    must reload (the contract reinit_mixer documents)."""
    return _MIXER_GENERATION


def _quit_mixer() -> None:
    """Quit the mixer and invalidate cached Sounds via the generation."""
    global _MIXER_GENERATION
    try:
        pygame.mixer.quit()
    finally:
        _MIXER_GENERATION += 1


def mixer_ready_for_play() -> bool:
    """Strict mixer check for cache loaders: True only when the mixer is
    usable right now.

    After an idle release this re-inits inline (direct init, no subprocess
    probe), so it never blocks the main thread the way a cold warm_mixer()
    could. In every other non-ready state it returns False like the old
    _MIXER_READY guard did.
    """
    if _MIXER_READY:
        return True
    if _RELEASING:
        return False
    return warm_mixer() if _IDLE_RELEASED else False


def should_attempt_play() -> bool:
    """Permissive gate for play_safe: is attempting Sound.play() sensible?

    Differs from mixer_ready_for_play() in the probe-in-flight state
    (_MIXER_READY is None without an idle release, e.g. during a hotplug
    re-probe): returns True so the play raises and play_safe's
    reinit-and-retry waits out the probe and recovers the sound, exactly
    as before idle release existed. False only when playing is pointless:
    known-broken output or a quit in flight.
    """
    if _MIXER_READY:
        return True
    if _RELEASING or _MIXER_READY is False:
        return False
    return warm_mixer() if _IDLE_RELEASED else True


def request_idle_release(min_quiet_seconds: float = AUDIO_IDLE_SECONDS) -> None:
    """Release the mixer if nothing has played for min_quiet_seconds.

    The quit runs in a daemon thread: mixer.quit() can wedge on a dying
    audio backend (see the UTM shutdown hang), and a wedged thread is
    harmless where a wedged UI is not. Racing plays are safe: the quiet
    period is re-checked under the lock, and a play that still loses the
    race is skipped (never crashed) by the _RELEASING gate.
    """
    from .audio import seconds_since_last_play
    if not _MIXER_READY or _RELEASING or \
            seconds_since_last_play() < min_quiet_seconds:
        return
    try:
        if pygame.mixer.get_busy():
            return
    except pygame.error:
        return
    _threading.Thread(target=_release_for_idle, args=(min_quiet_seconds,),
                      daemon=True, name="mixer-idle-release").start()


def _release_for_idle(min_quiet_seconds: float) -> None:
    global _MIXER_READY, _IDLE_RELEASED, _RELEASING
    from .audio import seconds_since_last_play
    from .tts import _dbg
    with _MIXER_LOCK:
        if not _MIXER_READY or _RELEASING:
            return
        try:
            busy = pygame.mixer.get_busy()
        except pygame.error:
            return
        if busy or seconds_since_last_play() < min_quiet_seconds:
            return
        _MIXER_READY = None
        _RELEASING = True
    # Quit OUTSIDE the lock: a wedged quit must strand only this daemon
    # thread. Holding the lock across it would block warm_mixer, and with
    # it the main thread's next play-recovery path. While _RELEASING is
    # set every mixer gate returns False, so nothing touches the
    # half-closed device.
    try:
        _quit_mixer()
    except Exception:
        pass
    with _MIXER_LOCK:
        _RELEASING = False
        _IDLE_RELEASED = True
    _dbg("mixer released after idle")


# Default backgrounds (dark and light themes)
