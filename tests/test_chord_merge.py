import random

import pytest

from purplecomputer.harness import make_app, run
from purplecomputer.color_mixing import mix_colors_paint
from purplecomputer.input import KeyCode, RawKeyEvent
from purplecomputer.keyboard import KeyboardStateMachine
from purplecomputer.palette import get_key_color

F, V, B, G = KeyCode.KEY_F, KeyCode.KEY_V, KeyCode.KEY_B, KeyCode.KEY_G
FV = mix_colors_paint([get_key_color("f"), get_key_color("v")])


def _colors(room) -> list:
    if hasattr(room, "_blocks"):
        return list(room._blocks.values())
    return [room._grid[p][2] for p in sorted(room._painted_positions)]


def _play(name, events) -> list:
    """Square count after each (seconds, key, down) event, and the colors at the end."""
    async def go():
        app = make_app()
        app.action_switch_room(name)
        room, counts = app.rooms[name], []
        for at, code, down in events:
            await app._handle_raw_key_event(RawKeyEvent(keycode=code, is_down=down, timestamp=100 + at))
            counts.append(len(_colors(room)))
        return counts, _colors(room)
    return run(go())


def test_a_chord_is_meant_unless_another_key_just_went_down():
    sm = KeyboardStateMachine()
    down = lambda code, t: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=t))[0]
    up = lambda code, t: sm.process(RawKeyEvent(keycode=code, is_down=False, timestamp=t))
    assert not down(F, 0.0).chord_meant
    assert down(V, 0.02).chord_meant
    up(F, 0.05), up(V, 0.06)
    down(G, 1.0), up(G, 1.05)
    down(F, 1.1)
    assert not down(V, 1.15).chord_meant      # G just before: mashing


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_a_quick_tap_of_both_keys_makes_one_mixed_square(name):
    assert _play(name, [(0, F, True), (0.02, V, True), (0.06, F, False), (0.08, V, False)])[1] == [FV]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_a_key_held_a_while_then_another_makes_one_mixed_square(name):
    assert _play(name, [(0, F, True), (1.0, V, True)])[1] == [FV]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_more_keys_while_holding_mix_into_the_same_square(name):
    colors = _play(name, [(0, F, True), (1.0, V, True), (1.5, B, True)])[1]
    assert colors == [mix_colors_paint([FV, get_key_color("b")])]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_mashing_keeps_the_plain_square_before_the_mixed_one(name):
    counts, colors = _play(name, [(0, G, True), (0.04, G, False), (0.08, F, True), (0.12, V, True)])
    assert counts[-1] == 3 and colors[-1] == FV


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_mashing_never_takes_a_square_back(name):
    rng = random.Random(7)
    keys = [KeyCode.KEY_A, KeyCode.KEY_S, KeyCode.KEY_D, F, G, V, B, KeyCode.KEY_R]
    events, t = [], 0.0
    for _ in range(60):
        k = rng.choice(keys)
        events += [(t, k, True), (t + rng.uniform(0.03, 0.15), k, False)]
        t += rng.uniform(0.02, 0.09)
    counts = _play(name, sorted(events, key=lambda e: e[0]))[0]
    assert counts == sorted(counts)
