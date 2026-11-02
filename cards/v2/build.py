"""Build the Purple 2.0 box cards from Typst: one 2-page PDF per card, plus PNG previews.

  python cards/v2/build.py            # every card -> cards/v2/out/<card>.pdf and <card>-pad.pdf
  python cards/v2/build.py code       # just one card
  python cards/v2/build.py --png      # also write PNG previews to /tmp/screenshots

Needs the `typst`, `qrcode` and `pymupdf` pip packages. Fonts come from the app's own
font folder (Figtree, IBM Plex Mono) plus Sora in cards/v2/fonts, the landing site's headline font.
"""

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF
import qrcode
import qrcode.image.svg
import typst

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FONTS = ROOT / "purple_tui" / "canvas" / "fonts"
OUT = HERE / "out"
CARDS = ("start", "quick-start", "play", "parents")
QRS = {"help-qr.svg": "https://purplecomputer.org/help", "studio-qr.svg": "https://studio.purplecomputer.org/"}
QR_COLOR = "#3b1a5c"
PAPER = "#faf8f5"  # theme.typ paper

sys.path.insert(0, str(HERE.parent))
from add_bleed import add_bleed  # noqa: E402


def write_qrs() -> None:
    for name, url in QRS.items():
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage, border=0, box_size=10)
        svg = img.to_string(encoding="unicode").replace('fill="#000000"', f'fill="{QR_COLOR}"')
        (HERE / name).write_text(svg.replace('<rect fill="white"', '<rect fill="none"'))


def build(name: str, png_dir: Path | None) -> None:
    pdf = OUT / f"{name}.pdf"
    typst.compile(str(HERE / f"{name}.typ"), output=str(pdf), root=str(HERE), font_paths=[str(FONTS), str(HERE / "fonts")])
    add_bleed(pdf, OUT / f"{name}-pad.pdf", 0.0, 0.125, PAPER, "none", "#5c2d91", 0.12)
    if png_dir:
        for i, page in enumerate(fitz.open(pdf)):
            page.get_pixmap(dpi=150).save(png_dir / f"card-{name}-{i + 1}.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cards", nargs="*", default=CARDS)
    ap.add_argument("--png", nargs="?", const="/tmp/screenshots", help="write PNG previews here")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    png_dir = Path(args.png) if args.png else None
    if png_dir:
        png_dir.mkdir(parents=True, exist_ok=True)
    write_qrs()
    for name in args.cards:
        build(name, png_dir)


if __name__ == "__main__":
    main()
