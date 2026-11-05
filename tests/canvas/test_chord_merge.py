import asyncio
import time

import pytest

from purple_tui.canvas.harness import make_app, run
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.constants import CHORD_HOLD
from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.keyboard import KeyboardStateMachine
from purple_tui.palette import get_key_color

F, V, B = KeyCode.KEY_F, KeyCode.KEY_V, KeyCode.KEY_B
FV = mix_colors_paint([get_key_color("f"), get_key_color("v")])


def _colors(room) -> list:
    if hasattr(room, "_blocks"):
        return list(room._blocks.values())
    return [room._grid[p][2] for p in sorted(room._painted_positions)]


def _play(name, events, settle=0.0):
    """Squares' colors after (seconds, key, down) events, then waiting `settle` seconds."""
    async def go():
        app = make_app()
        app.action_switch_room(name)
        t0 = time.monotonic()
        for at, code, down in events:
            await app._handle_raw_key_event(RawKeyEvent(keycode=code, is_down=down, timestamp=t0 + at))
        await asyncio.sleep(settle)
        return _colors(app.rooms[name])
    return run(go())


def test_chord_wait_counts_from_the_longest_held_key():
    sm = KeyboardStateMachine()
    down = lambda code, t: sm.process(RawKeyEvent(keycode=code, is_down=True, timestamp=t))[0]
    assert down(F, 0.0).chord_wait is None
    assert down(V, 0.1).chord_wait == pytest.approx(CHORD_HOLD - 0.1)
    assert down(B, 2.0).chord_meant
    assert sm.chord_held()
    sm.process(RawKeyEvent(keycode=F, is_down=False, timestamp=2.1))
    assert not sm.chord_held()


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_mashing_keeps_every_square(name):
    events = [(0, F, True), (0.05, V, True), (0.08, F, False), (0.12, V, False)]
    assert len(_play(name, events, settle=CHORD_HOLD + 0.1)) == 2


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_a_key_held_a_while_then_another_mixes_into_one_square(name):
    assert _play(name, [(0, F, True), (1.0, V, True)]) == [FV]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_keys_pressed_together_fold_into_one_square_once_held(name):
    events = [(0, F, True), (0.01, V, True)]
    assert len(_play(name, events)) == 2
    assert _play(name, events, settle=CHORD_HOLD + 0.1) == [FV]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_more_keys_while_holding_mix_into_the_same_square(name):
    colors = _play(name, [(0, F, True), (1.0, V, True), (1.5, B, True)])
    assert colors == [mix_colors_paint([FV, get_key_color("b")])]
