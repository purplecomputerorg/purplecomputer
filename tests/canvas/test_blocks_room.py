"""Blocks room: letters and Space drop blocks into the cursor's column, Enter
walks the cursor's height up and back down and that height carries to other
columns, Backspace eats down the column then steps left, a chord mixes the
second key's color into the block the first one dropped, holding a letter or
Space while arrowing lays a line, Tab flips to the back with arrows still
moving the way they point, blocks in front of the cursor's column turn
see-through, and the Esc picker reaches the room with 4."""

import time

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.blocks_room import HEIGHT, TURN_MAX_BLOCKS, TURN_S, WIDTH
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.keyboard import KeyboardStateMachine
from purple_tui.palette import get_key_color


def _blocks():
    app = make_app()
    app.action_switch_room("blocks")
    room = app.rooms["blocks"]
    room._x, room._z = 5, 5
    return app, room


def test_letters_and_space_stack_on_the_cursor_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "rg")
        await press(app, "space")
        assert room._blocks == {(5, 5, 0): get_key_color("r"), (5, 5, 1): get_key_color("g"),
                                (5, 5, 2): get_key_color("g")}
    run(go())


def test_held_letter_repeats_do_not_stack():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        await press(app, "a", is_repeat=True)
        assert len(room._blocks) == 1
    run(go())


def test_column_stops_at_the_height_limit():
    async def go():
        app, room = _blocks()
        await type_text(app, "a" * (HEIGHT + 3))
        assert len(room._blocks) == HEIGHT
    run(go())


def test_enter_walks_up_to_the_top_then_back_down():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        expected = list(range(2, HEIGHT)) + list(range(HEIGHT - 2, 0, -1)) + [2, 3]   # never into the block at 0
        heights = []
        for _ in expected:
            await press(app, "enter")
            heights.append(room._cursor_y())
        assert heights == expected
        assert list(room._blocks) == [(5, 5, 0)]
    run(go())


def test_chosen_height_stays_while_walking():
    async def go():
        app, room = _blocks()
        for _ in range(3):
            await press(app, "enter")
        await press(app, "right")
        await press(app, "right")
        await type_text(app, "qq")
        assert (7, 5, 3) in room._blocks and (7, 5, 4) in room._blocks
        await press(app, "right", char_held="q")
        assert (8, 5, 3) in room._blocks
    run(go())


def test_backspace_eats_down_from_the_cursor_then_steps_left():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")
        await press(app, "right")
        await type_text(app, "aa")
        await press(app, "enter")
        await press(app, "enter")
        await type_text(app, "b")               # floating above the column
        await press(app, "enter")
        await press(app, "enter")
        await press(app, "enter")
        await press(app, "backspace")           # the floating block first, the one nearest below
        assert (6, 5, 4) not in room._blocks and room._cursor_y() == 4
        await press(app, "backspace")
        await press(app, "backspace")
        assert not any(x == 6 for x, _, _ in room._blocks) and room._x == 6
        await press(app, "backspace")           # column empty: on to the left, from its top
        assert room._x == 5 and (5, 5, 2) not in room._blocks and len(room._blocks) == 2
    run(go())


def test_backspace_steps_over_empty_columns_and_stops_at_the_edge():
    async def go():
        app, room = _blocks()
        room._x = 1
        await press(app, "backspace")
        await press(app, "backspace")
        await press(app, "backspace")
        assert room._x == 0
    run(go())


def test_chord_mixes_into_the_block_the_held_key_dropped():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        assert room._blocks == {(5, 5, 0): mix_colors_paint([get_key_color("b"), get_key_color("g")])}
    run(go())


def test_keyboard_reports_the_still_held_letter():
    sm = KeyboardStateMachine()
    down = lambda code: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=time.monotonic()))
    assert down(KeyCode.KEY_B)[0].char_held is None
    assert down(KeyCode.KEY_Y)[0].char_held == "b"


def test_holding_a_letter_or_space_while_arrowing_lays_a_line():
    async def go():
        app, room = _blocks()
        for _ in range(WIDTH):
            await press(app, "right", char_held="z")
        assert room._x == WIDTH - 1
        assert all((x, 5, 0) in room._blocks for x in range(6, WIDTH))
        await press(app, "up", space_held=True)
        assert (WIDTH - 1, 6, 0) in room._blocks
    run(go())


def test_blocks_in_front_of_the_cursor_turn_see_through():
    async def go():
        app, room = _blocks()
        room._x, room._z = 5, 2
        await type_text(app, "aaaa")
        room._x, room._z = 5, 6
        app._draw()
        assert room._scene_xray and all(vz == 2 for _, vz, _ in room._scene_xray)
        room._x, room._z = 20, 10
        app._draw()
        assert not room._scene_xray
    run(go())


def test_flip_keeps_blocks_and_arrows_follow_the_screen():
    async def go():
        app, room = _blocks()
        await press(app, "r")
        await press(app, "tab")
        assert room._back and (5, 5, 0) in room._blocks
        before = room._view(room._x, room._z)
        await press(app, "right")
        after = room._view(room._x, room._z)
        assert (after[0] - before[0], after[1] - before[1]) == (1, 0)
        assert room._x == 4
        await press(app, "tab")
        assert not room._back
    run(go())


def test_turn_draws_and_stops_its_timer():
    async def go():
        app, room = _blocks()
        await type_text(app, "abc")
        app._draw()
        await press(app, "tab")
        assert room._fade_from is None          # small build: a live turn, not a crossfade
        for p in (0.25, 0.5, 0.75):
            room._fade_start = time.monotonic() - TURN_S * p
            app._draw()
        room._fade_start = time.monotonic() - TURN_S - 0.05
        app._draw()
        room._fade_tick()
        assert room._fade_timer is None
    run(go())


def test_big_builds_crossfade_instead_of_turning():
    async def go():
        app, room = _blocks()
        room._blocks = {(x % WIDTH, x // WIDTH % 12, x // (WIDTH * 12)): "#ff0000" for x in range(TURN_MAX_BLOCKS + 1)}
        app._draw()
        await press(app, "tab")
        assert room._fade_from is not None
        app._draw()
    run(go())


def test_shift_picks_a_color_without_dropping():
    async def go():
        app, room = _blocks()
        await press(app, "Q", shift_held=True)
        assert not room._blocks and room._color == get_key_color("q")
    run(go())


def test_timeline_round_trip():
    async def go():
        app, room = _blocks()
        await type_text(app, "qwe")
        await press(app, "enter")
        await press(app, "tab")
        state = room.timeline_state()
        room.clear()
        assert not room.has_content() and room._hover == 0 and not room._back
        room.restore_timeline_state(state)
        assert len(room._blocks) == 3 and room._hover == 4 and (room._x, room._z) == (5, 5) and room._back
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())
