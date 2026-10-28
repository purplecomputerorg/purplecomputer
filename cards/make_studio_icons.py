#!/usr/bin/env python3
"""Purple Studio's emoji icons: Twemoji recolored to the purple sticker sheet's ramp.

Output: studio/src/icons/<codepoints>.svg, named as Twemoji names them. Studio shows these in place
of the emoji wherever it has one (studio/src/ui/icons.ts). Twemoji source (CC-BY 4.0) attributed in README.
"""

import re
from pathlib import Path

from make_purple_sticker_sheet import recolor

CARDS = Path(__file__).parent
OUT = CARDS.parent / "studio/src/icons"

# Studio's sections, then its starter rooms.
EMOJI = "🖼️ 🎙️ 🗨️ 🎹 🎨 🧩 🗺️ 📖 🃏 🌻 🥁 🐍 ✏️ 🧱 ❓".split()

SHORT_HEX = re.compile(r"#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])\b")


def code(emoji: str) -> str:
    return "-".join(f"{ord(c):x}" for c in emoji if c != "️")


def main():
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for emoji in EMOJI:
        svg = (CARDS / f"twemoji-{code(emoji)}.svg").read_text()
        svg = SHORT_HEX.sub(lambda m: "#" + "".join(c * 2 for c in m.groups()), svg)
        (OUT / f"{code(emoji)}.svg").write_text(recolor(svg))
    print(f"wrote {len(EMOJI)} icons to {OUT}")


if __name__ == "__main__":
    main()
