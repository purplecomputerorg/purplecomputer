#import "theme.typ": *
#show: card

// ── Front: the Parent Menu ──
#header[For Grown-ups]

#note[*Hold* #key("Esc") for a second to open the Parent Menu.]
#gap

#tiles(cols: 2, height: 0.62in,
  ([Install], [Put Purple on the laptop for good.]),
  ([Kid Profiles], [Each kid's own name, work and Time Travel.]),
  ([Rooms], [Turn any room off, or turn on Pack rooms.]),
  ([Littles Mode], [In Rooms: one activity, no menus.]),
  ([Sound], [Set a volume limit. 0 is silent.]),
  ([Parent PIN], [Keep this menu for grown-ups.]),
)
#gap
#panel(title: [The Write room])[
A quiet page for stories, letters and school reports, for kids who can type. It starts off: turn it on in *Rooms*.
]
#gap
#panel(title: [Printing])[
Connect a printer with a USB printer cable (USB-B). Most printers have the port, even wireless ones. Then press #key("Esc") #key("P"). Not every printer works.
]

#gap
#flip[Make Purple your family's with Purple Studio]

#pagebreak()

// ── Back: Purple Studio ──
#header([Purple Studio], qr: "studio-qr.svg", note: text(fill: purple)[studio.purplecomputer.org])

#text(size: 11pt, weight: "semibold", fill: purple-dk)[Put your family into Purple.]
#v(-2pt)
#text(fill: ink-med)[Make a *Purple Pack* on any computer. Everything stays in your browser; nothing is uploaded.]
#gap

#tiles(gutter: 8pt,
  ([Your words.], [Type #typed("grandma") and see her photo.]),
  ([Your voice.], [Record yourself saying each letter.]),
  ([New sounds.], [Shape instruments like a kazoo or a harp.]),
  ([Your colors.], [Pick the screen and paint colors.]),
  ([New rooms.], [Stories, games and worlds to walk around.]),
)

#gap
#panel(title: [How it works])[
  #steps(spacing: 12pt,
    [Try everything on a real Purple, right in your browser],
    [Download your Purple Pack to any USB drive],
    [Plug it into Purple and press *Add*],
  )
]

#gap
#support[For Grown-ups]
