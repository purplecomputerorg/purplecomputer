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

The T-Rex is also available on the purple sticker sheet; the standalone
script is kept for when we want to print it as a single die-cut.

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

- **Layers**: `art` (everything visible), `cut` (die/kiss-cut paths), optional `guides` (dev-reference page border — not for printing).
- **Purple ramp** (dark → light): `#1e1033`, `#3b1a5c`, `#5c2d91`, `#9b59d0`, `#ebe2fd`.
- **Brand font**: Nunito (weights 500, 700, 800). Installed under `~/.local/share/fonts/Nunito/` if you need to re-render locally. Fallback chain in SVGs is `Nunito, Helvetica, Arial, sans-serif`.
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

- **Bot** (`logo.svg`) — original, in-house.
- **Emoji characters** (T-Rex, ringed planet, Earth, turtle, sun-with-face) — sourced from [jdecked/twemoji](https://github.com/jdecked/twemoji) under CC-BY 4.0, recolored to the purple ramp at render time. Raw sources live next to the scripts as `trex-source.svg` and `twemoji-*.svg`. Attribution lives in the main project `README.md` "Third-Party Credits" section.

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
