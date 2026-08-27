# UI fonts

Vendored from IBM's Plex release and Google Fonts, all under the SIL Open Font License 1.1.

- IBM Plex Sans (Regular 400, SemiBold 600, Bold 700): replies, dialog body text, tiles.
- IBM Plex Mono (Regular 400, SemiBold 600, Bold 700): the prompt line, code, and every
  piece of chrome (titles, room tabs, keycaps, hints). Plex is IBM's own face, so the
  DOS-era callback is literal, and it stays calm at small sizes.
- Press Start 2P (Regular): letters written on the Art grid. Every glyph is
  drawn on an em square, so one letter fills one cell and words stay even.

Color emoji come from Noto Color Emoji, installed on the ISO by the
`fonts-noto-color-emoji` package. On a dev machine put `NotoColorEmoji.ttf`
in `~/.local/share/fonts/` (see `scripts/setup_dev.sh`).
- DejaVu Sans (Bitstream Vera license, free to redistribute): fallback for
  arrows and shapes the families above don't carry (← ⇥ ▲ ● ░ ♪).
