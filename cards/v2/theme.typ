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

// The box set in order. After Start, cards wear the keyboard's sticker rows (purple_tui/palette.py).
#let SET = (
  (name: "Start", color: purple),
  (name: "Rooms", color: rgb("#E44444")),
  (name: "Code", color: rgb("#2E6AE1")),
  (name: "Grown-ups", color: rgb("#C4A81C")),
)
#let card-n = state("card-n", 1)
#let tint(c) = c.lighten(88%)

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
// The app's own Nerd Font icons (purple_tui/constants.py), so the card matches the screen
#let icon(cp, fill: purple) = text(font: "Symbols Nerd Font Mono", fill: fill, cp)
#let ICONS = (
  art: "\u{F03D8}", music: "\u{F001}", play: "\u{F0B79}", blocks: "\u{F01A7}",
  time-travel: "\u{F02DA}", save: "\u{F0193}", open: "\u{F0770}", code: "\u{F06A9}", write: "\u{F03EA}",
  // The Parent Menu has no icons on screen; these are picked from the same font
  install: "\u{F02CA}", kids: "\u{F000E}", rooms: "\u{F003B}", littles: "\u{F18FB}",
  sound: "\u{F057E}", pin: "\u{F033E}", printing: "\u{F042A}",
)
// Studio's own section icons (studio/src/main.ts SECTIONS, drawn from studio/src/icons)
#let studio-icon(code) = box(baseline: 15%, image("/studio/src/icons/" + code + ".svg", height: 1em))
// A key wearing its real sticker color (purple_tui/palette.py KEY_COLORS)
#let sticker(k, hex, ink: purple-dk) = box(inset: (x: 0.36em), outset: (y: 0.24em), radius: 2.6pt, fill: rgb(hex),
  text(font: "Figtree", weight: "bold", size: 0.86em, fill: ink, k))

// What a kid types, like Purple's code line
#let typed(s, color: purple) = box(
  inset: (x: 0.38em),
  outset: (y: 0.26em),
  radius: 2.6pt,
  fill: color.lighten(91%),
  text(font: "IBM Plex Mono", weight: "medium", size: 0.9em, fill: color.darken(22%), s),
)

#let badge(n, color: purple, r: 6.2pt) = box(
  circle(radius: r, fill: color.lighten(76%), stroke: none,
    align(center + horizon, text(font: "Sora", weight: "extrabold", size: r * 1.13, fill: color.darken(10%), str(n)))),
)

// A badge beside its content, centered on a one-line body; every numbered row goes through here
// Top-aligned, the badge is raised to center on the body's first 9pt line
#let numbered(n, color: purple, r: 6.2pt, valign: horizon, body) = grid(
  columns: (2 * r, 1fr), column-gutter: r + 1pt, align: (center + valign, left + valign),
  if valign == top { move(dy: 3.1pt - r, badge(n, color: color, r: r)) } else { badge(n, color: color, r: r) }, body,
)
#let steps(color: purple, spacing: 9pt, r: 6.2pt, valign: horizon, ..items) = stack(
  spacing: spacing,
  ..items.pos().enumerate().map(((i, b)) => numbered(i + 1, color: color, r: r, valign: valign, b)),
)

// The card's number in its color; every header and the set strip draw it
#let card-dot(n, r, on: true) = {
  let c = SET.at(n - 1).color
  box(circle(radius: r, fill: if on { c } else { c.lighten(65%) },
    align(center + horizon, text(font: "Sora", weight: "extrabold", size: r * 1.15, fill: if on { white } else { c.darken(30%) }, str(n)))))
}

// Fronts leave the title out to use the card's name; a titled header is a back, with a softer dot
#let header(title: none, front: auto, qr: "help-qr.svg", note: [Videos and help: #text(fill: purple)[purplecomputer.org/help]]) = context {
  let n = card-n.get()
  let front = if front == auto { title == none } else { front }
  grid(
    columns: (0.46in, 1fr, auto),
    column-gutter: 8pt,
    align: (left + horizon, left + horizon, right + horizon),
    card-dot(n, 0.23in, on: front),
    stack(
      text(weight: "bold", size: 6.6pt, fill: SET.at(n - 1).color.darken(10%), tracking: 0.14em, upper(if front [Purple Computer #sym.dot.c Card #n of #SET.len()] else [Card #n of #SET.len() #sym.dot.c Back])),
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
#let panel(title: none, color: purple, n: none, icon: none, fill: white, body) = block(
  width: 100%,
  inset: (x: 9pt, top: 8pt, bottom: 9pt),
  radius: 8pt,
  fill: fill,
  stroke: 0.6pt + hair,
  breakable: false,
  {
    if title != none {
      let t = text(font: "Sora", weight: "semibold", size: 10pt, fill: color.darken(12%), title)
      let t = if n != none { numbered(n, color: color, t) } else { t }
      if icon != none { grid(columns: (1fr, auto), align: horizon, t, text(size: 10pt, fill: color, icon)) } else { t }
      v(1pt)
    }
    body
  },
)

// The one line under a front's header that says how to get there
#let intro(body) = text(size: 9.4pt, body)
#let note(body) = context block(width: 100%, inset: (x: 9pt, y: 8pt), radius: 8pt, fill: SET.at(card-n.get() - 1).color.lighten(76%), body)

// Space between a page's sections; every gap on a page is the same
#let gap = v(5pt) + v(1fr)
// The whole set, this card filled in, so a missing card is easy to spot
#let set-strip = context {
  let n = card-n.get()
  SET.enumerate().map(((i, c)) => {
    let on = i + 1 == n
    box[#card-dot(i + 1, 4.4pt, on: on)#h(2pt)#text(size: 6.8pt, weight: if on { "bold" } else { "regular" }, fill: if on { ink } else { ink-dim }, c.name)]
  }).join(h(4pt))
}
#let footer(end: []) = v(7pt) + text(size: 8pt, fill: ink-med, grid(columns: (1fr, auto), align: (left + horizon, right + horizon), set-strip, end))
#let flip(body) = footer(end: [#body #h(3pt) #text(fill: magenta, weight: "bold", sym.arrow.r)])
#let support = footer(end: text(size: 7.4pt, fill: purple, weight: "semibold")[support\@purplecomputer.org])

// A room's real result for a line, drawn by cards/v2/room_results.py at its true size
// Pictures center on the code line beside them; Play answers sit on it
#let result(code, room: "play") = box(baseline: if room == "play" { 20% } else { 50% - 0.3em }, image("results/" + room + "/" + lower(code).replace(regex("[^a-z0-9]+"), "-") + ".png"))
// Example rows that show their result: a Play line, or code in Art or Blocks
#let ex(code) = (code, result(code))
#let art(code) = (code, result(code, room: "art"))
#let blocks(code) = (code, result(code, room: "blocks"))

// Code examples: a typed line beside what it does; long lines take the whole row.
// `comments` styles the "what it does" as a code comment.
#let examples(color: purple, comments: false, first: auto, gutter: 10pt, ..rows) = {
  let say(d) = if comments {
    text(font: "IBM Plex Mono", style: "italic", size: 0.84em, fill: ink-dim)[\# #d]
  } else { text(fill: ink-med, d) }
  // An array is ways of typing the same thing
  let code(c) = if type(c) == array { c.map(typed.with(color: color)).join[ #text(fill: ink-dim)[or] ] } else { typed(c, color: color) }
  grid(
    columns: (first, 1fr),
    column-gutter: 8pt,
    row-gutter: gutter,
    align: (left + horizon, left + horizon),
    ..rows.pos().map(((c, d)) => if comments or (type(c) == str and c.len() > 16) {
      (grid.cell(colspan: 2)[#code(c) #h(5pt) #say(d)],)
    } else {
      (code(c), say(d))
    }).flatten(),
  )
}

// Rows split by hairlines; each row is an array of cells. The outer rows leave their edge
// padding to the panel around them.
#let ruled(columns: (1fr,), pad: 8pt, ..rows) = {
  let last = rows.pos().len() - 1
  grid(
    columns: columns,
    ..rows.pos().enumerate().map(((i, row)) => row.map(c => grid.cell(
      stroke: if i > 0 { (top: 0.5pt + hair) },
      inset: (top: if i > 0 { pad } else { 0pt }, bottom: if i < last { pad } else { 0pt }), c))).flatten(),
  )
}

// Titled tips. One column is a single ruled list, title then text on a line. More columns are
// small cards, title above text, each row as tall as its tallest card.
#let tip-title(t) = text(font: "Sora", weight: "semibold", size: 9pt, fill: purple.darken(8%), t)
#let tiles(cols: 1, gutter: 6pt, pad: 9pt, title: none, ..items) = if cols == 1 {
  panel(title: title, ruled(pad: pad, ..items.pos().map(((t, body, ..icon)) =>
    (grid(columns: (1fr, auto), column-gutter: 6pt, align: horizon, [#tip-title(t) #h(2pt) #body], ..icon),))))
} else { layout(size => {
  let w = (size.width - gutter * (cols - 1)) / cols
  let tile((t, body, ..icon), tall) = block(
    width: w, height: tall, inset: (x: 9pt, top: 7pt, bottom: 9pt), radius: 7pt, fill: white, stroke: 0.6pt + hair,
    [#grid(columns: (1fr, auto), align: horizon, tip-title(t), ..icon) #v(2pt) #text(fill: ink-med, body)],
  )
  grid(columns: (w,) * cols, gutter: gutter, ..items.pos().chunks(cols).map(row => {
    let tall = calc.max(..row.map(i => measure(tile(i, auto)).height))
    row.map(i => tile(i, tall))
  }).flatten())
}) }

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
