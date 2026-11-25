"""Blocks' caches against painting from scratch: the kept composite, the patch split at the cursor's row, the
cursor's kept pictures, the falls' partial repaints and a moving view's kept shape must each show exactly what a
fresh paint shows, whatever was typed, moved, lifted, knocked, turned or resized on the way there."""

import random

import pygame
import pytest

from purplecomputer import palette as P
from purplecomputer.harness import make_app, press, run
from purplecomputer.palette import get_key_color
from purplecomputer.rooms import blocks_room
from purplecomputer.rooms.blocks_room import DEPTH, HEIGHT, HOVER, WIDTH
from purplecomputer.rooms.blocks_view import REST_PITCH, Camera, Painter


@pytest.fixture
def clock(monkeypatch):
    """Blocks' clock, frozen until a test moves it, so animations show the same frame both ways."""
    now = [1000.0]
    monkeypatch.setattr(blocks_room.time, "monotonic", lambda: now[0])
    return now


def _blocks(blocks=None):
    app = make_app()
    app.action_switch_room("blocks")
    room = app.rooms["blocks"]
    if blocks:
        room._blocks = dict(blocks)
        room._changed()
    return app, room


def _build(n, seed, gaps=True) -> dict:
    """n blocks in towers of a few colors, some floating over gaps."""
    r, out = random.Random(seed), {}
    while len(out) < n:
        x, z = r.randrange(WIDTH), r.randrange(DEPTH)
        y = r.randrange(HEIGHT) if gaps and r.random() < 0.2 else sum((x, z, h) in out for h in range(HEIGHT))
        if y < HEIGHT:
            out[(x, z, y)] = get_key_color(r.choice("asdf"))
    return out


def _screen(app) -> bytes:
    return pygame.image.tobytes(app.g.surface, "RGB")


def _land(room):
    for pos in list(room._falls):
        room._falls[pos] = (0.0, room._falls[pos][1])
    if room._falls:
        room._fall_tick()


def _from_scratch(app, room) -> bytes:
    """The screen with every Blocks cache dropped first."""
    room._scene = room._painter = room._built = None
    room._smoothed, room._split_at = {}, None
    app._draw()
    return _screen(app)


def _matches_scratch(app, room, why=""):
    app._draw()
    kept, kept_layer = _screen(app), pygame.image.tobytes(room._composed, "RGB") if room._moving() is None else None
    if kept_layer is None:          # moving: a frame of the floor's picture alone matches the whole screen's
        app.g.surface.fill((0, 0, 0), room._area)
        room._move_patch()
        assert _screen(app) == kept, why
    assert kept == _from_scratch(app, room), why
    if kept_layer is not None:
        assert kept_layer == pygame.image.tobytes(room._composed, "RGB"), why


STEPS = ["a", "s", "d", "space", "backspace", "left", "right", "up", "down", "lift", "sink", "enter_hold",
         "turn", "color", "wait", "wait_long"]


async def _step(app, room, clock, step):
    if step in ("lift", "sink"):
        await press(app, "up" if step == "lift" else "down", shift_held=True)
    elif step == "enter_hold":
        room._to_ground()
    elif step == "turn":
        room.turn()
        room._look = list(room._goal)
    elif step == "color":
        room.set_brush_color(get_key_color(random.choice("qwer")), "q")
    elif step == "wait":
        clock[0] += 0.07
    elif step == "wait_long":
        clock[0] += 3.0
    else:
        await press(app, step)


@pytest.mark.parametrize("seed", range(6))
def test_a_long_walk_of_keys_always_shows_what_a_fresh_paint_shows(clock, seed):
    """Long chains of kept state, checked now and then: moves across rows and into walls, blocks falling and
    landing, the lifted floor sliding and fading, knocks, turns and brush colors."""
    async def go():
        app, room = _blocks(_build(250, seed))
        r = random.Random(seed)
        for i in range(90):
            step = r.choice(STEPS)
            await _step(app, room, clock, step)
            if r.random() < 0.6:
                _land(room)
            if r.random() < 0.25:
                _land(room)
                _matches_scratch(app, room, f"step {i}: {step}")
            else:
                app._draw()
        _land(room)
        _matches_scratch(app, room, "end")
    run(go())


def test_every_row_and_every_wall_matches_a_fresh_paint(clock):
    """The cursor on the front row (nothing in front of it), the back row (everything), and each between,
    behind a tall wall, on every side."""
    async def go():
        wall = {(x, 6, y): get_key_color("a") for x in range(WIDTH) for y in range(5)}
        app, room = _blocks({**wall, **_build(120, 9)})
        for side in range(4):
            for z in range(DEPTH):
                room._x, room._z = room._world(side % WIDTH, z)
                room._next = None
                _matches_scratch(app, room, f"side {side} row {z}")
            room.turn()
            room._look = list(room._goal)
    run(go())


def test_up_and_down_then_back_leave_the_screen_as_it_was(clock):
    async def go():
        app, room = _blocks(_build(400, 4))
        room._x, room._z = 7, 8
        app._draw()
        before = _screen(app)
        for d in ("up", "up", "down", "down", "left", "right"):
            await press(app, d)
            app._draw()
        assert _screen(app) == before
    run(go())


def test_looking_around_off_a_side_and_back_matches_a_fresh_paint(clock):
    async def go():
        app, room = _blocks(_build(300, 5))
        for direction in ("left", "up", "up", "right", "right", "down"):
            room.look_around(direction)
            room._look = list(room._goal)
            _matches_scratch(app, room, direction)
        room.face_front()
        room._look = list(room._goal)
        _matches_scratch(app, room, "front")
    run(go())


def test_a_full_tower_an_empty_floor_and_the_corners_match_a_fresh_paint(clock):
    async def go():
        app, room = _blocks()
        for x, z in ((0, 0), (WIDTH - 1, 0), (0, DEPTH - 1), (WIDTH - 1, DEPTH - 1)):
            room._x, room._z = x, z
            _matches_scratch(app, room, f"empty {x},{z}")
            for _ in range(HEIGHT):
                await press(app, "a")
            _land(room)
            _matches_scratch(app, room, f"tower {x},{z}")
            for _ in range(HEIGHT + 2):
                await press(app, "backspace")
            _matches_scratch(app, room, f"erased {x},{z}")
    run(go())


def test_a_fall_painted_in_part_matches_a_whole_frame(clock):
    """_fall_patch repaints only around the falls and the cursor: at every moment of a drop, what it leaves on
    screen is a whole frame's picture."""
    async def go():
        app, room = _blocks(_build(300, 6))
        room._x, room._z = 8, 3
        app._draw()
        for _ in range(3):
            await press(app, "a")
        app._draw()
        assert room._falls
        while room._falls:
            clock[0] += 0.03
            if any(clock[0] - since >= blocks_room.DROP_S for since, _ in room._falls.values()):
                break
            room._fall_patch()
            part = _screen(app)
            app._draw()
            assert part == _screen(app), clock[0]
    run(go())


def test_a_moving_frame_from_the_kept_shape_matches_one_worked_out_fresh(clock):
    async def go():
        app, room = _blocks(_build(300, 7))
        r = random.Random(7)
        for _ in range(12):
            await _step(app, room, clock, r.choice(["a", "backspace", "left", "up"]))
            _land(room)
            room._look = [r.uniform(-80, 80), r.uniform(20, 70), r.uniform(0, 40)]
            _matches_scratch(app, room, tuple(room._look))
            room._look = list(room._goal)
    run(go())


def test_a_new_size_paints_fresh_layers_and_a_turn_keeps_its_own(clock):
    async def go():
        app, room = _blocks(_build(200, 8))
        app._draw()
        layer = room._composed
        room.turn()
        room._look = list(room._goal)
        app._draw()
        assert room._composed is layer          # same size: the same surfaces, painted over
        full = app.content_rect(app._viewport_rect())
        small = full.inflate(-full.w // 3, -full.h // 3)
        for rect in (small, full):
            room.draw(app.g, rect)
            kept = pygame.image.tobytes(room._composed, "RGB")
            room._scene = None
            room.draw(app.g, rect)
            assert kept == pygame.image.tobytes(room._composed, "RGB")
        assert room._composed is not layer and room._composed.get_size() == layer.get_size()
        _matches_scratch(app, room, "back to full size")
    run(go())


def test_the_cursor_s_kept_pictures_redraw_when_anything_they_show_changes(monkeypatch):
    async def go():
        app, room = _blocks()
        app._draw()
        painter, drawn = room._painter, []
        surf = pygame.Surface((400, 400), pygame.SRCALPHA)
        rect = pygame.Rect(10, 10, 50, 50)

        def paint(keep, r=rect, p=painter):
            room._smooth(surf, p, r, lambda layer, big: drawn.append(1), keep=keep)
            return len(drawn)
        assert paint(("hover", 1, 2)) == 1
        assert paint(("hover", 1, 2)) == 1                       # nothing changed: kept
        assert paint(("hover", 1, 3)) == 2                       # what it shows
        assert paint(("hover", 1, 3), r=rect.move(1, 0)) == 3    # where
        assert paint(("hover", 1, 3), p=painter.on(Camera(0.3, REST_PITCH, 400, 400))) == 4   # the camera
        assert paint(("hover", 1, 3)) == 5
        monkeypatch.setattr(P, "TEXT", "#123456")
        assert paint(("hover", 1, 3)) == 6                       # the theme
        assert paint(("keys", 1, 3)) == 7 and paint(("hover", 1, 3)) == 7    # kinds keep their own
        assert paint(None) == 8 and paint(None) == 9             # without keep, always drawn
    run(go())


def test_the_bubble_follows_the_brush_color_and_its_blink(clock):
    async def go():
        app, room = _blocks()
        app._draw()
        shown = _screen(app)
        room.set_brush_color(get_key_color("q"), "q")
        app._draw()
        assert _screen(app) != shown
        room.set_brush_color(get_key_color("a"), "a")
        app._draw()
        bright = _screen(app)
        app.g.dirty = False
        app.g.blink(0)
        assert _screen(app) != bright      # the blink's bubble is drawn too, not the bright one kept
        app._draw()
        assert _screen(app) == bright
    run(go())


@pytest.mark.parametrize("seed", range(4))
def test_painter_finds_what_touches_a_rect_as_a_check_of_every_item_would(seed):
    r = random.Random(seed)
    cam = Camera(r.uniform(-0.8, 0.8), r.uniform(0.3, 1.2), 900, 600, top=HOVER + 1, fit=0.2)
    painter = Painter(cam, _build(500, seed), row=r.randrange(DEPTH))
    for _ in range(40):
        rect = pygame.Rect(r.randrange(-50, 900), r.randrange(-50, 600), r.randrange(0, 300), r.randrange(0, 300))
        start = r.randrange(len(painter.items))
        assert painter.touching(rect, start) == [i for i in painter.items[start:] if painter._rect(i).colliderect(rect)]
    zoomed = painter.on(cam.zoomed(3, (100, 50)))      # its rects are in the zoomed camera's pixels, not shared
    rect = pygame.Rect(0, 0, 400, 400)
    assert zoomed.touching(rect) == [i for i in zoomed.items if zoomed._rect(i).colliderect(rect)]
    assert painter.on_row(3)._rects is painter._rects and zoomed._rects is not painter._rects


def test_painting_only_the_rows_in_front_matches_painting_them_one_by_one():
    cam = Camera(0.2, REST_PITCH, 900, 600, top=HOVER + 1, fit=0.2)
    for row in (0, 5, DEPTH - 1, DEPTH):
        painter = Painter(cam, _build(400, row), row=row)
        clip = pygame.Rect(200, 50, 300, 500)
        a, b = (pygame.Surface((900, 600), pygame.SRCALPHA) for _ in range(2))
        painter.paint_part(a, clip, in_front=True)
        painter.paint(b, [i for i in painter.items if i[2][1] < row], clip)
        assert pygame.image.tobytes(a, "RGBA") == pygame.image.tobytes(b, "RGBA"), row


def test_the_rows_behind_the_cursor_always_paint_before_those_in_front():
    """What lets the composite stand in for the rows behind the cursor: at any resting view, every item of
    a row comes before every item of a nearer row."""
    blocks = _build(600, 11)
    for yaw in (-45, -20, 0, 30, 45):
        for tilt in (15, 30, 60, 75):
            cam = Camera(*(v * 3.14159 / 180 for v in (yaw, tilt)), 900, 600, top=HOVER + 1, fit=abs(yaw) * 3.14159 / 180)
            rows = [i[2][1] for i in Painter(cam, blocks).items]
            assert rows == sorted(rows, reverse=True), (yaw, tilt)


def test_a_column_lists_its_heights_bottom_up_gaps_and_all():
    async def go():
        app, room = _blocks({(3, 4, 0): "#ff0000", (3, 4, 5): "#00ff00", (3, 4, 11): "#0000ff", (4, 4, 2): "#ffffff"})
        room._x, room._z = 3, 4
        assert room._column() == [0, 5, 11]
        room._x = 5
        assert room._column() == []
    run(go())


def test_working_out_a_build_s_shape_does_not_count_against_a_turn_s_frame(clock, monkeypatch):
    shape = blocks_room.shape

    def slow_shape(blocks):
        clock[0] += 1.0
        return shape(blocks)
    monkeypatch.setattr(blocks_room, "shape", slow_shape)

    async def go():
        app, room = _blocks(_build(50, 2))
        room._aim(yaw=90)
        room._look[0] = 45.0
        app._draw()
        assert room._moving() is not None and room._turn_detail_limit == blocks_room.TURN_DETAIL_BLOCKS
    run(go())
