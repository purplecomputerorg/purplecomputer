#import "theme.typ": *
#show: card.with(1)

// ── Front: starting Purple from the Purple Key ──
#header()

#text(size: 11.5pt)[*Trying Purple doesn't change the laptop. Steps:*]
#gap

#let big-step(n, body) = numbered(n, r: 9pt, text(size: 11.5pt, body))
#stack(spacing: 7pt,
  big-step(1)[Turn off the laptop.],
  big-step(2)[Plug in the #text(weight: "bold", fill: purple)[Purple Key].],
)
#v(-2pt)
// Step 3's badge runs a rail down to the Mac and PC ways it owns
#let way(title, keys, body) = panel(title: title)[
  #set text(size: 8.6pt)
  #box(height: 1.40in, width: 100%)[
    #v(2pt)
    #keys
    #v(5pt)
    #body
  ]
]
#grid(
  columns: (9pt, 9pt, 1fr), column-gutter: (0pt, 10pt), row-gutter: 5pt,
  align: (x, y) => if y == 0 { horizon } else { top },
  grid.cell(colspan: 2, badge(3, r: 9pt)), text(size: 11.5pt)[Turn it on:],
  grid.vline(x: 1, start: 1, stroke: (paint: purple.lighten(76%), thickness: 1.6pt, cap: "round")),
  [], [],
  grid(
    columns: (1fr, 1fr), column-gutter: 6pt,
    way([Mac], keyrow(gap: 3pt, bigkey("Option", width: 0.55in, size: 10.5pt), "+", bigkey("Power", width: 0.53in, size: 10.5pt)))[
      Hold *Option* and press *Power*. Keep holding, then pick the orange drive #box(width: 1.9em, height: 0.75em, place(horizon, dy: 0.15em, image("orange-drive.svg", height: 1.6em)))
    ],
    way([PC], keyrow(bigkey("F12", width: 0.52in), bigkey("Esc", width: 0.52in)))[
      Press *Power*, then *mash these keys*. When menu appears, pick the USB drive.
      #v(1fr)
      #text(size: 7.2pt, fill: ink-med)[*Mash* = tap fast, nonstop]
    ],
  ),
)

#gap
#block(width: 100%, inset: (x: 11pt, y: 7pt), radius: 8pt, fill: white, stroke: 1.2pt + magenta.lighten(35%))[
  #grid(columns: (1fr, auto), column-gutter: 8pt, align: (left + horizon, right + horizon),
    [
      #text(font: "Sora", weight: "semibold", size: 10.5pt, fill: purple-dk)[Purple didn't appear?]
      #v(-3pt)
      #text(size: 8.8pt)[Some laptops use a different key, like *HP* and *Surface* laptops. Find yours on the back.]
      #v(2pt)
      #line(length: 100%, stroke: 0.6pt + hair)
      #v(-1pt)
      #text(size: 8.6pt)[To *install Purple for good*, see the back.]
    ],
    text(font: "Sora", weight: "extrabold", size: 13pt, fill: magenta)[Flip #sym.arrow.r],
  )
]
#gap
#footer()

#pagebreak()

// ── Back: which keys to mash ──
#header(title: [Find your laptop's key], qr: none, note: [Turn it off, press *Power*, then mash your brand's key.])
#gap

#panel[
  #let brands = (
    ("Dell, Lenovo, Acer", key("F12")),
    ("Samsung, LG", key("F10")),
    ("Sony", key("F11")),
    ("ASUS", key("Esc")),
    ("HP", [#key("Esc"), then #key("F9")]),
    ("Surface", [Hold *Volume Down*, press *Power*. Let go when the logo appears.]),
    ("Mac", [Hold #key("Option"), press *Power*. Let go when the drives appear.]),
    ("Mac, 2018 to 2020", [Needs a one-time security setting first: #box(text(fill: purple)[purplecomputer.org/mac])]),
  )
  #ruled(columns: (1.25in, 1fr), pad: 4pt, ..brands.map(((b, k)) => (text(weight: "semibold", b), k)))
]
#gap
#panel(title: [Or try another way, from inside Windows])[
  #steps(spacing: 6pt,
    [Click *Start*, then the *Power* icon],
    [Hold #key("Shift") and click *Restart*],
    [Choose *Use a device*, then the USB drive],
  )
]

#gap
#panel(title: [Like it? Install it])[
  Hold #key("Esc") for the Parent Menu, then choose *Install*. Purple then starts without the Purple Key.
  #v(1pt)
  #text(fill: ink-med)[Installing erases everything else on the laptop.]
]

#gap
#support
