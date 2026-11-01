"""Noto Color Emoji as plain PNG pictures and a map of which pictures each emoji is made of, for a
browser: no emoji font format draws in every browser, and Pyodide's pygame can't draw this one.

build() runs in scripts/studio_bundle.py; EmojiPictures draws a run the way pygame draws the font
itself on Purple, and studio/src/emoji.ts shows the same pictures on Studio's pages.
"""

import json
from pathlib import Path

from .gfx import EMOJI_NATIVE_PX, _ONE_EMOJI_RE

VS16 = "️"


def build(font_path: Path, out: Path, sequences: list[str], version: str) -> None:
    """out/map.json and out/<version>/<glyph>.png. Each emoji in sequences, and every character the
    font maps, becomes the glyphs HarfBuzz shapes it to, as SDL_ttf does on Purple."""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont

    pygame.font.init()
    sized = pygame.font.Font(str(font_path), EMOJI_NATIVE_PX)
    font = TTFont(str(font_path), lazy=True)
    order, strike, upem = font.getGlyphOrder(), font["CBDT"].strikeData[0], font["head"].unitsPerEm
    shaper = hb.Font(hb.Face(font_path.read_bytes()))

    def shape(text: str) -> list[int]:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(shaper, buf, {})
        return [g.codepoint for g in buf.glyph_infos]

    texts = sorted({chr(c) for c in font.getBestCmap()} | set(sequences))
    seqs = {t: shape(t) for t in texts}
    pictures = out / version
    pictures.mkdir(parents=True, exist_ok=True)
    glyphs = {}
    for gid in sorted({0} | {g for gs in seqs.values() for g in gs}):  # 0: what an unknown character shapes to
        bitmap = strike.get(order[gid])
        if bitmap is None:  # SDL_ttf: no bitmap, so the outline font's advance, floored
            glyphs[gid] = [font["hmtx"][order[gid]][0] * EMOJI_NATIVE_PX // upem]
            continue
        (pictures / f"{gid}.png").write_bytes(bitmap.imageData)
        glyphs[gid] = [bitmap.metrics.Advance, bitmap.metrics.BearingX, bitmap.metrics.BearingY]
    (out / "map.json").write_text(json.dumps({
        "version": version, "ascent": sized.get_ascent(), "height": sized.get_height(),
        "pattern": _ONE_EMOJI_RE.pattern, "glyphs": glyphs, "seqs": seqs,
    }, ensure_ascii=False, separators=(",", ":")))


class EmojiPictures:
    def __init__(self, root: Path):
        m = json.loads((root / "map.json").read_text())
        self.dir = root / m["version"]
        self.ascent, self.height, self.seqs = m["ascent"], m["height"], m["seqs"]
        self.glyphs = {int(k): v for k, v in m["glyphs"].items()}
        self._loaded = {}

    def glyphs_for(self, text: str) -> list[int]:
        """A run's glyphs, an emoji at a time: one HarfBuzz shaped, else the same without VS16 (both
        forms are listed for every emoji), else character by character."""
        out, pos = [], 0
        for m in _ONE_EMOJI_RE.finditer(text):
            out += self._chars(text[pos:m.start()])
            out += self.seqs.get(m[0]) or self.seqs.get(m[0].replace(VS16, "")) or self._chars(m[0])
            pos = m.end()
        return out + self._chars(text[pos:])

    def _chars(self, text: str) -> list[int]:
        return [g for ch in text for g in self.seqs.get(ch, [0])]

    def render(self, text: str):
        """The run as pygame renders it in Noto at its one bitmap size: each picture on a shared baseline."""
        import pygame

        gids = self.glyphs_for(text)
        out = pygame.Surface((max(1, sum(self.glyphs[g][0] for g in gids)), self.height), pygame.SRCALPHA)
        x = 0
        for g in gids:
            advance, *bearing = self.glyphs[g]
            if bearing:
                out.blit(self._picture(g), (x + bearing[0], self.ascent - bearing[1]))
            x += advance
        return out

    def _picture(self, gid: int):
        import pygame

        if gid not in self._loaded:
            self._loaded[gid] = pygame.image.load(str(self.dir / f"{gid}.png")).convert_alpha()
        return self._loaded[gid]
