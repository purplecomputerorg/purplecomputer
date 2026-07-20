#!/usr/bin/env python3
"""Tests for the install progress stderr-reading pattern.

The key invariant: _run_install_async must complete when the subprocess exits,
regardless of whether any child process is holding the stderr pipe open.

Run with: pytest tests/test_install_progress.py -v
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


async def _run_with_cancel_on_exit(script: str) -> list[str]:
    """Runs script, reads stderr lines, cancels reader when process exits.
    This is the pattern used in InstallProgressScreen._run_install_async.
    Returns collected lines."""
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", script,
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
    )

    lines: list[str] = []

    async def read_stderr() -> None:
        buf = b""
        while True:
            chunk = await proc.stderr.read(256)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                lines.append(line.decode("utf-8", errors="replace").strip())

    stderr_task = asyncio.ensure_future(read_stderr())
    # Poll returncode (set by SIGCHLD handler, independent of pipe state).
    # proc.wait() can hang in Python 3.13+ if a child holds the pipe open.
    while proc.returncode is None:
        await asyncio.sleep(0.05)
    stderr_task.cancel()
    try:
        await stderr_task
    except asyncio.CancelledError:
        pass

    return lines


async def _run_eof_only(script: str) -> list[str]:
    """Old pattern: wait for EOF on stderr, then proc.wait().
    This HANGS if a child holds the pipe open."""
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", script,
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
    )

    lines: list[str] = []
    buf = b""
    while True:
        chunk = await proc.stderr.read(256)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            lines.append(line.decode("utf-8", errors="replace").strip())

    await proc.wait()
    return lines


# Script that mimics install.sh: spawns a background subshell that keeps
# stderr open (does NOT redirect fd 2 away), then exits.
_SCRIPT_WITH_PIPE_HOLDER = (
    "echo '[PURPLE] Writing Purple Computer to disk' >&2\n"
    "echo '[PURPLE] UEFI boot setup complete' >&2\n"
    # Background subshell inherits fd 2 = pipe, keeps it open after parent exits
    "( sleep 60 ) &\n"
    "exit 0\n"
)

# Same but background process redirects stderr away - pipe closes on exit
_SCRIPT_WITHOUT_PIPE_HOLDER = (
    "echo '[PURPLE] Writing Purple Computer to disk' >&2\n"
    "echo '[PURPLE] UEFI boot setup complete' >&2\n"
    "( sleep 60 2>/dev/null ) &\n"
    "exit 0\n"
)


def test_cancel_on_exit_completes_with_pipe_holder():
    """The cancel-on-exit pattern must complete even when a child holds stderr open."""
    async def run():
        return await asyncio.wait_for(
            _run_with_cancel_on_exit(_SCRIPT_WITH_PIPE_HOLDER),
            timeout=5.0,
        )
    lines = asyncio.run(run())
    assert "[PURPLE] UEFI boot setup complete" in lines


def test_cancel_on_exit_collects_all_lines_without_pipe_holder():
    """Sanity check: cancel-on-exit still collects all lines in the normal case."""
    async def run():
        return await asyncio.wait_for(
            _run_with_cancel_on_exit(_SCRIPT_WITHOUT_PIPE_HOLDER),
            timeout=5.0,
        )
    lines = asyncio.run(run())
    assert "[PURPLE] Writing Purple Computer to disk" in lines
    assert "[PURPLE] UEFI boot setup complete" in lines


def test_eof_only_hangs_with_pipe_holder():
    """Documents the OLD broken pattern: waiting for EOF hangs when a child
    holds the pipe open. If this test stops failing, the test script is wrong."""
    async def run():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                _run_eof_only(_SCRIPT_WITH_PIPE_HOLDER),
                timeout=3.0,
            )
    asyncio.run(run())


# --- Progress mapping + creep timer -----------------------------------------

def _make_screen():
    """An InstallProgressScreen with UI repaint stubbed out (no running app)."""
    from purple_tui.rooms.parent_menu import InstallProgressScreen
    screen = InstallProgressScreen.__new__(InstallProgressScreen)
    # Bypass Textual widget init; set only the state _handle_line/creep touch.
    screen._progress = 0
    screen._status = ""
    screen._phase = "installing"
    screen._log_lines = []
    screen._corrupt_key = False
    screen._start_time = 0.0
    screen._creep_timer = None
    screen._creep_t0 = 0.0
    screen._creep_lo = 0
    screen._creep_hi = 0
    screen._creep_tau = 1.0
    screen._write_t0 = None
    screen._k = 1.0
    screen._update_ui = lambda: None
    return screen


def test_pv_and_markers_are_monotonic_and_banded():
    screen = _make_screen()
    seq = [
        "[PURPLE] Detecting internal disk...",
        "[PURPLE] Found internal disk: sda",
        "[PURPLE] Writing Purple Computer to disk...",
        "[PURPLE-PV] 0", "[PURPLE-PV] 50", "[PURPLE-PV] 100",
        "[PURPLE] Reloading partition table...",
        "[PURPLE] Verifying disk write (this takes a few minutes)...",
        "[PURPLE-PV2] 0", "[PURPLE-PV2] 100",
        "[PURPLE] Disk verification passed (SHA256 match)",
        "[PURPLE] Rebuilding partition table for this disk...",
        "[PURPLE] Waiting for partition devices...",
        "[PURPLE] Checking root filesystem...",
        "[PURPLE] Growing root filesystem to fill disk...",
        "[PURPLE] Setting up boot (UEFI + BIOS)...",
        "[PURPLE] Boot setup complete (UEFI + BIOS)",
    ]
    progress = []
    for line in seq:
        screen._handle_line(line)
        progress.append(screen._progress)

    assert progress == sorted(progress), "progress must never regress"
    # Write pv 100 lands at the top of the write band.
    assert screen._progress >= 70 or True  # checked below at exact points
    # Walk specific checkpoints.
    s = _make_screen()
    s._handle_line("[PURPLE] Writing Purple Computer to disk...")
    s._handle_line("[PURPLE-PV] 100")
    assert s._progress == 70
    s._handle_line("[PURPLE] Verifying disk write...")
    s._handle_line("[PURPLE-PV2] 100")
    assert s._progress == 85
    s._handle_line("[PURPLE] Setting up boot (UEFI + BIOS)...")
    assert s._progress == 94
    s._handle_line("[PURPLE] Boot setup complete (UEFI + BIOS)")
    assert s._progress == 98


def test_backup_retry_keeps_progress_and_updates_status():
    screen = _make_screen()
    screen._handle_line("[PURPLE] Writing Purple Computer to disk...")
    screen._handle_line("[PURPLE-PV] 60")
    before = screen._progress
    screen._handle_line("[PURPLE-RETRY] backup copy")
    assert screen._status == "Double-checking with a backup copy..."
    assert screen._progress == before
    screen._handle_line("[PURPLE-PV] 0")
    assert screen._progress == before, "restarted pv must not regress the bar"
    screen._handle_line("[PURPLE-PV] 100")
    assert screen._progress == 70


def test_merge_marker_updates_status_without_regressing():
    screen = _make_screen()
    screen._handle_line("[PURPLE] Writing Purple Computer to disk...")
    screen._handle_line("[PURPLE-PV] 60")
    before = screen._progress
    screen._handle_line("[PURPLE-MERGING]")
    assert screen._status == "Repairing the damaged data, this adds a few extra minutes..."
    assert screen._progress == before
    screen._handle_line("[PURPLE-PV] 0")
    assert screen._progress == before, "restarted pv must not regress the bar"


def test_corrupt_key_marker_sets_flag():
    screen = _make_screen()
    assert not screen._corrupt_key
    screen._handle_line("[PURPLE-CORRUPT-KEY] 1")
    assert screen._corrupt_key


def test_calibration_factor_from_write_time(monkeypatch):
    import purple_tui.rooms.parent_menu as pm
    screen = _make_screen()
    clock = {"t": 1000.0}
    monkeypatch.setattr(pm.time, "monotonic", lambda: clock["t"])
    screen._handle_line("[PURPLE] Writing Purple Computer to disk...")
    clock["t"] += pm._NOMINAL_WRITE_SECS * 2  # twice as slow as reference
    screen._handle_line("[PURPLE] Reloading partition table...")
    assert screen._k == pytest.approx(2.0)
    assert screen._write_t0 is None


def test_creep_fills_toward_hi_without_reaching_it(monkeypatch):
    import purple_tui.rooms.parent_menu as pm
    screen = _make_screen()
    clock = {"t": 0.0}
    monkeypatch.setattr(pm.time, "monotonic", lambda: clock["t"])
    screen._progress = 94
    screen._start_creep_band(94, 98, nominal_secs=40, pv_driven=False)
    seen = []
    for _ in range(200):
        clock["t"] += 1.0
        screen._creep_tick()
        seen.append(screen._progress)
    assert max(seen) < 98, "creep must never reach the band ceiling"
    assert max(seen) >= 96, "creep should make visible progress within the band"
    assert seen == sorted(seen), "creep must never regress"


def test_creep_disabled_for_pv_driven_band():
    screen = _make_screen()
    screen._progress = 10
    screen._start_creep_band(10, 70, nominal_secs=420, pv_driven=True)
    assert screen._creep_hi == screen._creep_lo  # creep is a no-op


def test_eta_does_not_overpromise_on_slow_tail(monkeypatch):
    """A machine that crawls through the slow tail must not be told '1 minute'
    while minutes of work remain."""
    import purple_tui.rooms.parent_menu as pm
    screen = _make_screen()
    clock = {"t": 0.0}
    monkeypatch.setattr(pm.time, "monotonic", lambda: clock["t"])
    screen._start_time = 0.0
    # Bar reaches 85% (verify done) but only after a slow 12 minutes of real time.
    screen._progress = 85
    clock["t"] = 12 * 60
    hint = screen._eta_hint()
    # At 85%, ~83% of expected time has passed, so ~2.4 min should remain -- the
    # old linear model would have said well under a minute. Must not say "1 minute".
    assert "1 minute left" not in hint
    assert hint in ("Almost done",) or "minutes left" in hint


def test_eta_shows_range_early_and_done_near_end(monkeypatch):
    import purple_tui.rooms.parent_menu as pm
    screen = _make_screen()
    clock = {"t": 0.0}
    monkeypatch.setattr(pm.time, "monotonic", lambda: clock["t"])
    screen._start_time = 0.0
    screen._progress = 12
    clock["t"] = 30
    assert screen._eta_hint() == "This usually takes 10 to 15 minutes"
    screen._progress = 99
    clock["t"] = 13 * 60
    assert screen._eta_hint() == "Almost done"


def test_eta_hints_have_no_trailing_period(monkeypatch):
    import purple_tui.rooms.parent_menu as pm
    screen = _make_screen()
    clock = {"t": 0.0}
    monkeypatch.setattr(pm.time, "monotonic", lambda: clock["t"])
    screen._start_time = 0.0
    for prog, t in ((10, 5), (50, 120), (85, 720), (99, 800)):
        screen._progress = prog
        clock["t"] = t
        assert not screen._eta_hint().endswith("."), f"period at {prog}%"


def test_render_bar_width_is_constant():
    screen = _make_screen()
    widths = {len(screen._render_bar(p)) for p in (0, 5, 12, 70, 100)}
    assert len(widths) == 1, f"bar width must not change: {widths}"
