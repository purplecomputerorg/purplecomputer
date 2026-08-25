#!/usr/bin/env python3
"""Headless preview of Purple Computer UI.

Runs the app without a display, performs actions, saves a PNG.

Usage:
    just preview [room] [actions...]

    just preview play
    just preview music key:a key:s key:d
    just preview art type:hello
    just preview art code_panel type:red key:enter
    just preview play type:cat key:enter
    just preview play room_picker
    just preview music parent_menu

Actions (processed left to right):
    code_panel       Open the code panel
    parent_menu      Open the parent menu
    room_picker      Open the Esc room picker
    help_videos      Open the Help & Videos screen
    first_boot       Show the first-boot power-cycle screen
    doodle | photo   Paint the Secret Menu pictures onto the Art canvas
    time_travel      Open the Time Travel scrubber
    clear            Clear the current room
    type:TEXT        Type text characters one at a time (_ types a space)
    key:KEY          Press a key (enter, tab, space, up, down, left, right,
                     escape, backspace, or a single character)
    hold:KEY         Hold a key past the hold threshold (space, enter, escape)
    wait:SECONDS     Let timers run for N seconds

Output: path to the PNG. Set PURPLE_SCREENSHOT_DIR to change the folder and
PURPLE_WINDOW_SIZE=WxH to preview another screen size.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from purple_tui.harness import make_app, press  # noqa: E402

SCREENSHOT_DIR = os.environ.get("PURPLE_SCREENSHOT_DIR", "/tmp/screenshots")
ROOMS = ("play", "music", "art")


async def run_action(app, action: str):
    if action == "code_panel":
        app.room.open_code_panel()
    elif action == "parent_menu":
        app.action_parent_menu()
    elif action == "room_picker":
        app._show_room_picker()
    elif action == "help_videos":
        from purple_tui.rooms.help_videos import HelpVideosScreen
        app.push(HelpVideosScreen(app))
    elif action == "first_boot":
        from purple_tui.rooms.sleep_screen import FirstBootPowerCycleScreen
        app.push(FirstBootPowerCycleScreen(app))
    elif action in ("doodle", "photo"):
        from purple_tui.secret_doodle import paint_doodle, paint_photo
        (paint_doodle if action == "doodle" else paint_photo)(app)
    elif action == "time_travel":
        app._start_time_travel()
    elif action == "clear":
        app._start_fresh(app.active_room)
    elif action.startswith("type:"):
        for ch in action[5:]:
            await press(app, " " if ch == "_" else ch)
    elif action.startswith("key:"):
        await press(app, action[4:])
    elif action.startswith("hold:"):
        await press(app, action[5:], hold=1.2)
    elif action.startswith("wait:"):
        await asyncio.sleep(float(action[5:]))
    else:
        raise SystemExit(f"unknown action: {action}")
    await asyncio.sleep(0.05)


def build_filename(room: str, actions: list) -> str:
    name = room + "".join("_" + a.replace(":", "_").replace(" ", "_") for a in actions)
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:80]


async def preview(room: str, actions: list) -> str:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    app = make_app()
    if room != app.active_room:
        app.action_switch_room(room)
    for action in actions:
        await run_action(app, action)
    path = os.path.join(SCREENSHOT_DIR, f"{build_filename(room, actions)}.png")
    app.screenshot(path)
    return path


def main():
    args = sys.argv[1:]
    room = args[0] if args and args[0] in ROOMS else "play"
    actions = args[1:] if args and args[0] in ROOMS else args
    print(asyncio.run(preview(room, actions)))


if __name__ == "__main__":
    main()
