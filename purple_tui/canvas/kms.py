"""Scanout without X: one KMS dumb buffer on the first connected output.

Used where there is no display server (PURPLE_DISPLAY=kms). Only libdrm and
kernel ioctls, no GBM/EGL/Mesa: guides/chromebook-dev-mode-plan.md. Stands
alone (no package imports) so scripts/chromebook/probe.py can load it.
"""

import ctypes
import fcntl
import glob
import mmap
import os
import struct
import subprocess
import time

DRM_IOCTL_MODE_CREATE_DUMB = 0xC02064B2
DRM_IOCTL_MODE_MAP_DUMB = 0xC01064B3
DRM_MODE_CONNECTED = 1
XRGB_MASKS = (0xFF0000, 0xFF00, 0xFF, 0)
MASTER_WAIT_SECONDS = 1  # a console that holds master keeps it; this only covers one that is just leaving
EVICT_RETRY_SECONDS = 5
# Whoever holds DRM master when we start (ChromeOS's console) has to let go.
EVICT_COMMANDS = (["stop", "frecon"], ["pkill", "-9", "frecon"])

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


def _load_drm():
    drm = ctypes.CDLL("libdrm.so.2", use_errno=True)
    drm.drmModeGetResources.restype = ctypes.POINTER(Resources)
    drm.drmModeGetConnector.restype = ctypes.POINTER(Connector)
    drm.drmModeGetEncoder.restype = ctypes.POINTER(Encoder)
    return drm


class DumbDisplay:
    """One XRGB8888 dumb buffer scanned out on the first connected connector."""

    def __init__(self, path, drm, log, master_wait):
        self.drm, self.log = drm, log
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        connector_id, self.mode, crtc_id = self._pick_output()
        self.size = (self.mode.hdisplay, self.mode.vdisplay)
        self.evicted_console = self._take_master(master_wait)
        handle, self.pitch, length = self._create_dumb()
        fb_id = ctypes.c_uint32()
        self._check("drmModeAddFB", drm.drmModeAddFB(
            self.fd, *self.size, 24, 32, self.pitch, handle, ctypes.byref(fb_id)))
        self.pixels = self._map(handle, length)
        connector = ctypes.c_uint32(connector_id)
        self._check("drmModeSetCrtc", drm.drmModeSetCrtc(
            self.fd, crtc_id, fb_id, 0, 0, ctypes.byref(connector), 1, ctypes.byref(self.mode)))
        log(f"kms: {path} {self.size} '{self.mode.name.decode()}' crtc {crtc_id} pitch {self.pitch}")

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
            self.log(f"kms: connector {conn.connector_id} type {conn.connector_type}"
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

    def _master_within(self, seconds):
        deadline = time.monotonic() + seconds
        while self.drm.drmSetMaster(self.fd):
            if time.monotonic() > deadline:
                return False
            time.sleep(0.1)
        return True

    def _take_master(self, master_wait):
        """True when the console had to be evicted to get DRM master."""
        if self._master_within(master_wait):
            return False
        for cmd in EVICT_COMMANDS:
            self.log(f"kms: no DRM master after {master_wait}s: {' '.join(cmd)}")
            try:
                evicted = subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                continue
            if evicted and self._master_within(EVICT_RETRY_SECONDS):
                return True
        raise OSError("could not get DRM master")

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

    def make_surface(self, pygame):
        """The surface to draw on. It is a window onto a parent as wide as the
        buffer's pitch, so present() is one copy even when the pitch has padding."""
        self._frame = pygame.Surface((self.pitch // 4, self.size[1]), 0, 32, XRGB_MASKS)
        return self._frame.subsurface((0, 0, *self.size))

    def present(self):
        raw = self._frame.get_buffer().raw
        self.pixels[:len(raw)] = raw


def open_display(log=print, master_wait=MASTER_WAIT_SECONDS):
    """The first /dev/dri card that can scan out (others are render-only, like vgem)."""
    drm = _load_drm()
    for path in sorted(glob.glob("/dev/dri/card*")):
        try:
            return DumbDisplay(path, drm, log, master_wait)
        except OSError as err:
            log(f"kms: {path}: {err}")
    raise OSError("no usable KMS display")
