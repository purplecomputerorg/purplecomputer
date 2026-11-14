"""Self-healing printing against a real CUPS: the "purple" queue sends over IPP
to a second cupsd standing in for the printer, which these tests freeze (a
wedged ipp-usb looks like this: CUPS shows nothing wrong) or kill. Skipped
where CUPS isn't installed."""
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

from purple_tui import printing
from purple_tui.canvas.harness import run

pytestmark = pytest.mark.skipif(not all(map(shutil.which, ("cupsd", "lp", "lpadmin", "ipptool"))),
                                reason="needs CUPS")


def _port():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _cupsd(home: Path, server_bin: Path, data_dir: Path, port: int):
    for d in ("etc", "spool/tmp", "cache", "state", "log"):
        (home / d).mkdir(parents=True)
    me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    group = subprocess.run(["id", "-gn"], capture_output=True, text=True).stdout.strip()
    (home / "etc/cupsd.conf").write_text(f"Listen localhost:{port}\nErrorPolicy abort-job\n"
                                         "<Location />\n  Order allow,deny\n  Allow all\n</Location>\n"
                                         "<Policy default>\n  <Limit All>\n    Order deny,allow\n  </Limit>\n</Policy>\n")
    (home / "etc/cups-files.conf").write_text("\n".join([
        f"ServerRoot {home}/etc", f"ServerBin {server_bin}", f"DataDir {data_dir}",
        f"RequestRoot {home}/spool", f"TempDir {home}/spool/tmp", f"CacheDir {home}/cache",
        f"StateDir {home}/state", f"ErrorLog {home}/log/error_log", f"AccessLog {home}/log/access_log",
        f"PageLog {home}/log/page_log", "Printcap", f"User {me}", f"Group {group}", f"SystemGroup {group}",
        "FileDevice Yes", ""]))
    proc = subprocess.Popen(["cupsd", "-f", "-c", f"{home}/etc/cupsd.conf", "-s", f"{home}/etc/cups-files.conf"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = {**os.environ, "CUPS_SERVER": f"localhost:{port}"}
    for _ in range(40):
        if subprocess.run(["lpstat", "-r"], env=env, capture_output=True).returncode == 0:
            return proc, env
        time.sleep(0.25)
    proc.kill()
    pytest.skip("cupsd wouldn't start here")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A real CUPS with the purple queue, and the stand-in printer; yields the printer's process."""
    prefix = Path(shutil.which("cupsd")).resolve().parent.parent
    real_bin, data_dir = prefix / "lib/cups", prefix / "share/cups"
    server_bin = tmp_path / "lib/cups"  # copied so CUPS trusts filters owned by the test's user
    shutil.copytree(real_bin, server_bin)
    cups_port, printer_port = _port(), _port()
    sink, sink_env = _cupsd(tmp_path / "printer", server_bin, data_dir, printer_port)
    cups, env = _cupsd(tmp_path / "cups", server_bin, data_dir, cups_port)
    subprocess.run(["lpadmin", "-p", "sink", "-E", "-v", "file:/dev/null"], env=sink_env, check=True)
    uri = f"ipp://localhost:{printer_port}/printers/sink"
    subprocess.run(["lpadmin", "-p", "purple", "-E", "-v", uri, "-o", "printer-error-policy=abort-job"],
                   env=env, check=True)
    monkeypatch.setenv("CUPS_SERVER", env["CUPS_SERVER"])
    monkeypatch.setattr(printing, "CUPS", f"ipp://localhost:{cups_port}")
    monkeypatch.setattr(printing, "STATE", str(tmp_path / "printer.json"))
    (tmp_path / "printer.json").write_text(json.dumps({"ready": True, "model": "Sink", "via": "ipp-usb", "uri": uri}))
    for name, value in {"FAKE": False, "_last_at": -printing.COOLDOWN_S, "_count": 0, "_heals": 0,
                        "_healed_stamp": None, "WATCH_EVERY_S": 0.5, "ANSWER_S": 1, "LOST_S": 3,
                        "SLOW_S": 100, "STALL_S": 100}.items():
        monkeypatch.setattr(printing, name, value)
    monkeypatch.setattr(printing, "is_live_boot", lambda: False)
    heals = []

    async def heal():
        heals.append(time.monotonic())
    monkeypatch.setattr(printing, "_heal", heal)
    sink.heals = heals
    yield sink
    for proc in (sink, cups):
        if proc.poll() is None:
            proc.send_signal(signal.SIGCONT)
            proc.kill()
            proc.wait()


def print_page(during=None):
    """Print one page and follow it to the end; during() runs once it's sent. Returns what the screen said."""
    import pygame
    told = []

    async def go():
        assert await printing.print_pages([pygame.Surface((50, 50))], False, told.append)
        if during:
            await during()
        watchers = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        await asyncio.wait_for(asyncio.gather(*watchers), 60)
    run(go())
    return told


def job_state(job):
    out = subprocess.run(["ipptool", "-tv", f"{printing.CUPS}/jobs/{job}", "get-job-attributes.test"],
                         capture_output=True, text=True).stdout
    return printing._attr(out, "job-state")


def test_a_working_printer_just_prints(lab):
    assert print_page() == ["Printing!"]
    assert job_state(1) == "completed" and not lab.heals


def test_a_frozen_printer_is_caught_its_job_cancelled_and_the_next_print_goes_through(lab):
    lab.send_signal(signal.SIGSTOP)
    assert print_page() == ["Printing!", printing.NOT_PRINTED]
    assert job_state(1) == "canceled" and len(lab.heals) == 1
    lab.send_signal(signal.SIGCONT)
    assert printing.ready_in() == 0  # no wait to try again
    assert print_page() == ["Printing!"]
    assert job_state(2) == "completed"


def test_a_printer_that_went_away_is_caught(lab):
    lab.kill()
    lab.wait()
    assert print_page() == ["Printing!", printing.NOT_PRINTED]
    assert job_state(1) == "canceled" and len(lab.heals) == 1


def test_a_brief_freeze_is_ridden_out(lab):
    async def thaw_soon():
        lab.send_signal(signal.SIGSTOP)
        await asyncio.sleep(1.5)
        lab.send_signal(signal.SIGCONT)
    assert print_page(thaw_soon) == ["Printing!"]
    assert job_state(1) == "completed" and not lab.heals
