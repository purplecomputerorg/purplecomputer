#!/usr/bin/env python3
"""Precompute singular/plural mappings for Purple's closed vocabulary.

Inflect is ~1.4s of typeguard AST rewriting at import time on dev; 8-12s on
slow laptops. We only need it for a fixed set of words (emoji keys, color
names, ranked words, synonyms). Precompute offline and ship a tiny JSON
lookup instead, so runtime pays zero cost.

Output: purple_tui/plural_forms.json
Schema: {"singular_to_plural": {"cat": "cats", ...},
         "plural_to_singular": {"cats": "cat", ...}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import inflect

REPO = Path(__file__).resolve().parent.parent
EMOJI_JSON = REPO / "packs" / "core-emoji" / "content" / "emoji.json"
SYNONYMS_JSON = REPO / "packs" / "core-emoji" / "content" / "synonyms.json"
RANKINGS_TXT = REPO / "packs" / "core-emoji" / "content" / "rankings.txt"
OUTPUT = REPO / "purple_tui" / "plural_forms.json"


def load_vocabulary() -> set[str]:
    words: set[str] = set()

    with EMOJI_JSON.open() as f:
        words.update(json.load(f).keys())

    with SYNONYMS_JSON.open() as f:
        data = json.load(f)
        words.update(data.keys())
        words.update(data.values())

    with RANKINGS_TXT.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                words.add(line)

    # Colors live in content.py as a hardcoded dict. Import and scrape.
    sys.path.insert(0, str(REPO))
    from purple_tui.content import ContentManager
    cm = ContentManager.__new__(ContentManager)
    cm.emojis = {}
    cm.colors = {}
    cm._load_defaults()
    words.update(cm.colors.keys())

    # Only keep alphabetic words. Emoji keys like ":)" or "<3" would produce
    # nonsense plurals (":)S", "<3S") and have no meaningful singular form.
    return {w.lower() for w in words if w.isalpha()}


def build_tables(words: set[str]) -> dict:
    engine = inflect.engine()
    singular_to_plural: dict[str, str] = {}
    plural_to_singular: dict[str, str] = {}

    for word in sorted(words):
        plural = str(engine.plural(word))
        if plural and plural != word:
            singular_to_plural[word] = plural
            plural_to_singular[plural] = word
        singular = engine.singular_noun(word)
        if singular and singular != word:
            plural_to_singular[word] = str(singular)

    return {
        "singular_to_plural": singular_to_plural,
        "plural_to_singular": plural_to_singular,
    }


def main() -> None:
    words = load_vocabulary()
    tables = build_tables(words)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w") as f:
        json.dump(tables, f, indent=2, sort_keys=True)
    print(
        f"wrote {OUTPUT.relative_to(REPO)}: "
        f"{len(tables['singular_to_plural'])} singular→plural, "
        f"{len(tables['plural_to_singular'])} plural→singular "
        f"from {len(words)} vocabulary words"
    )


if __name__ == "__main__":
    main()
