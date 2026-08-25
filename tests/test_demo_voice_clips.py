"""Demo lines must pre-generate the voice clips the Play room looks up.

Regression: the clip generator evaluated `repeat 3: i love pizza!` as one
line and wrote `repeat_3:_i_love_pizza.wav`, but the room speaks each copy
on its own and looks up `i_love_pizza.wav`. Demo mode has piper disabled,
so the beat recorded silent.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from purple_tui.demo.script import TypeText
from purple_tui.play_eval import (
    SimpleEvaluator, parse_speech_trigger, speakables_for,
)

PROJECT_ROOT = Path(__file__).parent.parent


def _demo_speakables(composition: str, monkeypatch) -> list[str]:
    """Every phrase the app looks a clip up for while playing a composition."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from generate_voice_clips import _collect_all_actions

    monkeypatch.setenv("PURPLE_DEMO_COMPOSITION", composition)
    evaluator = SimpleEvaluator()
    phrases = []
    for action in _collect_all_actions():
        if not isinstance(action, TypeText):
            continue
        speaks, eval_text = parse_speech_trigger(action.text)
        if speaks and eval_text:
            phrases.extend(speakables_for(evaluator, eval_text))
    return phrases


def _generated_phrases(composition: str) -> list[str]:
    """Phrases the clip generator would synthesize, from a fresh interpreter.

    Subprocess because the generator stubs textual/rich into sys.meta_path.
    """
    code = (
        "import json, sys;"
        "sys.path.insert(0, 'scripts');"
        "import generate_voice_clips as g;"
        "print('PHRASES', json.dumps(g.extract_demo_phrases()))"
    )
    env = {**os.environ, "PURPLE_DEMO_COMPOSITION": composition}
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env,
                         capture_output=True, text=True, check=True).stdout
    line = [ln for ln in out.splitlines() if ln.startswith("PHRASES ")][-1]
    return json.loads(line[len("PHRASES "):])


def test_repeat_line_speaks_each_copy():
    speaks, eval_text = parse_speech_trigger("repeat 3: i love pizza!")
    assert speaks
    assert speakables_for(SimpleEvaluator(), eval_text) == ["i love pizza"] * 3


def test_repeat_speakables_stop_at_the_cap():
    assert len(speakables_for(SimpleEvaluator(), "repeat 9: hi")) == 5


def test_everything_demo_generates_every_clip_it_speaks(monkeypatch):
    spoken = set(_demo_speakables("everything.json", monkeypatch))
    generated = set(_generated_phrases("everything.json"))
    assert "i love pizza" in spoken
    assert not spoken - generated
