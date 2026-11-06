#import "theme.typ": *
#show: card.with(4)

// ── Front: the Parent Menu ──
#header()

#intro[*Hold* #key("Esc") for a second to open the Parent Menu.]
#gap

#tiles(cols: 2,
  ([Install], [Put Purple on the laptop for good.]),
  ([Kid Profiles], [Each kid's name, saved work and Time Travel.]),
  ([Rooms], [Turn any room off, or turn on your own custom rooms.]),
  ([Littles Mode], [In *Rooms*: one focused activity, including a screen-free option.]),
  ([Sound], [Set a volume limit. 0 is always silent.]),
  ([Parent PIN], [Keep this menu for grown-ups.]),
)
#gap
#panel(title: [The Write room #h(3pt) #tag[Off by default]])[
A quiet page for stories, letters and school reports, for kids who can type. Enable in the Parent Menu #sym.arrow.r *Rooms*.
]
#gap
#panel(title: [Printing #h(3pt) #tag[Experimental]])[
Connect a printer with a USB-B cable. Most printers have the port, even wireless ones. Then press #key("Esc") #key("P").
]

#gap
#flip[Purple Studio]

#pagebreak()

// ── Back: Purple Studio ──
#header(title: [Purple Studio], qr: "studio-qr.svg", note: text(fill: purple)[studio.purplecomputer.org])

// Wording from Studio itself: its home page (studio/src/ui/home.ts) and section cards (studio/src/main.ts)
#text(size: 11pt, weight: "semibold", fill: purple-dk)[Make Purple your own.]
#v(-2pt)
#text(fill: ink-med)[Everything happens in your web browser. Nothing you add is uploaded, and nothing is tracked.]
#gap

#tiles(
  ([Pictures.], [The dog, ready to paint on.]),
  ([Words.], [The dog's name, with a picture.]),
  ([Letters.], [Grandma, every time they press G.]),
  ([Instruments.], [Like a kazoo or a harp.]),
  ([Colors.], [An ocean-blue screen, or new colors on the keys.]),
  ([New Rooms.], [Like a world for them to walk around.]),
)

#gap
#panel(title: [How it works])[
  #steps(spacing: 12pt,
    [A real Purple runs right on the page as you work],
    [Download your Purple Pack],
    [Put it on Purple with a USB drive],
  )
]

#gap
#support
