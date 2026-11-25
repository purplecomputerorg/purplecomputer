"""Typing "admin" in the Parent Menu opens the admin menu; Record Performance closes both menus and
writes every frame, with the Blocks turn's phases, to frames.jsonl, and Copy Logs puts it all on a drive."""

import json
import time

from purplecomputer import perf_trace
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import admin_menu
from purplecomputer.rooms.parent_menu import ParentMenu


def _record_to(tmp_path, monkeypatch):
    monkeypatch.setattr(perf_trace, "DIR", tmp_path)
    monkeypatch.setattr(perf_trace, "FRAMES", tmp_path / "frames.jsonl")
    monkeypatch.setattr(perf_trace, "sampler", lambda cmd: None)


def test_admin_word_records_a_blocks_turn(tmp_path, monkeypatch):
    _record_to(tmp_path, monkeypatch)

    async def go():
        app = make_app()
        app.action_switch_room("blocks")
        app.action_parent_menu()
        await type_text(app, "hello")
        assert isinstance(app.top, ParentMenu)
        await type_text(app, "admin")
        assert isinstance(app.top, admin_menu.AdminMenu)
        await press(app, "enter")
        assert perf_trace.active() and app.top is None
        room = app.rooms["blocks"]
        room.turn()
        room._look[0] = -40.0
        start = time.monotonic()
        app._draw()
        now = time.monotonic()
        app._frame_stats.frame(start, now, now, "blocks")
        perf_trace.stop()
        header, rec, threads = [json.loads(line) for line in (tmp_path / "frames.jsonl").read_text().splitlines()]
        assert header["ticks_per_s"] > 0 and any(name.startswith("MainThread#") for name in threads["threads"])
        assert header["room"] == "blocks" and header["size"] == [app.g.w, app.g.h]
        assert {"camera", "floor", "sun", "behind", "front", "arrow_keys", "chrome"} <= set(rec["phases"])
        assert rec["room"] == "blocks" and rec["detailed"] and rec["view"][0] == -40.0
    run(go())


def test_copy_logs_writes_a_folder_on_the_drive(tmp_path, monkeypatch):
    _record_to(tmp_path / "perf", monkeypatch)
    monkeypatch.setattr(admin_menu, "LOGS", ())
    monkeypatch.setattr(admin_menu, "COMMANDS", {"hello.txt": "echo hi"})

    async def go():
        app = make_app()
        lines = admin_menu.LogExportScreen(app).copy(tmp_path)
        folder = next((tmp_path / admin_menu.FOLDER).iterdir())
        assert (folder / "hello.txt").read_text() == "hi\n"
        assert json.loads((folder / "app.json").read_text())["size"] == [app.g.w, app.g.h]
        assert "unplug" in lines[-1]
    run(go())


def test_next_start_switch_and_speed_test(tmp_path, monkeypatch):
    _record_to(tmp_path, monkeypatch)
    monkeypatch.setattr(admin_menu, "NEXT_START", tmp_path / "next")
    monkeypatch.setattr(admin_menu, "THIS_START", tmp_path / "now")
    (tmp_path / "now").write_text("noaccel\n")
    alone = '{"1px": {"wall": {"p50": 1.0}, "cpu": {"p50": 0.9}}, "full": {"wall": {"p50": 3.0}, "cpu": {"p50": 2.5}}}'
    monkeypatch.setattr(admin_menu, "_run", lambda cmd, **kw: alone if "screen_test" in str(cmd) else "")

    async def go():
        app = make_app()
        menu = admin_menu.AdminMenu(app)
        app.push(menu)
        assert "GPU Acceleration is off this start" in menu.DESCRIPTION
        menu._on_confirm("noaccel")
        assert (tmp_path / "next").read_text() == "noaccel\n" and ("noaccel", "Next Start: GPU Acceleration Off") in menu.options
        menu._on_confirm("noaccel")
        assert (tmp_path / "next").read_text() == ""
        menu._on_confirm("speed")
        test = json.loads((tmp_path / "screen-tests.jsonl").read_text())
        assert test["alone"]["full"]["wall"]["p50"] == 3.0 and set(test["inside"]) == {"1px", "full"}
        assert "Alone full: 3.0ms (cpu 2.5ms)" in app.top.DESCRIPTION
    run(go())
