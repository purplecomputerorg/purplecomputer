"""Holding Tab emits one tab action, so mode toggles flip once, not per repeat."""

from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.keyboard import ControlAction, KeyboardStateMachine


def test_held_tab_emits_one_action():
    sm = KeyboardStateMachine()
    events = [RawKeyEvent(keycode=KeyCode.KEY_TAB, is_down=True, timestamp=100.0)]
    events += [RawKeyEvent(keycode=KeyCode.KEY_TAB, is_down=True, timestamp=100.5 + i * 0.03, is_repeat=True)
               for i in range(10)]
    tabs = [a for e in events for a in sm.process(e) if isinstance(a, ControlAction) and a.action == "tab"]
    assert len(tabs) == 1
