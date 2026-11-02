#import "theme.typ": *
#show: card.with(2)

// ── Front: the rooms ──
#header()

#text(size: 9.4pt)[Tap #key("Esc") to pick a room, then press its number.]
#gap

#let room(n, name, body) = panel(title: name, n: n, body)

#room(1, [Art])[
  Every letter paints its sticker color. #key("Space") puts the brush down so arrows paint. #key("Tab") switches to letters.
]
#gap
#room(2, [Music])[
  Every key plays a note and lights up. Numbers are drums. #key("Enter") changes the sound. #key("Tab") says letters, and #key("Space") switches to their sounds.
]
#gap
#room(3, [Play])[
  Type words, math and colors, then #key("Enter"). #h(2pt) #typed("red + blue")
]
#gap
#room(4, [Blocks])[
  Every letter stacks a block. #key("Enter") builds up. #key("Tab") turns the room around.
]

#gap
#note[
  #set par(spacing: 1.1em)
  #text(font: "Sora", weight: "semibold", fill: purple)[Also in the #key("Esc") menu]
  #v(2pt)
  #grid(columns: (1fr, 1fr), row-gutter: 9pt,
    [#key("T") Time Travel], [#key("S") Save],
    [#key("O") Open], [#key("Space") Write code],
  )
]

#gap
#flip[Cool things to try]

#pagebreak()

// ── Back: the best things to try, coolest first ──
#header(title: [Cool things to try], qr: none, note: none)
#gap

#tiles(gutter: 9pt,
  ([Colors mix like paint.], [Hold two letters in Art or Blocks: #sticker("F", "#E6CE55") + #sticker("V", "#4C7FE5") makes green. #key("\\") opens every color.]),
  ([Purple talks.], [In Play, add #mono("!") or start with #mono("say"): #typed("I love you!"). #key("Tab") turns talking on.]),
  ([Loop like a DJ.], [In Music, *hold* #key("Enter") to record a tune, then play along with it.]),
  ([No wrong notes.], [Every key sounds good together. Arrows change the key.]),
  ([Nothing gets lost.], [Every room is kept. #key("Esc") #key("T") rewinds to any moment, even after a big erase.]),
  ([Keys match stickers.], [Each letter paints the color on its sticker.]),
  ([Made for little hands.], [Tap #key("Shift"), then a letter, for a capital. No need to hold two keys.]),
)


#gap
#support
