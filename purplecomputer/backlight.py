"""Panel backlight through /sys/class/backlight, shared by both UIs.

purple-backlight-max sets every backlight to full at boot and hands its
brightness file to the purple user, so any failure here leaves it bright.
"""

from pathlib import Path

from .power_manager import _power_log

BACKLIGHT_DIR = Path("/sys/class/backlight")
# Some panels go black at low raw values; nothing here goes below this.
FLOOR = 0.3
SLEEP_LEVEL = FLOOR


def set_level(fraction: float) -> bool:
    """Set every backlight to a fraction of its max. True if any took it."""
    fraction = max(FLOOR, min(1.0, fraction))
    ok = False
    for d in sorted(BACKLIGHT_DIR.glob("*")):
        try:
            top = int((d / "max_brightness").read_text())
            value = max(1, round(top * fraction))
            (d / "brightness").write_text(str(value))
            _power_log(f"BACKLIGHT {d.name}: {value}/{top}")
            ok = True
        except (OSError, ValueError) as e:
            _power_log(f"BACKLIGHT {d.name}: write failed ({e})")
    return ok
