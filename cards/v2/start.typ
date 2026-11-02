#import "theme.typ": *
#show: card.with(1)

// ── Front: starting Purple from the Purple Key ──
#header()

#note[
  #set text(size: 8.8pt)
  *Trying Purple changes nothing on the laptop.* Take out the Purple Key and restart to get it back. *Like it?* Hold #key("Esc") for the Parent Menu, then choose *Install* to keep it for good.
]
#gap

#let big-step(n, body) = numbered(n, r: 9pt, text(size: 11.5pt, body))
#big-step(1)[Turn off the laptop.]
#v(1pt)
#big-step(2)[Plug in the Purple Key.]
#v(1pt)
// Step 3's badge runs a rail down to the Mac and PC ways it owns
#let way(title, keys, body) = panel(title: title)[
  #set text(size: 8.6pt)
  #box(height: 1.36in, width: 100%)[
    #v(2pt)
    #keys
    #v(7pt)
    #body
  ]
]
#grid(
  columns: (9pt, 9pt, 1fr), column-gutter: (0pt, 10pt), row-gutter: 6pt,
  align: (x, y) => if y == 0 { horizon } else { top },
  grid.cell(colspan: 2, badge(3, r: 9pt)), text(size: 11.5pt)[Turn it on:],
  grid.vline(x: 1, start: 1, stroke: (paint: purple.lighten(76%), thickness: 1.6pt, cap: "round")),
  [], [],
  grid(
    columns: (1fr, 1fr), column-gutter: 6pt,
    way([Mac], keyrow(gap: 3pt, bigkey("Option", width: 0.55in, size: 10.5pt), "+", bigkey("Power", width: 0.53in, size: 10.5pt)))[
      Hold *Option* and press *Power*. Keep holding, then pick the orange drive #box(baseline: 30%, image("orange-drive.svg", height: 1.9em))
    ],
    way([PC], keyrow(bigkey("F12", width: 0.52in), bigkey("Esc", width: 0.52in)))[
      Press *Power*, then *mash these keys*: tap them fast, again and again. Pick the USB drive from the menu.
    ],
  ),
)

#gap
#block(width: 100%, inset: (x: 11pt, y: 9pt), radius: 8pt, fill: white, stroke: 1.2pt + magenta.lighten(35%))[
  #grid(columns: (1fr, auto), column-gutter: 8pt, align: (left + horizon, right + horizon),
    [
      #text(font: "Sora", weight: "semibold", size: 10.5pt, fill: purple-dk)[Laptop started like normal?]
      #v(-3pt)
      #text(size: 8.8pt)[Some laptops use a different key, like *HP* and *Surface* laptops. Find yours on the back.]
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
    ("Dell", key("F12")), ("Lenovo", key("F12")), ("Acer", key("F12")),
    ("HP", [#key("Esc"), then #key("F9")]),
    ("ASUS", key("Esc")), ("Samsung", key("F10")), ("LG", key("F10")), ("Sony", key("F11")),
    ("Surface", [Hold *Volume Down*, press *Power*. Keep Volume Down pressed.]),
  )
  #ruled(columns: (0.9in, 1fr), pad: 6.5pt, ..brands.map(((b, k)) => (text(weight: "semibold", b), k)))
]
#gap
#panel(title: [Another way, from Windows])[
  #steps(spacing: 13pt,
    [Click *Start*, then the *Power* icon],
    [Hold #key("Shift") and click *Restart*],
    [Choose *Use a device*, then the USB drive],
  )
]

#gap
#support
