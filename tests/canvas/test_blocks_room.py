"""Blocks room: letters and Space drop blocks on top of the cursor's column,
Enter lifts the block just dropped and Backspace lowers then removes it (or
moves the empty cursor when away from it), a chord mixes the second key's
color into the block the first one dropped, holding a letter or Space while
arrowing lays a line, Tab flips to the back with arrows still moving the way
they point, blocks in front of the cursor's column turn see-through, and the
Esc picker reaches the room with 4."""

import time

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.blocks_room import FLIP_S, HEIGHT, WIDTH
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


def test_enter_lifts_the_block_just_dropped_and_backspace_lowers_then_removes_it():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        await press(app, "enter")
        await press(app, "enter")
        assert list(room._blocks) == [(5, 5, 2)]
        await press(app, "backspace")
        assert list(room._blocks) == [(5, 5, 1)]
        await press(app, "backspace")
        await press(app, "backspace")
        assert not room._blocks
    run(go())


def test_lifted_height_carries_to_the_next_column():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        for _ in range(3):
            await press(app, "enter")
        await press(app, "right", char_held="q")
        await press(app, "right", char_held="q")
        assert (6, 5, 3) in room._blocks and (7, 5, 3) in room._blocks
    run(go())


def test_away_from_the_last_block_enter_and_backspace_move_the_cursor():
    async def go():
        app, room = _blocks()
        await type_text(app, "aa")
        await press(app, "left")
        await press(app, "enter")
        await press(app, "enter")
        assert room._cursor_y() == 2
        await press(app, "backspace")
        assert room._cursor_y() == 1 and len(room._blocks) == 2
        await press(app, "right")
        await press(app, "backspace")       # resting on a column: removes its top
        assert len(room._blocks) == 1
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


def test_flip_fade_stops_its_timer():
    async def go():
        app, room = _blocks()
        app._draw()
        await press(app, "tab")
        app._draw()
        assert room._fade_timer is not None
        time.sleep(FLIP_S + 0.05)
        app._draw()
        room._fade_tick()
        assert room._fade_timer is None and room._fade_from is None
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
        assert len(room._blocks) == 3 and room._hover == 3 and (room._x, room._z) == (5, 5) and room._back
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())
