"""Blocks room: letters drop sticker-colored blocks at the cursor, which rests
on its column unless Space lifted it (Enter lets it rest), a chord mixes the
second key's color into the block the first one dropped, holding a letter
while arrowing lays a line, Backspace takes the top block off, Tab turns the
room with arrows still moving the way they point, blocks in front of the
cursor's column turn see-through, and the Esc picker reaches the room with 4."""

import time

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.blocks_room import HEIGHT, SIZE, SPIN_S
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


def test_letters_stack_on_the_cursor_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "rrg")
        assert room._blocks == {(5, 5, 0): get_key_color("r"), (5, 5, 1): get_key_color("r"),
                                (5, 5, 2): get_key_color("g")}
        await press(app, "backspace")
        assert (5, 5, 2) not in room._blocks and len(room._blocks) == 2
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


def test_space_lifts_the_cursor_and_it_keeps_its_height_while_moving():
    async def go():
        app, room = _blocks()
        await type_text(app, "aa")
        for _ in range(2):
            await press(app, "space")
        assert room._cursor_y() == 4
        await press(app, "right")
        await press(app, "b")
        assert (6, 5, 4) in room._blocks
        await press(app, "enter")
        assert room._cursor_y() == 5      # rests on the block it just floated
        await press(app, "right")
        assert room._cursor_y() == 0
    run(go())


def test_cursor_rides_over_a_taller_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")
        await press(app, "left")
        await press(app, "space")
        await press(app, "right")
        assert room._cursor_y() == 3
    run(go())


def test_chord_mixes_into_the_block_the_held_key_dropped():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "y", char_held="b")
        assert room._blocks == {(5, 5, 0): mix_colors_paint([get_key_color("b"), get_key_color("y")])}
    run(go())


def test_keyboard_reports_the_still_held_letter():
    sm = KeyboardStateMachine()
    down = lambda code: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=time.monotonic()))
    assert down(KeyCode.KEY_B)[0].char_held is None
    assert down(KeyCode.KEY_Y)[0].char_held == "b"


def test_holding_a_letter_while_arrowing_lays_a_line():
    async def go():
        app, room = _blocks()
        for _ in range(SIZE):
            await press(app, "right", char_held="z")
        assert room._x == SIZE - 1
        assert all((x, 5, 0) in room._blocks for x in range(6, SIZE))
    run(go())


def test_blocks_in_front_of_the_cursor_turn_see_through():
    async def go():
        app, room = _blocks()
        room._x, room._z = 5, 2
        await type_text(app, "aaaa")
        room._x, room._z = 5, 6
        app._draw()
        assert room._scene_xray and all(vz == 2 for _, vz, _ in room._scene_xray)
        room._x, room._z = 12, 12
        app._draw()
        assert not room._scene_xray
    run(go())


def test_turning_keeps_blocks_and_arrows_follow_the_screen():
    async def go():
        app, room = _blocks()
        await press(app, "r")
        await press(app, "tab")
        assert room._turn == 1 and (5, 5, 0) in room._blocks
        before = room._view(room._x, room._z)
        await press(app, "right")
        after = room._view(room._x, room._z)
        assert (after[0] - before[0], after[1] - before[1]) == (1, 0)
        for _ in range(3):
            await press(app, "tab")
        assert room._turn == 0
    run(go())


def test_turn_animation_stops_its_timer():
    async def go():
        app, room = _blocks()
        app._draw()
        await press(app, "tab")
        app._draw()
        assert room._spin_timer is not None
        time.sleep(SPIN_S + 0.05)
        app._draw()
        room._spin_tick()
        assert room._spin_timer is None and room._spin_from is None
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
        await press(app, "space")
        await press(app, "tab")
        state = room.timeline_state()
        room.clear()
        assert not room.has_content() and room._hover == 0
        room.restore_timeline_state(state)
        assert len(room._blocks) == 3 and room._hover == 4 and (room._x, room._z) == (5, 5) and room._turn == 1
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())
