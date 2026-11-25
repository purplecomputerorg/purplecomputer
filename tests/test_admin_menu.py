"""Typing "admin" in the Parent Menu opens the admin menu; Record Performance closes both menus and
writes every frame, with the Blocks turn's phases, to frames.jsonl, and Copy Logs puts it all on a drive."""

import asyncio
import json
import time

from purplecomputer import perf_trace
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import admin_autorun, admin_menu
from purplecomputer.rooms.blocks_view import DEPTH, HEIGHT, WIDTH
from purplecomputer.rooms.parent_menu import ParentMenu
from purplecomputer.ui import Notice


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
        await press(app, "down")
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
    alone = '{"1px": {"wall": {"p50": 1.0}, "cpu": {"p50": 0.9}}, "full": {"wall": {"p50": 3.0}, "cpu": {"p50": 2.5}}}\nATTENTION: default value of option vblank_mode overridden by environment.\n'
    envs = []
    monkeypatch.setattr(admin_menu, "_run", lambda cmd, **kw: envs.append(kw["env"]) or alone if "screen_test" in str(cmd) else "")

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
        tests = json.loads((tmp_path / "screen-tests.jsonl").read_text())["tests"]
        assert tests["Alone GL"]["full"]["wall"]["p50"] == 3.0 and set(tests["Inside"]) == {"1px", "full"}
        assert [e.get("SDL_FRAMEBUFFER_ACCELERATION") for e in envs] == [None, "opengl", "opengles2", None]
        assert envs[1]["LIBGL_ALWAYS_SOFTWARE"] == "0"
        assert "Alone GL: 1px 1.0, full 3.0 ms (cpu 0.9, 2.5)" in app.top.DESCRIPTION
    run(go())


def test_run_all_tests_times_blocks_on_a_copy_and_puts_the_kids_build_back(tmp_path, monkeypatch):
    _record_to(tmp_path, monkeypatch)
    picom = [True]
    monkeypatch.setattr(admin_menu, "compositor_on", lambda: picom[0])
    monkeypatch.setattr(admin_menu, "toggle_compositor", lambda: picom.__setitem__(0, not picom[0]))
    monkeypatch.setattr(admin_menu, "speed_test", lambda app: ["Inside: 1px 25.0ms"])
    copied = []
    monkeypatch.setattr(admin_menu, "LogExportScreen", lambda app, lines: copied.append(lines) or Notice(app, "", ""))
    monkeypatch.setattr(admin_autorun, "BUILDS", (40,))
    seen = []

    async def turn_and_draw(room):
        seen.append((room is not kid, len(room._blocks)))
        room.turn()
        while room._moving() is not None:
            start = time.monotonic()
            app._draw()
            now = time.monotonic()
            app._frame_stats.frame(start, now, now, "blocks")
            await asyncio.sleep(0.01)
    monkeypatch.setattr(admin_autorun, "MOVES", {"turn": turn_and_draw})

    async def go():
        nonlocal app, kid
        app = make_app()
        app.action_switch_room("blocks")
        kid = app.rooms["blocks"]
        kid.restore_timeline_state({"floor": [WIDTH, DEPTH], "b:3,3,0": "#FFFFFF"})
        app.action_parent_menu()
        await type_text(app, "admin")
        await press(app, "enter")
        run_all = app.top
        assert isinstance(run_all, admin_autorun.AutoRun)
        await run_all.task
        assert seen == [(True, 40)] and picom == [True]
        assert app.rooms["blocks"] is kid and list(kid._blocks) == [(3, 3, 0)] and app.room is kid
        assert copied[0][:2] == ["Compositor on:", "Inside: 1px 25.0ms"] and copied[0][2] == "Compositor off:"
        assert copied[0][-1].startswith("40 blocks: turn ") and "fps (draw" in copied[0][-1]
        assert (tmp_path / admin_autorun.SUMMARY).read_text().splitlines() == copied[0]
    app = kid = None
    run(go())


def test_city_has_the_blocks_asked_for_inside_the_floor():
    spots = [tuple(map(int, k[2:].split(","))) for k in admin_autorun.city(850) if k.startswith("b:")]
    assert len(spots) == 850 and all(0 <= x < WIDTH and 0 <= z < DEPTH and 0 <= y < HEIGHT for x, z, y in spots)
