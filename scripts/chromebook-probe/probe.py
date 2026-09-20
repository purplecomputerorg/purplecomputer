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
import mmap
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

WATCHDOG_SECONDS = 300
MASTER_WAIT_SECONDS = 30
KEY_SECONDS = 10
CMD_TIMEOUT = 20
SPEECH_TIMEOUT = 120
EVIOCGRAB = 0x40044590
INPUT_EVENT = struct.Struct("llHHi")
EV_KEY = 1
KEY_Q = 16
DRM_IOCTL_MODE_CREATE_DUMB = 0xC02064B2
DRM_IOCTL_MODE_MAP_DUMB = 0xC01064B3
DRM_MODE_CONNECTED = 1
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

U32P = ctypes.POINTER(ctypes.c_uint32)


class ModeInfo(ctypes.Structure):
    _fields_ = [("clock", ctypes.c_uint32)] + [
        (name, ctypes.c_uint16) for name in (
            "hdisplay", "hsync_start", "hsync_end", "htotal", "hskew",
            "vdisplay", "vsync_start", "vsync_end", "vtotal", "vscan")
    ] + [("vrefresh", ctypes.c_uint32), ("flags", ctypes.c_uint32),
         ("type", ctypes.c_uint32), ("name", ctypes.c_char * 32)]


class Resources(ctypes.Structure):
    _fields_ = [("count_fbs", ctypes.c_int), ("fbs", U32P),
                ("count_crtcs", ctypes.c_int), ("crtcs", U32P),
                ("count_connectors", ctypes.c_int), ("connectors", U32P),
                ("count_encoders", ctypes.c_int), ("encoders", U32P),
                ("min_width", ctypes.c_uint32), ("max_width", ctypes.c_uint32),
                ("min_height", ctypes.c_uint32), ("max_height", ctypes.c_uint32)]


class Connector(ctypes.Structure):
    _fields_ = [("connector_id", ctypes.c_uint32), ("encoder_id", ctypes.c_uint32),
                ("connector_type", ctypes.c_uint32), ("connector_type_id", ctypes.c_uint32),
                ("connection", ctypes.c_int),
                ("mm_width", ctypes.c_uint32), ("mm_height", ctypes.c_uint32),
                ("subpixel", ctypes.c_int),
                ("count_modes", ctypes.c_int), ("modes", ctypes.POINTER(ModeInfo)),
                ("count_props", ctypes.c_int), ("props", U32P),
                ("prop_values", ctypes.POINTER(ctypes.c_uint64)),
                ("count_encoders", ctypes.c_int), ("encoders", U32P)]


class Encoder(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "encoder_id", "encoder_type", "crtc_id", "possible_crtcs", "possible_clones")]


DEST = os.path.dirname(os.path.abspath(__file__))
TONE_WAV = f"{DEST}/tone.wav"
SPEECH_WAV = f"{DEST}/speech.wav"
FRECON_KILLED_FLAG = f"{DEST}/frecon_killed"
F128_SHIM = f"{DEST}/libf128shim.so"

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


class DumbDisplay:
    """One XRGB8888 dumb buffer scanned out on the first connected connector."""

    def __init__(self, path, drm):
        self.drm = drm
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        connector_id, self.mode, crtc_id = self._pick_output()
        self.size = (self.mode.hdisplay, self.mode.vdisplay)
        self._wait_for_master()
        handle, self.pitch, length = self._create_dumb()
        fb_id = ctypes.c_uint32()
        self._check("drmModeAddFB", drm.drmModeAddFB(
            self.fd, *self.size, 24, 32, self.pitch, handle, ctypes.byref(fb_id)))
        self.pixels = self._map(handle, length)
        connector = ctypes.c_uint32(connector_id)
        self._check("drmModeSetCrtc", drm.drmModeSetCrtc(
            self.fd, crtc_id, fb_id, 0, 0, ctypes.byref(connector), 1, ctypes.byref(self.mode)))
        log(f"{path}: {self.size} '{self.mode.name.decode()}' crtc {crtc_id} pitch {self.pitch}")

    def _check(self, what, rc):
        if rc:
            raise OSError(f"{what} failed: rc={rc} errno={ctypes.get_errno()}")

    def _pick_output(self):
        drm = self.drm
        res_p = drm.drmModeGetResources(self.fd)
        if not res_p:
            raise OSError("no KMS resources (not a display device)")
        res = res_p.contents
        for i in range(res.count_connectors):
            conn = drm.drmModeGetConnector(self.fd, res.connectors[i]).contents
            log(f"connector {conn.connector_id}: type {conn.connector_type}"
                f" connection {conn.connection} modes {conn.count_modes}")
            if conn.connection != DRM_MODE_CONNECTED or not conn.count_modes:
                continue
            mode = ModeInfo.from_buffer_copy(conn.modes[0])
            encoder_ids = [conn.encoder_id] if conn.encoder_id else conn.encoders[:conn.count_encoders]
            for encoder_id in encoder_ids:
                enc = drm.drmModeGetEncoder(self.fd, encoder_id).contents
                crtc_id = enc.crtc_id or next(
                    (res.crtcs[c] for c in range(res.count_crtcs) if enc.possible_crtcs >> c & 1), 0)
                if crtc_id:
                    return conn.connector_id, mode, crtc_id
        raise OSError("no connected connector with a usable crtc")

    def _wait_for_master(self):
        deadline = time.time() + MASTER_WAIT_SECONDS
        while self.drm.drmSetMaster(self.fd):
            if time.time() > deadline:
                log("still no DRM master: killing frecon (probe.sh reboots at the end)")
                open(FRECON_KILLED_FLAG, "w").close()
                run("pkill", "-9", "frecon")
                time.sleep(1)
                self._check("drmSetMaster after frecon kill", self.drm.drmSetMaster(self.fd))
                return
            time.sleep(0.5)
        log("got DRM master")

    def _create_dumb(self):
        request = bytearray(struct.pack("IIIIIIQ", self.size[1], self.size[0], 32, 0, 0, 0, 0))
        fcntl.ioctl(self.fd, DRM_IOCTL_MODE_CREATE_DUMB, request)
        _, _, _, _, handle, pitch, length = struct.unpack("IIIIIIQ", request)
        return handle, pitch, length

    def _map(self, handle, length):
        request = bytearray(struct.pack("IIQ", handle, 0, 0))
        fcntl.ioctl(self.fd, DRM_IOCTL_MODE_MAP_DUMB, request)
        offset = struct.unpack("IIQ", request)[2]
        return mmap.mmap(self.fd, length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset)

    def present(self, frame):
        raw = frame.get_buffer().raw
        stride = frame.get_pitch()
        if stride == self.pitch:
            self.pixels[:len(raw)] = raw
            return
        for y in range(self.size[1]):
            self.pixels[y * self.pitch:y * self.pitch + stride] = raw[y * stride:(y + 1) * stride]


def load_drm():
    drm = ctypes.CDLL("libdrm.so.2", use_errno=True)
    drm.drmModeGetResources.restype = ctypes.POINTER(Resources)
    drm.drmModeGetConnector.restype = ctypes.POINTER(Connector)
    drm.drmModeGetEncoder.restype = ctypes.POINTER(Encoder)
    return drm


def draw(*lines):
    log("SCREEN:", " | ".join(lines))
    if not screen:
        return
    surface.fill((60, 20, 90))
    for i, line in enumerate(lines):
        surface.blit(font.render(line, True, (255, 255, 255)), (60, 60 + i * 70))
    screen.present(surface)


def display():
    global screen, surface, font
    drm = load_drm()
    for path in sorted(glob.glob("/dev/dri/card*")):
        try:
            screen = DumbDisplay(path, drm)
            break
        except OSError as err:
            log(f"{path}: {err}")
    if not screen:
        return False
    pygame.font.init()
    font = pygame.font.Font(None, 64)
    surface = pygame.Surface(screen.size, 0, 32, (0xFF0000, 0xFF00, 0xFF, 0))
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
