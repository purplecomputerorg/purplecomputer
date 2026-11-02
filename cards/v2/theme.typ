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

// The box set in order. Kid cards wear the red and blue sticker rows (purple_tui/palette.py).
#let SET = (
  (name: "Start", color: purple),
  (name: "Rooms", color: rgb("#E44444")),
  (name: "Type", color: rgb("#2E6AE1")),
  (name: "Grown-ups", color: magenta),
)
#let card-n = state("card-n", 1)
#let tint(c) = c.lighten(93%)

#let card(n, body) = {
  set page(width: 4in, height: 6in, margin: (x: 0.25in, top: 0.24in, bottom: 0.22in), fill: tint(SET.at(n - 1).color))
  set text(font: "Figtree", size: 9pt, fill: ink)
  set par(leading: 0.68em, spacing: 0.95em)
  set strong(delta: 250)
  card-n.update(n)
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

// The card's number in its color; every header and the set strip draw it
#let card-dot(n, r, on: true) = {
  let c = SET.at(n - 1).color
  box(circle(radius: r, fill: if on { c } else { c.lighten(80%) },
    align(center + horizon, text(font: "Sora", weight: "extrabold", size: r * 1.15, fill: if on { white } else { c.darken(15%) }, str(n)))))
}

// Fronts leave the title out to use the card's name
#let header(title: none, qr: "help-qr.svg", note: [Videos and help: #text(fill: purple)[purplecomputer.org/help]]) = context {
  let n = card-n.get()
  grid(
    columns: (0.46in, 1fr, auto),
    column-gutter: 8pt,
    align: (left + horizon, left + horizon, right + horizon),
    card-dot(n, 0.23in),
    stack(
      text(weight: "bold", size: 6.6pt, fill: SET.at(n - 1).color.darken(10%), tracking: 0.14em, upper[Purple Computer #sym.dot.c Card #n of #SET.len()]),
      v(7pt),
      display(if title == none { SET.at(n - 1).name } else { title }),
      ..if note != none { (v(8pt), text(size: 7.2pt, fill: ink-dim, note)) },
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
// The whole set, this card filled in, so a missing card is easy to spot
#let set-strip = context {
  let n = card-n.get()
  SET.enumerate().map(((i, c)) => {
    let on = i + 1 == n
    box[#card-dot(i + 1, 4.4pt, on: on)#h(2pt)#text(size: 6.8pt, weight: if on { "bold" } else { "regular" }, fill: if on { ink } else { ink-dim }, c.name)]
  }).join(h(4pt))
}
#let footer(end: []) = text(size: 8pt, fill: ink-med, grid(columns: (1fr, auto), align: (left + horizon, right + horizon), set-strip, end))
#let flip(body) = footer(end: [#body #h(3pt) #text(fill: magenta, weight: "bold", sym.arrow.r)])
#let support = footer(end: text(size: 7.4pt, fill: purple, weight: "semibold")[support\@purplecomputer.org])

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
