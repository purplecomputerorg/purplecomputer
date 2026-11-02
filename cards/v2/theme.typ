// Shared look for the Purple 2.0 box cards: 4x6 portrait, the landing site's palette.
// Sora for titles, Figtree for text, IBM Plex Mono for keys and code.

#let paper = rgb("#f8f4fd")
#let ink = rgb("#352a4a")
#let ink-med = rgb("#6b5e7d")
#let ink-dim = rgb("#8f82a3")
#let hair = rgb("#e9e1f3")
#let purple = rgb("#5c2d91")
#let purple-dk = rgb("#3b1a5c")
#let magenta = rgb("#9b59d0")
#let lilac = rgb("#efe6fa")


#let card(body) = {
  set page(width: 4in, height: 6in, margin: (x: 0.25in, top: 0.24in, bottom: 0.22in), fill: paper)
  set text(font: "Figtree", size: 9pt, fill: ink)
  set par(leading: 0.68em, spacing: 0.95em)
  set strong(delta: 250)
  body
}

#let display(size: 17pt, fill: purple-dk, body) = text(font: "Sora", weight: "extrabold", size: size, fill: fill, tracking: -0.02em, body)
#let mono(s) = text(font: "IBM Plex Mono", weight: "semibold", size: 0.92em, fill: purple, s)

#let keycap(k, size: 0.8em) = box(
  inset: (x: 0.36em),
  outset: (y: 0.24em),
  radius: 2.6pt,
  fill: white,
  stroke: 0.6pt + rgb("#d6c8ea"),
  text(font: "Figtree", weight: "semibold", size: size, fill: purple-dk, k),
)
#let key(k) = keycap(k, size: 0.86em)
// A key wearing its real sticker color (purple_tui/palette.py KEY_COLORS)
#let sticker(k, hex) = box(inset: (x: 0.36em), outset: (y: 0.24em), radius: 2.6pt, fill: rgb(hex),
  text(font: "Figtree", weight: "bold", size: 0.86em, fill: purple-dk, k))

// What a kid types, like Purple's code line
#let typed(s, color: purple) = box(
  inset: (x: 0.38em),
  outset: (y: 0.26em),
  radius: 2.6pt,
  fill: color.lighten(91%),
  text(font: "IBM Plex Mono", weight: "medium", size: 0.9em, fill: color.darken(22%), s),
)

#let badge(n, color: purple, r: 6.2pt) = box(
  circle(radius: r, fill: color.lighten(86%), stroke: none,
    align(center + horizon, text(font: "Sora", weight: "extrabold", size: r * 1.13, fill: color.darken(10%), str(n)))),
)

// A badge beside its content, centered on a one-line body; every numbered row goes through here
#let numbered(n, color: purple, r: 6.2pt, valign: horizon, body) = grid(
  columns: (2 * r, 1fr), column-gutter: r + 1pt, align: (center + valign, left + valign),
  badge(n, color: color, r: r), body,
)
#let steps(color: purple, spacing: 9pt, r: 6.2pt, ..items) = stack(
  spacing: spacing,
  ..items.pos().enumerate().map(((i, b)) => numbered(i + 1, color: color, r: r, b)),
)

#let header(title, qr: "help-qr.svg", note: [Videos and help: #text(fill: purple)[purplecomputer.org/help]]) = {
  grid(
    columns: (0.46in, 1fr, auto),
    column-gutter: 8pt,
    align: (left + horizon, left + horizon, right + horizon),
    image("bot.svg", width: 0.46in),
    stack(
      text(weight: "bold", size: 6.6pt, fill: magenta, tracking: 0.14em, upper[Purple Computer]),
      v(7pt),
      display(title),
      v(8pt),
      text(size: 7.2pt, fill: ink-dim, note),
    ),
    if qr != none {
      box(inset: 4pt, radius: 6pt, fill: white, stroke: 0.6pt + hair, image(qr, width: 0.5in))
    },
  )
  v(5pt)
}

// A white card with a hairline; an optional accent title row
#let panel(title: none, color: purple, n: none, fill: white, body) = block(
  width: 100%,
  inset: (x: 9pt, top: 8pt, bottom: 9pt),
  radius: 8pt,
  fill: fill,
  stroke: 0.6pt + hair,
  breakable: false,
  {
    if title != none {
      let t = text(font: "Sora", weight: "semibold", size: 10pt, fill: color.darken(12%), title)
      if n != none { numbered(n, color: color, t) } else { t }
      v(1pt)
    }
    body
  },
)

#let note(body) = block(width: 100%, inset: (x: 9pt, y: 8pt), radius: 8pt, fill: lilac, body)

// Space between a page's sections; every gap on a page is the same
#let gap = v(1fr)
// Fronts point to the back on the right; backs point to the front on the left, beside support
#let arrow(dir) = text(fill: magenta, weight: "bold", if dir == "r" { sym.arrow.r } else { sym.arrow.l })
#let footer(start: [], end: []) = text(size: 8pt, fill: ink-med, grid(columns: (1fr, auto), align: (left, right), start, end))
#let flip(body) = footer(end: [#body #h(3pt) #arrow("r")])
#let support(front) = footer(
  start: [#arrow("l") #h(3pt) Back to #front],
  end: [#text(fill: purple, weight: "semibold")[support\@purplecomputer.org]],
)

// Code examples: a typed line beside what it does; long lines take the whole row
#let examples(color: purple, ..rows) = grid(
  columns: (auto, 1fr),
  column-gutter: 8pt,
  row-gutter: 10pt,
  align: (left + horizon, left + horizon),
  ..rows.pos().map(((c, d)) => if c.len() > 16 {
    (grid.cell(colspan: 2)[#typed(c, color: color) #h(5pt) #text(fill: ink-med, d)],)
  } else {
    (typed(c, color: color), text(fill: ink-med, d))
  }).flatten(),
)

// Titled tips as small cards: one column reads title then text on a line, two columns stack them
#let tiles(cols: 1, height: auto, gutter: 6pt, ..items) = grid(
  columns: (1fr,) * cols, gutter: gutter,
  ..items.pos().map(((title, body)) => block(
    width: 100%, height: height, inset: (x: 9pt, y: 9pt), radius: 7pt, fill: white, stroke: 0.6pt + hair, {
      let t = text(font: "Sora", weight: "semibold", size: 9pt, fill: purple.darken(8%), title)
      if cols == 1 [#t #h(2pt) #body] else [#t #v(-3pt) #text(fill: ink-med, body)]
    },
  )),
)

// A big physical-looking key: a white top sitting on a lilac base
#let bigkey(k, width: 0.6in, height: 0.4in, size: 12pt) = box(
  width: width, height: height, radius: 5pt, fill: rgb("#ddd0ef"),
  place(top, box(
    width: 100%, height: height - 2.5pt, radius: 5pt, fill: white, stroke: 0.7pt + rgb("#d2c3ea"),
    align(center + horizon, text(font: "Figtree", weight: "bold", size: size, fill: purple-dk, k)),
  )),
)

// A small rounded label
#let tag(body, color: magenta) = box(
  inset: (x: 5pt), outset: (y: 2.5pt), radius: 8pt, fill: color.lighten(88%),
  text(size: 7pt, weight: "bold", fill: color.darken(10%), tracking: 0.04em, body),
)

// Big keys in a centered row, with optional joiners like "+" between them
#let keyrow(gap: 6pt, ..items) = align(center, grid(
  columns: items.pos().len(), column-gutter: gap, align: center + horizon,
  ..items.pos().map(i => if type(i) == str { text(fill: ink-dim, size: 11pt, i) } else { i }),
))
