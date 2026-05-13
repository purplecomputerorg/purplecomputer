"""One-off diagnostic: measure music grid dimensions across idle / loop / code states.

Mirrors the harness in scripts/preview.py but prints sizes instead of taking
a screenshot. Used to investigate grid shift when the code/loop panel opens.
"""
import asyncio
import os
import sys

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from purple_tui.purple_tui import PurpleApp
from purple_tui.rooms.music_room import MusicGrid, MusicMode, MusicRoomHeader, MusicExampleHint
from purple_tui.repl_panel import ReplPanel
from purple_tui.loop_panel import LoopPanel
from purple_tui.constants import ROOM_MUSIC


async def snapshot(app, label):
    music = app.query_one(MusicMode)
    grid = music.query_one(MusicGrid)
    header = music.query_one(MusicRoomHeader)
    hint = music.query_one(MusicExampleHint)
    panel_repl = music.query_one(ReplPanel)
    panel_loop = music.query_one(LoopPanel)
    viewport = app.query_one("#viewport")
    content_area = app.query_one("#content-area")

    print(f"\n--- {label} ---")
    print(f"viewport.size = {viewport.size}, styles.height = {viewport.styles.height}")
    print(f"content-area.size = {content_area.size}")
    print(f"MusicMode.size = {music.size}")
    print(f"  header.size = {header.size}, display = {header.display}")
    print(f"  grid.size = {grid.size}, styles.height = {grid.styles.height}")
    print(f"  hint.size = {hint.size}, display = {hint.display}")
    print(f"  repl.size = {panel_repl.size}, display = {panel_repl.display}, is_open = {panel_repl.is_open}")
    print(f"  loop.size = {panel_loop.size}, display = {panel_loop.display}, is_open = {panel_loop._open}")
    h = grid.size.height
    cell_h = min(h // 4, 5) if h > 0 else 0
    grid_h = cell_h * 4
    margin_top = (h - grid_h) // 2 if h > 0 else 0
    print(f"  computed: cell_height={cell_h}, grid_height={grid_h}, margin_top={margin_top}")
    print(f"  cached_layout = {grid._cached_layout}")


async def main():
    app = PurpleApp()
    async with app.run_test(size=(146, 38)) as pilot:
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        app.action_switch_room(ROOM_MUSIC[0])
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        await snapshot(app, "IDLE (music room, before any panel)")

        # --- Code mode open ---
        music = app.query_one(MusicMode)
        music._on_space_hold_fired()
        await pilot.pause()
        await asyncio.sleep(0.2)  # past the 50ms ReplPanel.open defer
        await pilot.pause()
        await snapshot(app, "CODE MODE OPEN")

        # --- Code mode close ---
        music._on_space_hold_fired()
        await pilot.pause()
        await asyncio.sleep(0.2)
        await pilot.pause()
        await snapshot(app, "AFTER CODE MODE CLOSE")

        # --- Loop mode open ---
        music._on_enter_hold_fired()
        await pilot.pause()
        await asyncio.sleep(0.2)
        await pilot.pause()
        await snapshot(app, "LOOP MODE OPEN (recording)")

        # --- Loop mode close ---
        music._on_enter_hold_fired()
        await pilot.pause()
        await asyncio.sleep(0.2)
        await pilot.pause()
        await snapshot(app, "AFTER LOOP MODE CLOSE")


if __name__ == "__main__":
    asyncio.run(main())
