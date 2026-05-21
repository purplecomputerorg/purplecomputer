"""Add print bleed (and an optional colored edge) to a postcard PDF.

Vistaprint's 4x6" postcard wants a 4.125x6.125" document: 0.0625" of bleed on
every side that gets trimmed off. This centers each trim-size page on a larger
bleed-size page and fills the new margin so the cut never shows a white sliver.

Edge modes (--edge):
  none      just the bleed, filled with --bg (clean, default)
  frame     a solid --edge-color band all around the edge
  gradient  --edge-color at the edge fading to --bg inward
  corners   short --edge-color L-marks bleeding off the four corners only

  just python cards/add_bleed.py                          # clean lavender bleed
  just python cards/add_bleed.py --edge corners           # purple corner marks
  just python cards/add_bleed.py --edge frame -o out.pdf in.pdf
"""

import argparse
from pathlib import Path

import fitz  # PyMuPDF

PT = 72.0
HERE = Path(__file__).resolve().parent


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _draw_edge(np, w, h, mode, bleed, edge_rgb, bg_rgb, visible_pt):
    """Draw the edge treatment on top of the placed page (outer margin only)."""
    band = bleed + visible_pt
    if mode == "corners":
        thick = bleed + visible_pt
        arm = bleed + 0.5 * PT  # 0.5" visible arm
        for hr, vr in (
            (fitz.Rect(0, 0, arm, thick), fitz.Rect(0, 0, thick, arm)),                  # TL
            (fitz.Rect(w - arm, 0, w, thick), fitz.Rect(w - thick, 0, w, arm)),          # TR
            (fitz.Rect(0, h - thick, arm, h), fitz.Rect(0, h - arm, thick, h)),          # BL
            (fitz.Rect(w - arm, h - thick, w, h), fitz.Rect(w - thick, h - arm, w, h)),  # BR
        ):
            np.draw_rect(hr, color=edge_rgb, fill=edge_rgb, width=0)
            np.draw_rect(vr, color=edge_rgb, fill=edge_rgb, width=0)
        return
    if mode == "frame":
        for rect in (fitz.Rect(0, 0, w, band), fitz.Rect(0, h - band, w, h),
                     fitz.Rect(0, 0, band, h), fitz.Rect(w - band, 0, w, h)):
            np.draw_rect(rect, color=edge_rgb, fill=edge_rgb, width=0)
        return
    # gradient: concentric rings, edge_rgb at the edge -> bg_rgb at band inner.
    # Solid edge color through the bleed so the cut edge stays fully colored.
    step = 0.5
    n = max(1, int(band / step))
    for i in range(n):
        dist = i * band / n
        t = 0.0 if dist <= bleed else min(1.0, (dist - bleed) / max(visible_pt, 1e-6))
        col = _lerp(edge_rgb, bg_rgb, t)
        rr = fitz.Rect(dist, dist, w - dist, h - dist)
        np.draw_rect(rr, color=col, width=band / n * 1.5)


def add_bleed(src_path, out_path, bleed_in, bg_hex, edge_mode, edge_hex, visible_in):
    bleed = bleed_in * PT
    bg = _rgb(bg_hex)
    edge = _rgb(edge_hex)
    visible_pt = visible_in * PT
    src = fitz.open(src_path)
    out = fitz.open()
    for page in src:
        r = page.rect
        w, h = r.width + 2 * bleed, r.height + 2 * bleed
        np = out.new_page(width=w, height=h)
        np.draw_rect(np.rect, color=bg, fill=bg, width=0)
        np.show_pdf_page(fitz.Rect(bleed, bleed, bleed + r.width, bleed + r.height),
                         src, page.number)
        if edge_mode != "none":
            _draw_edge(np, w, h, edge_mode, bleed, edge, bg, visible_pt)
    out.save(out_path)
    n = out.page_count
    out.close()
    src.close()
    print(f"Wrote {out_path} ({n} pages, {w/PT:.3f}x{h/PT:.3f} in, edge={edge_mode})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add print bleed to a postcard PDF.")
    ap.add_argument("input", nargs="?", default=str(HERE / "purple.pdf"))
    ap.add_argument("-o", "--output")
    ap.add_argument("--bleed", type=float, default=0.0625, help="bleed per side, inches")
    ap.add_argument("--bg", default="#fbf6ff", help="bleed/background fill color")
    ap.add_argument("--edge", choices=("none", "frame", "gradient", "corners"), default="none")
    ap.add_argument("--edge-color", default="#5c2d91")
    ap.add_argument("--edge-visible", type=float, default=0.12,
                    help="visible edge width inside the trim, inches")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.output) if args.output else src.with_name(src.stem + "-bleed.pdf")
    add_bleed(src, out, args.bleed, args.bg, args.edge, args.edge_color, args.edge_visible)


if __name__ == "__main__":
    main()
