"""Blocks room: letters and Space drop blocks at the cursor and move on the
way it last went (along an arrow, or up), Enter drops a block on top of the
one just laid and goes on up (held, it stops at the top), Shift
with Up or Down moves the cursor's height either way, that height carries to other columns, a
block goes in the first free spot at or above it, Backspace eats down the column
then steps left, a chord mixes the second key's color into the block the first
one dropped, holding a letter or Space while arrowing lays a line, a tap of Tab
turns the build a little and Tab held with the arrows looks around it to any angle and tilts the view, with arrows
still moving the way they point most, the cursor's block waits on the top level
over its column and a new block falls from it, the walls and the top stop everything rather than wrap, and the Esc picker
reaches the room with 4."""

import math

from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import blocks_room
from purplecomputer.rooms.blocks_room import DEPTH, DROP_S, HEIGHT, HOVER, LOOKS, REST_TILT, RISE, SINK, TILTS, TURN_DETAIL_BLOCKS, WIDTH
from purplecomputer.rooms.blocks_view import REST_PITCH, SLAB, TOP, Camera, shape
from purplecomputer.color_mixing import mix_colors_paint
from purplecomputer.input import KeyCode, RawKeyEvent
from purplecomputer.keyboard import CharacterAction, ControlAction, InputFloodGuard, KeyboardStateMachine, NavigationAction
from purplecomputer.palette import get_key_color


def _hold_tab(room):
    """Tab down, as the room sees it: the arrows now look around."""
    room._tab = False


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


def test_stacking_past_the_top_stays_on_the_top_block():
    async def go():
        app, room = _blocks()
        await type_text(app, "a" * (HEIGHT + 2))
        assert set(room._blocks) == {(5, 5, y) for y in range(HEIGHT)} and (room._x, room._z) == (5, 5)
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


def test_typing_goes_right_by_default_and_piles_up_at_the_wall():
    async def go():
        app = make_app()
        app.action_switch_room("blocks")
        room = app.rooms["blocks"]
        room._x, room._z = WIDTH - 2, DEPTH - 1
        await type_text(app, "abc")
        assert {(WIDTH - 2, DEPTH - 1, 0), (WIDTH - 1, DEPTH - 1, 0), (WIDTH - 1, DEPTH - 1, 1)} == set(room._blocks)
    run(go())


def test_walking_into_a_wall_turns_typing_along_it():
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
        await press(app, "enter")               # Enter builds up on the block just laid, in its color
        assert room._blocks[(8, 5, 1)] == get_key_color("c") and (room._x, room._cursor_y()) == (8, 2)
        await type_text(app, "ab")
        assert {(8, 5, 2), (8, 5, 3)} <= set(room._blocks)
        await press(app, "right")               # nothing is locked in: off sideways again
        await type_text(app, "a")
        assert (9, 5, 0) in room._blocks and room._x == 10
        await press(app, "right")
        await press(app, "enter")               # the cursor has moved since: Enter builds where it is
        assert (11, 5, 0) in room._blocks and (9, 5, 1) not in room._blocks
    run(go())


def test_holding_enter_grows_a_tower_and_stops_at_the_top():
    async def go():
        app, room = _blocks()
        await press(app, "right")
        await press(app, "q", shift_held=True)      # pick a color, then build up in it
        for i in range(HEIGHT + 3):
            await press(app, "enter", is_repeat=i > 0)
        assert room._blocks == {(6, 5, y): get_key_color("q") for y in range(HEIGHT)}
        assert (room._x, room._z) == (6, 5)
    run(go())


def test_space_then_enter_stacks_on_the_block_space_laid():
    async def go():
        app, room = _blocks()
        await press(app, "right")
        await app._dispatch_keyboard_action(ControlAction(action="space", is_down=True))
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True, space_held=True))
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True, space_held=True))
        assert set(room._blocks) == {(6, 5, 0), (6, 5, 1), (6, 5, 2)}
    run(go())


def test_shift_up_and_down_stop_at_the_top_and_the_floor():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        for i in range(HEIGHT + 2):
            await press(app, "up", shift_held=True, is_repeat=i > 0)
        await press(app, "up", shift_held=True)
        assert room._cursor_y() == HEIGHT - 1 and (room._x, room._z) == (5, 5)
        for i in range(HEIGHT + 2):
            await press(app, "down", shift_held=True, is_repeat=i > 0)
        await press(app, "down", shift_held=True)
        assert room._cursor_y() == 0                # on the block at 0
    run(go())


def test_a_tap_of_shift_then_up_or_down_moves_the_height():
    async def go():
        app, room = _blocks()
        await press(app, "up", shifted=True)
        assert room._cursor_y() == 1 and (room._x, room._z) == (5, 5)
        await press(app, "down", shifted=True)
        assert room._cursor_y() == 0
    run(go())


def test_shift_up_steps_onto_blocks_in_the_way_and_typing_mixes_into_them():
    async def go():
        app, room = _blocks()
        room._blocks[(5, 5, 2)] = room._blocks[(5, 5, HEIGHT - 1)] = "#ff0000"
        for y in range(1, HEIGHT):
            await press(app, "up", shift_held=True)
            assert room._cursor_y() == y
        await press(app, "a")
        assert len(room._blocks) == 2 and room._blocks[(5, 5, HEIGHT - 1)] != "#ff0000"
    run(go())


def test_the_walls_stop_the_arrows_held_or_pressed_again():
    async def go():
        app, room = _blocks()
        for i in range(WIDTH + 5):
            await press(app, "right", is_repeat=i > 0)
        await press(app, "right")
        assert (room._x, room._z) == (WIDTH - 1, 5)
        room._z = DEPTH - 1
        await press(app, "up")
        assert (room._x, room._z) == (WIDTH - 1, DEPTH - 1)
    run(go())


def test_chosen_height_stays_while_walking():
    async def go():
        app, room = _blocks()
        for _ in range(3):
            await press(app, "up", shift_held=True)
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
        await type_text(app, "a")
        await press(app, "enter")               # on top of it rather than along
        for _ in range(2):
            await press(app, "up", shift_held=True)
        await type_text(app, "b")               # floating above the column
        for _ in range(3):
            await press(app, "up", shift_held=True)
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


def test_a_chord_builds_the_next_block_in_the_mix():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "r", char_held="g")    # the keyboard reports the newest held letter
        two = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        assert sorted(room._blocks.values()) == sorted([get_key_color("b"), two, mix_colors_paint([two, get_key_color("r")])])
    run(go())


def test_holding_a_chord_keeps_building_the_mix():
    async def go():
        app, room = _blocks()
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "g", is_repeat=True)
        await press(app, "right", char_held="g")
        mixed = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        assert sorted(room._blocks.values()) == sorted([get_key_color("b")] + [mixed] * 3)
    run(go())


def test_keyboard_reports_the_still_held_letter_and_shift():
    sm = KeyboardStateMachine()
    down = lambda code: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=0.0))
    assert down(KeyCode.KEY_B)[0].char_held is None
    assert down(KeyCode.KEY_Y)[0].char_held == "b"
    down(KeyCode.KEY_LEFTSHIFT)
    assert down(KeyCode.KEY_UP)[0].shift_held
    down(KeyCode.KEY_SPACE)
    assert down(KeyCode.KEY_ENTER)[0].space_held


def test_a_fresh_press_gets_through_after_a_long_held_key():
    guard = InputFloodGuard(repeats_only=True)
    held = [guard.should_drop(CharacterAction(char="m", is_repeat=True), timestamp=i / 30) for i in range(60)]
    assert any(held)
    assert not guard.should_drop(CharacterAction(char="u"), timestamp=2.0)


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


def test_holding_space_while_pressing_enter_lays_a_column():
    async def go():
        app, room = _blocks()
        app._code_panel_enabled = True
        room._dir = "right"
        await app._dispatch_keyboard_action(ControlAction(action="space", is_down=True))
        for i in range(3):
            await app._dispatch_keyboard_action(ControlAction(action="enter", is_repeat=i > 0, space_held=True))
        await app._dispatch_keyboard_action(ControlAction(action="space", is_down=False))
        assert set(room._blocks) == {(5, 5, y) for y in range(4)} and room.code_panel is None
    run(go())


def _on_screen(app, room, x, y, z) -> tuple:
    """The color drawn at view point (x, y, z)."""
    px, py = room._cam.at(x, y, z)
    return tuple(app.g.surface.get_at((round(px + room._origin[0]), round(py + room._origin[1])))[:3])


def _shades(room, x, z, y, color) -> set:
    return {room._painter.face(room._painter.base(x, z, color), n, y) for n in (TOP, (0, -1))}


def test_the_cursor_s_block_waits_on_the_top_level_whatever_is_under_it_and_blinks():
    async def go():
        app, room = _blocks()
        for tower in (0, 7):
            room._blocks = {(5, 5, y): "#ff0000" for y in range(tower)}
            room._changed()
            app._draw()
            assert room._cursor_y() == tower
            assert _on_screen(app, room, 5.5, HOVER + 0.5, 5.5) in _shades(room, 5, 5, HOVER, room._color)
        app.g.dirty = False
        app.g.blink(0)
        assert _on_screen(app, room, 5.5, HOVER + 0.5, 5.5) not in _shades(room, 5, 5, HOVER, room._color)
    run(go())


def test_a_wall_in_front_hides_the_landing_spot_and_an_arrowhead_marks_where_the_line_goes_behind():
    async def go():
        app, room = _blocks()
        room._z = 6
        tips = []
        room._arrowhead = lambda surf, tip, cell: tips.append(tip)
        app._draw()
        assert tips == [room._cam.at(5.5, 1, 6.5)]                  # in the open: just the line's end
        room._blocks.update({(x, 4, y): "#ff0000" for x in range(WIDTH) for y in range(4)})
        room._changed()
        del tips[:]
        app._draw()
        assert _on_screen(app, room, 5.5, 0.5, 6.5) in _shades(room, 5, 4, 0, "#ff0000")     # the wall, whole
        (end, cut), front = tips, room._front
        assert end == room._cam.at(5.5, 1, 6.5) and cut[1] < end[1]
        assert not front.get_at((int(cut[0]), int(cut[1])))[3] and front.get_at((int(cut[0]), int(cut[1]) + 3))[3]
    run(go())


def test_a_new_block_falls_to_its_spot_from_the_cursor_s_block(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        await press(app, "a")
        assert room._falls == {(5, 5, 0): (100.0, HOVER)} and set(room._view_blocks()) == {(5, 5, HOVER)}
        now[0] += DROP_S / 2
        app._draw()
        assert set(room._view_blocks()) == {(5, 5, HOVER * 0.75)} and set(room._view_blocks(falling=False)) == {(5, 5, 0)}
        now[0] += DROP_S
        room._fall_tick()
        assert not room._falls and room._fall_timer is None and set(room._view_blocks()) == {(5, 5, 0)}
        await press(app, "a")                                       # onto a full spot: mixed in, nothing falls
        room._next = (5, 5, 0, True)
        await press(app, "b")
        assert list(room._falls) == [(5, 5, 1)]
        room._blocks[(8, 8, 3)] = "#ff0000"                         # under a block: from just under it
        room._x, room._z, room._next = 8, 8, None
        await press(app, "a")
        assert room._falls[(8, 8, 0)][1] == 2
        room.restore_timeline_state(room.timeline_state())
        assert not room._falls
    run(go())


def test_the_cursor_shows_while_the_view_turns_with_its_arrow_the_way_typing_will_go():
    async def go():
        app, room = _blocks()
        room._dir = "right"
        shown = []
        room._hover_marks = lambda surf, painter, x, z, way, bright=True: shown.append((x, z, way))
        for _ in range(5):
            room.look_around()
        room._look[0] = 40.0
        app._draw()
        (wx, wz), (nx, nz) = room._world(*room._view(5, 5)), room._world(room._view(5, 5)[0] + 1, room._view(5, 5)[1])
        assert room._side == 1 and shown == [(5, 5, (nx - wx, nz - wz))]
    run(go())


def test_blocks_are_plain_faces_with_no_mark_on_the_cursor_s_row():
    async def go():
        app, room = _blocks()
        room._blocks.update({(8, 5, 0): "#ff0000", (8, 7, 0): "#00ff00"})
        room._changed()
        app._draw()
        painter = room._painter
        for x, z, color in ((8, 5, "#ff0000"), (8, 7, "#00ff00")):      # on the cursor's row, and behind it
            top = painter.face(painter.base(x, z, color), TOP, 0)
            assert tuple(room._composed.get_at(tuple(map(int, room._cam.at(x + 0.5, 1, z + 0.5))))[:3]) == top
    run(go())


def test_a_build_is_painted_as_tall_boxes_with_only_the_faces_that_can_show():
    red, blue = "#ff0000", "#0000ff"
    blocks = {(2, 2, 0): red, (2, 2, 1): red, (2, 2, 2): blue, (3, 2, 0): red, (3, 2, 1): red, (2, 2, 5): blue, (2, 2, 6): blue}
    runs, floats, stacks = shape(blocks)
    assert [r[:5] for r in runs] == [(2, 2, 0, 1, red), (2, 2, 2, 2, blue), (2, 2, 5, 6, blue), (3, 2, 0, 1, red)]
    faces = {r[:4]: set(r[5]) for r in runs}
    assert faces[(2, 2, 0, 1)] == {(0, -1), (0, 1), (-1, 0)}        # under the blue block, and against the red column
    assert faces[(3, 2, 0, 1)] == {TOP, (0, -1), (0, 1), (1, 0)}
    assert faces[(2, 2, 2, 2)] == faces[(2, 2, 5, 6)] == {TOP, (0, -1), (0, 1), (-1, 0), (1, 0)}
    assert floats == [(2, 2, 3)] and stacks == [(2, 2, 0, 2), (2, 2, 5, 6), (3, 2, 0, 1)]
    assert shape({}) == ([], [], [])


def _settle(room):
    """The view lands where it is headed, as its timer would bring it."""
    room._look = list(room._goal)
    if room._look_timer:
        room._look_tick()


def test_from_every_side_blocks_stay_put_and_arrows_follow_the_screen():
    async def go():
        app, room = _blocks()
        await press(app, "r")
        for side in (1, 2, 3, 0):
            room._aim(yaw=90 * side)
            _settle(room)
            assert room._side == side and (5, 5, 0) in room._blocks
            for way, step in blocks_room.STEPS.items():
                before = room._view(room._x, room._z)
                await press(app, way)
                after = room._view(room._x, room._z)
                assert (after[0] - before[0], after[1] - before[1]) == step
            app._draw()
        room._aim(yaw=90)
        await press(app, "right")
        assert (room._x, room._z) == (5, 4)     # the front edge went right, so right on screen is toward the old front
    run(go())


def test_tab_with_left_or_right_turns_a_little_at_a_time_and_the_arrows_go_the_way_they_point_most():
    async def go():
        app, room = _blocks()
        _hold_tab(room)
        step = LOOKS["right"][1]
        for turns in range(1, 6):
            await press(app, "right")
            _settle(room)
            app._draw()
            assert room._goal[0] == step * turns and room._side == (turns * step + 45) // 90
            assert abs(room._off()) < 45
        assert room._goal[0] == 90 and room._side == 1              # five turns is a quarter of the way around
        await press(app, "left")
        room._tab = None
        await press(app, "right")
        _hold_tab(room)
        assert room._side == 1 and (room._x, room._z) == (5, 4)     # a little off the side still moves as that side does
        for _ in range(5):
            await press(app, "left")
            _settle(room)
        assert room._side == 0 and room._goal[0] == 342             # on past the front, with no turns left behind it
    run(go())


def test_a_held_turn_keeps_the_view_just_moving_and_a_press_mid_turn_carries_on():
    async def go():
        app, room = _blocks()
        _hold_tab(room)
        step = LOOKS["right"][1]
        await press(app, "right")
        await press(app, "right", is_repeat=True)     # held: waits until the view has nearly caught up
        assert room._goal[0] == step and room._look_timer is not None
        await press(app, "right")                     # pressed again: carries on around
        assert room._goal[0] == 2 * step
        room._look[0] = 2 * step - 1
        await press(app, "right", is_repeat=True)
        assert room._goal[0] == 3 * step
    run(go())


def test_the_view_eases_to_where_it_is_headed_then_its_timer_stops(monkeypatch):
    async def go():
        app, room = _blocks()
        await type_text(app, "abc")
        app._draw()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        room._aim(yaw=90)
        was = 0.0
        for _ in range(200):
            if room._look_timer is None:
                break
            now[0] += 1 / 60
            room._look_tick()
            assert was <= room._look[0] <= 90 and room._look[0] - was <= blocks_room.LOOK_SPEED / 60 + 1e-6
            was = room._look[0]
            app._draw()
        assert room._look == room._goal == [90.0, REST_TILT, 0.0] and room._moving() is None
        assert 0.3 < now[0] - 100 < 1.2
    run(go())


def test_every_side_shows_the_same_floor_and_the_front_is_the_short_way_back():
    async def go():
        app, room = _blocks()
        cells = {(x, z) for x in range(WIDTH) for z in range(DEPTH)}
        for side in range(4):
            room._aim(yaw=90 * side + 18, tilt=TILTS[1])
            _settle(room)
            assert room._side == side
            assert {room._view(*c) for c in cells} == cells
            assert all(room._world(*room._view(*c)) == c for c in cells)
            room.face_front()
            assert room._goal == [(0, 0, 360, 360)[side], REST_TILT, 0]
            _settle(room)
            assert room._goal[0] == 0 and room._side == 0
    run(go())


def test_a_turn_lands_on_its_side_s_picture_and_a_quarter_turn_keeps_one_size():
    for off in (0.0, math.radians(18), math.radians(-36)):
        rest = Camera(off, REST_PITCH, 900, 400, fit=off)
        for quarters in range(4):
            cam = Camera(math.pi / 2 * quarters + off, REST_PITCH, 900, 400, fit=abs(off))
            for x, z in ((0, 0), (WIDTH, 0), (3, 7)):
                vx, vz = x, z
                for _ in range(quarters):
                    vx, vz = WIDTH - vz, vx
                assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(cam.at(x, 2, z), rest.at(vx, 2, vz)))
    straight = Camera(0.0, REST_PITCH, 900, 400)
    assert math.isclose(Camera(0.7, REST_PITCH, 900, 400).s, straight.s)      # mid-turn between two sides
    turned = Camera(0.6, REST_PITCH, 900, 400, fit=0.6)
    assert turned.s < straight.s                                               # a turned floor needs more room
    corners = [turned.at(x, y, z) for x in (0, WIDTH) for z in (0, DEPTH) for y in (-SLAB, HEIGHT)]
    assert all(-1e-6 <= px <= 900 + 1e-6 and -1e-6 <= py <= 400 + 1e-6 for px, py in corners)


async def _real_key(app, sm, keycode, is_down):
    """A key as the keyboard reports it, through the same state machine as real keys."""
    for action in sm.process(RawKeyEvent(keycode=keycode, is_down=is_down, timestamp=0.0)):
        await app._dispatch_keyboard_action(action)


def test_tapping_real_tab_turns_a_little_when_it_is_let_go():
    async def go():
        app, room = _blocks()
        sm = KeyboardStateMachine()
        await _real_key(app, sm, KeyCode.KEY_TAB, True)
        assert room._goal[0] == 0 and room._tab is False
        await _real_key(app, sm, KeyCode.KEY_TAB, False)
        assert room._goal == [LOOKS["right"][1], REST_TILT, LOOKS["right"][1]] and room._tab is None
    run(go())


def test_real_tab_held_with_the_arrows_looks_around_and_then_does_not_turn():
    async def go():
        app, room = _blocks()
        sm = KeyboardStateMachine()
        await _real_key(app, sm, KeyCode.KEY_TAB, True)
        for key in (KeyCode.KEY_UP, KeyCode.KEY_LEFT):
            await _real_key(app, sm, key, True)
            await _real_key(app, sm, key, False)
            _settle(room)
        look = [360 + LOOKS["left"][1], REST_TILT + LOOKS["up"][1]]
        assert room._goal[:2] == look and (room._x, room._z) == (5, 5) and room._hover == 0
        await _real_key(app, sm, KeyCode.KEY_TAB, False)
        assert room._goal[:2] == look and room._side == 0
        await press(app, "right")
        await type_text(app, "a")
        app._draw()
        assert room._x == 7 and (6, 5, 0) in room._blocks    # both hands build again, in the view as it was left
    run(go())


def test_real_shift_with_up_or_down_moves_the_height_and_sideways_just_moves():
    async def go():
        app, room = _blocks()
        sm = KeyboardStateMachine()
        await _real_key(app, sm, KeyCode.KEY_LEFTSHIFT, True)
        for key in (KeyCode.KEY_UP, KeyCode.KEY_UP, KeyCode.KEY_DOWN, KeyCode.KEY_RIGHT):
            await _real_key(app, sm, key, True)
            await _real_key(app, sm, key, False)
        await _real_key(app, sm, KeyCode.KEY_LEFTSHIFT, False)
        assert room._hover == 1 and (room._x, room._z) == (6, 5) and room._goal[:2] == [0, REST_TILT]
    run(go())


def test_the_tilt_stops_at_the_side_and_at_nearly_straight_down():
    async def go():
        app, room = _blocks()
        _hold_tab(room)
        for way, end in (("up", TILTS[1]), ("down", TILTS[0])):
            for _ in range(8):
                await press(app, way)
                _settle(room)
                app._draw()
            assert room._goal[1] == end
    run(go())


def test_big_builds_still_turn():
    async def go():
        app, room = _blocks()
        room._blocks = {(x, z, y): "#ff0000" for x in range(WIDTH) for z in range(DEPTH) for y in range(HEIGHT)}
        assert len(room._blocks) > TURN_DETAIL_BLOCKS
        room._aim(yaw=90)
        room._look[0] = 45.0
        app._draw()
        assert room._moving() is not None
    run(go())


def test_slow_turn_frames_lower_the_detail_limit(monkeypatch):
    monkeypatch.setattr(blocks_room, "TURN_FRAME_BUDGET_S", 0.0)

    async def go():
        app, room = _blocks()
        await type_text(app, "abc")
        room._aim(yaw=90)
        room._look[0] = 45.0
        app._draw()
        assert room._turn_detail_limit == 2     # three blocks went over budget, so three now turn plain
    run(go())


def test_shift_picks_a_color_without_dropping():
    async def go():
        for kw in ({"shift_held": True}, {}):  # held, or a tap of Shift before (sticky): press sends Q as shifted
            app, room = _blocks()
            await press(app, "Q", **kw)
            assert not room._blocks and room._color == get_key_color("q")
    run(go())


def test_timeline_round_trip():
    async def go():
        app, room = _blocks()
        await type_text(app, "qwe")
        await press(app, "up", shift_held=True)
        state = room.timeline_state()
        room.clear()
        assert not room.has_content() and room._hover == 0
        await press(app, "tab")
        room.restore_timeline_state(state)
        assert len(room._blocks) == 3 and room._hover == 4 and (room._x, room._z) == (5, 5)
        assert room._goal[0] == LOOKS["right"][1]   # the view is the viewer's, not the history's
    run(go())


def test_tab_turns_the_build_while_time_traveling(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def go():
        app, room = _blocks()
        await type_text(app, "ab")
        app._start_time_travel()
        app._step_time_travel(-1)
        await press(app, "tab")
        assert room._goal[0] == LOOKS["right"][1] and app._time_travel is not None
        app._cancel_time_travel()
        assert room._goal[0] == LOOKS["right"][1] and len(room._blocks) == 2
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
        room._aim(yaw=180)
        _settle(room)
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


def test_the_colors_chip_hides_while_the_code_panel_types_backslash():
    async def go():
        app, room = _blocks()
        app._draw()
        assert room.bar_row is not None
        room.open_code_panel()
        app._draw()
        assert room.code_panel is not None and room.bar_row is None
    run(go())
