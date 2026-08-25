# UI fonts

Vendored latin subsets from Google Fonts, all under the SIL Open Font License 1.1.

- Nunito Sans (Regular 400, Bold 700, ExtraBold 800): labels, tiles, replies.
- JetBrains Mono (Regular 400, SemiBold 600): the prompt line and code.

Color emoji come from Noto Color Emoji, installed on the ISO by the
`fonts-noto-color-emoji` package. On a dev machine put `NotoColorEmoji.ttf`
in `~/.local/share/fonts/` (see `scripts/setup_dev.sh`).
- DejaVu Sans (Bitstream Vera license, free to redistribute): fallback for
  arrows and shapes the two families above don't carry (← ⇥ ▲ ● ░ ♪).
