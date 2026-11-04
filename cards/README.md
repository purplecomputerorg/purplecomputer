# Cards & Stickers

Print-ready vector art for Purple Computer's physical goods: the onboarding
cards and the sticker products. All scripts emit SVG first and (optionally)
a PDF via Inkscape; PDFs are what the print shop actually receives.

## Products

| Product | Script | Output | Size | Cut type |
|---|---|---|---|---|
| Keyboard sticker sheet (bi-fold) | `make_keyboard_sticker_sheet.py` | `keyboard-sticker-sheet.{svg,pdf}` | 12" × 4" unfolded → folds to 6" × 4" (two 4"×6" panels joined along their 4" edges) | Kiss-cut |
| Purple sticker sheet | `make_purple_sticker_sheet.py` | `purple-sticker-sheet.{svg,pdf}` | 4" × 6" | Kiss-cut |
| Purple-logo sticker | `make_purple_logo_sticker.py` | `purple-logo-sticker.{svg,pdf}` | 2.14" × 3.00" (silhouette) | Die-cut through liner |
| T-Rex sticker (standalone) | `make_trex_sticker.py` | `trex-sticker.{svg,pdf}` | 3" tall silhouette | Die-cut through liner |
| Lid badge (takes an Avery label) | `make_lid_badge.py` | `lid-badge-<variant>.{svg,pdf}` | 3.5" × 2.25" (standard name-badge size) | Kiss-cut |
| Name badge (written on directly) | `make_name_badge.py` | `name-badge-<variant>.{svg,pdf}` | 3.5" × 2.25" | Kiss-cut |

The T-Rex is also available on the purple sticker sheet; the standalone
script is kept for when we want to print it as a single die-cut.

### The two badges

Both are the same card, drawn from the same `badge_kit.py`: 3.5" × 2.25",
kiss-cut, rounded corner, purple field bleeding 0.125" past the cut.

**Lid badge** (`make_lid_badge.py`) reads "this computer belongs to" and
leaves a white window in the middle cut to the footprint of a stock **Avery
5160** label: 2.625" × 1", rounded corners, also sold as 8160/18660/5960, 30
per sheet. One design gets printed in quantity, then a label goes on the
window and the kid writes their name, so nothing is personalized at print
time. A hairline mount is drawn just outside the window, so a slightly
crooked label still lands inside a frame. Layouts: `crown`, `night`, `hero`,
`duo`, `serif`, `ticket`, `footer`. Print on white stock: the window is
unprinted material, not white ink.

The window is the label's exact footprint. `LABEL_INSET_IN` shrinks it a
little if hand-placed labels leave a white sliver down one side,
`MOUNT_GAP_IN` moves the hairline, and `LABEL_W_IN`/`LABEL_H_IN`/`LABEL_R_IN`
retarget a different Avery part. Measure the corner radius off a real sheet
before a long run.

**Name badge** (`make_name_badge.py`) writes the whole line onto the sticker
instead, with a rule to fill in by hand: `sentence`, `stagger`, `age`.

Either script takes a layout name as its first argument, or `all` (the
default). `--png DIR` writes one preview per layout and `--sheet out.png`
tiles them onto a single image for picking between them.

The lid badge layouts use the site's own faces (Sora, Figtree, Spectral) alongside Nunito; the name badge is Nunito only.
Those TTFs live in `~/landing/public/fonts`; copy them into
`~/.local/share/fonts` and run `fc-cache` to render locally. PDF export turns
text into paths, so the print shop needs none of them.

Run any of them:

```bash
just python cards/make_keyboard_sticker_sheet.py --pdf
```

Omit `--pdf` to write SVG only.

## Print-shop spec we target

- **Cut path layer** named `cut`, 1-pixel magenta (`#FF00FF`) stroke. (Inkscape's PDF export doesn't preserve OCG layer names, so the printer identifies the cut by color + stroke width.)
- **Cut paths ≥ 0.25"** apart from each other.
- **Bleed 0.125"** wherever printed color touches the cut line (purple sticker sheet, filled-badge logo variant). Transparent-background stickers need no bleed.
- Text is exported to paths (`--export-text-to-path`) so the printer doesn't need our font installed.

## Design conventions across all products

Geometry, palette, fonts, the bot, and the page/cut assembly for the two
badges live in `badge_kit.py`; the badge scripts hold only their layouts.

- **Layers**: `art` (everything visible), `cut` (die/kiss-cut paths), optional `guides` (dev-reference page border — not for printing).
- **Purple ramp** (dark → light): `#1e1033`, `#3b1a5c`, `#5c2d91`, `#9b59d0`, `#ebe2fd`.
- **Brand font**: Nunito (weights 500, 700, 800); the lid badge also uses the site faces noted above. Installed under `~/.local/share/fonts/Nunito/` if you need to re-render locally. Fallback chain in SVGs is `Nunito, Helvetica, Arial, sans-serif`.
- **Kid-math remaps on keyboard sheet**: `=` shows `+`, `/` shows `÷`, shift-`8` shows `×` — matches the global remap in `purple_tui/purple_tui.py`.

## Silhouette cutting (stickers that hug art)

`make_purple_sticker_sheet.py`, `make_trex_sticker.py`, and the silhouette
variant of `make_purple_logo_sticker.py` generate their cut paths from the
source SVG via `shapely` + `svgpathtools`:

1. Parse every `<path>`, splitting multi-subpath `d` attributes into
   continuous subpaths so small features (T-Rex arm, turtle feet, bot
   antenna stems, etc.) become their own polygons.
2. Union them + any `<circle>` and stroked `<line>` elements into a single
   silhouette.
3. `.buffer(pad)` outward to produce the cut path.

Tweak `PAD_IN` at the top of each script to trade off tight silhouette
fidelity vs. kiss-cut safety (industry-safe minimum is ~2mm = 0.08").

## Source artwork

- **Bot** (`assets/logo.svg`) — original, in-house.
- **Emoji characters** (T-Rex, ringed planet, Earth, turtle, sun-with-face, and Studio's section and room icons from `make_studio_icons.py`) — sourced from [jdecked/twemoji](https://github.com/jdecked/twemoji) under CC-BY 4.0, recolored to the purple ramp at render time. Raw sources live next to the scripts as `trex-source.svg` and `twemoji-*.svg`. Attribution lives in the main project `README.md` "Third-Party Credits" section.

## Iterating

Preview an SVG quickly as PNG:

```bash
inkscape cards/purple-sticker-sheet.svg \
  --export-type=png \
  --export-filename=/tmp/preview.png \
  --export-width=1200 \
  --export-background=white
```

Each script keeps its tunable constants at the top of the file. Common
knobs: `BG_COLOR`, `PAD_IN`, `BLEED_IN`, `HALO_OUT_IN`, sticker placement
lists, and the `PURPLE_RAMP` auto-recolor palette.

## Purple 2.0 box cards (`v2/`)

The box cards for Purple 2.0 are Typst sources, so an LLM can edit them and you can too. Four numbered two-sided 4x6 cards: 1 `start.typ` (booting from the Purple Key), 2 `rooms.typ` (the rooms, then cool things to try), 3 `type.typ` (things to type in Play, then code in Art, Music and Blocks), and 4 `grown-ups.typ` (the Parent Menu, then Purple Studio). Each card has its own color and number (`SET` in `theme.typ`), and every side's footer lists the whole set with that card filled in. A back is any side whose `header()` gets a `title:`; it says Back and wears a softer number. They share `theme.typ` for colors, keycaps and panels, in the landing site's palette. Text is Purple's own Figtree and IBM Plex Mono from `purple_tui/canvas/fonts/`; titles are Sora, from `v2/fonts/`.

```bash
just cards          # or: just cards rooms
```

Each card becomes `v2/out/<card>.pdf` (4x6 trim) and `<card>-pad.pdf` (0.125" safety pad, via `add_bleed.py`); `all.pdf` and `all-pad.pdf` hold the whole set in order for review. The QR codes are generated on every build.
