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
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# SDL minimizes a fullscreen window that loses focus, so the parent terminal's
# xterm left Purple iconified behind a black root window when it closed.
os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
import pygame  # noqa: E402

from .. import i18n, palette as P
from ..content import get_content, is_word_picture
from ..palette import NAMED_COLORS, rgb

FONT_DIR = Path(__file__).parent / "fonts"
IMAGE_DIR = Path(__file__).parent / "images"
FACES = {
    "sans": "Figtree-Regular.ttf",
    "sans-bold": "Figtree-SemiBold.ttf",
    "sans-heavy": "Figtree-Bold.ttf",
    "mono": "IBMPlexMono-Regular.ttf",
    "mono-bold": "IBMPlexMono-SemiBold.ttf",
    "mono-heavy": "IBMPlexMono-Bold.ttf",
    "mono-italic": "IBMPlexMono-Italic.ttf",  # parent-menu section headers
    "block": "MartianMonoArt-Bold.ttf",  # one letter per square Art cell
    "nerd": "SymbolsNerdFontMono-Regular.ttf",  # mono-tinted UI icon glyphs
    "symbols": "DejaVuSans.ttf",  # fallback for glyphs the faces above lack
}
# A char the requested face lacks falls through this chain, in order; language
# pack fonts (Chinese) join it before DejaVu, which stays the last resort.
FALLBACK_FACES = ("nerd", "symbols")
EMOJI_FONT_PATHS = [
    os.environ.get("PURPLE_EMOJI_FONT", ""),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    str(Path.home() / ".local/share/fonts/NotoColorEmoji.ttf"),
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]
EMOJI_NATIVE_PX = 109  # Noto Color Emoji is a bitmap font with one strike; we scale from it
CACHE_LIMIT = 4096

# Text-default symbols (arrows, shapes, ☀, ❤) are emoji only with VS16, as
# Unicode says; emoji-default ones (⭐, ⚽, everything in the SMP) always are.
_EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|(?:[©®‼⁉™ℹ↔-↙↩↪⌨⏏⏭-⏯⏱⏲⏸-⏺Ⓜ▪▫▶◀◻◼☀-➿⤴⤵⬅-⬇〰〽㊗㊙]\ufe0f"
    "|[⌚⌛⏩-⏬⏰⏳◽◾☔☕♈-♓♿⚓⚡⚪⚫⚽⚾⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽✅✊✋✨❌❎❓-❕❗➕-➗➰➿⬛⬜⭐⭕"
    "\U0001F000-\U0001FAFF\U00100000-\U0010FFFD])[️⃣\U0001F3FB-\U0001F3FF]*"
    "(?:‍[☀-➿\U0001F000-\U0001FAFF][️\U0001F3FB-\U0001F3FF]*)*)+"
)
# A word picture's share of its emoji square: the room a Noto emoji leaves around itself, so pictures in a row don't touch.
WORD_PICTURE_FILL = 0.88
_WORD_PICTURE_RE = re.compile("([\U00100000-\U0010FFFD])")
_TAG_RE = re.compile(r"\\\[|\[(/?)([^\[\]]*)\]")
# Wrap points: runs of space, and between any two Chinese characters.
_BREAK_RE = re.compile(r"(\s+|[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef])")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

def hexcolor(color) -> str:
    r, g, b = rgb(color)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(a, b, t: float) -> tuple:
    """Blend color a toward b by t (0 = a, 1 = b)."""
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)


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


def _row(pieces: list, gap: int = 0) -> pygame.Surface:
    """Surfaces side by side, centered on one line."""
    h = max(p.get_height() for p in pieces)
    out = pygame.Surface((sum(p.get_width() for p in pieces) + gap * (len(pieces) - 1), h), pygame.SRCALPHA)
    x = 0
    for p in pieces:
        out.blit(p, (x, (h - p.get_height()) // 2))
        x += p.get_width() + gap
    return out


def is_emoji(text: str) -> bool:
    return bool(text) and all(e for _, e in split_runs(text))


class _Cache(OrderedDict):
    def __init__(self, limit=CACHE_LIMIT):
        super().__init__()
        self.limit = limit

    def get_or(self, key, make):
        hit = self.get(key)
        if hit is None:
            hit = self[key] = make()
            if len(self) > self.limit:
                self.popitem(last=False)
        else:
            self.move_to_end(key)
        return hit


def _run_edge(pieces, i, step) -> bool:
    """Whether a background piece ends its run of touching backgrounds on that side."""
    j = i + step
    if not 0 <= j < len(pieces) or not pieces[j][2]:
        return True
    a, b = sorted((pieces[i], pieces[j]), key=lambda p: p[1])
    return a[1] + a[0].get_width() != b[1]


class Gfx:
    """The screen. Owns the surface, the fonts, and the caches."""

    def __init__(self, size=None, headless=False, windowed=False):
        pygame.display.init()
        pygame.font.init()
        self._kms = None
        if headless:
            self.surface = pygame.Surface(size or (1366, 768))
        elif os.environ.get("PURPLE_DISPLAY") == "kms":
            from . import kms
            from .. import boot_log
            self._kms = kms.open_display(log=boot_log.heartbeat)
            self.surface = self._kms.make_surface(pygame)
        else:
            self._flags = 0 if windowed else pygame.FULLSCREEN
            if not (windowed or size) and self._cap_screen():
                pygame.display.quit()   # SDL keeps the desktop size it saw at init
                pygame.display.init()
            self.surface = pygame.display.set_mode(size or (0, 0), self._flags)
            pygame.display.set_caption("Purple")
            pygame.mouse.set_visible(False)
        self.headless = headless or self._kms is not None  # no SDL window either way
        self.w, self.h = self.surface.get_size()
        self.all_caps = False
        self.dirty = True
        self.caret = None             # [rect, pixels without, pixels with, shown, since] for the frame on screen
        self._fonts = {}
        self._text = _Cache()
        self._emoji = _Cache()
        self._images = _Cache()
        self._coverage: dict = {}
        self._probes: dict = {}
        self._emoji_font = self._load_emoji_font()
        for name, path in i18n.fonts():
            FACES[name] = str(path)
        self._fallbacks = FALLBACK_FACES[:-1] + tuple(n for n, _ in i18n.fonts()) + FALLBACK_FACES[-1:]

    @staticmethod
    def _cap_screen() -> bool:
        from . import screen_size
        from .. import boot_log
        info = pygame.display.Info()
        try:
            return screen_size.cap(info.current_w, info.current_h, boot_log.heartbeat)
        except Exception as e:
            boot_log.heartbeat(f"screen size: cap failed: {e}")
            return True   # reopen anyway: SDL then reads whatever size X is at now

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

    def em(self, n: float = 1.0) -> int:
        """The chrome unit: 1.3% of screen width, the same scale the design
        mock used, so its em-based paddings, gaps and radii port verbatim."""
        return max(1, round(self.w * 0.013 * n))

    # ----- fonts -----
    def font(self, face: str, px: int) -> pygame.font.Font:
        key = (face, px)
        f = self._fonts.get(key)
        if f is None:
            f = self._fonts[key] = pygame.font.Font(str(FONT_DIR / FACES[face]), px)
        return f

    def cap_drop(self, px: int, face: str = "sans") -> float:
        """How far below its box middle a line's capitals are centered, so mixed sizes can share a visual center."""
        f = self.font(face, px)
        return f.get_ascent() - f.metrics("H")[0][3] / 2 - f.get_height() / 2

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
        text of size px, a pack's word pictures among them. Falls back to the
        sans face when no emoji font exists."""
        pictures = get_content().word_pictures
        found = tuple(pictures.get(c) for c in text if is_word_picture(c))

        def make():
            parts = [p for p in _WORD_PICTURE_RE.split(text) if p]
            return _row([self._word_picture(p, px) if is_word_picture(p) else self._emoji_run(p, px) for p in parts])
        return self._emoji.get_or((text, px, found), make)

    def _emoji_run(self, text: str, px: int) -> pygame.Surface:
        if self._emoji_font is None:
            return self.text(text, px, "sans", "#ffffff", _raw=True)
        native = self._emoji_font.render(text, True, (255, 255, 255))
        target_h = max(1, round(px * 1.2))
        scale = target_h / native.get_height()
        return pygame.transform.smoothscale(native, (max(1, round(native.get_width() * scale)), target_h))

    def _word_picture(self, char: str, px: int) -> pygame.Surface:
        """A pack's picture fitted in an emoji's square; a frame emoji once its pack is gone."""
        side = max(1, round(px * 1.2))
        try:
            loaded = pygame.image.load(str(get_content().word_pictures[char]))
        except (KeyError, pygame.error, OSError):
            return self._emoji_run("🖼️", px)
        # smoothscale takes only 24 and 32 bit surfaces; a PNG can be paletted.
        native = pygame.Surface(loaded.get_size(), pygame.SRCALPHA)
        native.blit(loaded, (0, 0))
        k = side * WORD_PICTURE_FILL / max(native.get_size())
        img = pygame.transform.smoothscale(native, (max(1, round(native.get_width() * k)), max(1, round(native.get_height() * k))))
        out = pygame.Surface((side, side), pygame.SRCALPHA)
        out.blit(img, img.get_rect(center=(side // 2, side // 2)))
        return out

    def image(self, name: str, height: int) -> pygame.Surface:
        """A picture from images/, scaled to height (cached)."""
        def make():
            native = pygame.image.load(str(IMAGE_DIR / name))
            w = max(1, round(native.get_width() * height / native.get_height()))
            return pygame.transform.smoothscale(native, (w, height))
        return self._images.get_or((name, height), make)

    def text(self, text: str, px: int, face: str = "sans", color="#ffffff", _raw=False, track: float = 0,
             tr: bool = True) -> pygame.Surface:
        """One line of text as a surface (cached). Emoji inside go through the
        emoji font; translation and ALL CAPS are applied here so every caller
        inherits them (tr=False for what a kid typed). track spaces letters
        apart by that fraction of px (chrome labels)."""
        if tr and not _raw:
            text = i18n.translate(text)
        if self.all_caps and not _raw:
            text = text.upper()
        key = (text, px, face, hexcolor(color), track)

        def make():
            if not text:
                return pygame.Surface((0, self.line_height(px, face)), pygame.SRCALPHA)
            runs = []  # (chunk, face) with face None for an emoji run
            for chunk, e in split_runs(text):
                if e:
                    runs.append((chunk, None))
                else:
                    runs.extend(self._split_faces(face, chunk))
            if _raw or (not track and len(runs) == 1 and runs[0][1] == face):
                return self.font(face, px).render(text, True, rgb(color))
            pieces = []
            for t, rf in runs:
                if rf is None:
                    pieces.append(self.emoji(t, px))
                    continue
                f = self.font(rf, px)
                pieces.extend(f.render(u, True, rgb(color)) for u in (t if track else [t]))
            return _row(pieces, round(px * track))
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

    def _resolve_face(self, face: str, ch: str) -> str:
        """The face that draws ch: the requested one, then the fallback chain
        (nerd icons, then DejaVu symbols). Spaces stay on the requested face."""
        if ch.isspace() or self._covers(face, ch):
            return face
        for fb in self._fallbacks:
            if fb != face and self._covers(fb, ch):
                return fb
        return self._fallbacks[-1]

    def _split_faces(self, face: str, text: str) -> list:
        """Split text into maximal (run, face) pairs by resolved face."""
        out, buf, cur = [], "", None
        for ch in text:
            rf = self._resolve_face(face, ch)
            if cur is None or rf == cur:
                buf += ch
            else:
                out.append((buf, cur))
                buf = ch
            cur = rf
        return out + [(buf, cur)] if buf else out

    def measure(self, text: str, px: int, face: str = "sans", track: float = 0, tr: bool = True) -> tuple:
        return self.text(text, px, face, track=track, tr=tr).get_size()

    def line_height(self, px: int, face: str = "sans") -> int:
        return self.font(face, px).get_linesize()

    # ----- drawing -----
    def fill(self, color, rect=None):
        self.surface.fill(rgb(color), rect)

    def rect(self, color, rect, width=0, radius=0, left=-1, right=-1):
        """left/right override radius on that side's corners (-1 keeps it)."""
        pygame.draw.rect(self.surface, rgb(color), rect, width, border_radius=radius,
                         border_top_left_radius=left, border_bottom_left_radius=left,
                         border_top_right_radius=right, border_bottom_right_radius=right)

    def draw_text(self, text, px, x, y, face="sans", color="#ffffff", anchor="topleft", bg=None, pad=0, track: float = 0,
                  tr: bool = True) -> pygame.Rect:
        """Blit one line. anchor is any pygame.Rect attribute name (topleft,
        center, midtop, topright, midleft, ...). bg paints a box behind it."""
        s = self.text(text, px, face, color, track=track, tr=tr)
        r = s.get_rect(**{anchor: (x, y)})
        if bg is not None:
            self.rect(bg, r.inflate(pad * 2, pad * 2))
        self.surface.blit(s, r)
        return r

    def layout(self, markup: str, px: int, face="sans", color="#ffffff", max_width=None, dim_to=None, tr=True) -> list:
        """Markup -> lines of placed pieces, word-wrapped to max_width and
        broken at newlines. Each line is (width, height, [(surface, x, bg)]).
        A whitespace-only span with a background is a color swatch and is
        kept even at the start of a line; a colored span never breaks across
        lines, and one holding a single letter or emoji is a square tile, so
        letter blocks line up in columns when they wrap. dim_to is the
        background dim text fades toward."""
        if tr:
            markup = i18n.translate(markup)
        pieces = []
        for chunk, style in parse_markup(markup):
            fg = style.get("fg", color)
            if style.get("dim"):
                fg = mix(fg, dim_to or P.BG, 0.5)
            f = face
            if style.get("bold") and not face.endswith("bold") and not face.endswith("heavy"):
                f = face + "-bold"
            bg = style.get("bg")
            for part in re.split(r"(\n)", chunk):
                if part == "\n":
                    pieces.append(None)
                elif bg:
                    pieces.append((part, f, fg, bg, part.isspace()))
                else:
                    pieces.extend((w, f, fg, bg, False) for w in _BREAK_RE.split(part) if w)
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
            word, f, fg, bg, swatch = piece
            if swatch:  # one square per span, not per space
                s = pygame.Surface((line_h, line_h), pygame.SRCALPHA)
                cur.append((s, cur_w, bg))
                cur_w += line_h + px // 6
                continue
            if bg and len(list(_units(word.strip()))) == 1:
                s = self._tile(word.strip(), px, f, fg, line_h)
                if max_width and cur and cur_w + s.get_width() > max_width:
                    flush()
                cur.append((s, cur_w, bg))
                cur_w += s.get_width()
                continue
            for part in self._split_to_fit(word, px, f, fg, max_width):
                s = self.text(part, px, f, fg, tr=False)
                if max_width and cur and cur_w + s.get_width() > max_width and not (part.isspace() and not bg):
                    flush()
                if not cur and part.isspace() and not bg:
                    continue
                cur.append((s, cur_w, bg))
                cur_w += s.get_width()
        if cur or not lines:
            flush()
        return lines

    def _tile(self, ch, px, face, color, side):
        s = self.text(ch, px, face, color, tr=False)
        side = max(side, s.get_width())
        tile = pygame.Surface((side, side), pygame.SRCALPHA)
        tile.blit(s, ((side - s.get_width()) // 2, (side - s.get_height()) // 2))
        return tile

    def _split_to_fit(self, word, px, face, color, max_width):
        if not max_width or self.text(word, px, face, color, tr=False).get_width() <= max_width:
            return [word]
        out, buf = [], ""
        for unit, _ in _units(word):
            if buf and self.text(buf + unit, px, face, color, tr=False).get_width() > max_width:
                out.append(buf)
                buf = ""
            buf += unit
        return out + [buf] if buf else out

    def draw_markup(self, markup, px, x, y, face="sans", color="#ffffff", max_width=None, align="left", dim_to=None, line_gap=0,
                    tr=True) -> int:
        """Draw wrapped markup at (x, y); returns the height used."""
        lines = self.layout(markup, px, face, color, max_width, dim_to, tr)
        top = y
        for w, h, pieces in lines:
            off = 0
            if align == "center" and max_width:
                off = (max_width - w) // 2
            elif align == "right" and max_width:
                off = max_width - w
            for i, (s, px_x, bg) in enumerate(pieces):
                r = pygame.Rect(x + off + px_x, y, s.get_width(), h)
                if bg:
                    self.rect(bg, r, left=h // 5 if _run_edge(pieces, i, -1) else 0,
                              right=h // 5 if _run_edge(pieces, i, 1) else 0)
                self.surface.blit(s, (r.x, y + (h - s.get_height()) // 2))
            y += h + line_gap
        return y - top

    def markup_size(self, markup, px, face="sans", max_width=None, line_gap=0, tr=True) -> tuple:
        lines = self.layout(markup, px, face, "#ffffff", max_width, tr=tr)
        return (max((w for w, _, _ in lines), default=0), sum(h for _, h, _ in lines) + line_gap * (len(lines) - 1))

    # ----- frame -----
    def present(self, rect=None):
        if self._kms:
            self._kms.present()
        elif not self.headless:
            pygame.display.update(rect) if rect else pygame.display.flip()
        if rect is None:
            self.dirty = False

    def draw_caret(self, rect, draw, draw_dim=None):
        """Run draw() and keep the pixels under rect both ways (bare, or as
        draw_dim() repaints the whole rect, run at the first blink), so blink()
        can swap them without repainting the frame."""
        rect = pygame.Rect(rect).clip(self.surface.get_rect())
        off = draw_dim or self.surface.subsurface(rect).copy()
        draw()
        self.caret = [rect, off, self.surface.subsurface(rect).copy(), True, time.monotonic()]

    def blink(self, period: float):
        """Toggle the caret once it has held still for `period`. Skipped when a
        redraw is due or something was painted over it after it was drawn."""
        c = self.caret
        if not c or self.dirty or time.monotonic() - c[4] < period:
            return
        rect, off, on, shown, _ = c
        # A VM window can shrink under us before its resize event is handled
        if not self.surface.get_rect().contains(rect) or pygame.image.tobytes(self.surface.subsurface(rect), "RGB") != pygame.image.tobytes(on if shown else off, "RGB"):
            self.caret = None
            return
        if callable(off):
            off()
            c[1] = self.surface.subsurface(rect).copy()
        else:
            self.surface.blit(off if shown else on, rect)
        c[3], c[4] = not shown, time.monotonic()
        self.present(rect)

    def save(self, path: str):
        pygame.image.save(self.surface, path)

    @contextmanager
    def drawing_on(self, surface):
        """Point the drawing calls at another surface (a printed page). Units stay the screen's."""
        screen, self.surface = self.surface, surface
        try:
            yield surface
        finally:
            self.surface = screen


# One emoji (with its modifiers/ZWJ joins), so long runs can wrap per emoji.
_EMOJI_ONE_RE = re.compile(_EMOJI_RE.pattern.rstrip("+"))


def _units(text: str):
    """Grapheme-ish units for character wrapping: each emoji is one unit."""
    for chunk, emoji in split_runs(text):
        if emoji:
            for m in _EMOJI_ONE_RE.finditer(chunk):
                yield m.group(0), True
        else:
            for ch in chunk:
                yield ch, False
