#!/usr/bin/env python3
"""Headless preview of Purple Computer UI.

Runs the app without a real terminal, performs actions, takes a screenshot.

Usage:
    just preview [room] [actions...]

    # Basic room previews
    just preview play
    just preview music
    just preview art

    # With code panel open
    just preview art code_panel

    # Type text into the Play room prompt
    just preview play type:hello

    # Type on art canvas then open code panel
    just preview art type:hi code_panel

    # Press specific keys
    just preview music key:tab key:a key:b key:c

    # Combine everything
    just preview art code_panel type:print key:enter

Actions (processed left to right):
    code_panel       Toggle the code panel on
    parent_menu      Open the parent menu
    type:TEXT        Type text characters one at a time
    key:KEY          Press a key (enter, tab, space, up, down, left, right,
                     escape, backspace, delete, or a single character)
    wait:SECONDS     Pause for N seconds (e.g. wait:0.5)
    clear            Clear the art canvas

Output: path to the PNG (or SVG if PNG conversion unavailable).
"""

import asyncio
import os
import shutil
import subprocess
import sys

# Set environment before any app imports
os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

# Suppress noisy import output
import io
_real_stdout = sys.__stdout__
_real_stderr = sys.__stderr__
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from purple_tui.purple_tui import PurpleApp  # noqa: E402
from purple_tui.constants import ROOM_PLAY, ROOM_MUSIC, ROOM_ART  # noqa: E402

# Restore
sys.stdout = _real_stdout
sys.stderr = _real_stderr

SCREENSHOT_DIR = os.environ.get("PURPLE_SCREENSHOT_DIR", "/tmp/screenshots")
ROOM_MAP = {
    "play": ROOM_PLAY[0],
    "music": ROOM_MUSIC[0],
    "art": ROOM_ART[0],
}


def svg_to_png(svg_path: str, png_path: str) -> bool:
    """Convert SVG to PNG using rsvg-convert (via nix-shell if needed)."""
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        try:
            subprocess.run([rsvg, "-o", png_path, svg_path],
                           check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            pass

    try:
        subprocess.run(
            ["nix-shell", "-p", "librsvg", "--run",
             f"rsvg-convert -o {png_path} {svg_path}"],
            check=True, capture_output=True, timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False


async def run_action(app, action_str: str) -> None:
    """Execute a single action string against the running app."""
    if action_str == "code_panel":
        app._open_repl_panel()
        # Open the REPL panel in the current room
        room = app.active_room
        app._open_code_panel_in_room(room)
        await asyncio.sleep(0.3)

    elif action_str == "parent_menu":
        app.action_parent_menu()
        await asyncio.sleep(0.3)

    elif action_str == "room_picker":
        app._show_room_picker()
        await asyncio.sleep(0.3)

    elif action_str == "help_videos":
        from purple_tui.rooms.help_videos import HelpVideosScreen
        app.push_screen(HelpVideosScreen())
        await asyncio.sleep(0.3)

    elif action_str == "clear":
        await app._execute_dev_command({"action": "clear"})
        await asyncio.sleep(0.1)

    elif action_str.startswith("type:"):
        text = action_str[5:]
        for char in text:
            await app._execute_dev_command({"action": "key", "value": char})
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)

    elif action_str.startswith("key:"):
        key = action_str[4:]
        await app._execute_dev_command({"action": "key", "value": key})
        await asyncio.sleep(0.1)

    elif action_str.startswith("wait:"):
        seconds = float(action_str[5:])
        await asyncio.sleep(seconds)


def build_filename(room: str, actions: list[str]) -> str:
    """Build a descriptive filename from room and actions."""
    parts = [room]
    for a in actions:
        # Sanitize for filename
        safe = a.replace(":", "_").replace(" ", "")
        parts.append(safe)
    name = "_".join(parts)
    # Truncate if too long
    if len(name) > 80:
        name = name[:80]
    return name


async def preview(room_name: str, actions: list[str]) -> str:
    """Run the app headlessly, perform actions, take a screenshot."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    fname = build_filename(room_name, actions)
    svg_path = os.path.join(SCREENSHOT_DIR, f"{fname}.svg")
    png_path = os.path.join(SCREENSHOT_DIR, f"{fname}.png")

    app = PurpleApp()

    async with app.run_test(size=(146, 38)) as pilot:
        # Let the app mount and render
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()

        # Switch room if not play (play is default)
        room_id = ROOM_MAP.get(room_name, ROOM_PLAY[0])
        if room_id != ROOM_PLAY[0]:
            app.action_switch_room(room_id)
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

        # Execute actions
        for action_str in actions:
            await run_action(app, action_str)
            await pilot.pause()

        # Take screenshot
        app.save_screenshot(svg_path)

    # Convert to PNG
    has_png = svg_to_png(svg_path, png_path)

    if has_png:
        return png_path
    return svg_path


def main():
    args = sys.argv[1:]

    # First arg is room (or default to play)
    if args and args[0] in ROOM_MAP:
        room = args[0]
        actions = args[1:]
    else:
        room = "play"
        actions = args

    result = asyncio.run(preview(room, actions))
    print(result)


if __name__ == "__main__":
    main()
