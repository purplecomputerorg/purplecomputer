#!/usr/bin/env python3
"""Headless preview of Purple Computer UI.

Runs the app without a real terminal, navigates to a room, takes a screenshot.
Outputs SVG and (if rsvg-convert is available) PNG.

Usage:
    just preview [room]        # play, music, or art (default: play)
    just preview art
    just preview music

The screenshot is saved to /tmp/screenshots/preview.svg (and .png if possible).
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

# Suppress pygame welcome message
import io
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from purple_tui.purple_tui import PurpleApp  # noqa: E402
from purple_tui.constants import ROOM_PLAY, ROOM_MUSIC, ROOM_ART  # noqa: E402

# Restore stdout/stderr
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

SCREENSHOT_DIR = "/tmp/screenshots"
ROOM_MAP = {
    "play": ROOM_PLAY[0],
    "music": ROOM_MUSIC[0],
    "art": ROOM_ART[0],
}


def svg_to_png(svg_path: str, png_path: str) -> bool:
    """Convert SVG to PNG using rsvg-convert (via nix-shell if needed)."""
    # Try direct rsvg-convert first
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        try:
            subprocess.run(
                [rsvg, "-o", png_path, svg_path],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            pass

    # Try via nix-shell
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


async def preview(room_name: str) -> str:
    """Run the app headlessly and take a screenshot."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    svg_path = os.path.join(SCREENSHOT_DIR, f"preview_{room_name}.svg")
    png_path = os.path.join(SCREENSHOT_DIR, f"preview_{room_name}.png")

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

        # Take screenshot
        app.save_screenshot(svg_path)

    # Convert to PNG
    has_png = svg_to_png(svg_path, png_path)

    if has_png:
        return png_path
    return svg_path


def main():
    room = sys.argv[1] if len(sys.argv) > 1 else "play"
    if room not in ROOM_MAP:
        print(f"Unknown room: {room}")
        print(f"Available: {', '.join(ROOM_MAP.keys())}")
        sys.exit(1)

    result = asyncio.run(preview(room))
    print(result)


if __name__ == "__main__":
    main()
