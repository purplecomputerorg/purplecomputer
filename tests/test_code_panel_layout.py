"""Tests that canvas/grid dimensions stay constant when code panel opens/closes and during typing."""

import asyncio
import os


# Set environment before app imports
os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4


def _run(coro):
    """Run an async test in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup(pilot):
    """Wait for app to mount and settle."""
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


async def _switch_room(app, pilot, room_id):
    app.action_switch_room(room_id)
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


async def _open_code_panel(app, pilot):
    app._open_repl_panel()
    app._open_code_panel_in_room(app.active_room)
    await asyncio.sleep(SETTLE)
    await pilot.pause()


async def _type_text(app, pilot, text):
    for char in text:
        await app._execute_dev_command({"action": "key", "value": char})
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.15)
    await pilot.pause()


# ---------------------------------------------------------------------------
# Art room: canvas height stability
# ---------------------------------------------------------------------------

class TestArtCodePanelLayout:

    def test_canvas_height_stable_on_open(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")

                from purple_tui.rooms.art_room import ArtCanvas
                canvas = app.query_one("#art-canvas", ArtCanvas)
                height_before = canvas.size.height

                await _open_code_panel(app, pilot)

                height_after = canvas.size.height
                assert height_after == height_before, (
                    f"Canvas height changed: {height_before} -> {height_after}"
                )
        _run(_test())

    def test_canvas_height_stable_while_typing(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _open_code_panel(app, pilot)

                from purple_tui.rooms.art_room import ArtCanvas
                canvas = app.query_one("#art-canvas", ArtCanvas)
                height_with_panel = canvas.size.height

                await _type_text(app, pilot, "forward")

                assert canvas.size.height == height_with_panel, (
                    f"Canvas height changed while typing: {height_with_panel} -> {canvas.size.height}"
                )
        _run(_test())

    def test_canvas_height_stable_after_clear_input(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _open_code_panel(app, pilot)

                from purple_tui.rooms.art_room import ArtCanvas
                canvas = app.query_one("#art-canvas", ArtCanvas)
                height_with_panel = canvas.size.height

                # Type then delete (switches recall <-> autocomplete)
                await _type_text(app, pilot, "hi")
                for _ in range(2):
                    await app._execute_dev_command({"action": "key", "value": "backspace"})
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.15)
                await pilot.pause()

                assert canvas.size.height == height_with_panel, (
                    f"Canvas height changed after clearing: {height_with_panel} -> {canvas.size.height}"
                )
        _run(_test())


# ---------------------------------------------------------------------------
# Music room: grid height stability
# ---------------------------------------------------------------------------

class TestMusicCodePanelLayout:

    def test_grid_height_stable_on_open(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "music")

                from purple_tui.rooms.music_room import MusicGrid
                grid = app.query_one(MusicGrid)
                height_before = grid.size.height

                await _open_code_panel(app, pilot)

                assert grid.size.height == height_before, (
                    f"Grid height changed: {height_before} -> {grid.size.height}"
                )
        _run(_test())

    def test_grid_margin_immune_to_taller_box(self):
        """A one-row-taller grid box (leaked hidden hint bar, then pinned by
        panel open) must not nudge the grid content down. Seen on a MacBook
        Air where the pinned 26-high box rendered the grid one row lower."""
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "music")

                from purple_tui.rooms.music_room import MusicGrid, MusicExampleHint
                grid = app.query_one(MusicGrid)
                margin_before = grid._cached_layout[3]

                app.query_one("#example-hint", MusicExampleHint).display = False
                await asyncio.sleep(SETTLE)
                await pilot.pause()
                music = app.query_one("#room-music")
                music._on_space_hold_fired()
                await asyncio.sleep(SETTLE)
                await pilot.pause()

                margin_after = grid._cached_layout[3]
                assert margin_after == margin_before, (
                    f"Grid top margin moved: {margin_before} -> {margin_after}"
                )
        _run(_test())

    def test_grid_height_stable_while_typing(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "music")
                await _open_code_panel(app, pilot)

                from purple_tui.rooms.music_room import MusicGrid
                grid = app.query_one(MusicGrid)
                height_with_panel = grid.size.height

                await _type_text(app, pilot, "choose")

                assert grid.size.height == height_with_panel, (
                    f"Grid height changed while typing: {height_with_panel} -> {grid.size.height}"
                )
        _run(_test())


# ---------------------------------------------------------------------------
# Viewport position stability
# ---------------------------------------------------------------------------

class TestViewportStability:

    def test_viewport_top_stable_art(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")

                viewport = app.query_one("#viewport")
                top_before = viewport.region.y

                await _open_code_panel(app, pilot)

                top_after = viewport.region.y
                assert abs(top_after - top_before) <= 1, (
                    f"Viewport shifted from y={top_before} to y={top_after}"
                )
        _run(_test())

    def test_viewport_top_stable_music(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "music")

                viewport = app.query_one("#viewport")
                top_before = viewport.region.y

                await _open_code_panel(app, pilot)

                top_after = viewport.region.y
                assert abs(top_after - top_before) <= 1, (
                    f"Viewport shifted from y={top_before} to y={top_after}"
                )
        _run(_test())
