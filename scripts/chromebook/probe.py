"""Purple Chromebook probe v2: display, sound, speech and keyboard, board-agnostic.

Run by probe.sh after `stop ui`. Design: guides/chromebook-dev-mode-plan.md
Uses only interfaces that are the same on every Chromebook: kernel KMS dumb buffers
(no GBM/EGL/Mesa), CRAS for audio (raw ALSA only as a data point), evdev for keys.
Everything is discovered at runtime; nothing is hardcoded to one board.
"""
import ctypes
import fcntl
import glob
import math
import os
import re
import select
import signal
import struct
import subprocess
import sys
import time
import traceback
import wave

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "alsa"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402

import kms  # noqa: E402  purple_tui/canvas/kms.py, copied next to this file by build-bundle.sh

WATCHDOG_SECONDS = 300
MASTER_WAIT_SECONDS = 30
KEY_SECONDS = 10
CMD_TIMEOUT = 20
SPEECH_TIMEOUT = 120
EVIOCGRAB = 0x40044590
INPUT_EVENT = struct.Struct("llHHi")
EV_KEY = 1
KEY_Q = 16
# Every symbol pygame-ce 2.5.8's SDL resolves before it will offer kmsdrm.
SDL_KMSDRM_SYMBOLS = {
    "libdrm.so.2": "drmAuthMagic drmDropMaster drmGetCap drmHandleEvent drmModeAddFB drmModeAddFB2"
    " drmModeAddFB2WithModifiers drmModeCrtcGetGamma drmModeCrtcSetGamma drmModeFreeConnector"
    " drmModeFreeCrtc drmModeFreeEncoder drmModeFreeFB drmModeFreeObjectProperties"
    " drmModeFreePlane drmModeFreePlaneResources drmModeFreeProperty drmModeFreeResources"
    " drmModeGetConnector drmModeGetCrtc drmModeGetEncoder drmModeGetFB drmModeGetPlane"
    " drmModeGetPlaneResources drmModeGetProperty drmModeGetResources drmModeMoveCursor"
    " drmModeObjectGetProperties drmModeObjectSetProperty drmModePageFlip drmModeRmFB"
    " drmModeSetCrtc drmModeSetCursor drmModeSetCursor2 drmModeSetPlane drmSetClientCap"
    " drmSetMaster",
    "libgbm.so.1": "gbm_bo_create gbm_bo_destroy gbm_bo_get_device gbm_bo_get_format"
    " gbm_bo_get_handle gbm_bo_get_handle_for_plane gbm_bo_get_height gbm_bo_get_modifier"
    " gbm_bo_get_offset gbm_bo_get_plane_count gbm_bo_get_stride gbm_bo_get_stride_for_plane"
    " gbm_bo_get_user_data gbm_bo_get_width gbm_bo_set_user_data gbm_bo_write gbm_create_device"
    " gbm_device_destroy gbm_device_is_format_supported gbm_surface_create gbm_surface_destroy"
    " gbm_surface_lock_front_buffer gbm_surface_release_buffer",
}

DEST = os.path.dirname(os.path.abspath(__file__))
TONE_WAV = f"{DEST}/tone.wav"
SPEECH_WAV = f"{DEST}/speech.wav"
FRECON_KILLED_FLAG = f"{DEST}/frecon_killed"
F128_SHIM = f"{os.path.dirname(DEST)}/libf128shim.so"

screen = None
surface = None
font = None
results = {}


def log(*parts):
    print(f"[{time.strftime('%H:%M:%S')}]", *parts, flush=True)


def run(*cmd, timeout=CMD_TIMEOUT):
    log("$", " ".join(cmd))
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as err:
        log(f"no result: {err!r}")
        return False
    log(f"rc={proc.returncode} in {time.time() - start:.1f}s", (proc.stdout + proc.stderr).strip())
    return proc.returncode == 0


def stage(name, fn):
    log(f"=== {name} ===")
    try:
        results[name] = fn()
    except Exception:
        results[name] = False
        log(traceback.format_exc())
    log(f"--- {name}: {'OK' if results[name] else 'FAILED'}")


def sdl_symbols():
    """For the record only: which symbol made SDL say 'kmsdrm not available'."""
    complete = True
    for lib_name, symbols in SDL_KMSDRM_SYMBOLS.items():
        lib = ctypes.CDLL(lib_name)
        missing = [s for s in symbols.split() if not hasattr(lib, s)]
        log(f"{lib_name}: missing {missing or 'nothing'}")
        complete = complete and not missing
    return complete


def draw(*lines):
    log("SCREEN:", " | ".join(lines))
    if not screen:
        return
    surface.fill((60, 20, 90))
    for i, line in enumerate(lines):
        surface.blit(font.render(line, True, (255, 255, 255)), (60, 60 + i * 70))
    screen.present()


def display():
    global screen, surface, font
    try:
        screen = kms.open_display(log=log, master_wait=MASTER_WAIT_SECONDS)
    except OSError as err:
        log(f"no display: {err}")
        return False
    if screen.evicted_console:
        open(FRECON_KILLED_FLAG, "w").close()
    pygame.font.init()
    font = pygame.font.Font(None, 64)
    surface = screen.make_surface(pygame)
    frames = 60
    start = time.time()
    for i in range(frames):
        draw("PURPLE PROBE", f"frame {i}", "is this purple, with white text?")
    log(f"full-screen redraw: {(time.time() - start) * 1000 / frames:.1f} ms/frame (includes logging)")
    return True


def write_tone():
    rate = 44100
    samples = (int(12000 * math.sin(2 * math.pi * 440 * t / rate)) for t in range(rate))
    with wave.open(TONE_WAV, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def mixer_child(path, device):
    """Runs in a child process so a wedged ALSA open cannot hang the probe."""
    if device != "default":
        os.environ["AUDIODEV"] = device
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024)
    print("mixer init", pygame.mixer.get_init(), flush=True)
    channel = pygame.mixer.Sound(path).play()
    while channel.get_busy():
        time.sleep(0.05)


def mixer_play(path, device):
    return run(sys.executable, "-u", __file__, "--mixer", path, device)


def speaker_card():
    """(index, id) of the first ALSA card that is not an HDMI-only HDA controller."""
    cards = re.findall(r"^\s*(\d+) \[(\S+)\s*\]", open("/proc/asound/cards").read(), re.M)
    log("cards:", cards)
    return next(((i, name) for i, name in cards if name != "PCH"), cards[0])


def audio_cras():
    run("sh", "-c", "cat /etc/asound.conf; ls /usr/lib64/alsa-lib")
    run("sh", "-c", "cras_test_client --dump_server_info | head -40")  # full dump once
    write_tone()
    draw("SOUND 1 of 6", "through CRAS: aplay")
    ok_aplay = run("aplay", TONE_WAV)
    draw("SOUND 2 of 6", "through CRAS: pygame")
    ok_mixer = mixer_play(TONE_WAV, "default")
    log(f"cras: aplay={ok_aplay} pygame={ok_mixer}")
    return ok_mixer


def cras_info():
    run("sh", "-c", "cras_test_client --dump_server_info | head -14")


def audio_cras_fresh():
    """CRAS restarted with Chrome never having run: the state Purple boots into."""
    cras_info()
    draw("SOUND 5 of 6", "fresh CRAS, untouched")
    ok_untouched = mixer_play(TONE_WAV, "default")
    dump = subprocess.run(["cras_test_client", "--dump_server_info"], capture_output=True, text=True).stdout
    node = re.search(r"^\s*\(\w+\)\s+(\d+:\d+).*INTERNAL_SPEAKER", dump, re.M)
    log("internal speaker node:", node and node.group(1))
    if node:
        run("cras_test_client", "--select_output", node.group(1))
    run("cras_test_client", "--mute", "0")
    run("cras_test_client", "--user_mute", "0")
    run("cras_test_client", "--volume", "75")
    cras_info()
    draw("SOUND 6 of 6", "fresh CRAS, speaker selected by us")
    return mixer_play(TONE_WAV, "default") and ok_untouched


def audio_raw_alsa():
    index, name = speaker_card()
    hw = f"plughw:{index},0"
    run("stop", "cras")
    try:
        run("alsaucm", "-c", name, "list", "_verbs")
        run("alsaucm", "-c", name, "set", "_verb", "HiFi", "set", "_enadev", "Speaker")
        draw("SOUND 3 of 6", f"raw ALSA: aplay {hw}")
        ok_aplay = run("aplay", "-D", hw, TONE_WAV)
        draw("SOUND 4 of 6", f"raw ALSA: pygame {hw}")
        ok_mixer = mixer_play(TONE_WAV, hw)
    finally:
        run("start", "cras")
        time.sleep(2)
    log(f"raw alsa: aplay={ok_aplay} pygame={ok_mixer}")
    return ok_mixer


def speech_child(wav_path):
    start = time.time()
    from piper import PiperVoice
    voice = PiperVoice.load(glob.glob(f"{DEST}/voice/*.onnx")[0])
    loaded = time.time()
    with wave.open(wav_path, "wb") as wav:
        voice.synthesize_wav("Hello from Purple Computer.", wav)
    print(f"piper: load {loaded - start:.1f}s, synth {time.time() - loaded:.1f}s", flush=True)


def speech():
    draw("SPEECH", "loading the voice")
    # ChromeOS's glibc lacks strfromf128, which onnxruntime links against; the shim supplies it.
    os.environ["LD_PRELOAD"] = F128_SHIM
    try:
        if not run(sys.executable, "-u", __file__, "--speak", SPEECH_WAV, timeout=SPEECH_TIMEOUT):
            return False
    finally:
        del os.environ["LD_PRELOAD"]
    draw("SPEECH", "Hello from Purple Computer.")
    return mixer_play(SPEECH_WAV, "default")


def has_letter_keys(key_bitmap):
    """key_bitmap is the B: KEY= line: 64-bit hex words, most significant first."""
    bits = int("".join(word.zfill(16) for word in key_bitmap.split()), 16)
    return bits >> KEY_Q & 0x3FF == 0x3FF


def keyboard_paths():
    paths = []
    for block in open("/proc/bus/input/devices").read().split("\n\n"):
        keys = re.search(r"B: KEY=(.*)", block)
        event = re.search(r"Handlers=.*?(event\d+)", block)
        if keys and event and has_letter_keys(keys.group(1)):
            log("keyboard:", re.search(r'N: Name="(.*)"', block).group(1), event.group(1))
            paths.append("/dev/input/" + event.group(1))
    return paths


def keyboard():
    fds = [os.open(p, os.O_RDONLY | os.O_NONBLOCK) for p in keyboard_paths()]
    for fd in fds:
        fcntl.ioctl(fd, EVIOCGRAB, 1)
    count = 0
    deadline = time.time() + KEY_SECONDS
    try:
        while (left := deadline - time.time()) > 0:
            draw("KEYBOARD", f"press keys: {left:.0f} s left", f"{count} key presses seen")
            for fd in select.select(fds, [], [], 0.5)[0]:
                data = os.read(fd, INPUT_EVENT.size * 64)
                for offset in range(0, len(data), INPUT_EVENT.size):
                    _, _, kind, code, value = INPUT_EVENT.unpack_from(data, offset)
                    if kind == EV_KEY:
                        log(f"key code={code} value={value}")
                        count += value == 1
    finally:
        for fd in fds:
            fcntl.ioctl(fd, EVIOCGRAB, 0)
            os.close(fd)
    return count > 0


def main():
    signal.alarm(WATCHDOG_SECONDS)
    log(f"pygame-ce {pygame.version.ver}, SDL {pygame.version.SDL}")
    stage("sdl_kmsdrm_symbols", sdl_symbols)
    stage("display", display)
    stage("audio_cras", audio_cras)
    stage("speech", speech)
    stage("audio_raw_alsa", audio_raw_alsa)
    stage("audio_cras_fresh", audio_cras_fresh)
    stage("keyboard", keyboard)
    log("RESULTS:", results)
    draw("DONE", *(f"{k}: {'OK' if v else 'FAILED'}" for k, v in results.items()))
    time.sleep(5)


if sys.argv[1:2] == ["--mixer"]:
    mixer_child(*sys.argv[2:4])
elif sys.argv[1:2] == ["--speak"]:
    speech_child(sys.argv[2])
else:
    main()
