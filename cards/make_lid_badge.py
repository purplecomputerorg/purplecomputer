#!/usr/bin/env python3
"""Lid badge: "this computer belongs to", with a stock label for the name.

One of these gets printed in quantity and stuck on the laptop lid. The middle
of the card is a white window cut to the footprint of a stock Avery 5160
address label (2.625" x 1", rounded corners, also sold as 8160/18660/5960,
30 per sheet). A label goes on the window and the kid writes their name on it,
so nothing has to be personalized at print time.

A hairline mount is drawn just outside the window, so the label lands inside a
frame and a slightly crooked placement still reads as deliberate.

Layouts, all the same card and the same window:

  crown   dark band across the top, Nunito caps, bot on the left
  hero    no band: Sora caps in two lines, big bot to the right
  duo     band split down the middle in the two brand purples
  night   the whole card in ink, white window the only bright thing
  serif   Spectral italic in sentence case, the quietest of the set
  ticket  tracked Figtree caps between two short rules
  footer  band across the bottom instead, window sitting high

Card is 3.5" x 2.25" (standard name-badge size), kiss-cut, 0.125" bleed.
Print on white stock: the window is unprinted material, not white ink.

Output: cards/lid-badge-<variant>.svg and .pdf (Inkscape).
"""

from badge_kit import (
    BORDER, FIELD, FIGTREE, INK, INK_DEEP, NUNITO, ON_FIELD, ON_INK, RULE,
    SORA_SB, SORA_XB, SPECTRAL, STICKER_H_IN, STICKER_W_IN, WHITE,
    bot, cli, rect, rule_line, text,
)

# The stock label the window is cut for. Measured from the label itself, not
# from Avery's marketing copy; the corner radius is the part worth checking
# against a real sheet before a long print run.
LABEL_W_IN = 2.625
LABEL_H_IN = 1.0
LABEL_R_IN = 0.0625
LABEL_NAME = "Avery 5160/8160/18660/5960 (2.625\" x 1\", rounded, 30-up)"

# Window is the label's exact footprint. Raise INSET to print it slightly
# smaller than the label, so the label edge lands on purple and a crooked
# placement leaves no white sliver down one side.
LABEL_INSET_IN = 0.0
# Gap from the window to the hairline mount around it.
MOUNT_GAP_IN = 0.055

LABEL_X_IN = (STICKER_W_IN - LABEL_W_IN) / 2

BELONGS = "THIS COMPUTER BELONGS TO"


def window(y_in, mount=True) -> str:
    """White label window at y_in, with its hairline mount just outside."""
    d = LABEL_INSET_IN
    g = MOUNT_GAP_IN
    parts = []
    if mount:
        parts.append(rect(LABEL_X_IN - g, y_in - g,
                          LABEL_W_IN + 2 * g, LABEL_H_IN + 2 * g,
                          LABEL_R_IN + g, fill="none", stroke=BORDER,
                          stroke_width=1.1))
    parts.append(rect(LABEL_X_IN + d, y_in + d,
                      LABEL_W_IN - 2 * d, LABEL_H_IN - 2 * d,
                      LABEL_R_IN, fill=WHITE))
    return "".join(parts)


# ---------- layouts ----------

def layout_crown() -> str:
    """Dark band across the top, Nunito caps, bot on the left."""
    return "".join([
        rect(0, 0, STICKER_W_IN, 0.56, fill=INK),
        bot(0.40, 0.27, 0.40, ON_INK),
        text(BELONGS, 1.95, 0.27, 12.5, weight=800, fill=FIELD, tracking=1.7),
        window(0.88),
    ])


def layout_hero() -> str:
    """No band: two lines of Sora caps at the left, big bot at the right."""
    return "".join([
        text("THIS COMPUTER", LABEL_X_IN, 0.32, 13.5, weight=800, fill=INK_DEEP,
             tracking=0.4, font=SORA_XB, anchor="start"),
        text("BELONGS TO", LABEL_X_IN, 0.58, 13.5, weight=800, fill=INK_DEEP,
             tracking=0.4, font=SORA_XB, anchor="start"),
        bot(3.02, 0.45, 0.64),
        window(0.90),
    ])


def layout_duo() -> str:
    """Band split down the middle in the two brand purples, a half-line each."""
    half = STICKER_W_IN / 2
    return "".join([
        rect(0, 0, half, 0.58, fill=INK),
        rect(half, 0, half, 0.58, fill=RULE),
        bot(0.30, 0.28, 0.38, ON_INK),
        text("THIS COMPUTER", 1.04, 0.28, 11, weight=800, fill=FIELD, tracking=1.3),
        text("BELONGS TO", 2.62, 0.28, 11, weight=800, fill=FIELD, tracking=1.3),
        window(0.90),
    ])


def layout_serif() -> str:
    """Spectral italic, sentence case, the quietest of the set."""
    return "".join([
        text("This computer belongs to", 1.75, 0.38, 19, weight=500,
             font=SPECTRAL, italic=True),
        window(0.68),
        bot(1.75, 1.99, 0.34),
    ])


def layout_ticket() -> str:
    """Tracked Figtree caps between two short rules."""
    return "".join([
        rule_line(0.36, 0.66, 0.38, 1.4, BORDER),
        text(BELONGS, 1.75, 0.38, 10, weight=500, tracking=2.2, font=FIGTREE),
        rule_line(2.84, 3.14, 0.38, 1.4, BORDER),
        window(0.70),
        bot(1.75, 1.99, 0.32),
    ])


def layout_footer() -> str:
    """Band across the bottom instead, window sitting high."""
    return "".join([
        window(0.28),
        rect(0, 1.66, STICKER_W_IN, STICKER_H_IN - 1.66, fill=INK),
        text(BELONGS, 1.62, 1.955, 11, weight=600, fill=FIELD,
             tracking=1.1, font=SORA_SB),
        bot(3.14, 1.955, 0.42, ON_INK),
    ])


def layout_night() -> str:
    """The whole card in ink, so the white window is the only bright thing."""
    return "".join([
        rect(0, 0, STICKER_W_IN, STICKER_H_IN, fill=INK),
        text(BELONGS, 1.75, 0.38, 12.5, weight=800, fill=FIELD, tracking=1.7),
        window(0.68, mount=False),
        bot(1.75, 1.99, 0.34, ON_INK),
    ])


LAYOUTS = {
    "crown":  layout_crown,
    "night":  layout_night,
    "hero":   layout_hero,
    "duo":    layout_duo,
    "serif":  layout_serif,
    "ticket": layout_ticket,
    "footer": layout_footer,
}


if __name__ == "__main__":
    cli(LAYOUTS, "lid-badge", doc=__doc__,
        note=f'label  : {LABEL_NAME}, mount gap {MOUNT_GAP_IN}"')
