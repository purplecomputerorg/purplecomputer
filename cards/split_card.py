"""Split the 4-page postcard PDF into its installation (1-2) and guide (3-4) halves.

Outputs are named after the input stem, so it works on the trim file and the
bleed file alike:

  just python cards/split_card.py                      # purple-{installation,guide}.pdf
  just python cards/split_card.py cards/purple-bleed.pdf  # purple-bleed-{installation,guide}.pdf
"""

import argparse
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent

PARTS = (("installation", 0, 1), ("guide", 2, 3))


def split(src_path) -> list[Path]:
    src_path = Path(src_path)
    src = fitz.open(src_path)
    needed = max(last for _, _, last in PARTS) + 1
    if src.page_count < needed:
        src.close()
        raise SystemExit(f"{src_path} has {src.page_count} pages, need {needed}")
    written = []
    for name, first, last in PARTS:
        part = fitz.open()
        part.insert_pdf(src, from_page=first, to_page=last)
        out = src_path.with_name(f"{src_path.stem}-{name}.pdf")
        part.save(out)
        part.close()
        print(f"Wrote {out} (pages {first + 1}-{last + 1})")
        written.append(out)
    src.close()
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", nargs="?", default=str(HERE / "purple.pdf"))
    split(ap.parse_args().input)


if __name__ == "__main__":
    main()
