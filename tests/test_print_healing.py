"""Printing heals itself: a sent job is followed until it prints, and when Purple
loses the printer the job is cancelled and the print stack rebuilt. Only Purple's
own link to the printer is timed tightly, so any printer's pace is fine."""
import asyncio
import json
import time

import pytest

from purple_tui import printing
from purple_tui.canvas.harness import run

URI = "ipp://localhost:60000/ipp/print"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(printing, "STATE", str(tmp_path / "printer.json"))
    monkeypatch.setattr(printing, "FAKE", False)
    monkeypatch.setattr(printing, "is_live_boot", lambda: False)
    monkeypatch.setattr(printing, "_last_at", -printing.COOLDOWN_S)
    monkeypatch.setattr(printing, "_count", 0)
    monkeypatch.setattr(printing, "_heals", 0)
    monkeypatch.setattr(printing, "_healed_stamp", None)
    clock = [0.0]

    async def sleep(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)
    monkeypatch.setattr(printing, "_now", lambda: clock[0])
    monkeypatch.setattr(printing, "_sleep", sleep)
    plug_in()


def plug_in(uri=URI):
    with open(printing.STATE, "w") as f:
        json.dump({"ready": True, "model": "Any Printer", "via": "ipp-usb", "uri": uri}, f)


def look(state="processing", answers=True, alerts="Alerts: none", moved=0):
    """moved: anything that changes as a job advances, like pages done."""
    return printing.Look(state, (state, "", str(moved), ""), alerts, answers)


def clocks_over(seconds, look_at):
    """Every verdict a job's clocks give, checking each WATCH_EVERY_S; look_at(t) is the look at time t."""
    clocks, verdicts = printing._Clocks(0), []
    for t in range(printing.WATCH_EVERY_S, seconds + 1, printing.WATCH_EVERY_S):
        verdicts.append(clocks.next(look_at(t), t))
        if verdicts[-1] in (printing.COMPLETED, printing.CANCELED, printing.STUCK):
            break
    return verdicts


# The clocks: what each kind of printer gets


def test_a_slow_printer_that_keeps_answering_is_never_cancelled():
    verdicts = clocks_over(3600, lambda t: look(moved=t // 120))  # a page every 2 minutes for an hour
    assert printing.STUCK not in verdicts
    assert set(verdicts) == {None, printing.STILL_WORKING}
    assert verdicts.index(printing.STILL_WORKING) * printing.WATCH_EVERY_S + printing.WATCH_EVERY_S >= printing.SLOW_S


def test_a_printer_that_stops_answering_is_stuck_after_lost_s_and_not_before():
    verdicts = clocks_over(600, lambda t: look(answers=False))
    assert verdicts[-1] == printing.STUCK
    assert printing.STILL_WORKING not in verdicts  # it isn't working: it's gone quiet
    assert len(verdicts) * printing.WATCH_EVERY_S == printing.WATCH_EVERY_S + printing.LOST_S


def test_a_short_blip_like_a_printer_waking_up_is_ridden_out():
    verdicts = clocks_over(1200, lambda t: look(answers=t > printing.LOST_S - 10, moved=t // 60))
    assert printing.STUCK not in verdicts


def test_a_job_stuck_in_place_while_the_printer_answers_gives_up_after_stall_s():
    verdicts = clocks_over(3600, lambda t: look())
    assert verdicts[-1] == printing.STUCK
    assert len(verdicts) * printing.WATCH_EVERY_S == printing.WATCH_EVERY_S + printing.STALL_S


def test_a_paper_wait_is_never_timed_out():
    verdicts = clocks_over(3 * 3600, lambda t: look(alerts="Alerts: media-empty-error"))
    assert set(verdicts) == {"The printer needs paper"}


def test_how_cups_ends_a_job():
    assert clocks_over(3, lambda t: look("completed", answers=False)) == [printing.COMPLETED]
    assert clocks_over(3, lambda t: look("canceled")) == [printing.CANCELED]
    assert clocks_over(3, lambda t: look("aborted")) == [printing.STUCK]


# The watcher: what the kid sees and what Purple does


class FakeCups:
    """Stands in for CUPS and the printer behind printing._run. Each check of the
    job takes the next look from the script; the last one repeats."""

    def __init__(self, *looks, on_heal=None):
        self.looks, self.ran, self.on_heal = list(looks), [], on_heal

    async def run(self, *argv, check=True, timeout=30):
        self.ran.append(argv)
        if argv[0] == "lp":
            return "request id is purple-7 (1 file(s))\n"
        if argv[0] == "ipptool" and "/jobs/" in argv[-2]:
            self.now = self.looks.pop(0) if len(self.looks) > 1 else self.looks[0]
            if self.now is None:
                raise OSError("ipptool exited 1")
            return f"job-state (enum) = {self.now.state}\njob-impressions-completed (integer) = {self.now.news[2]}\n"
        if argv[0] == "lpstat":
            return f"printer purple is idle.\n\t{self.now.alerts}\n"
        if argv[0] == "ipptool":
            got = "5620" if self.now.answers else "0"  # what ipptool says for a reply, and for a timeout
            return f"RECEIVED: {got} bytes in response\nstatus-code = successful-ok\n"
        if argv[0] == "sudo" and self.on_heal:
            self.on_heal()
        return ""

    def did(self, cmd):
        return [argv for argv in self.ran if argv[0] == cmd]


def watch(monkeypatch, *looks, jobs=("7",), on_heal=None):
    """Follow jobs through the scripted looks; returns (what the screen was told, the fake)."""
    cups, told = FakeCups(*looks, on_heal=on_heal), []
    monkeypatch.setattr(printing, "_run", cups.run)
    stamp = printing.state_stamp()

    async def go():
        await asyncio.gather(*(printing._watch(job, stamp, told.append) for job in jobs))
    run(go())
    return told, cups


def test_a_printed_job_says_nothing_and_resets_the_heals(monkeypatch):
    printing._heals = 1
    told, cups = watch(monkeypatch, look(), look("completed"))
    assert told == [] and printing._heals == 0 and not cups.did("cancel")


def test_a_slow_job_says_so_once_then_prints(monkeypatch):
    working = [look(moved=i // 10) for i in range(40)]
    told, _ = watch(monkeypatch, *working, look("completed"))
    assert told == [printing.STILL_WORKING]


def test_a_printer_that_stops_answering_is_cancelled_and_rebuilt(monkeypatch):
    printing._last_at, printing._count = time.monotonic(), 5
    told, cups = watch(monkeypatch, look(answers=False))
    assert told == [printing.NOT_PRINTED]
    assert cups.did("cancel") == [("cancel", "purple-7")]
    (heal,) = cups.did("sudo")
    assert printing.HEAL in heal[-1] and "restart purple-printer.service" in heal[-1]
    assert printing.ready_in() == 0 and printing._count == 4  # the stuck print didn't use one up


def test_a_job_cups_gave_up_on_is_rebuilt_too(monkeypatch):
    told, cups = watch(monkeypatch, look("aborted"))
    assert told == [printing.NOT_PRINTED] and cups.did("sudo")


def test_cups_itself_not_answering_is_rebuilt(monkeypatch):
    told, cups = watch(monkeypatch, None)
    assert told == [printing.NOT_PRINTED] and cups.did("sudo")


def test_after_heals_rebuilds_it_asks_for_the_power_button(monkeypatch):
    printing._heals = printing.HEALS
    told, cups = watch(monkeypatch, look(answers=False))
    assert told == [printing.NOT_ANSWERING] and not cups.did("sudo")
    assert cups.did("cancel") and printing.ready_in() == 0


def test_a_job_someone_cancelled_isnt_rebuilt(monkeypatch):
    told, cups = watch(monkeypatch, look("canceled"))
    assert told == [printing.NOT_PRINTED] and not cups.did("sudo")


def test_a_job_lost_with_its_queue_says_so_without_a_rebuild(monkeypatch):
    def rebuilt():
        time.sleep(0.01)  # a fresh mtime for the state stamp
        plug_in()
    looks = [look(), look()]
    cups = FakeCups(*looks)
    original = cups.run

    async def rebuild_after_first_check(*argv, **kw):
        out = await original(*argv, **kw)
        if argv[0] == "lpstat" and len(cups.did("lpstat")) == 1:
            rebuilt()
        return out
    monkeypatch.setattr(printing, "_run", rebuild_after_first_check)
    told = []
    run(printing._watch("7", printing.state_stamp(), told.append))
    assert told == [printing.NOT_PRINTED] and not cups.did("sudo") and printing.ready_in() == 0


def test_two_stuck_jobs_ask_for_one_rebuild(monkeypatch):
    told, cups = watch(monkeypatch, look(answers=False), jobs=("7", "8"))
    assert told == [printing.NOT_PRINTED] * 2
    assert len(cups.did("sudo")) == 1 and len(cups.did("cancel")) == 2


def test_problems_the_family_can_fix_are_said_once_and_never_rebuilt(monkeypatch):
    paper = [look(alerts="Alerts: media-empty-error")] * 500  # 25 minutes without paper
    told, cups = watch(monkeypatch, *paper, look("completed"))
    assert told == ["The printer needs paper"] and not cups.did("sudo")


def test_a_failed_send_frees_the_kid_to_try_again_and_rebuilds(monkeypatch):
    import pygame
    cups = FakeCups(look())

    async def lp_fails(*argv, **kw):
        if argv[0] == "lp":
            raise OSError("lp exited 1")
        return await cups.run(*argv, **kw)
    monkeypatch.setattr(printing, "_run", lp_fails)
    told = []
    assert run(printing.print_pages([pygame.Surface((4, 4))], False, told.append)) is False
    assert told == [printing.NOT_PRINTED] and cups.did("sudo")
    assert printing.ready_in() == 0 and printing._count == 0


# Asking the printer


def test_the_printer_is_asked_at_its_own_address(monkeypatch):
    cups = FakeCups(look())
    cups.now = look()
    monkeypatch.setattr(printing, "_run", cups.run)
    assert run(printing._printer_answers()) is True
    assert cups.did("ipptool")[0][-2] == URI
    cups.now = look(answers=False)
    assert run(printing._printer_answers()) is False


def test_the_usb_driver_route_has_no_address_to_ask(monkeypatch):
    plug_in("usb://Acme/Laser%209?serial=1")
    cups = FakeCups(look())
    monkeypatch.setattr(printing, "_run", cups.run)
    assert run(printing._printer_answers()) is True and not cups.ran


def test_a_hung_command_is_killed_not_waited_on():
    started = time.monotonic()
    with pytest.raises(OSError, match="took over"):
        run(printing._run("sleep", "5", timeout=0.2))
    assert time.monotonic() - started < 2
