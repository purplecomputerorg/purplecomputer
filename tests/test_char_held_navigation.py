"""
Tests for char_held on NavigationAction.

When a character key is held and an arrow key is pressed/repeated,
NavigationAction should carry the held character so doodle mode can
paint continuously (symmetric with holding arrow first then letter).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.input import RawKeyEvent, KeyCode
from purple_tui.keyboard import KeyboardStateMachine, NavigationAction, CharacterAction


def make_event(keycode, is_down=True, timestamp=0.0, is_repeat=False):
    """Helper to create RawKeyEvent."""
    return RawKeyEvent(
        keycode=keycode,
        is_down=is_down,
        timestamp=timestamp,
        is_repeat=is_repeat,
    )


class TestCharHeldOnNavigation:
    """NavigationAction should carry char_held when a character key is held."""

    def test_arrow_without_char_has_no_char_held(self):
        """Pressing arrow with no character held gives char_held=None."""
        sm = KeyboardStateMachine()
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held is None

    def test_hold_char_then_arrow_carries_char_held(self):
        """Hold 'a', then press DOWN: NavigationAction has char_held='a'."""
        sm = KeyboardStateMachine()
        # Press 'a'
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        # Press DOWN (while 'a' still held)
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'a'

    def test_arrow_repeat_carries_char_held(self):
        """Hold 'a', press DOWN, DOWN repeats: repeats still carry char_held."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        # Arrow repeat
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.15, is_repeat=True))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'a'

    def test_char_released_clears_char_held(self):
        """Release 'a', then arrow press has char_held=None."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        sm.process(make_event(KeyCode.KEY_A, is_down=False, timestamp=0.1))
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.2))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held is None

    def test_different_char_replaces_held(self):
        """Press 'a', then 'b': held char becomes 'b'."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        sm.process(make_event(KeyCode.KEY_B, timestamp=0.1))
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.2))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'b'

    def test_release_old_char_keeps_new_char(self):
        """Press 'a', press 'b', release 'a': held char is still 'b'."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        sm.process(make_event(KeyCode.KEY_B, timestamp=0.1))
        sm.process(make_event(KeyCode.KEY_A, is_down=False, timestamp=0.15))
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.2))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'b'

    def test_number_key_held(self):
        """Number keys also populate char_held."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_5, timestamp=0.0))
        actions = sm.process(make_event(KeyCode.KEY_RIGHT, timestamp=0.1))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == '5'

    def test_char_repeat_does_not_clobber_held(self):
        """Character repeat events don't change the held char."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        # 'a' repeats (should not change held char)
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.05, is_repeat=True))
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'a'

    def test_all_arrow_directions(self):
        """char_held works for all four arrow directions."""
        for arrow_key in [KeyCode.KEY_UP, KeyCode.KEY_DOWN, KeyCode.KEY_LEFT, KeyCode.KEY_RIGHT]:
            sm = KeyboardStateMachine()
            sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
            actions = sm.process(make_event(arrow_key, timestamp=0.1))
            nav = [a for a in actions if isinstance(a, NavigationAction)]
            assert len(nav) == 1
            assert nav[0].char_held == 'a', f"Failed for arrow keycode {arrow_key}"


class TestCharHeldSymmetry:
    """The two key orderings (char-first vs arrow-first) should both enable painting."""

    def test_arrow_first_then_char_has_arrow_held(self):
        """Hold arrow first, then press char: CharacterAction has arrow_held."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.0))
        actions = sm.process(make_event(KeyCode.KEY_A, timestamp=0.1))
        chars = [a for a in actions if isinstance(a, CharacterAction)]
        assert len(chars) == 1
        assert chars[0].arrow_held == 'down'

    def test_char_first_then_arrow_has_char_held(self):
        """Hold char first, then press arrow: NavigationAction has char_held."""
        sm = KeyboardStateMachine()
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        actions = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        nav = [a for a in actions if isinstance(a, NavigationAction)]
        assert len(nav) == 1
        assert nav[0].char_held == 'a'

    def test_continuous_arrow_repeats_with_char_held(self):
        """Simulates the exact bug scenario: hold char, press arrow, arrow repeats."""
        sm = KeyboardStateMachine()
        # Hold 'a'
        sm.process(make_event(KeyCode.KEY_A, timestamp=0.0))
        # Press DOWN
        actions1 = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.1))
        # DOWN repeats (OS stopped repeating 'a')
        actions2 = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.15, is_repeat=True))
        actions3 = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.20, is_repeat=True))
        actions4 = sm.process(make_event(KeyCode.KEY_DOWN, timestamp=0.25, is_repeat=True))

        for i, actions in enumerate([actions1, actions2, actions3, actions4]):
            nav = [a for a in actions if isinstance(a, NavigationAction)]
            assert len(nav) == 1
            assert nav[0].char_held == 'a', f"Arrow repeat #{i+1} lost char_held"
