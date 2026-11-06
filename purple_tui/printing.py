"""USB printing: whether a printer is ready, and sending it a page.

The system side (scripts/purple-printer-setup.sh, run on every printer plug)
sets up the queue and writes STATE; this module only reads it, so checking
costs one small file read and no process. Design: guides/printing.md.
"""

import asyncio
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass

from . import boot_log
from .constants import is_live_boot, is_usb_present

STATE = "/run/purple-printer.json"
HEAL = "/run/purple-printer.heal"  # the setup script rebuilds everything when it finds this
QUEUE = "purple"
CUPS = "ipp://localhost"
COOLDOWN_S = 20
SESSION_LIMIT = 20
# Only Purple's own link to the printer is timed tightly: how long a printer
# takes to print varies too much between models to judge (guides/printing.md).
WATCH_EVERY_S = 3
ANSWER_S = 10  # for one "are you there?" to the printer
LOST_S = 45  # nothing answers this long: cancel and rebuild the print stack
SLOW_S = 45  # still not done this long: say so
STALL_S = 600  # nothing about the job changes this long: cancel and rebuild
HEALS = 2  # rebuilds in a row before asking for the printer's power button
NOT_PRINTED = "The printer didn't print that"
STILL_WORKING = "The printer is still working on it"
NOT_ANSWERING = "The printer isn't answering. Try turning it off and on"
# printer-state-reasons prefixes, most specific first, with what the screen says
PROBLEMS = (
    ("media-jam", "Paper is stuck in the printer"),
    ("media-empty", "The printer needs paper"),
    ("media-needed", "The printer needs paper"),
    ("marker-supply-empty", "The printer is out of ink"),
    ("toner-empty", "The printer is out of ink"),
    ("door-open", "A printer door is open"),
    ("cover-open", "A printer door is open"),
)
COMPLETED, CANCELED, STUCK, GONE = "completed", "canceled", "stuck", "gone with its queue"

FAKE = os.environ.get("PURPLE_FAKE_PRINTER") == "1"
_last_at = -COOLDOWN_S
_count = 0
_heals = 0
_healed_stamp = None
_now, _sleep = time.monotonic, asyncio.sleep  # the watcher's clock, for tests


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
    if FAKE:
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
    if FAKE:
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


async def _run(*argv, check=True, timeout=30) -> str:
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise OSError(f"{argv[0]} took over {timeout}s")
    if check and proc.returncode:
        raise OSError(f"{argv[0]} exited {proc.returncode}")
    return out.decode(errors="replace")


async def print_pages(surfaces, landscape: bool, notify) -> bool:
    """Send the pages as one job; notify(text) tells the screen what happened.
    Returns whether they were sent."""
    global _last_at, _count
    if printer() is None or ready_in():
        return False
    _last_at, _count = time.monotonic(), _count + 1
    import pygame
    if FAKE:  # previews and tests: the pages land next to the screenshots
        folder = os.environ.get("PURPLE_SCREENSHOT_DIR", tempfile.gettempdir())
        for i, surface in enumerate(surfaces):
            pygame.image.save(surface, os.path.join(folder, f"print{i + 1 if i else ''}.png"))
        notify("Printing!")
        return True
    stamp, paths = state_stamp(), []
    try:
        for surface in surfaces:
            fd, path = tempfile.mkstemp(prefix="purple-print-", suffix=".png")
            os.close(fd)
            paths.append(path)
            pygame.image.save(surface, path)
        opts = ["-o", "fit-to-page"] + (["-o", "landscape"] if landscape else [])
        job = _job_id(await _run("lp", "-d", QUEUE, "-t", "Purple Computer", *opts, *paths))
    except Exception as e:
        boot_log.heartbeat(f"print: failed to send ({e})")
        await _give_up(None, notify, heal=True)
        return False
    finally:
        for path in paths:
            os.unlink(path)  # lp has copied them into the spool
    boot_log.heartbeat(f"print: {len(surfaces)} page(s) sent as job {job}")
    notify("Printing!")
    if job:
        asyncio.ensure_future(_watch(job, stamp, notify))
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


@dataclass(frozen=True)
class Look:
    """One check on a sent job. The default is what a check that got no answer from CUPS sees."""
    state: str = ""  # job-state
    news: tuple = ()  # all CUPS says about the job, to notice it moving
    alerts: str = ""  # the queue's printer-state-reasons
    answers: bool = False  # CUPS knows the job and the printer answers


async def _look(job) -> Look:
    try:
        info = await _run("ipptool", "-tv", f"{CUPS}/jobs/{job}", "get-job-attributes.test")
        queue = await _run("lpstat", "-l", "-p", QUEUE)
    except OSError:
        return Look()
    news = tuple(_attr(info, name) for name in ("job-state", "job-printer-state-message",
                                                "job-impressions-completed", "job-media-sheets-completed"))
    alerts = next((line.strip() for line in queue.splitlines() if "Alerts:" in line), "")
    done = news[0] in (COMPLETED, CANCELED, "aborted")
    return Look(news[0], news, alerts, done or await _printer_answers())


async def _printer_answers() -> bool:
    """Whether the printer answers a status query. A printer that stops
    responding behind ipp-usb shows nothing wrong in CUPS: the job just sits."""
    uri = _state().get("uri", "")
    if not uri.startswith("ipp://"):
        return True  # the USB backend's route has no address to ask
    try:
        out = await _run("ipptool", "-T", str(ANSWER_S), "-tv", uri, "get-printer-attributes.test",
                         check=False, timeout=ANSWER_S + 5)
    except OSError:
        return False
    # Any reply counts: the stock test also fails on attributes a printer may lack. A timeout
    # still prints "status-code = successful-ok", so only the bytes received tell.
    return re.search(r"RECEIVED: [1-9]\d* bytes", out) is not None


class _Clocks:
    """A sent job's timers: each look at it says what happens next."""

    def __init__(self, now):
        self.started = self.changed = now
        self.lost_since = None
        self.last = None

    def next(self, look: Look, now: float):
        """COMPLETED, CANCELED or STUCK when the job is over; else a line for the screen, or None."""
        if look.state in (COMPLETED, CANCELED):
            return look.state
        if look.state == "aborted":
            return STUCK
        trouble = problem(look.alerts)  # a paper or ink wait is the family's to fix: never time it out
        if trouble or (look.news, look.alerts) != self.last:
            self.last, self.changed = (look.news, look.alerts), now
        self.lost_since = None if look.answers else (now if self.lost_since is None else self.lost_since)
        lost = self.lost_since is not None and now - self.lost_since >= LOST_S
        if lost or now - self.changed >= STALL_S:
            return STUCK
        slow = now - self.started >= SLOW_S and self.lost_since is None
        return trouble or (STILL_WORKING if slow else None)


async def _watch(job, stamp, notify):
    """Follow a sent job until it's over, saying once per problem what's wrong."""
    global _heals
    clocks, said, seen = _Clocks(_now()), set(), None
    while True:
        await _sleep(WATCH_EVERY_S)
        look = await _look(job)
        if look != seen:
            seen = look
            boot_log.heartbeat(f"print: job {job} {look.news or 'unknown to CUPS'} {look.alerts} answers={look.answers}")
        verdict = clocks.next(look, _now())
        if verdict != COMPLETED and state_stamp() != stamp:
            verdict = GONE  # unplugged or rebuilt: the job went with the old queue
        if verdict in (COMPLETED, CANCELED, STUCK, GONE):
            break
        if verdict and verdict not in said:
            said.add(verdict)
            boot_log.heartbeat(f"print: job {job} {verdict}")
            notify(verdict)
    boot_log.heartbeat(f"print: job {job} {verdict}")
    if verdict == COMPLETED:
        _heals = 0
    else:
        await _give_up(job, notify, heal=verdict == STUCK)


async def _give_up(job, notify, heal: bool):
    """The pages won't print: let the kid try again right away, and when Purple
    lost the printer, rebuild the print stack the way a restart would."""
    global _last_at, _count
    _last_at, _count = -COOLDOWN_S, max(0, _count - 1)
    if job:  # a stuck job blocks every page behind it
        try:
            await _run("cancel", f"{QUEUE}-{job}")
        except OSError:
            pass  # already over
    if heal and _heals >= HEALS:
        notify(NOT_ANSWERING)
        return
    notify(NOT_PRINTED)
    if heal:
        await _heal()


async def _heal():
    global _heals, _healed_stamp
    stamp = state_stamp()
    if stamp == _healed_stamp:
        return  # another job already asked for this rebuild
    _heals, _healed_stamp = _heals + 1, stamp
    boot_log.heartbeat(f"print: rebuilding the print stack ({_heals} of {HEALS})")
    try:
        await _run("sudo", "-n", "sh", "-c", f"touch {HEAL} && systemctl --no-block restart purple-printer.service")
    except OSError as e:
        boot_log.heartbeat(f"print: couldn't rebuild ({e})")
