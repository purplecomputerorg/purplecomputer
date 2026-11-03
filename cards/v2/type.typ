#import "theme.typ": *
#show: card.with(3)

// ── Front: things to type in Play ──
#header()
#intro[In the *Play* room, type anything, then press #key("Enter").]
#gap

#let try(title, ..rows) = panel(title: title, examples(..rows))

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
#flip[Write code]

#pagebreak()

// ── Back: code in Art, Music and Blocks ──
#header(title: [Write Code])
#note[
  In *Art*, *Music* or *Blocks*, press #key("Esc") then #key("Space"). #key("↓") shows ideas. Typos get fixed for you.
]
#gap
#panel(title: [Art])[
  #examples(comments: true,
    ("right 5", [paint 5 squares]),
    ("right 2 brush up right 3", [leaves a gap]),
    ("write hi", [letters on the grid]),
    ("red repeat 4 forward 6 turn", [a square!]),
  )
]
#gap
#panel(title: [Music])[
  #examples(comments: true,
    ("asdf", [play keys, #mono("1234") for drums]),
    ("fast qwertyuiop", [quick notes, or #mono("slow")]),
    ("choose ukulele zxcvbnm", [play a ukulele]),
  )
]
#gap
#panel(title: [Blocks])[
  #examples(comments: true,
    ("red up 5", [a tower]),
    ("right hello", [a block per letter]),
    ("green repeat 4 right 1 up 1", [stairs]),
  )
]
#gap
#support
