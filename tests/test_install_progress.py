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
