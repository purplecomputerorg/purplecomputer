#import "theme.typ": *
#show: card.with(2)

// ── Front: the rooms ──
#header()

#intro[Tap #key("Esc") to pick a room, then press its number.]
#gap

#let room(n, name, body) = panel(title: grid(columns: (1fr, auto), name, icon(ICONS.at(lower(name.text)))), n: n, body)

#room(1, [Art])[
  Every letter paints its sticker color. #key("Space") puts the brush down so arrows paint. #key("Tab") switches to letters.
]
#gap
#room(2, [Music])[
  Every key plays a note and lights up. #key("Enter") changes the instrument. #key("Tab") switches to saying letters.
]
#gap
#room(3, [Play])[
  Type words, math and colors, then #key("Enter"). #h(2pt) #typed("red + blue") \
  #typed("cat * 5") #h(2pt) #typed("dog + cat") #h(2pt) #typed("2 + 3") #h(2pt) #typed("say I love cat")
]
#gap
#room(4, [Blocks])[
  Every letter places a 3D block. #key("Enter") builds up. #key("Tab") turns the room around. Hold #key("Tab") to look from above.
]

#gap
#note[
  #set par(spacing: 1.1em)
  #text(font: "Sora", weight: "semibold", fill: purple)[Also in the #key("Esc") menu]
  #v(2pt)
  #grid(columns: (1fr, 1fr), row-gutter: 9pt,
    [#key("T") #icon(ICONS.time-travel) Time Travel], [#key("S") #icon(ICONS.save) Save],
    [#key("O") #icon(ICONS.open) Open], [#key("Space") #icon(ICONS.code) Write code],
  )
]

#gap
#flip[Cool things to try]

#pagebreak()

// ── Back: the best things to try, coolest first ──
#header(title: [Cool things to try], qr: none, note: none)
#gap

#tiles(pad: 12pt,
  ([Purple talks.], [In Play, add #mono("!") or start with #mono("say"): #typed("hello!") or #typed("say I love you"). #key("Tab") also turns talking on.]),
  ([Loop like a DJ.], [In Music, *hold* #key("Enter") to record a tune, then play along with it.]),
  ([Colors mix like paint.], [Hold two letters in Art or Blocks: #sticker("F", "#E6CE55") + #sticker("V", "#4C7FE5", ink: white) makes green. #key("\\") opens every color.]),
  ([Spell a word.], [In Music, press #key("Tab"), then type #mono("cat"). The cat shows up, and #key("Space") says it.]),
  ([Rewind anything.], [Press #key("Esc") #key("T") for *Time Travel*, then hold #key("←") to watch the room go backward. #key("Enter") keeps that moment, even after a big erase.]),
  ([See your own code.], [Paint or build something, then hold #key("Esc") and press #key("Space"). Purple shows the code for what you just did. More on card 3.]),
  ([Made for little hands.], [Tap #key("Shift"), then a letter, for a capital. No need to hold two keys. Typos are OK: #typed("2 plsu 3") or #typed("2++3") still makes 5.]),
)


#gap
#support
