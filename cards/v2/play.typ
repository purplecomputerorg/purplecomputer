#import "theme.typ": *
#show: card

// ── Front: things to type in Play ──
#header[The Play Room]
#text(size: 9.4pt)[In the *Play* room, type anything, then press #key("Enter").]
#gap

#let try(title, ..rows) = panel(title: title, color: violet, examples(color: violet, ..rows))

#try([Words become pictures],
  ("cat", [a cat]),
  ("3 cats", [three of them]),
  ("pink fish", [colors and pictures together]),
)
#gap
#try([Numbers],
  ("2 + 3", [the answer, with dots to count]),
  ("3 x 4 bananas", [twelve bananas]),
  ("1234", [an abacus]),
  ("2 4 6 8...", [keep a pattern going]),
)
#gap
#try([Colors],
  ("red + blue", [mix like paint]),
  ("2 dark red", [two dark red squares]),
)
#gap
#try([Talking],
  ("cat!", [add #mono("!") and Purple says it]),
  ("say hello", [or start with #mono("say")]),
)
#gap
#flip[Code for Art, Music and Blocks on the back]

#pagebreak()

// ── Back: code in Art, Music and Blocks ──
#header[Write Code]
#note[
  In *Art*, *Music* or *Blocks*, press #key("Esc") then #key("Space"). #key("↓") shows ideas. Typos get fixed for you.
]
#gap
#panel(title: [Art], color: red)[
  #examples(color: red,
    ("right 5", [paint 5 squares]),
    ("brush up", [move without painting]),
    ("write hi", [letters on the grid]),
    ("red repeat 4 forward 6 turn", [a square!]),
  )
]
#gap
#panel(title: [Music], color: blue)[
  #examples(color: blue,
    ("asdf", [play those keys, #mono("1234") for drums]),
    ("fast qwertyuiop", [quick notes, or #mono("slow")]),
    ("choose ukulele zxcvbnm", [pick a sound, then play]),
  )
]
#gap
#panel(title: [Blocks], color: green)[
  #examples(color: green,
    ("red up 5", [a tower]),
    ("right hello", [a block per letter]),
    ("green repeat 4 right 1 up 1", [stairs]),
  )
]
#gap
#support[The Play Room]
