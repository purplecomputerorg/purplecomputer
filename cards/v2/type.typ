#import "theme.typ": *
#show: card.with(3)

// ── Front: things to type in Play ──
#header()
#intro[In the *Play* room, type anything, then press #key("Enter").]
#gap

#let try(title, ..rows) = panel(title: title, examples(..rows))

#try([Words become little pictures],
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
  ("2 dark burgundy", [two dark burgundy squares]),
)
#gap
#try([Talking],
  ("cat!", [add #mono("!") and Purple says it]),
  ("say 5 x 5 apples", [or start with #mono("say")]),
)
#gap
#flip[Write code]

#pagebreak()

// ── Back: code in Art, Music and Blocks ──
#header(title: [Write Code])
#note[
  In *Art*, *Music* or *Blocks*, hold #key("Esc") and press #key("Space"). \
  Press #key("↓") for ideas. Typos get fixed for you.
]
#gap
#panel(title: [Art])[
  #examples(comments: true,
    ("red right 5", [paint 5 red squares]),
    ("brush up right 5 asdf", [a gap, then colors]),
    ("write hi", [write letters]),
    ("red repeat 4 forward 6 turn", [a square!]),
  )
]
#gap
#panel(title: [Music])[
  #examples(comments: true,
    ("asdf", [each letter is a note]),
    ("fast asdf slow jkl", [quick notes, then slow]),
    ("choose ukulele zxcvbnm", [play a ukulele]),
    ("letters", [keys say letters, #mono("notes") goes back]),
  )
]
#gap
#panel(title: [Blocks])[
  #examples(comments: true,
    ("red up 3 blue up 2", [a two-color tower]),
    ("right hello", [each letter is a block]),
    ("green repeat 4 right 1 up 1", [stairs]),
  )
]
#gap
#support
