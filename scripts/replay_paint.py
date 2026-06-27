#!/usr/bin/env python3
"""Replay a saved paint-command recording onto the Art canvas and screenshot it.

The recording is a JSON list of paint_at dev commands (see
recordings/heub_doodle.paint.json). Order matters: base colors are painted
first, then overlays mix (yellow+blue=green, yellow+red=orange).

Usage:
    just python scripts/replay_paint.py recordings/heub_doodle.paint.json
"""
import asyncio
import io
import json
import os
import sys

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_o, _e = sys.stdout, sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
from purple_tui.purple_tui import PurpleApp  # noqa: E402
from purple_tui.constants import ROOM_ART  # noqa: E402
from purple_tui.rooms.art_room import ArtMode, ArtCanvas  # noqa: E402
from scripts.preview import svg_to_png, SCREENSHOT_DIR  # noqa: E402
sys.stdout, sys.stderr = _o, _e


async def replay(ops: list[dict]) -> str:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    base = os.path.join(SCREENSHOT_DIR, "replay_paint")
    svg, png = base + ".svg", base + ".png"

    app = PurpleApp()
    async with app.run_test(size=(146, 38)) as pilot:
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        app.action_switch_room(ROOM_ART[0])
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        canvas = app.query_one(ArtMode).query_one(ArtCanvas)
        for op in ops:
            canvas.paint_at(int(op["x"]), int(op["y"]), op["color"])
        canvas._invalidate_all()
        canvas.refresh()
        await pilot.pause()
        await asyncio.sleep(0.2)
        await pilot.pause()
        app.save_screenshot(svg)

    return png if svg_to_png(svg, png) else svg


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        ops = json.load(f)
    print(asyncio.run(replay(ops)))


if __name__ == "__main__":
    main()
