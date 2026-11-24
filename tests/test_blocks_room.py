"""Blocks room: letters and Space drop blocks into the cursor's column, on top of what is
there, the arrows move the cursor across the floor, Shift with Up or Down moves its
height, that height carries to other columns, a
block goes in the first free spot at or above it, Enter drops one in the brush color and held
stops at the top, Backspace eats down the column then steps left, a chord mixes the second
key's color into the block the first one dropped, holding a letter or Space while moving
across the floor lays a line, a tap of Tab turns the build a quarter and Tab held with the
arrows looks around it to any angle and tilts the view, the arrows still moving the way
they point most, the cursor's block waits on the top level over its column and a new block
falls from it, the walls and the top stop everything rather than wrap, and the Esc picker
reaches the room with 4."""

import math

import random
import pygame

from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import blocks_room
from purplecomputer.rooms.blocks_room import DEPTH, DROP_S, HEIGHT, HOVER, LOOKS, REST_TILT, RISE, SINK, TILTS, TURN_DETAIL_BLOCKS, WIDTH
from purplecomputer.rooms.blocks_view import REST_PITCH, SLAB, TOP, Camera, Painter, shape
from purplecomputer.color_mixing import mix_colors_paint
from purplecomputer.input import KeyCode, RawKeyEvent
from purplecomputer.keyboard import CharacterAction, ControlAction, InputFloodGuard, KeyboardStateMachine
from purplecomputer.palette import get_key_color


def _hold_tab(room):
    """Tab down, as the room sees it: the arrows now look around."""
    room._tab = False


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


def test_held_letter_repeats_like_in_art():
    async def go():
        app, room = _blocks()
        await press(app, "a")
        await press(app, "a", is_repeat=True)
        await press(app, "a", is_repeat=True)
        assert len(room._blocks) == 3
    run(go())


def test_stacking_past_the_top_wraps_on_to_the_next_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "a" * (HEIGHT + 2))
        assert set(room._blocks) == {(5, 5, y) for y in range(HEIGHT)} | {(6, 5, 0), (6, 5, 1)} and (room._x, room._z) == (6, 5)
    run(go())


def test_a_full_column_puts_the_cursor_on_its_top_block_and_a_letter_there_starts_the_next_column():
    async def go():
        app, room = _blocks()
        room._blocks.update({(5, 5, y): "#ff0000" for y in range(HEIGHT)})
        assert room._cursor_y() == HEIGHT - 1
        await press(app, "b")
        assert room._blocks[(5, 5, HEIGHT - 1)] == "#ff0000" and room._blocks[(6, 5, 0)] == get_key_color("b")
        app._draw()
    run(go())


def test_letters_always_stack_and_the_cursor_stays():
    async def go():
        app, room = _blocks()
        await type_text(app, "ab")
        assert set(room._blocks) == {(5, 5, 0), (5, 5, 1)} and (room._x, room._z) == (5, 5)
        await press(app, "right")
        await type_text(app, "cd")
        assert {(6, 5, 0), (6, 5, 1)} <= set(room._blocks) and room._x == 6
        await press(app, "right")
        await type_text(app, "e")
        assert (7, 5, 0) in room._blocks and len(room._blocks) == 5
    run(go())


def test_shift_with_up_or_down_moves_the_height_and_typing_stacks_from_there_to_the_top():
    async def go():
        app, room = _blocks()
        for i in range(HEIGHT - 2):
            await press(app, "up", shift_held=True, is_repeat=i > 0)
        assert room._cursor_y() == HEIGHT - 2 and (room._x, room._z) == (5, 5)
        await type_text(app, "abc")
        assert set(room._blocks) == {(5, 5, HEIGHT - 2), (5, 5, HEIGHT - 1), (6, 5, HEIGHT - 2)}     # then on at that height
    run(go())


def test_the_arrows_move_across_the_floor_up_away_and_down_toward():
    async def go():
        app, room = _blocks()
        await press(app, "up")
        assert (room._x, room._z) == (5, 6) and room._cursor_y() == 0
        await press(app, "down")
        await press(app, "down")
        await press(app, "right", shift_held=True)      # sideways, Shift changes nothing
        assert (room._x, room._z) == (6, 4) and room._hover == 0
    run(go())


def test_a_tap_of_enter_lifts_the_floor_and_holding_it_puts_it_back_on_the_ground():
    async def go():
        app, room = _blocks()
        await type_text(app, "ab")
        for _ in range(2):
            await press(app, "enter")
        assert room._cursor_y() == 4 and len(room._blocks) == 2          # a tap: the floor up a level, no block
        await room.handle(ControlAction(action="enter", is_down=True))
        assert room.hold_progress() is not None and room._lit_row() == "lift"
        room.enter_hold.hold._fire_hold()                                 # held long enough
        await room.handle(ControlAction(action="enter", is_down=False))
        assert room._hover == 0 and room._cursor_y() == 2                 # back on what the column holds
        await press(app, "right")
        await room.handle(ControlAction(action="enter", is_down=True))
        room.enter_hold.hold._fire_hold()
        assert room._bump is not None and room._bump[2] == -1             # on the ground already: a knock
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
        assert room._cursor_y() == HEIGHT - 1                      # on the ground the drop lands on the highest block
        for y in range(HEIGHT - 2, 1, -1):
            await press(app, "down", shift_held=True)
            assert room._cursor_y() == y
        await press(app, "a")
        assert len(room._blocks) == 2 and room._blocks[(5, 5, 2)] != "#ff0000"
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
        await type_text(app, "q")
        await press(app, "right")
        await type_text(app, "q")
        assert (7, 5, 3) in room._blocks and (8, 5, 3) in room._blocks and room._x == 8
        await press(app, "right", char_held="q")
        assert (9, 5, 3) in room._blocks
    run(go())


def test_backspace_eats_down_from_the_cursor_then_steps_left():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")
        await press(app, "right")
        await type_text(app, "aa")
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


def test_on_the_ground_a_letter_drops_onto_a_floating_block_not_into_the_gap_under_it():
    async def go():
        app, room = _blocks()
        room._blocks[(5, 5, 2)] = get_key_color("b")
        assert room._cursor_y() == 3
        await type_text(app, "gg")
        assert room._blocks[(5, 5, 2)] == get_key_color("b") and {(5, 5, 3), (5, 5, 4)} <= set(room._blocks)
        assert (5, 5, 0) not in room._blocks
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
        count = len(room._blocks)
        await press(app, "up", char_held="z", shift_held=True)      # Shift with Up is the height: it lays nothing
        assert len(room._blocks) == count and room._cursor_y() == 2      # from on top of the last block
    run(go())


def _on_screen(app, room, x, y, z) -> tuple:
    """The color drawn at view point (x, y, z)."""
    px, py = room._cam.at(x, y, z)
    return tuple(app.g.surface.get_at((round(px + room._origin[0]), round(py + room._origin[1])))[:3])


def _shades(room, x, z, y, color) -> set:
    return {room._painter.face(room._painter.base(x, z, color), n, y) for n in (TOP, (0, -1))}


def _close(color, shades) -> bool:
    """Whether a color is one of the shades, give or take what scaling a picture down smooth does to it."""
    return any(max(abs(a - b) for a, b in zip(color, shade)) <= 4 for shade in shades)


def test_the_cursor_s_block_waits_on_the_top_level_whatever_is_under_it_and_blinks():
    async def go():
        app, room = _blocks()
        for tower in (0, 7):
            room._blocks = {(5, 5, y): "#ff0000" for y in range(tower)}
            room._changed()
            app._draw()
            assert room._cursor_y() == tower
            assert _close(_on_screen(app, room, 5.5, HOVER + 0.5, 5.5), _shades(room, 5, 5, HOVER, room._color))
        app.g.dirty = False
        app.g.blink(0)
        assert not _close(_on_screen(app, room, 5.5, HOVER + 0.5, 5.5), _shades(room, 5, 5, HOVER, room._color))
    run(go())


def test_a_wall_in_front_hides_the_landing_spot_and_an_arrowhead_marks_where_the_line_goes_behind():
    async def go():
        app, room = _blocks()
        room._z = 6
        tips = []
        room._arrowhead = lambda surf, cam, x, z, h: tips.append(h)
        app._draw()
        assert tips == [1]                                          # in the open: just the line's end, on the landing spot
        room._blocks.update({(x, 4, y): "#ff0000" for x in range(WIDTH) for y in range(4)})
        room._changed()
        del tips[:]
        app._draw()
        assert _on_screen(app, room, 5.5, 0.5, 6.5) in _shades(room, 5, 4, 0, "#ff0000")     # the wall, whole
        (end, cut), front = tips, room._front
        at = lambda h: tuple(map(int, room._cam.at(5.5, h, 6.5)))
        assert end == 1 < cut < HOVER and not front.get_at(at(cut))[3] and front.get_at(at(cut - 0.25))[3]
    run(go())


def test_a_new_block_falls_to_its_spot_from_the_cursor_s_block(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        app._draw()
        painter = room._painter
        await press(app, "a")
        color = get_key_color("a")
        assert room._falls == {(5, 5, 0): (100.0, HOVER)} and not room._dirty        # the layers wait for it to land
        assert room._view_blocks() == {} and room._view_blocks(falling=True) == {(5, 5, 0): color}
        assert room._falling() == [(5, 5, HOVER, 0, HOVER, color)]
        now[0] += DROP_S / 2
        app._draw()
        assert room._falling() == [(5, 5, HOVER * 0.75, 0, HOVER, color)] and room._painter.items is painter.items
        assert _on_screen(app, room, 5.5, HOVER * 0.75 + 1, 5.5) in _shades(room, 5, 5, HOVER * 0.75, color)
        now[0] += DROP_S
        room._fall_tick()
        app._draw()
        assert not room._falls and not room._hide and room._fall_timer is None and room._view_blocks() == {(5, 5, 0): color}
        assert _on_screen(app, room, 5.5, 0.5, 5) in _shades(room, 5, 5, 0, color)      # its front: the next spot's shadow is on its top
        await press(app, "a")
        room._next = (5, 5, 1, True)                                # onto a block: mixed in, nothing falls
        await press(app, "b")
        assert list(room._falls) == [(5, 5, 1)]
        room._blocks[(8, 8, 3)] = "#ff0000"                         # a floor lifted under a block: from just under it
        room._x, room._z, room._next, room._hover = 8, 8, None, 1
        await press(app, "a")
        assert room._falls[(8, 8, 1)][1] == 2
        room.restore_timeline_state(room.timeline_state())
        assert not room._falls and not room._hide
    run(go())


def test_a_falling_block_passes_behind_what_stands_in_front_of_it(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        room._blocks.update({(x, 3, y): "#ff0000" for x in range(WIDTH) for y in range(5)})
        room._z = 6
        room._changed()
        await press(app, "a")
        now[0] += DROP_S * 0.95                                     # nearly down, behind the wall
        app._draw()
        (vx, vz, h, *_), = room._falling()
        seen, wall = _on_screen(app, room, 5.5, h + 0.5, 6), _shades(room, 5, 3, 0, "#ff0000")
        block = _shades(room, 5, 6, 0, room._color)
        ghost = {tuple(round(w + (b - w) * blocks_room.GHOST_ALPHA / 255) for w, b in zip(ws, bs)) for ws in wall for bs in block}
        assert h < 2 and _close(seen, ghost) and seen not in wall      # the wall, with the block faintly through it
        assert [item[2][:2] for item in room._hide[(5, 6, 0)][1]] and all(item[2][1] == 3 for item in room._hide[(5, 6, 0)][1])
    run(go())


def test_the_cursor_shows_while_the_view_turns():
    async def go():
        app, room = _blocks()
        shown = []
        room._hover_marks = lambda surf, painter, x, z, bright=True: shown.append((x, z))
        room._drop_marks = lambda surf, painter, x, z, y: shown.append((x, z, y))
        room.turn()
        room._look[0] = -40.0
        app._draw()
        assert room._side == 3 and shown == [(5, 5, 0), (5, 5)]
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


def test_a_turn_to_another_side_repaints_the_layers_even_with_the_same_camera():
    async def go():
        app, room = _blocks()
        room._blocks.update({(2, 3, y): "#ff0000" for y in range(4)})
        room._blocks.update({(x, 12, 0): "#00ff00" for x in range(6, 14)})
        room._changed()
        app._draw()
        cam, front = room._cam, pygame.image.tobytes(room._composed, "RGB")
        for _ in range(3):
            room.turn()
            _settle(room)
            app._draw()
            shown = pygame.image.tobytes(room._composed, "RGB")
            room._changed()
            app._draw()
            assert room._cam is cam and shown == pygame.image.tobytes(room._composed, "RGB") != front
    run(go())


def test_each_arrow_s_flat_key_lies_the_way_that_arrow_moves_the_cursor_clear_of_the_box():
    async def go():
        app, room = _blocks()
        for yaw, tilt in ((0, 30), (36, 30), (90, 30), (126, 60), (18, 15), (0, 75)):
            room._aim(yaw=yaw, tilt=tilt)
            _settle(room)
            app._draw()
            cam, (vx, vz) = room._cam, room._view(room._x, room._z)
            keys = {glyph: spot for glyph, spot, _, _ in room._arrow_keys(cam, vx, vz)}
            middle, bubble = pygame.Vector2(cam.at(vx + 0.5, HOVER + 0.5, vz + 0.5)), blocks_room.bubble_radius(cam, vx, vz)
            spots = []
            for way, (dx, dz) in blocks_room.STEPS.items():
                spot = keys[blocks_room.ARROW_KEYS[way]]
                step = pygame.Vector2(cam.at(vx + 0.5 + dx, HOVER + 0.5, vz + 0.5 + dz)) - middle
                assert (spot - middle).dot(step) > 0 and (spot.y < middle.y) == (cam.away(dx, dz) > 0), (yaw, tilt, way)
                assert spot.distance_to(middle) > bubble, (yaw, tilt, way)       # the arrow on it is clear of the bubble
                spots.append(spot)
            far = 0.5 * cam.cell(vx, HOVER, vz)       # spread out even from low down, where flat keys would lie edge on
            assert all(a.distance_to(b) > far for i, a in enumerate(spots) for b in spots[i + 1:]), (yaw, tilt)
    run(go())



def test_no_arrow_key_rises_out_of_the_room_at_any_tilt():
    async def go():
        app, room = _blocks()
        app._draw()
        w, h = room._composed.get_size()
        for tilt in range(TILTS[0], TILTS[1] + 1, 15):
            for off in (-36, 0, 36):
                cam = blocks_room.resting_camera(off, tilt, w, h)
                top = min(p.y for x in range(WIDTH) for z in range(DEPTH) for _, _, face, _ in room._arrow_keys(cam, x, z) for p in face)
                assert top >= 0, (tilt, off)
    run(go())

def test_each_floor_cell_keeps_its_shade_from_every_side():
    async def go():
        app, room = _blocks()
        world = Painter(room._cam, {})
        for side in range(4):
            room._aim(yaw=90 * side)
            _settle(room)
            app._draw()
            for x, z in ((1, 1), (1, 2), (12, 3)):
                vx, vz = room._view(x, z)
                spot = tuple(map(round, room._cam.at(vx + 0.5, 0, vz + 0.5)))
                assert tuple(room._composed.get_at(spot)[:3]) == world.tile(x, z), (side, x, z)
    run(go())


def test_a_frame_of_falling_blocks_paints_only_around_them_and_matches_a_whole_frame(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        room._blocks.update({(x, 3, y): "#ff0000" for x in range(WIDTH) for y in range(3)})
        room._z = 6
        room._changed()
        await type_text(app, "ab")
        await press(app, "right")
        await type_text(app, "s")
        app._draw()
        for step in (0.3, 0.6, 0.9):
            now[0] = 100.0 + DROP_S * step
            app.g.dirty, app.g.patches = False, []
            room._fall_tick()
            assert not app.g.dirty and len(app.g.patches) == 1
            spot = app.g.patches[0]()
            assert spot and spot.w * spot.h < app.g.surface.get_width() * app.g.surface.get_height() // 4
            part = pygame.image.tobytes(app.g.surface, "RGB")
            app._draw()
            assert part == pygame.image.tobytes(app.g.surface, "RGB"), step
    run(go())


def test_at_a_wall_the_key_that_way_is_a_curb_and_pushing_into_it_knocks_the_waiting_block(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        room._x, room._z = WIDTH - 1, 0
        app._draw()
        vx, vz = room._view(room._x, room._z)
        glyphs = {glyph for glyph, *_ in room._arrow_keys(room._cam, vx, vz)}
        assert glyphs == {blocks_room.LEFT, blocks_room.UP, None}       # right and down are walls here
        await press(app, "right")
        assert (room._x, room._z) == (WIDTH - 1, 0) and room._bump is not None
        now[0] += blocks_room.BUMP_S / 2
        ox, oz, oy = room._nudge()
        assert ox > 0.1 and oz == oy == 0                                 # it knocks toward the wall
        quiet = room._composed.copy()
        app._draw()
        vx, vz = room._view(room._x, room._z)
        edge = tuple(map(round, room._cam.at(WIDTH, HEIGHT / 2, 2)))
        shown = app.g.surface.get_at((edge[0] + room._origin[0] - 2, edge[1] + room._origin[1]))[:3]
        assert shown != quiet.get_at((edge[0] - 2, edge[1]))[:3]          # the right wall flashes
        now[0] += blocks_room.FLASH_S
        room._bump_tick()
        assert room._bump is None and room._nudge() == (0.0, 0.0, 0.0)
    run(go())


def test_at_the_top_level_going_higher_knocks_and_a_full_tower_wraps_right(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        app._draw()
        room._hover = HEIGHT - 1
        await press(app, "up", shift_held=True)
        assert room._hover == HEIGHT - 1 and room._nudge() == (0.0, 0.0, 0.0) and room._bump is not None
        now[0] += blocks_room.BUMP_S / 2
        assert room._nudge()[2] > 0.1                                    # up, into the glass
        now[0] += blocks_room.BUMP_S
        room._bump_tick()
        room._blocks.update({(room._x, room._z, y): "#ff0000" for y in range(HEIGHT)})
        room._hover = 0
        room._changed()
        column = (room._x, room._z)
        await type_text(app, "a")                                        # a full tower: on to the next column
        vx, vz = room._view(*column)
        assert room._view(room._x, room._z) == (vx + 1, vz) and (room._x, room._z, 0) in room._blocks
        room._blocks.update({(room._x, room._z, y): "#ff0000" for y in range(HEIGHT)})
        room._x, room._z = room._world(WIDTH - 1, vz)
        room._blocks.update({(room._x, room._z, y): "#ff0000" for y in range(HEIGHT)})
        room._changed()
        await type_text(app, "a")                                        # at the wall there's nowhere to go: it knocks
        assert room._view(room._x, room._z) == (WIDTH - 1, vz) and room._bump is not None
    run(go())


def test_letters_typed_while_a_block_falls_join_its_fall_as_one_stack(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        app._draw()
        await press(app, "a")
        now[0] += DROP_S / 3
        await type_text(app, "sd")
        (since, top), = {room._falls[(5, 5, 0)]}
        assert room._falls == {(5, 5, 0): (since, top), (5, 5, 1): (since, top + 1), (5, 5, 2): (since, top + 2)}
        heights = [f[2] - f[3] for f in room._falling()]
        assert len(set(heights)) == 1                         # all three the same way above their spots: one stack
        now[0] = since + DROP_S * 1.01
        room._fall_tick()
        assert not room._falls and {(5, 5, y) for y in range(3)} <= set(room._blocks)
    run(go())


def test_layers_kept_up_piece_by_piece_match_a_fresh_paint():
    async def go():
        app, room = _blocks()
        r = random.Random(3)
        for _ in range(120):
            await press(app, r.choice(["a", "s", "a", "backspace", "left", "right", "up", "down"]))
            while room._falls and r.random() < 0.7:
                for pos in list(room._falls):
                    room._falls[pos] = (0.0, room._falls[pos][1])
                room._fall_tick()
            app._draw()
        while room._falls:
            for pos in list(room._falls):
                room._falls[pos] = (0.0, room._falls[pos][1])
            room._fall_tick()
        app._draw()
        kept = pygame.image.tobytes(room._composed, "RGB")
        room._scene = None
        app._draw()
        assert kept == pygame.image.tobytes(room._composed, "RGB")
    run(go())


def test_tapping_real_tab_turns_a_quarter_when_it_is_let_go():
    async def go():
        app, room = _blocks()
        sm = KeyboardStateMachine()
        await _real_key(app, sm, KeyCode.KEY_TAB, True)
        assert room._goal[0] == 0 and room._tab is False
        await _real_key(app, sm, KeyCode.KEY_TAB, False)
        assert room._goal == [-90, REST_TILT, 0] and room._tab is None
        room._aim(yaw=126, tilt=60)                 # from a view looked around to: on to the next side, squared up
        room.turn()                                 # clockwise, so back to the front, at the resting tilt
        assert room._goal == [0, REST_TILT, 0]
        room._aim(yaw=126, tilt=60)
        room.clear()                                # a clear room starts from the front
        assert room._goal == [0, REST_TILT, 0]
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
        assert room._x == 6 and (6, 5, 0) in room._blocks    # both hands build again, in the view as it was left
    run(go())


def test_real_shift_with_up_or_down_moves_the_height_and_plain_up_steps_away():
    async def go():
        app, room = _blocks()
        sm = KeyboardStateMachine()
        await _real_key(app, sm, KeyCode.KEY_LEFTSHIFT, True)
        for key in (KeyCode.KEY_UP, KeyCode.KEY_UP, KeyCode.KEY_DOWN, KeyCode.KEY_RIGHT):
            await _real_key(app, sm, key, True)
            await _real_key(app, sm, key, False)
        await _real_key(app, sm, KeyCode.KEY_LEFTSHIFT, False)
        assert room._hover == 1 and (room._x, room._z) == (6, 5) and room._goal[:2] == [0, REST_TILT]
        await _real_key(app, sm, KeyCode.KEY_UP, True)
        await _real_key(app, sm, KeyCode.KEY_UP, False)
        assert room._hover == 1 and (room._x, room._z) == (6, 6)
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


def test_at_a_tilt_stop_the_view_springs_back_and_the_hint_drops_the_arrow_that_cannot_go():
    async def go():
        app, room = _blocks()
        _hold_tab(room)
        assert room._tab_hint().split()[:4] == [blocks_room.LEFT, blocks_room.UP, blocks_room.DOWN, blocks_room.RIGHT]
        await press(app, "down")
        _settle(room)
        assert room._goal[1] == TILTS[0] and blocks_room.DOWN not in room._tab_hint() and blocks_room.UP in room._tab_hint()
        await press(app, "down")                                    # nowhere to go: back off the stop, toward Up
        assert room._goal[1] == TILTS[0] and room._look[1] == TILTS[0] + blocks_room.LOOK_BOUNCE and room._look_timer
        app._draw()
        await press(app, "down", is_repeat=True)                    # held, or already springing: nothing more
        await press(app, "down")
        assert room._look[1] == TILTS[0] + blocks_room.LOOK_BOUNCE
        _settle(room)
        assert room._moving() is None
        for _ in range(4):
            await press(app, "up")
            _settle(room)
        await press(app, "up")
        assert room._goal[1] == TILTS[1] and room._look[1] == TILTS[1] - blocks_room.LOOK_BOUNCE
        assert blocks_room.UP not in room._tab_hint()
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
        assert room._goal[0] == -90                  # the view is the viewer's, not the history's
    run(go())


def test_tab_turns_the_build_while_time_traveling(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def go():
        app, room = _blocks()
        await type_text(app, "ab")
        app._start_time_travel()
        app._step_time_travel(-1)
        await press(app, "tab")
        assert room._goal[0] == -90 and app._time_travel is not None
        app._cancel_time_travel()
        assert room._goal[0] == -90 and len(room._blocks) == 2
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())


def test_a_step_from_the_old_wide_floor_keeps_its_middle_on_the_floor_s_middle():
    """History saved on the 30 by 12 floor says no size: its middle lands on today's middle, and what
    falls past the walls goes, without crashing the back view."""
    async def go():
        app, room = _blocks()
        room.restore_timeline_state({"b:15,6,0": "#FF0000", "b:15,6,1": "#FF0000", "b:22,0,0": "#00FF00", "b:2,6,0": "#0000FF",
                                     "cursor": [15, 6]})
        assert room._blocks == {(8, 8, 0): "#FF0000", (8, 8, 1): "#FF0000", (15, 2, 0): "#00FF00"}
        assert (room._x, room._z) == (8, 8)
        room._aim(yaw=180)
        _settle(room)
        room.draw(app.g, app.g.surface.get_rect())
        state = room.timeline_state()
        assert state["floor"] == [WIDTH, DEPTH]
        room.restore_timeline_state(state)                                # today's steps come back as they were
        assert room._blocks == {(8, 8, 0): "#FF0000", (8, 8, 1): "#FF0000", (15, 2, 0): "#00FF00"}
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


def test_the_guide_sits_beside_the_floor_and_a_held_key_lights_its_row():
    async def go():
        app, room = _blocks()
        app._draw()
        spots = room._guide_spots()
        assert set(spots) == {"build", "look"} and spots["build"].right < spots["look"].x
        look = spots["look"]
        quiet = pygame.image.tobytes(room._composed.subsurface(look), "RGB")
        _hold_tab(room)
        app._draw()
        assert pygame.image.tobytes(room._composed.subsurface(look), "RGB") != quiet     # held: its row comes up
        room._tab = None
        app._draw()
        assert pygame.image.tobytes(room._composed.subsurface(look), "RGB") == quiet
        room.open_code_panel()
        app._draw()
        assert set(room._guide_spots()) == {"look"}            # the code line takes the letters and arrows
    run(go())


def test_in_the_code_line_tab_held_with_an_arrow_looks_around_and_a_tap_still_turns():
    async def go():
        app, room = _blocks()
        room.open_code_panel()
        field = room.code_panel.field
        field.set("up 3")
        await room.handle(ControlAction(action="tab", is_down=True))
        await press(app, "right")
        await room.handle(ControlAction(action="tab", is_down=False))
        assert room._goal[0] == LOOKS["right"][1] and field.value == "up 3" and field.cursor == 4
        _settle(room)
        field.set("")                                          # nothing for Tab to accept
        await room.handle(ControlAction(action="tab", is_down=True))
        await room.handle(ControlAction(action="tab", is_down=False))
        assert room._goal[0] == -90                            # a tap: on to the next side, clockwise
    run(go())


def test_the_guide_holds_still_however_the_view_turns_or_tilts():
    async def go():
        app, room = _blocks()
        app._draw()
        spots = room._guide_spots()
        assert set(spots) == {"build", "look"}
        for yaw, tilt in ((18, 30), (45, 15), (-36, 75), (90, 60)):
            room._aim(yaw=yaw, tilt=tilt)
            _settle(room)
            app._draw()
            assert room._guide_spots() == spots, (yaw, tilt)
    run(go())


def test_the_lifted_floor_shows_while_a_block_would_float_and_fades_after_shift(monkeypatch):
    async def go():
        app, room = _blocks()
        now = [100.0]
        monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
        app._draw()
        assert room._lifted()[0] == 0                                     # on the ground: no lifted floor
        for _ in range(3):
            await press(app, "up", shift_held=True)
        now[0] += blocks_room.LIFT_SLIDE_S / 2
        strength, h = room._lifted()
        assert strength == 1 and 2 < h < 3                                # it slides up to its new height
        now[0] += blocks_room.LIFT_SLIDE_S / 2
        assert room._lifted() == (1.0, 3)
        app._draw()
        now[0] += blocks_room.LIFT_HOLD_S + blocks_room.LIFT_FADE_S
        assert room._lifted()[0] == 0                                     # a moment after Shift: gone
        app._keyboard_state_machine._shift_held = True
        assert room._lifted()[0] == 1                                     # Shift down again brings it back
        room._blocks.update({(room._x, room._z, y): "#ff0000" for y in range(3)})
        assert room._lifted()[0] == 0                                     # a block there would not float
    run(go())


def test_home_puts_the_cursor_in_the_middle_on_the_ground_from_the_front():
    async def go():
        app, room = _blocks()
        room._step_height(2)
        room.turn()
        room.home()
        assert (room._x, room._z, room._hover, room._side) == (WIDTH // 2, DEPTH // 2, 0, 0)
        await press(app, "a")
        assert (WIDTH // 2, DEPTH // 2, 0) in room._blocks
    run(go())
