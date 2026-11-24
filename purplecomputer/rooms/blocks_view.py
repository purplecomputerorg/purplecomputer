"""How Blocks looks: one perspective camera on the floor's center, which turns around it to any angle and
tips from the side to nearly straight down, and the floor, blocks and shadows painted through it,
far to near. Coordinates are (x, z, y) cells with y up, in whatever frame the caller passes: view coordinates
at rest, world ones mid-turn."""

import bisect
import copy
import math
from functools import cache
from operator import itemgetter

import pygame

from .. import palette as P
from .. import paper
from ..gfx import mix, rgb
from . import art_room

WIDTH, DEPTH, HEIGHT = 16, 16, 12   # square, so every side is the same floor
SLAB = 0.35                   # the floor's thickness, in cells
REST_PITCH, PEEK_PITCH = math.radians(30), math.radians(76)
EYE_DISTANCE = (44, 70)       # cells from the floor's center at rest and looking down; nearer is stronger perspective
TARGET_Y = 2.0                # the height the camera looks at, over the floor's center
SUN = (0.3, 0.55)             # a level's shadow reach, (right, away) from the camera, in cells
SUN_ALPHA, SUN_INK = 40, (10, 0, 25)
DEPTH_FADE = 0.3              # how far the back row's blocks lean toward the floor color
TOP_LIGHT, TOP_LIGHT_PER_LEVEL = 0.18, 0.015   # tops light up toward white, a little more each level up
SIDE_DARK = 0.36              # the darkest side, turned away from the light
SHADOW_ALPHA = 140            # the square under a floating block
TOP = None                    # a face's normal: None for the top, else (x, z)
FACES = (TOP, (0, -1), (0, 1), (-1, 0), (1, 0))


def lerp(a, b, t):
    return a + (b - a) * t


@cache
def tint(color, toward, t: float) -> tuple:
    """`mix`, remembered: painting asks for the same few shades over and over."""
    return mix(color, toward, t)


@cache
def haze(color, row: int) -> tuple:
    return mix(color, art_room.CANVAS_BG, DEPTH_FADE * row / (DEPTH - 1))


def screen_floor() -> tuple:
    """(ground, tile, other tile, slab front, slab side); a family theme can change the canvas colors."""
    bg = art_room.CANVAS_BG
    return P.SURFACE, bg, art_room.CANVAS_ALT, mix(bg, "#000000", 0.4), mix(bg, "#000000", 0.55)


PAPER_FLOOR = (paper.WHITE, "#f1f1f1", "#e4e4e4", "#c8c8c8", "#b4b4b4")


def hull(points) -> list:
    """Convex hull, counterclockwise (monotone chain)."""
    pts = sorted(set(points))

    def half(seq):
        out = []
        for p in seq:
            while len(out) > 1 and (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]
    return half(pts) + half(reversed(pts))


def shape(blocks: dict) -> tuple:
    """A build as it is painted, whatever the camera: (runs, floats, stacks). A run is one column's
    touching blocks of one color, (x, z, bottom, top, color, open), painted as one tall box: `open` is
    the faces with no blocks all along them, the only ones that can show. Floats are the shadows under
    runs with air below them, (x, z, ground); stacks are a column's touching blocks whatever their
    colors, (x, z, bottom, top), for the sun's shadows."""
    cols: dict = {}
    for x, z, y in blocks:
        cols.setdefault((x, z), []).append(y)
    return joined(column_shape(blocks, x, z, sorted(ys)) for (x, z), ys in sorted(cols.items()))


def joined(parts) -> tuple:
    """Columns' shapes as one build's."""
    runs, floats, stacks = [], [], []
    for r, f, s in parts:
        runs += r
        floats += f
        stacks += s
    return runs, floats, stacks


def column_shape(blocks: dict, x: int, z: int, ys=None) -> tuple:
    """shape() of one column, its blocks at heights `ys` (bottom up), or found by looking. Its runs' faces
    depend on the columns beside it too."""
    if ys is None:
        ys = [y for y in range(HEIGHT) if (x, z, y) in blocks]
    runs, floats, stacks = [], [], []
    for y in ys:
        color = blocks[(x, z, y)]
        touching = bool(stacks) and stacks[-1][3] == y - 1
        if touching and runs[-1][4] == color:
            runs[-1][3] = y
        else:
            runs.append([x, z, y, y, color])
        if touching:
            stacks[-1][3] = y
            continue
        if y:
            floats.append((x, z, stacks[-1][3] + 1 if stacks else 0))
        stacks.append([x, z, y, y])

    def bare(x, z, bottom, top, color):
        levels = range(bottom, top + 1)
        return tuple(n for n in FACES if ((x, z, top + 1) not in blocks if n is TOP else
                                          any((x + n[0], z + n[1], y) not in blocks for y in levels)))
    return [(*r, bare(*r)) for r in runs], floats, [tuple(k) for k in stacks]


def bbox(points) -> pygame.Rect:
    xs, ys = zip(*points)
    left, top = math.floor(min(xs)), math.floor(min(ys))
    return pygame.Rect(left, top, math.ceil(max(xs)) - left + 2, math.ceil(max(ys)) - top + 2)


class Camera:
    """Looks at the floor's center from `yaw` around it and `pitch` down, scaled so the floor up to
    `top` (the ceiling) fills a w by h box at `origin`: the floor as it sits turned `fit` off straight
    on, either way, whatever its yaw, so a turn from one side to the next keeps one size and the
    floor's middle stays put. Grid points are projected once and remembered."""

    def __init__(self, yaw: float, pitch: float, w: int, h: int, origin=(0, 0), top: float = HEIGHT, fit: float = 0.0):
        sy, cy, sp, cp = math.sin(yaw), math.cos(yaw), math.sin(pitch), math.cos(pitch)
        self.f, self.r, self.u = (sy * cp, -sp, cy * cp), (cy, 0.0, -sy), (sy * sp, cp, cy * sp)
        # The eye backs off as it tips down from rest, so tall towers lean less.
        away = lerp(*EYE_DISTANCE, min(1.0, max(0.0, (pitch - REST_PITCH) / (PEEK_PITCH - REST_PITCH))))
        self.eye = (WIDTH / 2 - away * self.f[0], TARGET_Y - away * self.f[1], DEPTH / 2 - away * self.f[2])
        ahead = (sy, cy)
        self.sun = (SUN[0] * cy + SUN[1] * ahead[0], SUN[0] * -sy + SUN[1] * ahead[1])
        light = (-0.45 * cy - ahead[0], 0.45 * sy - ahead[1])
        n = math.hypot(*light)
        self.dark = {side: round(SIDE_DARK * (1 - max(0.0, (side[0] * light[0] + side[1] * light[1]) / n)), 2)
                     for side in ((0, -1), (0, 1), (-1, 0), (1, 0))}
        self._ahead, self._memo, self.rects, self.floor = ahead, {}, {}, {}
        # A stack's shadow is its foot slid along the sun from its bottom to its top: the outline's
        # points, as (x, z) of a foot corner and which end, are the same for every stack.
        ends = {(px + self.sun[0] * end, pz + self.sun[1] * end): (px, pz, end) for px in (0, 1) for pz in (0, 1) for end in (0, 1)}
        self._sun_outline = [ends[p] for p in hull(ends)]
        self.s, self.ox, self.oy, self.zoom = 1.0, 0.0, 0.0, 1
        sf, cf = math.sin(fit), math.cos(fit)
        corners = [(a * cf - b * s, a * s + b * cf) for a in (-WIDTH / 2, WIDTH / 2) for b in (-DEPTH / 2, DEPTH / 2) for s in (sf, -sf)]
        xs, ys = zip(*(self._flat(WIDTH / 2 + a * cy + b * sy, y, DEPTH / 2 - a * sy + b * cy) for a, b in corners for y in (-SLAB, top)))
        self.s = min(w / (max(xs) - min(xs)), h / (max(ys) - min(ys)))
        self.ox = origin[0] + (w - self.s * (max(xs) + min(xs))) / 2
        self.oy = origin[1] + (h - self.s * (max(ys) + min(ys))) / 2

    def zoomed(self, by: int, corner) -> "Camera":
        """This camera painting `by` times the size, with screen point `corner` at the picture's corner:
        for a patch painted large and scaled down, which smooths its edges."""
        cam = copy.copy(self)
        cam.s, cam.ox, cam.oy, cam.zoom = self.s * by, (self.ox - corner[0]) * by, (self.oy - corner[1]) * by, self.zoom * by
        cam._memo, cam.rects, cam.floor = {}, {}, {}
        return cam

    def _flat(self, x, y, z) -> tuple:
        dx, dy, dz = x - self.eye[0], y - self.eye[1], z - self.eye[2]
        f, r, u = self.f, self.r, self.u
        depth = dx * f[0] + dy * f[1] + dz * f[2]
        return (dx * r[0] + dz * r[2]) / depth, -(dx * u[0] + dy * u[1] + dz * u[2]) / depth

    def at(self, x, y, z) -> tuple:
        """Screen point of (x, y, z): note y, the height, comes second."""
        p = self._memo.get((x, y, z))
        if p is None:
            fx, fy = self._flat(x, y, z)
            p = self._memo[(x, y, z)] = (self.ox + self.s * fx, self.oy + self.s * fy)
        return p

    def key(self, x, z, y) -> tuple:
        """Paint order: rows farther from the eye first, then columns farther from it, then bottom up.
        Right for a grid of cubes while the eye is above all of them, which it always is."""
        return -abs(z + 0.5 - self.eye[2]), -abs(x + 0.5 - self.eye[0]), y

    def away(self, dx, dz) -> float:
        """How much the floor direction (dx, dz) points away from the eye: 1 straight away, -1 straight toward."""
        return dx * self._ahead[0] + dz * self._ahead[1]

    def row(self, x, z) -> int:
        """How far back a cell sits, 0 to DEPTH - 1, for its haze."""
        back = (x + 0.5 - WIDTH / 2) * self._ahead[0] + (z + 0.5 - DEPTH / 2) * self._ahead[1] + DEPTH / 2 - 0.5
        return min(DEPTH - 1, max(0, round(back)))

    def cell(self, x, y, z) -> float:
        """A cell's width on screen there."""
        (ax, ay), (bx, by) = self.at(x, y, z), self.at(x + 1, y, z)
        return math.hypot(bx - ax, by - ay)

    def box(self, lo, hi, open=FACES) -> list:
        """(normal, polygon) for each face of the box from lo to hi, both (x, y, z), that the eye sees
        and is in `open`. A side's polygon runs along its bottom edge, then back along its top."""
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        ex, ey, ez = self.eye
        at, faces = self.at, []
        if ey > y1 and TOP in open:
            faces.append((TOP, [at(x0, y1, z0), at(x1, y1, z0), at(x1, y1, z1), at(x0, y1, z1)]))
        if ez < z0 and (0, -1) in open:
            faces.append(((0, -1), [at(x0, y0, z0), at(x1, y0, z0), at(x1, y1, z0), at(x0, y1, z0)]))
        if ez > z1 and (0, 1) in open:
            faces.append(((0, 1), [at(x1, y0, z1), at(x0, y0, z1), at(x0, y1, z1), at(x1, y1, z1)]))
        if ex < x0 and (-1, 0) in open:
            faces.append(((-1, 0), [at(x0, y0, z1), at(x0, y0, z0), at(x0, y1, z0), at(x0, y1, z1)]))
        if ex > x1 and (1, 0) in open:
            faces.append(((1, 0), [at(x1, y0, z0), at(x1, y0, z1), at(x1, y1, z1), at(x1, y1, z0)]))
        return faces

    def run_rect(self, x, z, bottom, top) -> pygame.Rect:
        key = ("b", x, z, bottom, top)
        if key not in self.rects:
            self.rects[key] = bbox([self.at(x + a, h, z + b) for a in (0, 1) for b in (0, 1) for h in (bottom, top + 1)])
        return self.rects[key]

    def block_rect(self, x, z, y) -> pygame.Rect:
        return self.run_rect(x, z, y, y)

    def sun_shadow(self, x, z, lo, hi) -> tuple:
        """(polygon, rect) of the shadow on the floor of the run of blocks lo to hi high in cell (x, z)."""
        key = ("sun", x, z, lo, hi)
        if key not in self.rects:
            (sx, sz), reach = self.sun, (lo, hi + 1)
            poly = [self.at(x + px + sx * reach[end], 0, z + pz + sz * reach[end]) for px, pz, end in self._sun_outline]
            self.rects[key] = poly, bbox(poly)
        return self.rects[key]

    def column_rect(self, x, z) -> pygame.Rect:
        """Everything a block anywhere in the column can touch: the column, floor to ceiling, and its sun shadow."""
        key = ("c", x, z)
        if key not in self.rects:
            sx, sz = self.sun[0] * HEIGHT, self.sun[1] * HEIGHT
            self.rects[key] = bbox([self.at(x + a, h, z + b) for a in (0, 1) for b in (0, 1) for h in (0, HEIGHT)]
                                   + [self.at(x + a + sx, 0, z + b + sz) for a in (0, 1) for b in (0, 1)]).inflate(4, 4)
        return self.rects[key]


class Painter:
    """One camera and one set of blocks {(x, z, y): color}, as its `shape` (worked out here unless
    `built` passes it), sorted far to near once. `row` is the cursor's row: `paint_part` picks out the
    rows in front of it, so the cursor can be drawn behind them.
    Without `detail`, floating blocks cast no shadow."""

    def __init__(self, cam: Camera, blocks: dict, row=None, hazy: bool = True, detail: bool = True, floor=None, built=None,
                 quarters: int = 0):
        self.cam, self.blocks, self.row, self.hazy = cam, blocks, row, hazy
        self.flip = quarters % 2      # an odd quarter turn swaps which cells are light, since a side is an even 16 cells
        self.floor = floor or screen_floor()
        runs, floats, self.stacks = built or shape(blocks)
        items = [(cam.key(*run[:3]), 0, run) for run in runs if run[5]]     # a run closed in on every side never shows
        if detail:
            items += [(cam.key(x, z, ground - 0.5), 1, (x, z, ground)) for x, z, ground in floats]
        items.sort(key=itemgetter(0))
        self.items, self._sun, self._rects = items, None, [None]    # each item's rect, found once and shared by on_row's copies

    def on_row(self, row) -> "Painter":
        """The same blocks, already sorted, with the cursor on another row."""
        other = copy.copy(self)
        other.row = row
        return other

    def on(self, cam: Camera) -> "Painter":
        """The same blocks through another camera, for the few things painted one at a time."""
        other = copy.copy(self)
        other.cam, other._rects = cam, [None]
        return other

    # ------------------------------------------------------------ colors
    def base(self, x, z, color) -> tuple:
        return haze(color, self.cam.row(x, z)) if self.hazy else rgb(color)

    def face(self, base, normal, y) -> tuple:
        if normal is TOP:
            return tint(base, "#ffffff", round(TOP_LIGHT + TOP_LIGHT_PER_LEVEL * y, 3))
        return tint(base, "#000000", self.cam.dark[normal])

    def tile(self, x, z) -> tuple:
        return rgb(self.floor[2] if (x + z + self.flip) % 2 else self.floor[1])

    # ------------------------------------------------------------ painting
    def paint_floor(self, surf):
        """The slab's sides, then the checkerboard: one fill for the floor, then every other tile."""
        cam, (_, tile, alt, slab_front, slab_side) = self.cam, self.floor
        for n, poly in cam.box((0, -SLAB, 0), (WIDTH, 0, DEPTH), FACES[1:]):
            pygame.draw.polygon(surf, rgb(slab_front if n == (0, -1) else slab_side), poly)
        pygame.draw.polygon(surf, rgb(tile), [cam.at(0, 0, 0), cam.at(WIDTH, 0, 0), cam.at(WIDTH, 0, DEPTH), cam.at(0, 0, DEPTH)])
        for x in range(WIDTH):
            for z in range((1 + x + self.flip) % 2, DEPTH, 2):
                pygame.draw.polygon(surf, rgb(alt), self._tile_poly(x, z))

    def floor_picture(self, size) -> pygame.Surface:
        """The floor on its ground color, painted once per camera and checkerboard."""
        if self.flip not in self.cam.floor:
            pic = self.cam.floor[self.flip] = pygame.Surface(size)
            pic.fill(rgb(self.floor[0]))
            self.paint_floor(pic)
        return self.cam.floor[self.flip]

    def _tile_poly(self, x, z, y=0) -> list:
        at = self.cam.at
        return [at(x, y, z), at(x + 1, y, z), at(x + 1, y, z + 1), at(x, y, z + 1)]

    def paint_sun(self, surf, clip=None):
        """Each run of blocks' shadow on the floor, away from the light, in one see-through layer so overlaps don't darken twice."""
        clip = clip or surf.get_rect()
        shadows = [s for s in self._sun_shadows() if s[1].colliderect(clip)]
        if shadows:
            # The layer holds each shadow whole: a polygon cut by its edge fills that edge differently, a seam where a patch was repainted.
            area = shadows[0][1].unionall([rect for _, rect in shadows[1:]])
            layer = pygame.Surface(area.size, pygame.SRCALPHA)
            for poly, _ in shadows:
                pygame.draw.polygon(layer, (*SUN_INK, 255), [(round(px) - area.x, round(py) - area.y) for px, py in poly])   # whole pixels first: a patch's offset must not move an edge
            layer.set_alpha(SUN_ALPHA)
            spot = area.clip(clip)
            surf.blit(layer, spot, spot.move(-area.x, -area.y))

    def _sun_shadows(self) -> list:
        """(polygon, rect) of each stack's shadow, the camera remembering each one's."""
        if self._sun is None:
            self._sun = [self.cam.sun_shadow(*stack) for stack in self.stacks]
        return self._sun

    def paint(self, surf, items, clip=None):
        """Runs and the shadows under floating ones, in paint order; with `clip`, only what touches it."""
        if clip is not None and clip.contains(surf.get_rect()):
            clip = None
        for item in items:
            if clip is None or self._rect(item).colliderect(clip):
                self._draw(surf, item)

    def paint_part(self, surf, clip, in_front: bool = False):
        """paint(self.items, clip), found by pygame in one call; with `in_front`, only the rows in front of the cursor's."""
        for item in self.touching(clip):
            if not in_front or item[2][1] < self.row:
                self._draw(surf, item)

    def touching(self, rect, start: int = 0) -> list:
        """The items from `start` on whose rects touch `rect`, in paint order."""
        if self._rects[0] is None:
            self._rects[0] = [self._rect(item) for item in self.items]
        return [self.items[i] for i in rect.collidelistall(self._rects[0]) if i >= start]

    def _draw(self, surf, item):
        (self.shadow if item[1] else self.box)(surf, *item[2])

    def _rect(self, item) -> pygame.Rect:
        _, kind, d = item
        return self._shadow_rect(*d) if kind else self.cam.run_rect(*d[:4])

    def after(self, x, z, y, rect) -> list:
        """The items painted after a block at (x, z, y) that touch `rect`: all that can stand in front of it there."""
        return self.touching(rect, bisect.bisect_right(self.items, (self.cam.key(x, z, y), 2)))

    def box(self, surf, x, z, bottom, top, color, open=FACES, inset: float = 0.0):
        """One column's blocks from bottom to top as one tall box in one color, `inset` cells smaller
        all around: its `open` faces that the eye can see. Nearer columns paint over whatever they hide."""
        base = self.base(x, z, color)
        lo, hi = (x + inset, bottom + inset, z + inset), (x + 1 - inset, top + 1 - inset, z + 1 - inset)
        for n, poly in self.cam.box(lo, hi, open):
            pygame.draw.polygon(surf, self.face(base, n, top), poly)

    def shadow(self, surf, x, z, ground, alpha=None, dark=1.0):
        """The square a floating block casts straight down onto what it would land on, `dark` as dark as
        it gets. Mixed into what it covers, or with `alpha`, see-through onto a layer."""
        below = self.blocks.get((x, z, ground - 1))
        under = self.face(self.base(x, z, below), TOP, ground - 1) if below else self.tile(x, z)
        fill = tint(under, "#000000", round(dark * SHADOW_ALPHA) / 255) if alpha is None else (0, 0, 0, min(alpha, SHADOW_ALPHA))
        pygame.draw.polygon(surf, fill, self._tile_poly(x, z, ground))

    def _shadow_rect(self, x, z, ground) -> pygame.Rect:
        key = ("s", x, z, ground)
        rects = self.cam.rects
        if key not in rects:
            rects[key] = bbox(self._tile_poly(x, z, ground))
        return rects[key]
