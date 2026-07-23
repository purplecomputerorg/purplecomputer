"""Performance regression guards.

Purple runs on weak fanless Celerons, so per-keystroke and idle CPU are
product features. These tests pin the two optimizations that fixed the HP
Stream sluggishness (fuzzy vocabulary precompute + idle wakeup removal) and
guard against new busywork creeping in. Comparative assertions use wide
margins so they stay stable across machines.
"""

import asyncio
import os
import time

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import pytest

from purple_tui import fuzzy
from purple_tui.content import ContentManager, pluralize
from purple_tui.constants import REQUIRED_TERMINAL_ROWS


@pytest.fixture(scope="module")
def content():
    cm = ContentManager()
    cm.load_all()
    return cm


# A realistic worst-ish case: a full line of kid typing where the last word
# is a typo, so exact lookups miss and the fuzzy path runs.
TYPING_WORDS = ["i", "love", "the", "big", "red", "dinosuar"]


def _reference_line_validation(cm, words):
    """The pre-optimization cost model: every fuzzy lookup rebuilds the
    pluralized candidate table from scratch (what shipped before)."""
    def rebuild_lookup(word, table):
        forms = {k: k for k in table}
        for k in table:
            forms.setdefault(pluralize(k), k)
        match = fuzzy.fuzzy_match(word, list(forms))
        return table[forms[match]] if match else None

    for word in words:
        if not (cm.exact_emoji(word) or cm.exact_color(word)):
            rebuild_lookup(word, cm.emojis)
            rebuild_lookup(word, cm.colors)


def _current_line_validation(cm, words):
    for word in words:
        cm.is_valid_word(word)


def test_keystroke_validation_beats_percall_rebuild(content):
    """Prove the optimization: validating a line via the shipped path must
    be at least 10x faster than the old rebuild-per-lookup path (measured
    ~100x+; 10x leaves headroom for machine noise)."""
    reps = 30
    _current_line_validation(content, TYPING_WORDS)  # prime caches

    start = time.perf_counter()
    for _ in range(reps):
        _reference_line_validation(content, TYPING_WORDS)
    reference = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(reps):
        _current_line_validation(content, TYPING_WORDS)
    current = time.perf_counter() - start

    assert current < reference / 10, (
        f"line validation {current:.4f}s vs old-path {reference:.4f}s: "
        "the per-keystroke fuzzy path has regressed")


def test_repeat_validation_never_recomputes_fuzzy(content, monkeypatch):
    """The highlighter re-validates every word on every keystroke; after the
    first sighting of a word the memo must answer, not fuzzy_match."""
    calls = {"n": 0}
    real = fuzzy.fuzzy_match

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(fuzzy, "fuzzy_match", counting)
    content._emoji_fuzzy_cache.clear()
    content._color_fuzzy_cache.clear()

    content.is_valid_word("dinosuar")
    first = calls["n"]
    assert first >= 1  # the miss really did run fuzzy

    for _ in range(100):  # 100 more keystrokes re-validating the same word
        content.is_valid_word("dinosuar")
    assert calls["n"] == first, "fuzzy re-ran for a memoized word"


def test_line_validation_absolute_budget(content):
    """Canary: 200 full-line validations (about 200 keystrokes of
    highlighter work) must be far from per-keystroke-visible cost. Budget
    is ~50x looser than measured so it only trips on a real regression."""
    _current_line_validation(content, TYPING_WORDS)
    start = time.perf_counter()
    for _ in range(200):
        _current_line_validation(content, TYPING_WORDS)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"200 line validations took {elapsed:.2f}s"


def _running_timers(app):
    """All unpaused Textual timers in the app, as (interval, owner) pairs."""
    found = []
    for node in [app, *app.screen_stack, *app.query("*")]:
        for timer in getattr(node, "_timers", ()):
            if timer._active.is_set():
                found.append((timer._interval, repr(node)))
    return found


def test_no_subsecond_timers_while_idle():
    """The idle-CPU contract: an idle app must not tick faster than 1s.
    Catches regressions like cursor blink (0.5s repaint), an always-on
    toast reaper, or any new fast poll. Dev-mode-only screenshot/command
    triggers (0.1s/0.2s) are exempt: they never ship enabled."""
    from purple_tui.purple_tui import PurpleApp

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=(146, REQUIRED_TERMINAL_ROWS)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.5)
            await pilot.pause()

            offenders = [
                (interval, owner)
                for interval, owner in _running_timers(app)
                if interval is not None and interval < 1.0
                and interval not in (0.1, 0.2)  # dev-mode triggers
            ]
            assert offenders == [], f"sub-second timers while idle: {offenders}"

            # The caret must not blink (each blink recomposites the screen)
            from purple_tui.code_input import CodeInput
            for inp in app.query(CodeInput):
                assert inp.cursor_blink is False
                blink = getattr(inp, "_blink_timer", None)
                assert blink is None or not blink._active.is_set()

            # The toast reaper must not run with no toasts on screen
            assert app._toast_reaper_timer is None

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
