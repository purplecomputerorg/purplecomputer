"""The Play room's real answers for the cards: each example the .typ files name with ex("..."), says("...")
or result("...") goes through the room's own evaluator and is drawn by its own print code onto
white, so a card always shows what Purple shows."""

import asyncio
import re
from pathlib import Path

EXAMPLE = re.compile(r'\b(?:ex|says|result)\("((?:[^"\\]|\\.)*)"')
SIZE = (2732, 1536)  # twice the default screen, so answers stay sharp in print
EM_PT = 5.0          # one screen em on the card; theme.typ's result() trusts the PNG's dpi for this
ANSWER_EMS = 1.7     # one size for every answer: the screen gives emoji-only answers 2 and the rest 1.3
ABACUS_SCALE = 1.1    # the abacus keeps its own fixed size, small beside the answers above
CARD_EMS = 33       # answers wrap at the card's answer column, as they would on a screen that narrow
INK = ("#352a4a", "#6b5e7d", (255, 255, 255))  # theme.typ ink, ink-med, white panels
PAPER_LIGHTNESS = 0.64  # the abacus pastels are picked for the dark screen and wash out on white


def for_paper(hex_color: str) -> str:
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(h, l * PAPER_LIGHTNESS, s))


def slug(code: str) -> str:
    """Matches result() in theme.typ."""
    return re.sub(r"[^a-z0-9]+", "-", code.lower())


def examples(typ_files) -> list:
    codes = sorted({m.group(1) for f in typ_files for m in EXAMPLE.finditer(Path(f).read_text())})
    slugs = [slug(c) for c in codes]
    if len(set(slugs)) != len(slugs):
        raise SystemExit(f"two examples share a file name: {codes}")
    return codes


async def _render(codes: list, out: Path) -> None:
    import pygame
    from purple_tui.canvas.harness import make_app
    from purple_tui.canvas.rooms import play_room
    from purple_tui.canvas.rooms.play_room import answer_parts
    from purple_tui.play_eval import SimpleEvaluator
    SimpleEvaluator.ABACUS_COLORS = [for_paper(c) for c in SimpleEvaluator.ABACUS_COLORS]
    play_room.abacus_group_gap = lambda g: 0  # the screen's comma gap reads as a glitch on one small card abacus

    app = make_app(size=SIZE, room="play")
    room, g = app.room, app.g
    room._answer_px = lambda g, e: g.em(ANSWER_EMS)
    width = g.em(CARD_EMS)
    dpi = 72 * g.em(1) / EM_PT
    for code in codes:
        room.clear()
        room._submit_line(code, allow_speak=False)
        e = room.history[-1]
        s = pygame.Surface((max(width, room._entry_width(g, e)), room._entry_height(g, e, width)))
        s.fill(INK[2])
        with g.drawing_on(s):
            room._draw_entry(g, e, 0, 0, s.get_width(), INK)
        abacus = any(isinstance(p, tuple) for p in answer_parts(e.markup))
        _save(s.subsurface(_ink_rect(s)), out / f"{slug(code)}.png", dpi / (ABACUS_SCALE if abacus else 1))


def _ink_rect(s):
    """The drawn part: everything that isn't the white ground."""
    import pygame
    mask = pygame.mask.from_threshold(s, (255, 255, 255), (1, 1, 1, 255))
    mask.invert()
    rects = mask.get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else s.get_rect()


def _save(s, path: Path, dpi: float) -> None:
    import pygame
    from PIL import Image
    Image.frombytes("RGB", s.get_size(), pygame.image.tobytes(s, "RGB")).save(path, dpi=(dpi, dpi))


def render(typ_files, out: Path) -> None:
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    asyncio.run(_render(examples(typ_files), out))
