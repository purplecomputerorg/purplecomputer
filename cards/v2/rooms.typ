#import "theme.typ": *
#show: card.with(2)

// ── Front: the rooms ──
#header()

#intro[Tap #key("Esc") or #key("~") to pick a room, then press its number.]
#gap

#let room(n, name, body) = panel(title: grid(columns: (1fr, auto), name, icon(ICONS.at(lower(name.text)))), n: n, body)

#room(1, [Art])[
  Every letter paints its color. #key("Space") puts the brush down so arrows paint. #key("Tab") switches between colors and letters.
]
#gap
#room(2, [Music])[
  Every key plays a note. #key("Enter") changes the instrument. #key("Tab") switches between music and saying letters.
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

#tiles(pad: 10pt,
  ([Purple talks.], [In *Play*, add #mono("!") or start with #mono("say"): #typed("hello!") or #typed("say I love you"). #key("Tab") also turns talking on.]),
  ([Loop like a DJ.], [In *Music*, *hold* #key("Enter") to record a tune, then play along with it.]),
  ([Colors mix like paint.], [Hold two letters in *Art* or *Blocks*: #sticker("F", "#E6CE55") + #sticker("V", "#4C7FE5", ink: white) makes green. #key("\\") opens the color menu.]),
  ([Letter sounds.], [In *Music*, press #key("Tab") and keys say their letters. #key("Enter") switches between letter names and sounds. Type #mono("cat"), then #key("Space") to hear the word.]),
  ([Rewind anything.], [Press #key("Esc") #key("T") for *Time Travel*, then hold #key("←") to watch the room go backward. #key("Enter") restores to that moment.]),
  ([Write code.], [In *Art*, *Music* or *Blocks*, tap #key("Esc"), then press #key("Space"). If you just drew something, you'll see the code for drawing it again.]),
  ([Made for little hands.], [Tap #key("Shift"), then a letter, for a capital. No need to hold two keys. Typos are okay: #typed("2 plsu 3") or #typed("2++3") still makes 5.]),
)


#gap
#support
