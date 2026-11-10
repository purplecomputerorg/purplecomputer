#import "theme.typ": *
#show: card.with(3)

// ── Front: things to type in Play ──
#header(title: [Code in Play], front: true)
#intro[In *Play*: type anything, press #key("Enter"). Nothing breaks!]
#gap

#let try(title, ..rows) = panel(title: title, examples(first: 1.25in, gutter: 8pt, ..rows))

#let says(code, ..also) = ((code, ..also.pos()), [#result(code) #h(3pt) #icon("\u{F057E}") #h(2pt) #text(fill: ink-med)[and says "#code.trim("!")" out loud]])
#try([Words make pictures], ex("unicorn"), ex("3 trex"), ex("pink fish"), says("cat!", "say cat"))
#gap
#try([Numbers come alive], ex("2 + 3"), ex("2 x 3 apples"), ex("1234"), ex("2 4 6 8..."))
#gap
#try([Colors mix], ex("bright red + blue"), ex("2 burgundy"))
#gap
#flip[Code everywhere]

#pagebreak()

// ── Back: code in Art, Music and Blocks ──
#header(title: [Code Everywhere])
#note[
  In *Art*, *Music* or *Blocks*, tap #key("Esc"), then press #key("Space"). \
  Press #key("↓") for ideas. Typos get fixed for you.
]
#gap
#panel(title: [Art])[
  #examples(first: 1.05in, gutter: 4pt,
    art("brush up right 3 ujmmm"),
    art("red repeat 4 forward 4 turn"),
    art("write repeat 3 hello"),
  )
]
#gap
#panel(title: [Music])[
  #examples(comments: true,
    ("asdf", [4 notes, one per letter]),
    ("fast asdf slow jkl", [quick notes, then slow]),
    ("choose ukulele zxcvbnm", [zxcvbnm on a ukulele]),
    ("letters", [switch to saying letter names]),
  )
]
#gap
#panel(title: [Blocks])[
  #examples(first: 1.05in, gutter: 4pt,
    blocks("right qazwsx"),
    blocks("red up 3 blue up 2"),
    blocks("green repeat 4 right 1 up 1"),
  )
]
#gap
#support
