# UI fonts

Vendored from IBM's Plex release and Google Fonts, all under the SIL Open Font License 1.1.

- Figtree (Regular 400, SemiBold 600, Bold 700): the sans face, for system screens like the
  live-boot welcome, glosses and family room text. The landing site's body font, so screen,
  site and box match. Static instances of the Google Fonts variable build, cut with
  `fonttools varLib.instancer Figtree[wght].ttf wght=400` (and 600, 700).
- IBM Plex Mono (Regular 400, SemiBold 600, Bold 700, Italic 400): the prompt line, code,
  every piece of chrome (titles, room tabs, keycaps, hints), and the menus (Parent Menu
  and Picker option lists). Plex is IBM's own face, so the DOS-era callback is literal, and
  it stays calm at small sizes. The italic sets the Parent Menu's section headers.
- Martian Mono Art (Bold): letters written on the Art grid. Martian Mono at
  wdth 112.5 / wght 700, instanced and widened 1.15x with fontTools so a normal
  lowercase fills a square cell without gaps. Press Start 2P is the old Art face.

Color emoji come from Noto Color Emoji, installed on the ISO by the
`fonts-noto-color-emoji` package. On a dev machine put `NotoColorEmoji.ttf`
in `~/.local/share/fonts/` (see `scripts/setup_dev.sh`).
- Symbols Nerd Font Mono (Regular, SIL Open Font License 1.1): the UI icon
  glyphs (room marks, volume, broom, rewind, robot, battery). Icons-only build,
  so any chrome string can embed an `ICON_*` codepoint and it renders mono-tinted
  in the surrounding text color. Sits between the requested face and DejaVu in
  the fallback chain (`gfx.FALLBACK_FACES`).
- DejaVu Sans (Bitstream Vera license, free to redistribute): fallback for
  arrows and shapes the families above don't carry (← ⇥ ▲ ● ░ ♪).
