"""Add print bleed and/or safety padding (and an optional colored edge) to a postcard PDF.

Two knobs, for the two kinds of print shop:

  --pad    (the default, 0.125") keeps the page at exactly 4x6 and shrinks the
           art inward. For upload flows that print at 4x6 with their own margin
           or crop, like FedEx Office, where an oversize page gets scaled or
           clipped and we have no say in where the cut lands.
  --bleed  grows the page outward past the 4x6 trim instead, and drops the
           padding unless you ask for both. For shops that print oversize and
           cut, like Vistaprint (needs >=0.0625"; 0.125" matches the sticker
           sheets).

Padding is one uniform scale for both axes, so an inch of pad on the short side
is the same fraction of the page on the long side: 0.125" of --pad on a 4x6
leaves 0.125" at the sides and 0.1875" top and bottom. The background is a flat
fill either way, so padding is invisible unless something crops; it only ever
costs a slightly smaller design.

Edge modes (--edge):
  none      just the bleed, filled with --bg (clean, default)
  frame     a solid --edge-color band all around the edge
  gradient  --edge-color at the edge fading to --bg inward
  corners   short --edge-color L-marks bleeding off the four corners only

  just print-card                                  # 4x6 with safety padding (FedEx upload)
  just print-card --bleed 0.125                    # 4.25x6.25 bleed, for a trim-and-cut shop
  just print-card --edge corners                   # purple corner marks
  just print-card --edge frame -o out.pdf in.pdf

The bleed file is also split into its installation (pages 1-2) and guide
(pages 3-4) halves, matching what the upload sends to the files host.
"""

import argparse
from pathlib import Path

import fitz  # PyMuPDF

from split_card import split

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


def add_bleed(src_path, out_path, bleed_in, pad_in, bg_hex, edge_mode, edge_hex, visible_in):
    bleed = bleed_in * PT
    pad = pad_in * PT
    bg = _rgb(bg_hex)
    edge = _rgb(edge_hex)
    visible_pt = visible_in * PT
    src = fitz.open(src_path)
    out = fitz.open()
    for page in src:
        r = page.rect
        w, h = r.width + 2 * bleed, r.height + 2 * bleed
        # One scale for both axes, so an inch of pad on the short side stays the
        # same fraction of the page on the long side (no squash, no crop).
        scale = min((r.width - 2 * pad) / r.width, (r.height - 2 * pad) / r.height)
        cw, ch = r.width * scale, r.height * scale
        np = out.new_page(width=w, height=h)
        np.draw_rect(np.rect, color=bg, fill=bg, width=0)
        np.show_pdf_page(fitz.Rect((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2),
                         src, page.number)
        if edge_mode != "none":
            _draw_edge(np, w, h, edge_mode, bleed, edge, bg, visible_pt)
    out.save(out_path)
    n = out.page_count
    out.close()
    src.close()
    print(f"Wrote {out_path} ({n} pages, {w/PT:.3f}x{h/PT:.3f} in, "
          f"art {(w - cw)/2/PT:.3f}x{(h - ch)/2/PT:.3f} in from edge, edge={edge_mode})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add print bleed to a postcard PDF.")
    ap.add_argument("input", nargs="?", default=str(HERE / "purple.pdf"))
    ap.add_argument("-o", "--output")
    ap.add_argument("--bleed", type=float,
                    help="grow the page past the trim by this much per side, inches "
                         "(default 0; passing it defaults --pad to 0)")
    ap.add_argument("--pad", type=float,
                    help="shrink the art inside the page by this much per side, inches, "
                         "default 0.125 (negative overscans it off the edge)")
    ap.add_argument("--bg", default="#fbf6ff", help="bleed/background fill color")
    ap.add_argument("--edge", choices=("none", "frame", "gradient", "corners"), default="none")
    ap.add_argument("--edge-color", default="#5c2d91")
    ap.add_argument("--edge-visible", type=float, default=0.12,
                    help="visible edge width inside the trim, inches")
    ap.add_argument("--no-split", action="store_true",
                    help="skip the installation/guide halves")
    args = ap.parse_args()

    # Asking for bleed means you want a trim-and-cut file, so it drops the padding
    # unless you also ask for that explicitly.
    bleed = args.bleed or 0.0
    pad = args.pad if args.pad is not None else (0.0 if args.bleed else 0.125)

    src = Path(args.input)
    out = (Path(args.output) if args.output
           else src.with_name(f"{src.stem}{'-bleed' if bleed else '-pad'}.pdf"))
    add_bleed(src, out, bleed, pad, args.bg, args.edge, args.edge_color, args.edge_visible)
    if not args.no_split:
        split(out)


if __name__ == "__main__":
    main()
