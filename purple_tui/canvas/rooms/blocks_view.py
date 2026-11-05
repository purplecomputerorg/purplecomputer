"""How Blocks looks: one perspective camera on the floor's center, which Tab turns around and held Tab tips
down to look from above, and the floor, blocks and shadows painted through it, far to near. Coordinates are
(x, z, y) cells with y up, in whatever frame the caller passes: view coordinates at rest, world ones mid-turn."""

import copy
import math
from functools import cache
from operator import itemgetter

import pygame

from ... import palette as P
from .. import paper
from ..gfx import mix, rgb
from . import art_room

WIDTH, DEPTH, HEIGHT = 30, 12, 12
SLAB = 0.35                   # the floor's thickness, in cells
REST_PITCH, PEEK_PITCH = math.radians(30), math.radians(76)
EYE_DISTANCE = (44, 70)       # cells from the floor's center at rest and looking down; nearer is stronger perspective
TARGET_Y = 2.0                # the height the camera looks at, over the floor's center
SUN = (0.3, 0.55)             # a level's shadow reach, (right, away) from the camera, in cells
SUN_ALPHA, SUN_INK = 85, (10, 0, 25)
DEPTH_FADE = 0.3              # how far the back row's blocks lean toward the floor color
TOP_LIGHT, TOP_LIGHT_PER_LEVEL = 0.18, 0.015   # tops light up toward white, a little more each level up
SIDE_DARK = 0.36              # the darkest side, turned away from the light
SHADOW_ALPHA = 140            # the square under a floating block
STEM_ALPHA, STEM_DARKEN = 150, 0.35
RIBBON_FROM, RIBBON_TO, RIBBON_ALPHA = 0.38, 0.62, 70   # the cursor row's band across a face
STRIPE_ALPHA, FRAME_ALPHA = 22, 90
FRONT_ALPHA = 40              # front towers in the way of the cursor's glass column or landing block fade to this
TOP = None                    # a face's normal: None for the top, else (x, z)
SIDES = (TOP, (0, -1), (0, 1), (-1, 0), (1, 0))
STAMPS_KEPT = 20000           # block pictures a camera keeps before starting over


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


def bbox(points) -> pygame.Rect:
    xs, ys = zip(*points)
    left, top = math.floor(min(xs)), math.floor(min(ys))
    return pygame.Rect(left, top, math.ceil(max(xs)) - left + 2, math.ceil(max(ys)) - top + 2)


class Camera:
    """Looks at the floor's center from `yaw` around it and `pitch` down, scaled so the floor up to
    `top` (the ceiling) fills a w by h box at `origin`. Grid points are projected once and remembered."""

    def __init__(self, yaw: float, pitch: float, w: int, h: int, origin=(0, 0), top: float = HEIGHT):
        sy, cy, sp, cp = math.sin(yaw), math.cos(yaw), math.sin(pitch), math.cos(pitch)
        self.f, self.r, self.u = (sy * cp, -sp, cy * cp), (cy, 0.0, -sy), (sy * sp, cp, cy * sp)
        away = lerp(*EYE_DISTANCE, (pitch - REST_PITCH) / (PEEK_PITCH - REST_PITCH))   # rises as it tips down, so tall towers lean less
        self.eye = (WIDTH / 2 - away * self.f[0], TARGET_Y - away * self.f[1], DEPTH / 2 - away * self.f[2])
        ahead = (sy, cy)
        self.sun = (SUN[0] * cy + SUN[1] * ahead[0], SUN[0] * -sy + SUN[1] * ahead[1])
        light = (-0.45 * cy - ahead[0], 0.45 * sy - ahead[1])
        n = math.hypot(*light)
        self.dark = {side: round(SIDE_DARK * (1 - max(0.0, (side[0] * light[0] + side[1] * light[1]) / n)), 2)
                     for side in ((0, -1), (0, 1), (-1, 0), (1, 0))}
        self._ahead, self._memo, self.rects, self.floor = ahead, {}, {}, None
        self.s, self.ox, self.oy = 1.0, 0.0, 0.0
        xs, ys = zip(*(self._flat(x, y, z) for x in (0, WIDTH) for y in (-SLAB, top) for z in (0, DEPTH)))
        self.s = min(w / (max(xs) - min(xs)), h / (max(ys) - min(ys)))
        self.ox = origin[0] + (w - self.s * (max(xs) + min(xs))) / 2
        self.oy = origin[1] + (h - self.s * (max(ys) + min(ys))) / 2

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

    def row(self, x, z) -> int:
        """How far back a cell sits, 0 to DEPTH - 1, for its haze."""
        back = (x + 0.5 - WIDTH / 2) * self._ahead[0] + (z + 0.5 - DEPTH / 2) * self._ahead[1] + DEPTH / 2 - 0.5
        return min(DEPTH - 1, max(0, round(back)))

    def cell(self, x, y, z) -> float:
        """A cell's width on screen there."""
        (ax, ay), (bx, by) = self.at(x, y, z), self.at(x + 1, y, z)
        return math.hypot(bx - ax, by - ay)

    def box(self, lo, hi, shown=None) -> list:
        """(normal, polygon) for each face the eye sees of the box from lo to hi, both (x, y, z).
        A side's polygon runs along its bottom edge, then back along its top."""
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        ex, ey, ez = self.eye
        faces = []
        if ey > y1:
            faces.append((TOP, ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1))))
        if ez < z0:
            faces.append(((0, -1), ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0))))
        if ez > z1:
            faces.append(((0, 1), ((x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1))))
        if ex < x0:
            faces.append(((-1, 0), ((x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1))))
        if ex > x1:
            faces.append(((1, 0), ((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0))))
        return [(n, [self.at(*p) for p in pts]) for n, pts in faces if shown is None or shown(n)]

    def block_rect(self, x, z, y) -> pygame.Rect:
        key = ("b", x, z, y)
        if key not in self.rects:
            self.rects[key] = bbox([self.at(x + a, y + h, z + b) for a in (0, 1) for b in (0, 1) for h in (0, 1)])
        return self.rects[key]

    def sun_shadow(self, x, z, lo, hi) -> tuple:
        """(polygon, rect) of the shadow on the floor of the run of blocks lo to hi high in cell (x, z)."""
        key = ("sun", x, z, lo, hi)
        if key not in self.rects:
            sx, sz = self.sun
            square = ((x, z), (x + 1, z), (x + 1, z + 1), (x, z + 1))
            poly = [self.at(px, 0, pz) for px, pz in hull([(px + sx * h, pz + sz * h) for px, pz in square for h in (lo, hi + 1)])]
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
    """One camera and one set of blocks {(x, z, y): color}, sorted far to near once. `row` marks the
    cursor's row (a stripe on the floor, a ribbon on its blocks) and splits the blocks into the ones
    behind it, on it and in front of it, so the cursor can be drawn between them."""

    def __init__(self, cam: Camera, blocks: dict, row=None, hazy: bool = True, detail: bool = True, floor=None):
        self.cam, self.blocks, self.row, self.hazy, self.detail = cam, blocks, row, hazy, detail
        self.floor = floor or screen_floor()
        items = []
        for (x, z, y), color in blocks.items():
            items.append((cam.key(x, z, y), 0, (x, z, y, color)))
            if detail and y and (x, z, y - 1) not in blocks:
                ground = max((h + 1 for h in range(y) if (x, z, h) in blocks), default=0)
                items.append((cam.key(x, z, ground - 0.5), 1, (x, z, ground, y, color)))
        items.sort(key=itemgetter(0))
        self.items, self._sun = items, None
        self._split()

    def on_row(self, row) -> "Painter":
        """The same blocks, already sorted, with the cursor on another row."""
        other = copy.copy(self)
        other.row = row
        other._split()
        return other

    def _split(self):
        row, items = self.row, self.items
        if row is None:
            self.behind, self.on_row_items, self.in_front = items, [], []
        else:
            self.behind = [i for i in items if i[2][1] > row]
            self.on_row_items = [i for i in items if i[2][1] == row]
            self.in_front = [i for i in items if i[2][1] < row]
        self.front_blocks = [i[2] for i in self.in_front if i[1] == 0]

    # ------------------------------------------------------------ colors
    def base(self, x, z, color) -> tuple:
        return haze(color, self.cam.row(x, z)) if self.hazy else rgb(color)

    def face(self, base, normal, y) -> tuple:
        if normal is TOP:
            return tint(base, "#ffffff", round(TOP_LIGHT + TOP_LIGHT_PER_LEVEL * y, 3))
        return tint(base, "#000000", self.cam.dark[normal])

    def tile(self, x, z) -> tuple:
        color = rgb(self.floor[2] if (x + z) % 2 else self.floor[1])
        return tint(color, P.TEXT, STRIPE_ALPHA / 255) if z == self.row else color

    # ------------------------------------------------------------ painting
    def paint_floor(self, surf):
        """The slab's sides, then the checkerboard: one fill for the floor, then every other tile."""
        cam, (_, tile, alt, slab_front, slab_side) = self.cam, self.floor
        for n, poly in cam.box((0, -SLAB, 0), (WIDTH, 0, DEPTH), shown=lambda n: n is not TOP):
            pygame.draw.polygon(surf, rgb(slab_front if n == (0, -1) else slab_side), poly)
        pygame.draw.polygon(surf, rgb(tile), [cam.at(0, 0, 0), cam.at(WIDTH, 0, 0), cam.at(WIDTH, 0, DEPTH), cam.at(0, 0, DEPTH)])
        for x in range(WIDTH):
            for z in range(1 - x % 2, DEPTH, 2):
                pygame.draw.polygon(surf, rgb(alt), self._tile_poly(x, z))

    def floor_picture(self, size) -> pygame.Surface:
        """The floor on its ground color, painted once per camera."""
        if self.cam.floor is None:
            self.cam.floor = pygame.Surface(size)
            self.cam.floor.fill(rgb(self.floor[0]))
            self.paint_floor(self.cam.floor)
        return self.cam.floor

    def stripe(self) -> tuple:
        """(picture, where) of the light wash over the cursor row's floor, kept by the camera."""
        key = ("stripe", self.row)
        if key not in self.cam.rects:
            polys = [self._tile_poly(x, self.row) for x in range(WIDTH)]
            rect = bbox([p for poly in polys for p in poly])
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            for poly in polys:
                pygame.draw.polygon(s, (*rgb(P.TEXT), STRIPE_ALPHA), [(px - rect.x, py - rect.y) for px, py in poly])
            self.cam.rects[key] = s, rect.topleft
        return self.cam.rects[key]

    def _tile_poly(self, x, z) -> list:
        at = self.cam.at
        return [at(x, 0, z), at(x + 1, 0, z), at(x + 1, 0, z + 1), at(x, 0, z + 1)]

    def paint_sun(self, surf, clip=None):
        """Each run of blocks' shadow on the floor, away from the light, in one see-through layer so overlaps don't darken twice."""
        area = clip or surf.get_rect()
        shadows = [poly for poly, rect in self._sun_shadows() if rect.colliderect(area)]
        if shadows:
            layer = pygame.Surface(area.size, pygame.SRCALPHA)
            for poly in shadows:
                pygame.draw.polygon(layer, (*SUN_INK, 255), [(px - area.x, py - area.y) for px, py in poly])
            layer.set_alpha(SUN_ALPHA)
            surf.blit(layer, area.topleft)

    def _sun_shadows(self) -> list:
        """(polygon, rect) of each run of touching blocks' shadow, the camera remembering each run's."""
        if self._sun is None:
            runs = []
            for x, z, y in sorted(self.blocks):
                if runs and runs[-1][:2] == (x, z) and runs[-1][3] == y - 1:
                    runs[-1][3] = y
                else:
                    runs.append([x, z, y, y])
            self._sun = [self.cam.sun_shadow(*run) for run in runs]
        return self._sun

    def paint(self, surf, items, clip=None, faded=frozenset(), stamp=False):
        """Blocks and the shadows under floating ones, in paint order; with `clip`, only what touches it.
        Columns in `faded` go see-through, replacing what is under them in `surf`. With `stamp`, solid
        blocks are pictures the camera keeps, so a repaint redraws only blocks that changed."""
        cam = self.cam
        for _, kind, d in items:
            if clip is not None and not (cam.block_rect(*d[:3]) if kind == 0 else self._shadow_rect(*d[:4])).colliderect(clip):
                continue
            alpha = FRONT_ALPHA if d[:2] in faded else 255
            if kind == 1:
                self.shadow(surf, *d, alpha=alpha if alpha < 255 else None)
            elif stamp and alpha == 255:
                picture = self._stamp(*d)
                if picture:
                    surf.blit(*picture)
            else:
                self.block(surf, *d, alpha=alpha)

    def _stamp(self, x, z, y, color):
        """(picture, where) of a block as `block` draws it, kept by the camera until its look changes;
        None for a block with no face to show, buried in the build."""
        key = ("stamp", x, z, y, color, self._shown(x, z, y), z == self.row)
        stamps = self.cam.rects
        if key not in stamps:
            if len(stamps) > STAMPS_KEPT:
                stamps.clear()
            rect = self.cam.block_rect(x, z, y)
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            stamps[key] = (s, rect.topleft) if self.block(s, x, z, y, color, at=rect.topleft) else None
        return stamps[key]

    def _shown(self, x, z, y) -> tuple:
        """For each of SIDES, whether that face of block (x, z, y) is clear of a neighbor."""
        b = self.blocks
        return ((x, z, y + 1) not in b, (x, z - 1, y) not in b, (x, z + 1, y) not in b,
                (x - 1, z, y) not in b, (x + 1, z, y) not in b)

    def block(self, surf, x, z, y, color, alpha=255, solo=False, at=(0, 0)):
        """A block's faces the eye can see, those against a neighbor left out; `solo` draws it on its own (the cursor's).
        `at` is where `surf` sits in screen coordinates."""
        base, ribbon = self.base(x, z, color), not solo and z == self.row
        clear = self._shown(x, z, y)
        seam = rgb(P.LINE) if alpha == 255 else (*rgb(P.LINE), alpha)
        faces = self.cam.box((x, y, z), (x + 1, y + 1, z + 1), None if solo else lambda n: clear[SIDES.index(n)])
        for n, poly in faces:
            if at != (0, 0):
                poly = [(px - at[0], py - at[1]) for px, py in poly]
            color = self.face(base, n, y)
            pygame.draw.polygon(surf, color if alpha == 255 else (*color, alpha), poly)
            if ribbon and n in (TOP, (0, -1)):
                band = tint(color, P.TEXT, RIBBON_ALPHA / 255)
                p0, p1, p2, p3 = poly
                edge = [(lerp(a[0], b[0], t), lerp(a[1], b[1], t)) for a, b, t in
                        ((p0, p3, RIBBON_FROM), (p1, p2, RIBBON_FROM), (p1, p2, RIBBON_TO), (p0, p3, RIBBON_TO))]
                pygame.draw.polygon(surf, band if alpha == 255 else (*band, alpha), edge)
            if self.detail:
                pygame.draw.polygon(surf, seam, poly, 1)
        return bool(faces)

    def shadow(self, surf, x, z, ground, y, color, alpha=None):
        """The square a floating block casts straight down onto what it would land on, and a line up to the block.
        Mixed into what it covers, or with `alpha`, see-through onto a layer."""
        at = self.cam.at
        square = [at(x, ground, z), at(x + 1, ground, z), at(x + 1, ground, z + 1), at(x, ground, z + 1)]
        below = self.blocks.get((x, z, ground - 1))
        under = self.face(self.base(x, z, below), TOP, ground - 1) if below else self.tile(x, z)
        if alpha is None:
            fill = tint(under, "#000000", SHADOW_ALPHA / 255)
            stem = tint(tint(self.base(x, z, color), "#000000", STEM_DARKEN), art_room.CANVAS_BG, 1 - STEM_ALPHA / 255)
        else:
            fill = (0, 0, 0, min(alpha, SHADOW_ALPHA))
            stem = (*tint(self.base(x, z, color), "#000000", STEM_DARKEN), min(alpha, STEM_ALPHA))
        pygame.draw.polygon(surf, fill, square)
        if y > ground:
            pygame.draw.line(surf, stem, at(x + 0.5, ground, z + 0.5), at(x + 0.5, y, z + 0.5), 2)

    def _shadow_rect(self, x, z, ground, y) -> pygame.Rect:
        key = ("s", x, z, ground, y)
        rects = self.cam.rects
        if key not in rects:
            rects[key] = bbox([self.cam.at(x + a, ground, z + b) for a in (0, 1) for b in (0, 1)] + [self.cam.at(x + 0.5, y, z + 0.5)])
        return rects[key]

    def frame_row(self, surf):
        """An upright frame on the back of the cursor's row, floor to ceiling, wall to wall, so the row reads as one slice."""
        if self.row is not None:
            at, z = self.cam.at, self.row + 1
            ink = tint(rgb(art_room.CANVAS_BG), P.TEXT, FRAME_ALPHA / 255)
            pygame.draw.polygon(surf, ink, [at(0, 0, z), at(WIDTH, 0, z), at(WIDTH, HEIGHT, z), at(0, HEIGHT, z)], 2)
