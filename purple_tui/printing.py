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
STUCK_S = 60  # a job still waiting this long means the printer isn't taking it
NOT_PRINTED = "The printer didn't print that"
NOT_ANSWERING = "The printer isn't answering. Is it turned on?"
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
        job = _job_id(await _run("lp", "-d", QUEUE, "-t", "Purple Computer", *opts, path))
    except Exception as e:
        boot_log.heartbeat(f"print: failed to send ({e})")
        notify("The printer didn't answer. Try again soon")
        return False
    finally:
        os.unlink(path)  # lp has copied it into the spool
    boot_log.heartbeat(f"print: page sent as job {job}")
    notify("Printing!")
    asyncio.ensure_future(_watch(job, notify))
    return True


def _job_id(lp_out: str):
    """'request id is purple-12 (1 file(s))' -> '12'."""
    word = next((w for w in lp_out.split() if w.startswith(f"{QUEUE}-")), "")
    return word.rsplit("-", 1)[-1] or None


def _attr(ipp_out: str, name: str) -> str:
    """One attribute's value from ipptool -v output."""
    for line in ipp_out.splitlines():
        key, _, value = line.strip().partition(" = ")
        if key.split(" (")[0] == name:
            return value
    return ""


async def _watch(job, notify):
    """Until the job finishes, say once per problem what's wrong: no paper, a
    jam, a job CUPS gave up on, or a printer that never takes it."""
    said = set()

    def say(msg, why=""):
        if msg and msg not in said:
            said.add(msg)
            boot_log.heartbeat(f"print: job {job} {msg} {why}".rstrip())
            notify(msg)

    for tick in range(1, WATCH_S // WATCH_EVERY_S + 1):
        await asyncio.sleep(WATCH_EVERY_S)
        try:
            info = await _run("ipptool", "-tv", f"ipp://localhost/jobs/{job}", "get-job-attributes.test")
            reasons = await _run("lpstat", "-l", "-p", QUEUE)
        except Exception as e:
            boot_log.heartbeat(f"print: job {job} can't be checked ({e})")
            return
        state, why = _attr(info, "job-state"), f"({_attr(info, 'job-printer-state-message')})"
        if state in ("completed", "aborted", "canceled"):
            boot_log.heartbeat(f"print: job {job} {state} {why}")
            if state != "completed":
                say(NOT_PRINTED, why)
            return
        msg = problem(reasons)
        say(msg)
        if tick * WATCH_EVERY_S >= STUCK_S and not msg:
            say(NOT_ANSWERING, f"(still {state} {why})")
    # A job that never finishes holds up every page after it, since CUPS prints one at a time.
    boot_log.heartbeat(f"print: job {job} cancelled after {WATCH_S}s")
    try:
        await _run("cancel", f"{QUEUE}-{job}")
    except Exception:
        pass
