"""Build the Purple 2.0 box cards from Typst: one 2-page PDF per card, plus PNG previews.

  python cards/v2/build.py            # every card -> cards/v2/out/<card>.pdf and <card>-pad.pdf,
                                      # plus all.pdf and all-pad.pdf with every card in order,
                                      # and print-sheets.pdf for FedEx Office (see print_sheets)
  python cards/v2/build.py rooms      # just one card
  python cards/v2/build.py --png      # also write PNG previews to /tmp/screenshots

Needs the `typst`, `qrcode` and `pymupdf` pip packages. Fonts come from the app's own
font folder (Figtree, IBM Plex Mono) plus Sora in cards/v2/fonts, the landing site's headline font.
Room results on the cards (ex("..."), art("..."), blocks("...") in a .typ) are drawn by the app itself, see room_results.py.
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
CARDS = ("start", "rooms", "type", "grown-ups")
QRS = {"help-qr.svg": "https://purplecomputer.org/help", "studio-qr.svg": "https://studio.purplecomputer.org/"}
QR_COLOR = "#3b1a5c"

sys.path.insert(0, str(HERE.parent))
from add_bleed import _rgb, add_bleed  # noqa: E402
sys.path.insert(0, str(ROOT))
from room_results import render as render_results  # noqa: E402


def write_qrs() -> None:
    for name, url in QRS.items():
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage, border=0, box_size=10)
        svg = img.to_string(encoding="unicode").replace('fill="#000000"', f'fill="{QR_COLOR}"')
        (HERE / name).write_text(svg.replace('<rect fill="white"', '<rect fill="none"'))


def paper_color(pdf: Path) -> str:
    """Each card tints its own page in theme.typ; the pad fill matches its top-left pixel."""
    return "#%02x%02x%02x" % fitz.open(pdf)[0].get_pixmap(clip=fitz.Rect(0, 0, 1, 1)).pixel(0, 0)


def build(name: str, png_dir: Path | None) -> None:
    pdf = OUT / f"{name}.pdf"
    typst.compile(str(HERE / f"{name}.typ"), output=str(pdf), root=str(ROOT), font_paths=[str(FONTS), str(HERE / "fonts")])
    add_bleed(pdf, OUT / f"{name}-pad.pdf", 0.0, 0.125, paper_color(pdf), "none", "#5c2d91", 0.12)
    if png_dir:
        for i, page in enumerate(fitz.open(pdf)):
            page.get_pixmap(dpi=150).save(png_dir / f"card-{name}-{i + 1}.png")


def combine(suffix: str) -> None:
    """One PDF of the whole set, to scroll through when reviewing."""
    doc = fitz.open()
    for name in CARDS:
        if (OUT / f"{name}{suffix}.pdf").exists():
            doc.insert_pdf(fitz.open(OUT / f"{name}{suffix}.pdf"))
    doc.save(OUT / f"all{suffix}.pdf")


PT = 72
SHEET = fitz.Rect(0, 0, 8.5 * PT, 11 * PT)
BLEED = 0.125 * PT
MARK_GAP, MARK_LEN = 0.1875 * PT, 0.25 * PT
# Two cards per sheet, turned sideways (6x4 trim) and stacked with a 1" gap for crop marks
SLOTS = [fitz.Rect(1.25 * PT, y * PT, 7.25 * PT, (y + 4) * PT) for y in (1, 6)]


def crop_marks(page: fitz.Page, trim: fitz.Rect) -> None:
    for x, y, sx, sy in ((trim.x0, trim.y0, -1, -1), (trim.x1, trim.y0, 1, -1),
                         (trim.x0, trim.y1, -1, 1), (trim.x1, trim.y1, 1, 1)):
        page.draw_line((x, y + sy * MARK_GAP), (x, y + sy * (MARK_GAP + MARK_LEN)), color=(0, 0, 0), width=0.25)
        page.draw_line((x + sx * MARK_GAP, y), (x + sx * (MARK_GAP + MARK_LEN), y), color=(0, 0, 0), width=0.25)


def print_sheets() -> None:
    """FedEx Office: 8.5x11 portrait, 100 lb matte cover, double-sided, long-edge flip; trim to 4x6.

    Pages go front, back, front, back: two cards per sheet. A long-edge flip mirrors left and
    right, so each back turns the other way to keep its top on the same edge as its front's top.
    """
    out = fitz.open()
    for sheet in (CARDS[:2], CARDS[2:]):
        for side, rotate in (("FRONT", 270), ("BACK", 90)):
            page = out.new_page(width=SHEET.width, height=SHEET.height)
            page.insert_font(fontname="figtree", fontfile=str(FONTS / "Figtree-Regular.ttf"))
            for slot, name, letter in zip(SLOTS, sheet, "AB"):
                pdf = OUT / f"{name}.pdf"
                page.draw_rect(slot + (-BLEED, -BLEED, BLEED, BLEED), color=None, fill=_rgb(paper_color(pdf)), width=0)
                with fitz.open(pdf) as src:
                    page.show_pdf_page(slot, src, 0 if side == "FRONT" else 1, rotate=rotate)
                crop_marks(page, slot)
                page.insert_text((slot.x0 + 12, slot.y0 - BLEED - 4), f"{letter} {side}: {name}".upper(), fontname="figtree",
                                 fontsize=6, color=(0.55, 0.55, 0.55))
    out.save(OUT / "print-sheets.pdf", garbage=3, deflate=True)


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
    render_results([HERE / f"{name}.typ" for name in CARDS], HERE / "results")
    for name in args.cards:
        build(name, png_dir)
    for suffix in ("", "-pad"):
        combine(suffix)
    if all((OUT / f"{name}.pdf").exists() for name in CARDS):
        print_sheets()


if __name__ == "__main__":
    main()
