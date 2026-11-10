#import "theme.typ": *
#show: card.with(3)

// ── Front: things to type in Play ──
#header()
#intro[In the *Play* room, type anything, then press #key("Enter").]
#gap

#let try(title, ..rows) = panel(title: title, examples(first: 1.25in, gutter: 8pt, ..rows))

#let says(code, ..also) = ((code, ..also.pos()), [#result(code) #h(3pt) #icon("\u{F057E}") #h(2pt) #text(fill: ink-med)[and says "#code.trim("!")" out loud]])
#try([Words become little pictures], ex("unicorn"), ex("3 trex"), ex("pink fish"), says("cat!", "say cat"))
#gap
#try([Numbers], ex("2 + 3"), ex("2 x 3 bananas"), ex("1234"), ex("2 4 6 8..."))
#gap
#try([Colors], ex("bright red + blue"), ex("2 burgundy"))
#gap
#flip[Write code]

#pagebreak()

// ── Back: code in Art, Music and Blocks ──
#header(title: [Write Code])
#note[
  In *Art*, *Music* or *Blocks*, tap #key("Esc"), then press #key("Space"). \
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
