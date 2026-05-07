"""Guard that nerd-font icons fit their containing widgets at 2 cells each.

Rich treats PUA glyphs as 1 cell by default, but we patch it (see
purple_tui/__init__.py) to 2 cells to match how JetBrainsMono Nerd Font
actually paints them. Widget widths must agree, or icons wrap or push
content sideways. This test pins that math so a future copy edit (longer
room name, extra icon) or a CSS width tweak fails loudly here instead of
on a real laptop.
"""

import os

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import purple_tui  # noqa: F401  -- triggers the PUA cell-width patch
from rich.cells import cell_len

from purple_tui.constants import (
    ICON_CHAT, ICON_MUSIC, ICON_PALETTE,
    ICON_VOLUME_HIGH, ICON_BROOM, ICON_CODE, ICON_ROBOT,
    VIEWPORT_WIDTH, display_len,
)


def test_pua_patch_active():
    """If this fails, the cell-width patch silently no-opped and every
    other assertion below would be measuring the wrong thing."""
    assert cell_len(ICON_MUSIC) == 2
    assert cell_len(ICON_CHAT) == 2


# (icon, label, widget_total_width, border_cells, padding_cells_each_side)
ROOM_OPTION_CASES = [
    (ICON_CHAT, "Play", 18, 2, 1),
    (ICON_MUSIC, "Music", 18, 2, 1),
    (ICON_PALETTE, "Art", 18, 2, 1),
]


def test_room_option_icons_fit():
    """RoomOption renders `icon  label  icon` — must fit inside the
    border+padding budget so the right-hand icon doesn't wrap."""
    for icon, label, width, border, pad in ROOM_OPTION_CASES:
        inner = width - border - pad * 2
        line = f"{icon}  {label}  {icon}"
        assert cell_len(line) <= inner, (
            f"RoomOption {label!r} content is {cell_len(line)} cells, "
            f"only {inner} available (width={width})"
        )


EXTRA_OPTION_CASES = [
    (ICON_VOLUME_HIGH, "Volume", 25, 2, 0),
    (ICON_BROOM, "Clear Rooms", 25, 2, 0),
    (ICON_CODE, "Open Code", 52, 2, 0),
    (ICON_CODE, "Close Code", 52, 2, 0),
]


def test_extra_option_icons_fit():
    """ExtraOption renders the same `icon  label  icon` shape."""
    for icon, label, width, border, pad in EXTRA_OPTION_CASES:
        inner = width - border - pad * 2
        line = f"{icon}  {label}  {icon}"
        assert cell_len(line) <= inner, (
            f"ExtraOption {label!r} content is {cell_len(line)} cells, "
            f"only {inner} available (width={width})"
        )


ROOM_BADGE_CASES = [
    (ICON_CHAT, "Play", 12, 2, 1),
    (ICON_MUSIC, "Music", 12, 2, 1),
    (ICON_PALETTE, "Art", 12, 2, 1),
]


def test_room_badge_icons_fit():
    """RoomBadge in the bottom indicator renders `icon label`."""
    for icon, label, width, border, pad in ROOM_BADGE_CASES:
        inner = width - border - pad * 2
        line = f"{icon} {label}"
        assert cell_len(line) <= inner, (
            f"RoomBadge {label!r} content is {cell_len(line)} cells, "
            f"only {inner} available (width={width})"
        )


# Bottom-border subtitle hints used in music/art rooms. Textual reserves
# 6 cells of border + corner + padding inside VIEWPORT_WIDTH for the label.
# A min-1-cell `━` filler sits between left and right when both are set.
SUBTITLE_AVAILABLE = VIEWPORT_WIDTH - 6

SUBTITLE_HINTS = [
    ("idle music looping",      f"{ICON_MUSIC} Hold Enter: record a loop {ICON_MUSIC}",  None),
    ("idle music + code",       f"{ICON_MUSIC} Hold Enter: record a loop {ICON_MUSIC}",  f"{ICON_ROBOT} Hold Space: write code! {ICON_ROBOT}"),
    ("idle art + code",         None,                                                     f"{ICON_ROBOT} Hold Space: write code! {ICON_ROBOT}"),
    ("loop panel open",         f"{ICON_MUSIC} Hold Enter: close looping {ICON_MUSIC}",   None),
    ("code panel open",         None,                                                     f"{ICON_ROBOT} Hold Space: close code {ICON_ROBOT}"),
]


def test_bottom_subtitle_hints_fit():
    """Both single- and dual-hint border subtitles must fit the viewport
    with at least 1 cell of `━` filler between left and right."""
    for name, left, right in SUBTITLE_HINTS:
        used = display_len(left or "") + display_len(right or "")
        gap = 1 if (left and right) else 0
        total = used + gap
        assert total <= SUBTITLE_AVAILABLE, (
            f"subtitle {name!r}: {total} cells used, "
            f"only {SUBTITLE_AVAILABLE} available"
        )
