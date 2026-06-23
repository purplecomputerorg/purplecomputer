"""Palm tree pixel art for the Art demo, as a bitmap plus a keystroke generator.

The Art room palette has no green key, so green is made by painting a gold key
then a blue key on the same cell (paint mode mixes over an existing stamp). The
bitmap below uses single-letter codes; LEGEND maps each to the key(s) to press.

build_palm() turns the bitmap into paint keystrokes, positioned absolutely so
the tree lands centered on the canvas with no clipping. Edit BITMAP to reshape
the tree; keep rows within the canvas (~24 tall) and the generator handles the
rest.
"""

from ..script import PressKey, MoveSequence

# Each code -> the color key(s) to stamp. Two keys = stamp first, then stamp the
# second on the same cell so paint mode mixes them (gold + blue = green).
LEGEND = {
    'G': ['g', 'v'],   # mid green   (#77B377)
    'g': ['d', 'x'],   # light green (#B2CB9D)
    'D': ['l', 'b'],   # dark green
    'T': ['l'],        # trunk (olive-brown)
    'b': ['k'],        # trunk highlight
    'B': [';'],        # trunk shadow / coconuts (dark brown)
    'S': ['h'],        # sand
    's': ['f'],        # light sand
}

# '.' = empty (skip). Rows are padded to equal width by build_palm().
BITMAP = """\
............g.............G.............g..............
..........ggG..........GGGG..........Ggg..............
........gg.GGg.......GGGGGGGG.......gGG.gg............
......gggGGGGg....GGGGGGGGGGGG...gGGGGGggg............
....ggGGGGGGGGg..GGGGGGGGGGGGG..gGGGGGGGGGgg..........
...gGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGg.........
..gGGGGGGGGGGGGGGGGGGGDDDGGGGGGGGGGGGGGGGGGGGg........
...ggg..GGGGGGGGGGGGGDDDDDGGGGGGGGGGGGG..ggg.........
........gggG......GGGGDbbDGGGG.....Gggg..............
...................GGBbbBGG........................
.....................bTTb.........................
.....................BTTb..........................
....................BTTb...........................
....................BTT............................
...................BTTb............................
...................BTT.............................
..................BTTb.............................
..................BTT..............................
.................BTTb..............................
.................BTT...............................
..............sSSSSSSSSSss.........................
.........sssSSSSSSSSSSSSSSSSSSsss...................
......ssSSSSSSSSSSSSSSSSSSSSSSSSSSSSss..............
"""


def _row_lines():
    lines = [ln for ln in BITMAP.splitlines() if ln != ""]
    width = max(len(ln) for ln in lines)
    return [ln.ljust(width, '.') for ln in lines], width


def palm_size():
    """(width, height) of the bitmap in cells."""
    lines, width = _row_lines()
    return width, len(lines)


def centered_margins(canvas_width: int, canvas_height: int):
    """(left_margin, top_margin) that centers the palm on the canvas."""
    w, h = palm_size()
    return max(0, (canvas_width - w) // 2), max(0, (canvas_height - h) // 2)


def build_palm(left_margin: int, top_margin: int):
    """Return paint keystrokes that draw the palm with its top-left at the given
    canvas cell. Cursor is moved absolutely (clamp to corner, then offset) before
    each row, so the result is independent of where painting starts."""
    lines, width = _row_lines()
    actions = []
    # Absolute origin: clamp to the top-left corner, then offset to the start.
    clamp = ['left'] * (left_margin + width + 4) + ['up'] * (top_margin + len(lines) + 4)
    actions.append(MoveSequence(directions=clamp, delay_per_step=0.004))
    actions.append(MoveSequence(
        directions=['right'] * left_margin + ['down'] * top_margin,
        delay_per_step=0.004,
    ))
    cur_x = left_margin
    for r, line in enumerate(lines):
        last = max((i for i, c in enumerate(line) if c != '.'), default=-1)
        # Carriage return to the row's left edge, then down one (except row 0).
        back = ['left'] * (cur_x - left_margin)
        down = ['down'] * (1 if r > 0 else 0)
        if back or down:
            actions.append(MoveSequence(directions=back + down, delay_per_step=0.004))
        cur_x = left_margin
        if last < 0:
            continue
        col = 0
        while col <= last:
            ch = line[col]
            if ch == '.':
                run = 0
                while col + run <= last and line[col + run] == '.':
                    run += 1
                actions.append(MoveSequence(directions=['right'] * run, delay_per_step=0.004))
                cur_x += run
                col += run
                continue
            keys = LEGEND[ch]
            if len(keys) == 1:
                actions.append(PressKey(keys[0]))
            else:
                actions.append(PressKey(keys[0]))
                actions.append(MoveSequence(directions=['left'], delay_per_step=0.004))
                actions.append(PressKey(keys[1]))
            cur_x += 1
            col += 1
    return actions
