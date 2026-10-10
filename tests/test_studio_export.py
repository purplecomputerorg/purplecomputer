"""Purple Studio's TypeScript reads studio/src/purple/export.json and checks its synth
port against studio/tests/golden.json. Both are written by scripts/export_studio.py;
this test fails when Purple has changed and the files were not regenerated."""

import json

from scripts.export_studio import EXPORT_PATH, GOLDEN_PATH, build_export, build_golden

STALE = "Purple changed under Studio: run `just studio-fixtures` and commit the result."


def test_export_is_current():
    assert json.loads(EXPORT_PATH.read_text()) == build_export(), STALE


def test_golden_renders_are_current():
    assert json.loads(GOLDEN_PATH.read_text()) == build_golden(), STALE
