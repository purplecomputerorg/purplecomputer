#import "theme.typ": *
#show: card

// ── Front: the Parent Menu ──
#header[For Grown-ups]

#text(size: 9.4pt)[*Hold* #key("Esc") for a second to open the Parent Menu.]
#gap

#panel[
  #tips(space: 3pt,
    ([Install for good.], [Put Purple on the laptop so the Purple Key isn't needed.]),
    ([Kid Profiles.], [Each kid gets their own computer name, saved work and Time Travel.]),
    ([Littles Mode.], [One activity with no menus: Music, Art, or sounds with a dark screen.]),
    ([Rooms.], [Turn rooms on or off, like *Write*, a quiet page for stories.]),
    ([Sound.], [Set a volume limit. 0 makes Purple silent.]),
    ([Parent PIN.], [Keeps the Parent Menu for grown-ups.]),
  )
]
#gap
#panel(title: [Printing], color: amber)[
  Plug in a USB printer, then #key("Esc") #key("P"). Each page is signed with the computer's name.
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

#panel[
  #tips(color: purple, space: 4pt,
    ([Your words.], [Type #typed("grandma") and see her photo.]),
    ([Your voice.], [Record yourself saying each letter.]),
    ([New sounds.], [Shape instruments like a kazoo or a harp.]),
    ([Your colors.], [Pick the screen and paint colors.]),
    ([New rooms.], [Stories, games and worlds to walk around.]),
  )
]
#gap
#panel(title: [How it works], color: violet)[
  #steps(color: violet, spacing: 12pt,
    [Try everything on a real Purple, right in your browser],
    [Download your Purple Pack to any USB drive],
    [Plug it into Purple and press *Add*],
  )
]

#gap
#support[For Grown-ups]
