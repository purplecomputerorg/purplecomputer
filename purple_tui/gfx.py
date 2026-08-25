"""Rendering core: one software surface, cached text, color emoji, markup spans.

Everything on screen is drawn through here. Sizes are given in pixels that
callers derive from ``vh`` (percent of screen height) so the layout scales the
same way on a 1024x768 netbook and a 1440x900 MacBook. Text and emoji are
rasterized once per (face, size, string, color) and blitted from a cache, so a
full-screen repaint is a few dozen blits. There is no GPU path on purpose: the
fleet includes machines whose GL drivers lie, and a software frame at these
resolutions costs a couple of milliseconds even on 2006 hardware.

Markup is the small subset of Rich's syntax the rooms already speak:
``[bold]``, ``[dim]``, ``[#rrggbb]``, ``[on #rrggbb]``, combinations like
``[bold #hex on #hex]``, ``[/]`` to pop, and ``\\[`` for a literal bracket.
"""

import os
import re
from collections import OrderedDict
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

FONT_DIR = Path(__file__).parent / "fonts"
FACES = {
    "sans": "NunitoSans-Regular.ttf",
    "sans-bold": "NunitoSans-Bold.ttf",
    "sans-heavy": "NunitoSans-ExtraBold.ttf",
    "mono": "JetBrainsMono-Regular.ttf",
    "mono-bold": "JetBrainsMono-SemiBold.ttf",
    "symbols": "DejaVuSans.ttf",  # fallback for glyphs the faces above lack
}
EMOJI_FONT_PATHS = [
    os.environ.get("PURPLE_EMOJI_FONT", ""),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    str(Path.home() / ".local/share/fonts/NotoColorEmoji.ttf"),
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]
EMOJI_NATIVE_PX = 109  # Noto Color Emoji is a bitmap font with one strike; we scale from it
CACHE_LIMIT = 4096

_EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[©®‼⁉™ℹ↔-↙↩↪⌚⌛⌨⏏"
    "⏩-⏳⏸-⏺Ⓜ▪▫▶◀◻-◾☀-➿"
    "⤴⤵⬅-⬇⬛⬜⭐⭕〰〽㊗㊙"
    "\U0001F000-\U0001FAFF][️⃣\U0001F3FB-\U0001F3FF]*"
    "(?:‍[☀-➿\U0001F000-\U0001FAFF][️\U0001F3FB-\U0001F3FF]*)*)+"
)
_TAG_RE = re.compile(r"\\\[|\[(/?)([^\[\]]*)\]")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

NAMED_COLORS = {
    "red": "#d94a4a", "green": "#5cb85c", "blue": "#4a7fd9", "yellow": "#e8d24a",
    "white": "#ffffff", "black": "#000000", "cyan": "#4ac8d9", "magenta": "#d94ac8",
}


def rgb(color) -> tuple:
    """'#rrggbb' or a tuple -> (r, g, b)."""
    if isinstance(color, str):
        c = NAMED_COLORS.get(color, color).lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return tuple(color[:3])


def hexcolor(color) -> str:
    r, g, b = rgb(color)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(a, b, t: float) -> tuple:
    """Blend color a toward b by t (0 = a, 1 = b)."""
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)


def luminance(color) -> float:
    def ch(v):
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_text(bg) -> str:
    """Black or white, whichever reads better on bg (WCAG)."""
    lum = luminance(bg)
    return "#FFFFFF" if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 else "#000000"


def parse_markup(text: str) -> list:
    """Markup -> [(text, style)] with style = {bold, dim, fg, bg}. Unknown tags
    are kept as literal text, so kid input can never break rendering."""
    spans, stack, style, pos = [], [], {}, 0

    def emit(chunk):
        if chunk:
            spans.append((chunk, dict(style)))

    for m in _TAG_RE.finditer(text):
        emit(text[pos:m.start()])
        pos = m.end()
        if m.group(0) == "\\[":
            emit("[")
            continue
        closing, body = m.group(1), m.group(2).strip()
        if closing:
            style = stack.pop() if stack else {}
            continue
        parsed = _parse_style(body)
        if parsed is None:
            emit(m.group(0))
            continue
        stack.append(style)
        style = {**style, **parsed}
    emit(text[pos:])
    return spans


def _parse_style(body: str):
    words = body.split()
    if not words:
        return None
    out, i = {}, 0
    while i < len(words):
        w = words[i]
        if w == "on" and i + 1 < len(words) and _is_color(words[i + 1]):
            out["bg"] = words[i + 1]
            i += 2
            continue
        if w in ("bold", "b"):
            out["bold"] = True
        elif w == "dim":
            out["dim"] = True
        elif w in ("italic", "i", "underline", "u", "not"):
            pass
        elif _is_color(w):
            out["fg"] = w
        else:
            return None
        i += 1
    return out


def _is_color(w: str) -> bool:
    return bool(_HEX_RE.match(w)) or w in NAMED_COLORS


def strip_markup(text: str) -> str:
    return "".join(t for t, _ in parse_markup(text))


def split_runs(text: str) -> list:
    """Text -> [(chunk, is_emoji)], so emoji go through the emoji font."""
    runs, pos = [], 0
    for m in _EMOJI_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], False))
        runs.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], False))
    return runs


def is_emoji(text: str) -> bool:
    return bool(text) and all(e for _, e in split_runs(text))


class _Cache(OrderedDict):
    def get_or(self, key, make):
        hit = self.get(key)
        if hit is None:
            hit = self[key] = make()
            if len(self) > CACHE_LIMIT:
                self.popitem(last=False)
        else:
            self.move_to_end(key)
        return hit


class Gfx:
    """The screen. Owns the surface, the fonts, and the caches."""

    def __init__(self, size=None, headless=False, windowed=False):
        pygame.display.init()
        pygame.font.init()
        if headless:
            self.surface = pygame.Surface(size or (1366, 768))
        else:
            self._flags = 0 if windowed else pygame.FULLSCREEN
            self.surface = pygame.display.set_mode(size or (0, 0), self._flags)
            pygame.display.set_caption("Purple")
            pygame.mouse.set_visible(False)
        self.headless = headless
        self.w, self.h = self.surface.get_size()
        self.all_caps = False
        self.dirty = True
        self._fonts = {}
        self._text = _Cache()
        self._emoji = _Cache()
        self._coverage: dict = {}
        self._probes: dict = {}
        self._emoji_font = self._load_emoji_font()

    def resize(self):
        """Follow the window when the X screen changes size under us (a VM
        display agent after the window opens, or a hotplugged monitor)."""
        size = pygame.display.get_window_size()
        if self.headless or size == (self.w, self.h):
            return
        self.surface = pygame.display.set_mode(size, self._flags)
        self.w, self.h = self.surface.get_size()
        self.dirty = True

    # ----- units -----
    def vh(self, pct: float) -> int:
        return max(1, round(self.h * pct / 100))

    def vw(self, pct: float) -> int:
        return max(1, round(self.w * pct / 100))

    # ----- fonts -----
    def font(self, face: str, px: int) -> pygame.font.Font:
        key = (face, px)
        f = self._fonts.get(key)
        if f is None:
            f = self._fonts[key] = pygame.font.Font(str(FONT_DIR / FACES[face]), px)
        return f

    def _load_emoji_font(self):
        for path in EMOJI_FONT_PATHS:
            if path and os.path.exists(path):
                try:
                    return pygame.font.Font(path, EMOJI_NATIVE_PX)
                except pygame.error:
                    continue
        return None

    def emoji(self, text: str, px: int) -> pygame.Surface:
        """Emoji run rendered at the bitmap strike and scaled so it sits with
        text of size px. Falls back to the sans face when no emoji font exists."""
        if self._emoji_font is None:
            return self.text(text, px, "sans", "#ffffff", _raw=True)

        def make():
            native = self._emoji_font.render(text, True, (255, 255, 255))
            target_h = max(1, round(px * 1.2))
            scale = target_h / native.get_height()
            size = (max(1, round(native.get_width() * scale)), target_h)
            return pygame.transform.smoothscale(native, size)
        return self._emoji.get_or((text, px), make)

    def text(self, text: str, px: int, face: str = "sans", color="#ffffff", _raw=False) -> pygame.Surface:
        """One line of text as a surface (cached). Emoji inside go through the
        emoji font; ALL CAPS is applied here so every caller inherits it."""
        if self.all_caps and not _raw:
            text = text.upper()
        key = (text, px, face, hexcolor(color))

        def make():
            if not text:
                return pygame.Surface((0, self.line_height(px, face)), pygame.SRCALPHA)
            runs = [(t, e) for chunk, e in split_runs(text) for t in ([chunk] if e else self._by_coverage(face, chunk))]
            if _raw or (len(runs) == 1 and not runs[0][1] and self._covers(face, runs[0][0])):
                return self.font(face, px).render(text, True, rgb(color))
            pieces = [self.emoji(t, px) if e else self.font(face if self._covers(face, t) else "symbols", px).render(t, True, rgb(color))
                      for t, e in runs]
            h = max(p.get_height() for p in pieces)
            out = pygame.Surface((sum(p.get_width() for p in pieces), h), pygame.SRCALPHA)
            x = 0
            for p in pieces:
                out.blit(p, (x, (h - p.get_height()) // 2))
                x += p.get_width()
            return out
        return self._text.get_or(key, make)

    def _covers(self, face: str, text: str) -> bool:
        """True when every char has a glyph in the face (cached per char)."""
        cache = self._coverage.setdefault(face, {})
        probe = self._probes.get(face)
        if probe is None:
            import pygame.freetype
            pygame.freetype.init()
            probe = self._probes[face] = pygame.freetype.Font(str(FONT_DIR / FACES[face]), 16)
        for ch in text:
            hit = cache.get(ch)
            if hit is None:
                hit = cache[ch] = ch.isspace() or probe.get_metrics(ch)[0] is not None
            if not hit:
                return False
        return True

    def _by_coverage(self, face: str, text: str) -> list:
        """Split text into maximal runs the face can and cannot draw."""
        out, buf, state = [], "", None
        for ch in text:
            ok = self._covers(face, ch)
            if state is None or ok == state:
                buf += ch
            else:
                out.append(buf)
                buf = ch
            state = ok
        return out + [buf] if buf else out

    def measure(self, text: str, px: int, face: str = "sans") -> tuple:
        return self.text(text, px, face).get_size()

    def line_height(self, px: int, face: str = "sans") -> int:
        return self.font(face, px).get_linesize()

    # ----- drawing -----
    def fill(self, color, rect=None):
        self.surface.fill(rgb(color), rect)

    def rect(self, color, rect, width=0, radius=0):
        pygame.draw.rect(self.surface, rgb(color), rect, width, border_radius=radius)

    def draw_text(self, text, px, x, y, face="sans", color="#ffffff", anchor="topleft", bg=None, pad=0) -> pygame.Rect:
        """Blit one line. anchor is any pygame.Rect attribute name (topleft,
        center, midtop, topright, midleft, ...). bg paints a box behind it."""
        s = self.text(text, px, face, color)
        r = s.get_rect(**{anchor: (x, y)})
        if bg is not None:
            self.rect(bg, r.inflate(pad * 2, pad * 2), radius=max(1, pad // 3))
        self.surface.blit(s, r)
        return r

    def layout(self, markup: str, px: int, face="sans", color="#ffffff", max_width=None, dim_to=None) -> list:
        """Markup -> lines of placed pieces, word-wrapped to max_width and
        broken at newlines. Each line is (width, height, [(surface, x, bg)]).
        A whitespace-only span with a background is a color swatch and is
        kept even at the start of a line. dim_to is the background dim text
        fades toward."""
        pieces = []
        for chunk, style in parse_markup(markup):
            fg = style.get("fg", color)
            if style.get("dim"):
                fg = mix(fg, dim_to or "#1e1033", 0.5)
            f = face
            if style.get("bold") and not face.endswith("bold") and not face.endswith("heavy"):
                f = face + "-bold"
            bg = style.get("bg")
            for part in re.split(r"(\n)", chunk):
                if part == "\n":
                    pieces.append(None)
                    continue
                if bg and part.isspace():
                    pieces.append((part, f, fg, bg))
                    continue
                for word in re.split(r"(\s+)", part):
                    if word:
                        pieces.append((word, f, fg, bg))
        lines, cur, cur_w = [], [], 0
        line_h = self.line_height(px, face)

        def flush():
            nonlocal cur, cur_w
            h = max([line_h] + [s.get_height() for s, _, _ in cur])
            lines.append((cur_w, h, cur))
            cur, cur_w = [], 0

        for piece in pieces:
            if piece is None:
                flush()
                continue
            word, f, fg, bg = piece
            if bg and word.isspace():  # a color swatch: one square per span, not per space
                s = pygame.Surface((line_h, line_h), pygame.SRCALPHA)
                cur.append((s, cur_w, bg))
                cur_w += line_h + px // 6
                continue
            for part in self._split_to_fit(word, px, f, fg, max_width):
                s = self.text(part, px, f, fg)
                if max_width and cur and cur_w + s.get_width() > max_width and not (part.isspace() and not bg):
                    flush()
                if not cur and part.isspace() and not bg:
                    continue
                cur.append((s, cur_w, bg))
                cur_w += s.get_width()
        if cur or not lines:
            flush()
        return lines

    def _split_to_fit(self, word, px, face, color, max_width):
        if not max_width or self.text(word, px, face, color).get_width() <= max_width:
            return [word]
        out, buf = [], ""
        for unit, _ in _units(word):
            if buf and self.text(buf + unit, px, face, color).get_width() > max_width:
                out.append(buf)
                buf = ""
            buf += unit
        return out + [buf] if buf else out

    def draw_markup(self, markup, px, x, y, face="sans", color="#ffffff", max_width=None, align="left", dim_to=None, line_gap=0) -> int:
        """Draw wrapped markup at (x, y); returns the height used."""
        lines = self.layout(markup, px, face, color, max_width, dim_to)
        top = y
        for w, h, pieces in lines:
            off = 0
            if align == "center" and max_width:
                off = (max_width - w) // 2
            elif align == "right" and max_width:
                off = max_width - w
            for s, px_x, bg in pieces:
                r = pygame.Rect(x + off + px_x, y, s.get_width(), h)
                if bg:
                    self.rect(bg, r)
                self.surface.blit(s, (r.x, y + (h - s.get_height()) // 2))
            y += h + line_gap
        return y - top

    def markup_size(self, markup, px, face="sans", max_width=None) -> tuple:
        lines = self.layout(markup, px, face, "#ffffff", max_width)
        return (max((w for w, _, _ in lines), default=0), sum(h for _, h, _ in lines))

    # ----- frame -----
    def present(self):
        if not self.headless:
            pygame.display.flip()
        self.dirty = False

    def save(self, path: str):
        pygame.image.save(self.surface, path)


def _units(text: str):
    """Grapheme-ish units for character wrapping: emoji runs stay whole."""
    for chunk, emoji in split_runs(text):
        if emoji:
            yield chunk, True
        else:
            for ch in chunk:
                yield ch, False
