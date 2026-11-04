#!/usr/bin/env python3
"""Name badge written straight onto the sticker: "This is ______'s computer".

Same card as the lid badge (3.5" x 2.25", kiss-cut, 0.125" bleed), but the
name goes on the sticker itself: a ruled blank to fill in with a marker, no
stock label involved. For the version that carries an Avery label instead,
see make_lid_badge.py.

  sentence  stacked and centered, thin border, bot underneath
  stagger   left-aligned and hand-set, the name line biggest
  age       plus a second short blank for how old they are

Output: cards/name-badge-<variant>.svg and .pdf (Inkscape).
"""

from badge_kit import (
    BORDER, INK_DEEP, RULE, STICKER_H_IN, STICKER_W_IN,
    bot, cli, rect, rule_line, text,
)


def layout_sentence() -> str:
    """The sentence stacked down the badge, thin border, bot underneath."""
    return "".join([
        rect(0.1, 0.1, STICKER_W_IN - 0.2, STICKER_H_IN - 0.2, 0.1,
             fill="none", stroke=BORDER, stroke_width=1.5),
        text("This is", 1.75, 0.46, 19, weight=700),
        rule_line(0.62, 2.88, 1.06, 2.6),
        text("&#8217;s computer", 1.75, 1.38, 19, weight=700),
        bot(1.75, 1.84, 0.42),
    ])


def layout_stagger() -> str:
    """Same sentence, left-aligned and hand-set, the name line biggest."""
    return "".join([
        text("This is", 0.42, 0.5, 16, weight=700, anchor="start"),
        rule_line(0.40, 2.72, 1.2, 3.0),
        text("&#8217;s computer", 0.56, 1.7, 24, weight=800, fill=INK_DEEP,
             anchor="start"),
        bot(3.0, 0.62, 0.74),
    ])


def layout_age() -> str:
    """Sentence plus a second blank for how old they are."""
    return "".join([
        text("This is", 1.75, 0.48, 18, weight=700),
        rule_line(0.5, 3.0, 1.08, 2.6),
        text("&#8217;s computer", 0.42, 1.52, 18, weight=700, anchor="start"),
        text("age", 2.56, 1.52, 14, weight=700, fill=RULE, anchor="start"),
        rule_line(2.84, 3.2, 1.59, 2.2),
        bot(1.75, 2.0, 0.30),
    ])


LAYOUTS = {
    "sentence": layout_sentence,
    "stagger":  layout_stagger,
    "age":      layout_age,
}


if __name__ == "__main__":
    cli(LAYOUTS, "name-badge", doc=__doc__)
