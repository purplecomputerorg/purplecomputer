#import "theme.typ": *
#show: card.with(4)

// ── Front: the Parent Menu ──
#header()

#intro[*Hold* #key("Esc") for a second to open the Parent Menu.]
#gap

#tiles(cols: 2,
  ([Install], [Put Purple on the laptop for good.], icon(ICONS.install)),
  ([Kid Profiles], [Each kid's name, saved work and Time Travel.], icon(ICONS.kids)),
  ([Rooms], [Turn any room off, or turn on your own custom rooms.], icon(ICONS.rooms)),
  ([Littles Mode], [In *Rooms*: one focused activity, including a screen-free option.], icon(ICONS.littles)),
  ([Sound], [Set a volume limit. 0 is always silent.], icon(ICONS.sound)),
  ([Parent PIN], [Keep this menu for grown-ups.], icon(ICONS.pin)),
)
#gap
#panel(title: [The Write room #h(3pt) #tag[Off by default]], icon: icon(ICONS.write))[
A quiet page for stories, letters and school reports, for kids who can type. Enable in the Parent Menu #sym.arrow.r *Rooms*.
]
#gap
#panel(title: [Printing #h(3pt) #tag[Experimental]], icon: icon(ICONS.printing))[
Connect a printer with a USB-B cable. Most printers have the port, even wireless ones. Then press #key("Esc") #key("P").
]

#gap
#flip[Purple Studio]

#pagebreak()

// ── Back: Purple Studio ──
#header(title: [Purple Studio], qr: "studio-qr.svg", note: text(size: 9pt, weight: "semibold", fill: purple-dk)[Make Purple your own.])

#intro[Studio is a website for adding your family's own pictures, words, sounds and whole new rooms to Purple.]
#gap

// Section headings sit above their panels, a step up from the purple item titles inside
#let section(title, body) = [
  #text(font: "Sora", weight: "bold", size: 11pt, fill: purple-dk, title)
  #v(-3pt)
  #body
]
#section[How it works][
  #panel[
    #steps(spacing: 9pt, valign: top,
      [Personalize and build at #text(fill: purple)[studio.purplecomputer.org]],
      [Download your unique Purple Pack from Studio],
      [Plug in your Purple Key (or any USB drive) and drag your Purple Pack onto it
       #v(1pt) #text(size: 7.6pt, fill: ink-med)[Your Purple Key can transfer files and still runs Purple.]],
    )
  ]
]

#gap
#section[Use Purple Studio to make:][
  #tiles(pad: 7pt,
    ([Pictures.], [Upload a photo for them to paint in *Art*.], studio-icon("1f5bc")),
    ([Words.], [Add your family's names and silly phrases.], studio-icon("1f5e8")),
    ([Letters.], [Audio from Grandma when they press "G".], sticker("G", "#E2C63A")),
    ([Instruments.], [Invent instruments to play in *Music*.], studio-icon("1f3b9")),
    ([Colors.], [Change Purple's theme and letter colors.], studio-icon("1f3a8")),
    ([New Rooms.], [Build rooms, like a world to explore.], studio-icon("1f9e9")),
  )
]

#gap
#support
