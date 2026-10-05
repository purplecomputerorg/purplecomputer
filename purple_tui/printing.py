"""USB printing: whether a printer is ready, and sending it a page.

The system side (scripts/purple-printer-setup.sh, run on every printer plug)
sets up the queue and writes STATE; this module only reads it, so checking
costs one small file read and no process. Design: guides/printing.md.
"""

import asyncio
import json
import os
import tempfile
import time

from . import boot_log
from .constants import is_live_boot, is_usb_present

STATE = "/run/purple-printer.json"
QUEUE = "purple"
COOLDOWN_S = 20
SESSION_LIMIT = 20
WATCH_S, WATCH_EVERY_S = 180, 3
# printer-state-reasons prefixes, most specific first, with what the screen says
PROBLEMS = (
    ("media-jam", "Paper is stuck in the printer"),
    ("media-empty", "The printer needs paper"),
    ("media-needed", "The printer needs paper"),
    ("marker-supply-empty", "The printer is out of ink"),
    ("toner-empty", "The printer is out of ink"),
    ("door-open", "A printer door is open"),
    ("cover-open", "A printer door is open"),
    ("offline", "The printer is turned off"),
)

_FAKE = os.environ.get("PURPLE_FAKE_PRINTER") == "1"
_last_at = -COOLDOWN_S
_count = 0


NONE, SETTING_UP, BROKEN, READY = "none", "setting up", "broken", "ready"
SETUP_TIMEOUT_S = 120  # the setup service gives up at 90 s
# What a press on a Print card that can't print says
WHY_NOT = {
    NONE: "Plug in a printer with its USB cable",
    SETTING_UP: "The printer is getting ready",
    BROKEN: "This printer doesn't work with Purple yet",
}


def status() -> str:
    """NONE, SETTING_UP, BROKEN or READY, from the file the setup script writes.
    On a live boot the print stack is read from the stick, so a pulled stick can't print."""
    if _FAKE:
        return READY
    state = _state()
    if not state:
        return NONE
    if is_live_boot() and not is_usb_present():
        return BROKEN
    if state.get("ready"):
        return READY
    if state.get("via") == SETTING_UP and time.time() - _state_mtime() < SETUP_TIMEOUT_S:
        return SETTING_UP
    return BROKEN


def why_not():
    """What to say when Print is pressed but can't print, or None when it can."""
    now = status()
    if now == BROKEN and _state().get("ready"):
        return "Put the Purple USB back in to print"
    return WHY_NOT.get(now)


def printer():
    """The ready printer's state, or None."""
    if _FAKE:
        return {"ready": True, "model": "Pretend Printer", "via": "fake"}
    return _state() if status() == READY else None


def _state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def state_stamp():
    """Changes whenever the setup script rewrites or removes its file: one stat, no read."""
    try:
        st = os.stat(STATE)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return 0


def _state_mtime() -> float:
    try:
        return os.stat(STATE).st_mtime
    except OSError:
        return 0.0


def status_line() -> str:
    """One line for Support info."""
    state, now = _state(), status()
    if now == NONE:
        return "Printer: none plugged in"
    if now == READY:
        return f"Printer: {state.get('model')}, ready"
    if now == SETTING_UP:
        return "Printer: getting ready"
    return f"Printer: {state.get('model')} can't print yet (Technical: {state.get('via')})"


def ready_in() -> float:
    """Seconds until the next print is allowed: 0 now, inf for the rest of this boot."""
    if _count >= SESSION_LIMIT:
        return float("inf")
    return max(0.0, _last_at + COOLDOWN_S - time.monotonic())


def problem(reasons: str):
    return next((msg for key, msg in PROBLEMS if key in reasons), None)


async def _run(*argv) -> str:
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    if proc.returncode:
        raise OSError(f"{argv[0]} exited {proc.returncode}")
    return out.decode(errors="replace")


async def print_page(surface, landscape: bool, notify) -> bool:
    """Send one page; notify(text) tells the screen what happened. Returns
    whether the page was sent."""
    global _last_at, _count
    if printer() is None or ready_in():
        return False
    _last_at, _count = time.monotonic(), _count + 1
    import pygame
    if _FAKE:  # previews and tests: the page lands next to the screenshots
        pygame.image.save(surface, os.path.join(os.environ.get("PURPLE_SCREENSHOT_DIR", tempfile.gettempdir()), "print.png"))
        notify("Printing!")
        return True
    fd, path = tempfile.mkstemp(prefix="purple-print-", suffix=".png")
    os.close(fd)
    try:
        pygame.image.save(surface, path)
        opts = ["-o", "fit-to-page"] + (["-o", "landscape"] if landscape else [])
        await _run("lp", "-d", QUEUE, "-t", "Purple Computer", *opts, path)
    except Exception as e:
        boot_log.heartbeat(f"print: failed to send ({e})")
        notify("The printer didn't answer. Try again soon")
        return False
    finally:
        os.unlink(path)  # lp has copied it into the spool
    boot_log.heartbeat("print: page sent")
    notify("Printing!")
    asyncio.ensure_future(_watch(notify))
    return True


async def _watch(notify):
    """Until the queue empties, say once per problem what's wrong (no paper, a jam)."""
    said = set()
    for _ in range(WATCH_S // WATCH_EVERY_S):
        await asyncio.sleep(WATCH_EVERY_S)
        try:
            if not (await _run("lpstat", "-o", QUEUE)).strip():
                return
            msg = problem(await _run("lpstat", "-l", "-p", QUEUE))
        except Exception:
            return
        if msg and msg not in said:
            said.add(msg)
            boot_log.heartbeat(f"print: {msg}")
            notify(msg)
