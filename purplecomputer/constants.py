"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""
import os

# =============================================================================
# SUPPORT
# =============================================================================

SUPPORT_EMAIL = "support@purplecomputer.org"

# Debug mode: touch /opt/purple/debug to enable debug features on any install.
# Controls: "Exit to System" in parent menu, debug shell on exit, extra diagnostics.
# PURPLE_DEBUG_FLAG moves the flag where /opt is read-only (ChromeOS rootfs).
DEBUG_FLAG_PATH = os.environ.get("PURPLE_DEBUG_FLAG", "/opt/purple/debug")

def is_debug() -> bool:
    """Check if this install has debug mode enabled."""
    from pathlib import Path
    return Path(DEBUG_FLAG_PATH).exists()


ART_COLS, ART_ROWS = 70, 30   # the canvas Art grid, in square cells
ART_SIDE_UNITS, ART_BAND_UNITS = 1, 3   # Art's margin beside the grid, and its header and hint bands
# The canvas viewport in square units, one unit per Art cell, so Art fills it in whole cells on every
# screen and leftover pixels land outside the frame. 72x36, a 2:1 shape.
CANVAS_COLS = ART_COLS + 2 * ART_SIDE_UNITS
CANVAS_ROWS = ART_ROWS + 2 * ART_BAND_UNITS
# Art's grid before it grew: pack pictures and Art states that name no grid were made on it, and are centered on today's.
OLD_ART_GRID = (56, 24)

# =============================================================================
# TIMING
# =============================================================================

STICKY_SHIFT_GRACE = 8.0     # How long sticky shift stays active (seconds)
ESCAPE_HOLD_THRESHOLD = 1.0  # How long to hold Escape for parent mode (seconds)
HOLD_OR_TAP_THRESHOLD = 0.8  # Space/Enter hold threshold for code panel / loop mode (seconds)
MASH_GAP = 0.4              # A key pressed while another is held mixes into its square, unless a third key went down this recently: then it's mashing (seconds)

# Volume 1 to 10 (0 is Sound Off), about 5.4 dB apart under pactl's cubic
# map from -49 dB (15%) to 0 dB (100%). Laptops differ by 30 dB or more, so
# the scale is wide enough that a loud one has a whisper at the bottom and a
# quiet one its loud at the top; the first-boot chime picks the starting
# step. Icons run parallel to the steps. docs/plans/audio-volume.md.
VOLUME_LEVELS = [0, 15, 19, 23, 28, 35, 43, 53, 66, 81, 100]
VOLUME_DEFAULT = 53  # volume 7: where a first boot starts when the chime can't measure

# Nerd Font icons (https://www.nerdfonts.com/cheat-sheet)
# Volume icons (nf-md-volume variants)
ICON_VOLUME_OFF = "󰖁"       # nf-md-volume_off (muted)
ICON_VOLUME_LOW = "󰕿"       # nf-md-volume_low
ICON_VOLUME_MED = "󰖀"       # nf-md-volume_medium
ICON_VOLUME_HIGH = "󰕾"      # nf-md-volume_high
VOLUME_ICONS = [ICON_VOLUME_OFF] + [ICON_VOLUME_LOW] * 3 + [ICON_VOLUME_MED] * 4 + [ICON_VOLUME_HIGH] * 3
ICON_SAVE = "󰆓"             # nf-md-content_save
ICON_PALETTE = "󰏘"          # nf-md-palette
ICON_MUSIC = "\uf001"       # nf-fa-music
ICON_DRUM = "\uee32"        # nf-fa-drum
ICON_CHAT = "󰭹"             # nf-md-chat_question
ICON_MENU = "󰀻"             # nf-md-apps (grid icon for room picker)
ICON_PENCIL = "󰏪"           # nf-md-pencil (write mode)
ICON_KEYBOARD = "󰌌"          # nf-md-keyboard (key capture indicator)
ICON_BROOM = "󰃢"              # nf-md-broom (start fresh / clear)
ICON_ROBOT = "󰚩"              # nf-md-robot (code space toggle)
ICON_COMPUTER = "\U000F0379"  # nf-md-monitor (this computer, title bar)
ICON_LAPTOP = "\U000F0322"    # nf-md-laptop (lid status lines)
ICON_PLUG = "\U000F06A5"      # nf-md-power_plug (plugged in)
ICON_HOURGLASS = "\U000F051F" # nf-md-timer_sand (countdowns)

# Battery icons (nf-md-battery variants)
ICON_BATTERY_FULL = "󰁹"     # nf-md-battery (100%)
ICON_BATTERY_HIGH = "󰂀"     # nf-md-battery_70 (70-99%)
ICON_BATTERY_MED = "󰁾"      # nf-md-battery_50 (30-69%)
ICON_BATTERY_LOW = "󰁻"      # nf-md-battery_20 (10-29%)
ICON_BATTERY_EMPTY = "󰂃"    # nf-md-battery_alert (<10%)
ICON_BATTERY_CHARGING = "󰂄" # nf-md-battery_charging


# USB / installed indicator
ICON_USB = "\uf287"           # nf-fa-usb
ICON_HARDDISK = "󰋊"         # nf-md-harddisk (installed)


# Where the live stick keeps its squashfs and install payload: casper's paths,
# unless the 32-bit Key's boot script recorded its own (initramfs/purple-live).
LIVE_CONF_PATH = "/run/purple-live.conf"


def _live_conf() -> dict:
    try:
        with open(LIVE_CONF_PATH) as f:
            return dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)
    except OSError:
        return {}


_LIVE_CONF = _live_conf()
SQUASHFS_PATH = _LIVE_CONF.get("SQUASHFS", "/cdrom/casper/filesystem.squashfs")
PAYLOAD_DIR = _LIVE_CONF.get("PURPLE_PAYLOAD_DIR", "/cdrom/purple")
USB_CACHE_MARKER = "/tmp/purple-usb-cached"
# Written instead when there is not enough RAM to hold what a session needs
USB_KEEP_MARKER = "/tmp/purple-usb-keep"
# Static reboot/poweroff binary on its own tmpfs (scripts/purple-stage-reboot.sh)
REBOOT_BIN = "/run/purple-reboot-mount/purple-reboot"

# Touched after the first frame paints. xinitrc waits for this before starting
# the compositor, so picom's GL init lands after the import/first-paint crunch
# instead of contending with it and slowing boot. See intel-display-tuning.md.
UI_READY_MARKER = "/tmp/purple-ui-ready"

# Written into the installed system by install.sh when audio worked during
# the live session; consumed on the first installed boot to tell "worked
# minutes ago, silent now" (warm-reboot codec wedge, fixed by a power off)
# apart from hardware that never had sound. See rooms/sleep_screen.py.
LIVE_AUDIO_MARKER = "/var/log/purple/audio-worked-in-live"

# PURPLE_FAKE_USB env var simulates USB boot states for testing.
# Values: "caching" (USB blinking), "cached" (safe to remove), "removed" (USB pulled out),
# "reinserted" (pulled out, then plugged back in), "keep" (too little RAM, must stay in),
# "keep-removed" (pulled out anyway)
_FAKE_USB = os.environ.get("PURPLE_FAKE_USB", "")


def is_live_boot() -> bool:
    """Check if running from a live boot: casper, or the 32-bit Key's purple-live.

    Reads /proc/cmdline once and caches the result (doesn't change at runtime).
    Set PURPLE_FAKE_USB=caching|cached|removed to simulate in dev/test.
    """
    if not hasattr(is_live_boot, "_cached"):
        if _FAKE_USB:
            is_live_boot._cached = True
        else:
            try:
                from pathlib import Path
                cmdline = Path("/proc/cmdline").read_text()
                is_live_boot._cached = any(f"boot={mode}" in cmdline for mode in ("casper", "purple-live"))

            except Exception:
                is_live_boot._cached = False
    return is_live_boot._cached


def is_usb_cached() -> bool:
    """Check if the USB squashfs has been cached to RAM."""
    if _FAKE_USB:
        return _FAKE_USB in ("cached", "removed", "reinserted")
    return os.path.exists(USB_CACHE_MARKER)


def is_usb_needed() -> bool:
    """Too little RAM to hold the system: the USB has to stay in."""
    if _FAKE_USB:
        return _FAKE_USB.startswith("keep")
    return os.path.exists(USB_KEEP_MARKER)


MOUNTS_PATH = "/proc/self/mounts"
SYS_BLOCK_DIR = "/sys/class/block"
DISK_BY_LABEL_DIR = "/dev/disk/by-label"
USB_LABELS = ("PURPLE_INSTALLER", "PURPLE_DEBUG")


def _usb_block_device(path: str) -> str | None:
    """Kernel name (sdb1, sr0) of the block device mounted under path, or None."""
    best, dev = "", None
    try:
        with open(MOUNTS_PATH) as f:
            for src, mnt, *_ in (line.split() for line in f):
                if src.startswith("/dev/") and len(mnt) > len(best) and (path + "/").startswith(mnt.rstrip("/") + "/"):
                    best, dev = mnt, os.path.basename(os.path.realpath(src))
    except OSError:
        pass
    return dev


def is_usb_present() -> bool:
    """Check if the USB drive is still physically connected."""
    if _FAKE_USB:
        return not _FAKE_USB.endswith(("removed", "reinserted"))
    # The mount and the squashfs inode outlive a pulled stick; its sysfs entry does not.
    if not getattr(is_usb_present, "_dev", None):
        is_usb_present._dev = _usb_block_device(SQUASHFS_PATH)
    if is_usb_present._dev:
        return os.path.exists(os.path.join(SYS_BLOCK_DIR, is_usb_present._dev))
    return os.path.exists(SQUASHFS_PATH)


def is_usb_reinserted() -> bool:
    """A Purple USB is plugged in again after the one this session booted from was pulled.

    It comes back under a new kernel name, and this session's mounts and save
    stay tied to the old one, so nothing reads from it until a restart.
    """
    if _FAKE_USB:
        return _FAKE_USB == "reinserted"
    return not is_usb_present() and any(os.path.exists(os.path.join(DISK_BY_LABEL_DIR, label)) for label in USB_LABELS)

# =============================================================================
# ZOOM REGIONS FOR DEMO RECORDING
# =============================================================================
# Named regions for dynamic zoom during demo videos.
# Coordinates are percentages of the viewport (0.0-1.0) for resolution independence.
# Format: (x_center, y_center, width_fraction, height_fraction)
# The post-processor calculates actual pixels based on recording resolution.
#
# Note: "input" focuses on the Play room input area (bottom portion of viewport).
ZOOM_REGIONS = {
    # Full viewport (no zoom, 100% of content visible)
    "viewport": (0.5, 0.5, 1.0, 1.0),

    # Play room input area (bottom 40% of viewport, horizontally centered)
    # Shows the input line and a few lines of results above it
    "input": (0.5, 0.75, 0.7, 0.4),

    # Play room results area (middle portion, for showing computation results)
    "results": (0.5, 0.5, 0.8, 0.5),

    # Ad: Play content is left-aligned ("Ask ->" starts at the far left), so
    # centered crops cut it off. These shift the center left (only x_center is
    # used by the crop math) so the left edge stays in frame.
    # "ad-input": tight on the input line for typing.
    # "ad-reveal": wider pull-back to show the stacked result.
    "ad-input": (0.18, 0.80, 0.4, 0.4),
    "ad-reveal": (0.33, 0.50, 0.75, 0.75),

    # Art room center (center of canvas for drawing demos)
    "art-center": (0.5, 0.5, 0.6, 0.6),

    # Music room keyboard area (lower portion where keys are displayed)
    "music-keys": (0.5, 0.7, 0.8, 0.5),

    # Play room welcome area (upper-left where text history appears)
    # With 3x zoom, center must be in range 0.17-0.83 to avoid clamping
    "play-welcome": (0.4, 0.28, 0.7, 0.5),

    # Art room lower-right (for "This is Art room" intro text)
    "art-text-right": (0.7, 0.7, 0.5, 0.4),

    # Art room lower-left (for "Now let's go to Music room" text)
    # Text is at very bottom-left, center at 0.83 vertical to show it
    "art-text-left": (0.25, 0.82, 0.4, 0.3),

    # Closing screen: "This is Purple Computer" centered text
    "closing-title": (0.5, 0.38, 0.6, 0.4),
}
