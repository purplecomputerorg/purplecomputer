"""Blocks room: letters and Space drop blocks at the cursor and move on the
way it last went (along an arrow, or up after Enter), Enter walks the
cursor's height up and starts over from the floor (not while held), Shift
with Up or Down moves it either way, that height carries to other columns, a
block goes in the first free spot at or above it, Backspace eats down the column
then steps left, a chord mixes the second key's color into the block the first
one dropped, holding a letter or Space while arrowing lays a line, Tab flips
to the back with arrows still moving the way they point, rows in front of the
cursor's row fade when they hide it, and the Esc picker reaches the room with
4."""

import time

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.blocks_room import DEPTH, FRONT_ALPHA, HEIGHT, RISE, SINK, TURN_DETAIL_BLOCKS, TURN_S, WIDTH
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.keyboard import KeyboardStateMachine, NavigationAction
from purple_tui.palette import get_key_color


def _blocks():
    app = make_app()
    app.action_switch_room("blocks")
    room = app.rooms["blocks"]
    room._x, room._z = 5, 5
    room._dir = RISE                        # most tests stack; typing to the right is tested on its own
    return app, room


def test_letters_and_space_stack_on_the_cursor_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "rg")
        await press(app, "space")
        assert room._blocks == {(5, 5, 0): get_key_color("r"), (5, 5, 1): get_key_color("g"),
                                (5, 5, 2): get_key_color("g")}
    run(go())


def test_held_letter_repeats_like_in_art():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        await press(app, "a", is_repeat=True)
        await press(app, "a", is_repeat=True)
        assert len(room._blocks) == 3
    run(go())


def test_stacking_past_the_top_starts_the_next_column_from_the_floor():
    async def go():
        app, room = _blocks()
        await type_text(app, "a" * (HEIGHT + 1))
        assert all((5, 5, y) in room._blocks for y in range(HEIGHT)) and (6, 5, 0) in room._blocks
    run(go())


def test_a_full_column_puts_the_cursor_on_its_top_block():
    async def go():
        app, room = _blocks()
        room._blocks.update({(5, 5, y): "#ff0000" for y in range(HEIGHT)})
        assert room._cursor_y() == HEIGHT - 1
        await press(app, "b")
        assert room._blocks[(5, 5, HEIGHT - 1)] == mix_colors_paint(["#ff0000", get_key_color("b")])
        app._draw()
    run(go())


def test_typing_goes_right_by_default_and_wraps_like_lines_of_text():
    async def go():
        app = make_app()
        app.action_switch_room("blocks")
        room = app.rooms["blocks"]
        room._x, room._z = WIDTH - 2, DEPTH - 1
        await type_text(app, "abc")
        assert {(WIDTH - 2, DEPTH - 1, 0), (WIDTH - 1, DEPTH - 1, 0), (0, 0, 0)} == set(room._blocks)
    run(go())


def test_walking_into_a_wall_turns_typing_along_it_instead_of_wrapping():
    async def go():
        app, room = _blocks()
        for i in range(DEPTH):
            await press(app, "down", is_repeat=i > 0)
        assert room._dir == "right"
        await type_text(app, "ab")
        assert {(5, 0, 0), (6, 0, 0)} == set(room._blocks)
    run(go())


def test_in_the_right_hand_corner_typing_turns_left():
    async def go():
        app, room = _blocks()
        room._x = WIDTH - 1
        await press(app, "right", is_repeat=True)
        await type_text(app, "ab")
        assert {(WIDTH - 1, 5, 0), (WIDTH - 2, 5, 0)} == set(room._blocks)
    run(go())


def test_shift_up_to_the_ceiling_turns_typing_right():
    async def go():
        app, room = _blocks()
        for i in range(HEIGHT):
            await app._dispatch_keyboard_action(NavigationAction(direction="up", shift_held=True, is_repeat=i > 0))
        await type_text(app, "ab")
        assert {(5, 5, HEIGHT - 1), (6, 5, HEIGHT - 1)} == set(room._blocks)
    run(go())


def test_shift_down_builds_downward():
    async def go():
        app, room = _blocks()
        room._hover = 3
        await press(app, "down", shift_held=True)
        await type_text(app, "ab")
        assert set(room._blocks) == {(5, 5, 2), (5, 5, 1)}
    run(go())


def test_typing_builds_the_way_the_cursor_last_moved():
    async def go():
        app, room = _blocks()
        await press(app, "right")
        await type_text(app, "abc")
        assert set(room._blocks) == {(6, 5, 0), (7, 5, 0), (8, 5, 0)} and room._x == 9
        await press(app, "enter")               # first Enter only turns typing upward
        assert room._cursor_y() == 0
        await type_text(app, "ab")
        assert {(9, 5, 0), (9, 5, 1)} <= set(room._blocks)
    run(go())


def test_enter_walks_up_and_starts_over_from_the_floor():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")                 # the cursor starts at 3
        for y in range(4, HEIGHT):
            await press(app, "enter", is_repeat=y > 4)
            assert room._cursor_y() == y
        await press(app, "enter", is_repeat=True)   # held: sticks at the top
        assert room._cursor_y() == HEIGHT - 1
        await press(app, "enter")                   # pressed again: the lowest free level
        assert room._cursor_y() == 3 and len(room._blocks) == 3
    run(go())


def test_shift_up_and_down_held_stop_at_the_ends_and_a_fresh_press_wraps():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        for i in range(HEIGHT + 2):
            await press(app, "up", shift_held=True, is_repeat=i > 0)
        assert room._cursor_y() == HEIGHT - 1 and (room._x, room._z) == (5, 5)
        for i in range(HEIGHT + 2):
            await press(app, "down", shift_held=True, is_repeat=i > 0)
        assert room._cursor_y() == 1                # rests on the block at 0
        await press(app, "down", shift_held=True)
        assert room._cursor_y() == HEIGHT - 1
        await press(app, "up", shift_held=True)
        assert room._cursor_y() == 1
    run(go())


def test_held_arrows_stop_at_the_wall_and_a_fresh_press_comes_out_the_far_side():
    async def go():
        app, room = _blocks()
        for i in range(WIDTH + 5):
            await press(app, "right", is_repeat=i > 0)
        assert room._x == WIDTH - 1
        await press(app, "right")
        assert (room._x, room._z) == (0, 5)
        await press(app, "up")
        room._z = DEPTH - 1
        await press(app, "up")
        assert room._z == 0
    run(go())


def test_chosen_height_stays_while_walking():
    async def go():
        app, room = _blocks()
        for _ in range(3):
            await press(app, "enter")
        await press(app, "right")
        await press(app, "right")
        await type_text(app, "qq")
        assert (7, 5, 3) in room._blocks and (8, 5, 3) in room._blocks and room._x == 9
        await press(app, "right", char_held="q")
        assert (10, 5, 3) in room._blocks
    run(go())


def test_backspace_eats_down_from_the_cursor_then_steps_left():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")
        await press(app, "right")
        await press(app, "enter")               # stack here rather than along
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


def test_stacking_up_to_a_floating_block_passes_it():
    async def go():
        app, room = _blocks()
        room._blocks[(5, 5, 2)] = get_key_color("b")
        await type_text(app, "gg")
        assert room._cursor_y() == 3
        await press(app, "g")
        assert room._blocks[(5, 5, 2)] == get_key_color("b") and (5, 5, 3) in room._blocks
    run(go())


def test_typing_a_row_climbs_over_blocks_in_its_way():
    async def go():
        app, room = _blocks()
        room._dir = "right"
        room._blocks[(6, 5, 0)] = get_key_color("b")
        await type_text(app, "ggg")
        assert room._blocks == {(5, 5, 0): get_key_color("g"), (6, 5, 0): get_key_color("b"),
                                (6, 5, 1): get_key_color("g"), (7, 5, 0): get_key_color("g")}
    run(go())


def test_laying_a_line_climbs_over_blocks_in_its_way():
    async def go():
        app, room = _blocks()
        room._blocks[(6, 5, 0)] = get_key_color("b")
        await press(app, "right", char_held="g")
        await press(app, "right", char_held="g")
        assert room._blocks == {(6, 5, 0): get_key_color("b"), (6, 5, 1): get_key_color("g"),
                                (7, 5, 0): get_key_color("g")}
    run(go())


def test_chord_mixes_into_the_block_the_held_key_dropped():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        assert room._blocks == {(5, 5, 0): mix_colors_paint([get_key_color("b"), get_key_color("g")])}
    run(go())


def test_a_chord_keeps_mixing_while_letters_stay_held():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "r", char_held="g")    # the keyboard reports the newest held letter
        two = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        assert room._blocks == {(5, 5, 0): mix_colors_paint([two, get_key_color("r")])}
    run(go())



def test_holding_a_chord_keeps_building_the_mix():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "g", is_repeat=True)
        await press(app, "right", char_held="g")
        mixed = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        assert set(room._blocks.values()) == {mixed} and len(room._blocks) == 3
    run(go())

def test_keyboard_reports_the_still_held_letter_and_shift():
    sm = KeyboardStateMachine()
    down = lambda code: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=time.monotonic()))
    assert down(KeyCode.KEY_B)[0].char_held is None
    assert down(KeyCode.KEY_Y)[0].char_held == "b"
    down(KeyCode.KEY_LEFTSHIFT)
    assert down(KeyCode.KEY_UP)[0].shift_held


def test_holding_a_letter_or_space_while_arrowing_lays_a_line():
    async def go():
        app, room = _blocks()
        for i in range(WIDTH):
            await press(app, "right", char_held="z", is_repeat=i > 0)
        assert room._x == WIDTH - 1
        assert all((x, 5, 0) in room._blocks for x in range(6, WIDTH))
        await press(app, "up", space_held=True)
        assert (WIDTH - 1, 6, 0) in room._blocks
    run(go())


def test_rows_in_front_fade_only_when_they_hide_the_landing_spot():
    async def go():
        app, room = _blocks()
        room._blocks.update({(15, 4, y): "#ff0000" for y in range(3)})
        room._x, room._z = 15, 6
        app._draw()
        assert room._front.get_bounding_rect().w and room._front.get_alpha() == FRONT_ALPHA
        room._x = 20                            # the same row, clear of those blocks
        app._draw()
        assert room._front.get_alpha() == 255
        room._x, room._z = 5, 2
        app._draw()
        assert not room._front.get_bounding_rect().w
    run(go())


def test_building_backward_keeps_the_block_just_laid_solid():
    async def go():
        app, room = _blocks()
        await press(app, "up")
        await type_text(app, "aaa")
        app._draw()
        assert room._front.get_bounding_rect().w and room._front.get_alpha() == 255
    run(go())


def test_a_front_block_over_only_the_thread_stays_solid():
    async def go():
        app, room = _blocks()
        room._blocks.update({(6, 2, y): "#ff0000" for y in range(4)})
        room._z, room._hover = 6, 8
        app._draw()
        assert room._front.get_bounding_rect().w and room._front.get_alpha() == 255
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
        await press(app, "tab")                 # mid-turn: ignored
        assert room._back
        room._fade_start = None
        await press(app, "tab")
        assert not room._back
    run(go())


def test_turn_draws_and_stops_its_timer():
    async def go():
        app, room = _blocks()
        await type_text(app, "abc")
        app._draw()
        await press(app, "tab")
        for p in (0.25, 0.5, 0.75):
            room._fade_start = time.monotonic() - TURN_S * p
            app._draw()
        room._fade_start = time.monotonic() - TURN_S - 0.05
        app._draw()
        room._fade_tick()
        assert room._fade_timer is None
    run(go())


def test_big_builds_still_turn():
    async def go():
        app, room = _blocks()
        room._blocks = {(x, z, y): "#ff0000" for x in range(WIDTH) for z in range(DEPTH) for y in range(HEIGHT)}
        assert len(room._blocks) > TURN_DETAIL_BLOCKS
        await press(app, "tab")
        room._fade_start = time.monotonic() - TURN_S * 0.5
        app._draw()
        assert room._fade_progress() is not None
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
        state = room.timeline_state()
        room.clear()
        assert not room.has_content() and room._hover == 0
        await press(app, "tab")
        room.restore_timeline_state(state)
        assert len(room._blocks) == 3 and room._hover == 4 and (room._x, room._z) == (5, 5)
        assert room._back                       # front or back is the viewer's, not the history's
    run(go())


def test_tab_turns_around_while_time_traveling(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def go():
        app, room = _blocks()
        await type_text(app, "ab")
        app._start_time_travel()
        app._step_time_travel(-1)
        await press(app, "tab")
        assert room._back and app._time_travel is not None
        app._cancel_time_travel()
        assert room._back and len(room._blocks) == 2
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())


def test_restoring_blocks_past_the_walls_drops_them():
    """Steps from an older, bigger floor must not crash the back view."""
    async def go():
        app, room = _blocks()
        room.restore_timeline_state({f"b:3,{DEPTH + 2},0": "#FF0000", "b:3,4,0": "#00FF00",
                                     "cursor": [WIDTH + 3, DEPTH + 3]})
        assert room._blocks == {(3, 4, 0): "#00FF00"}
        assert (room._x, room._z) == (WIDTH - 1, DEPTH - 1)
        await press(app, "tab")
        room.draw(app.g, app.g.surface.get_rect())
    run(go())


def _code(room, *moves):
    """Code moves as the code runner drives them: (way, count) pairs."""
    for way, count in moves:
        room.set_way(way)
        for _ in range(count):
            room.build()


def test_code_turning_straight_back_retraces_without_extending():
    async def go():
        app, room = _blocks()
        _code(room, (RISE, 10), (SINK, 2))
        tower = {(5, 5, y) for y in range(10)}
        assert set(room._blocks) == tower
        _code(room, ("right", 3))
        assert set(room._blocks) - tower == {(6, 5, 7), (7, 5, 7)}
    run(go())


def test_code_turning_straight_back_along_a_row_mixes_into_it():
    async def go():
        app, room = _blocks()
        _code(room, ("right", 4), ("left", 2))
        assert set(room._blocks) == {(x, 5, 0) for x in range(5, 9)}
        assert room._x == 6
    run(go())


def test_a_code_row_still_climbs_over_a_tower_in_its_way():
    async def go():
        app, room = _blocks()
        _code(room, (RISE, 2))
        room._x, room._next = 4, None
        _code(room, ("right", 3))
        assert {(4, 5, 0), (5, 5, 2), (6, 5, 2)} <= set(room._blocks)
    run(go())
