"""Read-only system diagnostics for the Support info screen.

Every helper is pure: it reads sysfs/proc/commands and returns formatted
text. No side effects on the running app. All subprocess calls are wrapped
with short timeouts and never raise, so a flaky tool like dmidecode or
lsusb can't crash the screen.
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def _run(*args, timeout: float = 2.0) -> str:
    """Run a command, return stdout trimmed, or '(unavailable)' on any failure."""
    try:
        r = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (r.stdout or "").strip()
        return out or "(no output)"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "(unavailable)"


def _read(path: str, default: str = "(unavailable)") -> str:
    try:
        text = Path(path).read_text().strip()
        return text or default
    except OSError:
        return default


def get_version_label() -> str:
    """Format Purple's installed/dev version for display.

    Semver (v1.0, v1.2.3) shows as "Version 1.0".
    Date-time (v2026.03.30-1430) shows as "Build: Mar 30, 2026".
    Dev builds (build-abc1234-20260330) show as "Dev build: abc1234".
    Falls back to git short hash for dev/VM environments.
    Returns empty string if nothing is discoverable.
    """
    version_file = Path("/etc/purple-version")
    if not version_file.exists():
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=2,
                cwd=Path(__file__).parent,
            )
            if r.returncode == 0 and r.stdout.strip():
                return f"Dev: {r.stdout.strip()}"
        except Exception:
            pass
        return ""

    version = version_file.read_text().strip()
    if not version:
        return ""

    if re.match(r'^v?\d+\.\d+(\.\d+)?$', version):
        return f"Version {version.lstrip('v')}"

    m = re.match(r'^v?(\d{4})\.(\d{2})\.(\d{2})-(\d{4})$', version)
    if m:
        year, month, day, _ = m.groups()
        names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mon = names[int(month)] if 1 <= int(month) <= 12 else month
        return f"Build: {mon} {int(day)}, {year}"

    m = re.match(r'^build-([a-f0-9]+)-', version)
    if m:
        return f"Dev build: {m.group(1)}"

    return version


def get_product_name() -> str:
    """Return the machine's DMI product name, or a fallback."""
    name = _read("/sys/class/dmi/id/product_name", "")
    if name:
        return name
    vendor = _read("/sys/class/dmi/id/sys_vendor", "")
    return vendor or "Unknown hardware"


def get_audio_status_line(audio_ok) -> str:
    if audio_ok is True:
        return "Audio: working"
    if audio_ok is False:
        return "Audio not working. Plug in a USB speaker or USB audio adapter. Sound should start within a few seconds."
    return "Audio: checking..."


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "(unknown)"


def _ram_total() -> str:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return f"{kb // 1024} MB"
    except (OSError, ValueError):
        pass
    return "(unknown)"


def collect_device_info() -> str:
    """Broad device dump for the Device info sub-screen."""
    lines = []

    version = get_version_label() or "(dev)"
    lines.append(f"Purple: {version}")

    uname = _run("uname", "-rvm")
    lines.append(f"Kernel: {uname}")

    lines.append(f"Model: {_read('/sys/class/dmi/id/product_name', '(unknown)')}")
    lines.append(f"Vendor: {_read('/sys/class/dmi/id/sys_vendor', '(unknown)')}")
    lines.append(f"BIOS: {_read('/sys/class/dmi/id/bios_version', '(unknown)')}")

    lines.append(f"CPU: {_cpu_model()}")
    lines.append(f"RAM: {_ram_total()}")
    lines.append("")

    lines.append("Disks:")
    disks = _run("lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,MODEL")
    if disks in ("(unavailable)", "(no output)"):
        lines.append("  (unavailable)")
    else:
        for ln in disks.splitlines():
            lines.append(f"  {ln}")
    lines.append("")

    lines.append("Network:")
    try:
        nics = [n for n in sorted(os.listdir("/sys/class/net")) if n != "lo"]
        if not nics:
            lines.append("  (none)")
        for iface in nics:
            state = _read(f"/sys/class/net/{iface}/operstate", "?")
            lines.append(f"  {iface} ({state})")
    except OSError:
        lines.append("  (unavailable)")
    lines.append("")

    lines.append("Display:")
    lines.append(f"  DISPLAY={os.environ.get('DISPLAY', '(none)')}")
    xrandr = _run("xrandr", "--current")
    if xrandr not in ("(unavailable)", "(no output)"):
        for ln in xrandr.splitlines():
            stripped = ln.strip()
            if "connected" in stripped or re.search(r'\d+x\d+.*\*', stripped):
                lines.append(f"  {stripped}")
    lines.append("")

    lines.append("USB devices:")
    usb = _run("lsusb")
    if usb in ("(unavailable)", "(no output)"):
        lines.append("  (unavailable)")
    else:
        for ln in usb.splitlines():
            lines.append(f"  {ln}")

    return "\n".join(lines)


def collect_audio_info(audio_ok) -> str:
    """Focused audio dump for the Audio info sub-screen."""
    if audio_ok is True:
        status = "working"
    elif audio_ok is False:
        status = "not working"
    else:
        status = "checking"
    lines = [f"Status: {status}", ""]

    # Report the mixer state only if pygame is already loaded (via
    # warm_mixer). Don't import pygame here: a fresh import prints a
    # banner to stdout and drags in numpy.
    mixer_state = "(not initialized)"
    pg = sys.modules.get("pygame")
    if pg is not None:
        try:
            init = pg.mixer.get_init()
            if init:
                freq, size, channels = init
                mixer_state = f"{freq} Hz, {abs(size)}-bit, {channels} channels"
        except Exception:
            pass
    lines.append(f"pygame mixer: {mixer_state}")
    lines.append("")

    lines.append("Sound cards:")
    cards = _read("/proc/asound/cards", "")
    if cards:
        for ln in cards.splitlines():
            lines.append(f"  {ln}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("HDA codecs:")
    try:
        sound_root = Path("/sys/class/sound")
        hw_devs = sorted(p.name for p in sound_root.glob("hwC*D*")) if sound_root.exists() else []
        if not hw_devs:
            lines.append("  (none found)")
        for dev in hw_devs:
            base = sound_root / dev
            vendor = _read(str(base / "vendor_name"), "?")
            chip = _read(str(base / "chip_name"), "?")
            ssid = _read(str(base / "subsystem_id"), "?")
            lines.append(f"  {dev}: {vendor} {chip} ({ssid})")
    except OSError:
        lines.append("  (unavailable)")
    lines.append("")

    lines.append("/dev/snd:")
    try:
        entries = sorted(os.listdir("/dev/snd"))
        lines.append("  " + " ".join(entries) if entries else "  (empty)")
    except OSError:
        lines.append("  (unavailable)")
    lines.append("")

    lines.append("Kernel audio messages (recent):")
    dmesg = _run("dmesg", "-t", timeout=3)
    if dmesg in ("(unavailable)", "(no output)"):
        lines.append("  (dmesg not readable without elevated privileges)")
    else:
        pat = re.compile(r'cs8409|hda|cirrus|snd_pcm|snd_hda|audio|sound', re.IGNORECASE)
        matches = [ln for ln in dmesg.splitlines() if pat.search(ln)][-25:]
        if matches:
            for ln in matches:
                lines.append(f"  {ln}")
        else:
            lines.append("  (no audio-related lines found)")
    lines.append("")

    lines.append("USB audio devices:")
    usb = _run("lsusb")
    if usb in ("(unavailable)", "(no output)"):
        lines.append("  (unavailable)")
    else:
        pat = re.compile(r'audio|sound|headset|\bdac\b|\bmic\b', re.IGNORECASE)
        matches = [ln for ln in usb.splitlines() if pat.search(ln)]
        if matches:
            for ln in matches:
                lines.append(f"  {ln}")
        else:
            lines.append("  (none detected)")

    return "\n".join(lines)
