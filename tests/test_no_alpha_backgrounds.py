"""Guard: no alpha (percentage) background anywhere in the UI CSS.

An alpha background composites whatever is behind a widget/modal through it.
That is a real transparency artifact on old Intel panels and was a real bug:
commit 8fe4ca5 removed a 60% alpha from the modal base. It is distinct from
the FBC/PSR checkerboard, which is a display-engine scanout artifact unrelated
to opacity (see guides/intel-display-tuning.md). Everything is opaque today;
this test locks that in so the transparency class can't silently regress.
"""

import re
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent / "purple_tui"

# `background:` up to the next `;` (so trailing comments can't false-match),
# containing a percentage = Textual alpha syntax, e.g. `background: $primary 60%`.
_ALPHA_BG = re.compile(r"background:[^;\n]*\d+%")


def test_no_alpha_backgrounds():
    hits = []
    for py in sorted(_PKG.rglob("*.py")):
        for lineno, line in enumerate(py.read_text().splitlines(), 1):
            if _ALPHA_BG.search(line):
                hits.append(f"{py.relative_to(_PKG.parent)}:{lineno}: {line.strip()}")
    assert not hits, (
        "Alpha background(s) found; use an opaque color instead:\n" + "\n".join(hits)
    )
