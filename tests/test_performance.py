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


def test_no_subsecond_timers_while_idle():
    """An idle Purple must not wake the CPU several times a second: no blink,
    no reaper, no fast poll. Dev-mode screenshot triggers (0.1s/0.2s) are
    exempt: they never ship enabled."""
    from purple_tui.harness import make_app, run

    async def scenario():
        app = make_app()
        await asyncio.sleep(0.3)
        offenders = [(p, name) for p, name in app.timers.intervals() if p < 1.0 and p not in (0.1, 0.2)]
        assert offenders == [], f"sub-second timers while idle: {offenders}"
    run(scenario())


def test_typing_and_repainting_stays_cheap():
    """Each keystroke redraws the whole screen from cached text; eight of them,
    frames included, must stay well inside a keystroke's worth of time even on
    a 20x slower laptop."""
    from purple_tui.harness import make_app, press, run

    async def scenario():
        app = make_app()
        for c in "warm":
            await press(app, c)
        app._draw()
        start = time.perf_counter()
        for c in "dinosaur":
            await press(app, c)
            app._draw()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.25, f"8 keystrokes with repaints took {elapsed * 1000:.0f} ms"
    run(scenario())
