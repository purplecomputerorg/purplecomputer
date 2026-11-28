#import "theme.typ": paper, purple, purple-dk, magenta, hair, ink-dim
// The welcome card on top of the box, 6x4 landscape: the Canva original, plus the fridge note.
// Positions are measured from the Canva card (268 px/in); every dy is a cap top, since text
// boxes run cap height to baseline here. Each line is sized to its width on the Canva card, so
// any face lands in the same spots.

// Glacial Indifference stands in for Nourd, the Canva card's font
#let face = "Glacial Indifference"
// The site's light purple fill, which the slot and the background's far corner share
#let light = rgb("#ebe2fd")
#set page(width: 6in, height: 4in, margin: 0pt,
  fill: gradient.linear(paper, light, angle: 33.7deg))
#set text(font: face, fill: magenta, top-edge: "cap-height", bottom-edge: "baseline")
#set par(leading: 0pt)
#let px = 1in / 268
// Lines at one size, set so the widest of `sample` (default: the lines) spans `w`;
// `pitch` is baseline to baseline
#let t(w, weight: "regular", fill: magenta, sample: none, pitch: 1.3em, ..ls) = context {
  let probe = if sample == none { ls.pos() } else { (sample,) }
  let size = 10pt * (w / calc.max(..probe.map(l => measure(text(size: 10pt, weight: weight, l)).width)))
  set text(size: size, weight: weight, fill: fill)
  stack(spacing: pitch.to-absolute() - measure[H].height, ..ls.pos())
}
#let at(x, y, body) = place(top + left, dx: x, dy: y, body)
#let margin = 0.27in
#let right-col = 3.55in
#let logo = (top: 0.25in, h: 0.58in)
#let lists-top = 2.40in

// The mascot, cropped from assets/logo.svg's 200-unit box to the bot itself (x 55..145, y 41..170)
#let logo-s = logo.h / 129
#at(0.31in - 55 * logo-s, logo.top - 41 * logo-s, image("/assets/logo.svg", width: 200 * logo-s))
// Cap centered on the mascot's middle
#at(0.87in, 0.48in, t(1230 * px, weight: "bold")[Welcome to Purple Computer and thank you!])

// The open band between the header and the lists holds the key and the fridge note, each
// centered in it vertically
#let band = (top: logo.top + logo.h, bottom: lists-top)
#let in-band(x, body) = context at(x, (band.top + band.bottom - measure(body).height) / 2, body)

// The slot the Purple Key sits in and its label, centered from the left margin to the fridge note
#let slot = (w: 1.96in, h: 0.58in)
#in-band((margin + right-col - slot.w) / 2, stack(spacing: 0.14in,
  rect(width: slot.w, height: slot.h, radius: 0.13in, fill: light,
    stroke: (paint: magenta, thickness: 1.1pt, dash: (array: (4pt, 2.6pt)))),
  box(width: slot.w, align(center, t(435 * px, weight: "bold")[Your Purple Key])),
))

// The two lists: a heading, then items on a 0.205in pitch
#let heading(body) = t(290 * px, weight: "bold", fill: purple-dk, sample: [In the box:], body)
// Both lists share the size at which the Canva card's longest item spans 565 px
#let items(..args) = t(565 * px, sample: [Welcome card and Purple Key], pitch: 0.205in, fill: purple, ..args)
#at(margin, lists-top, heading[In the box:])
#at(margin, 2.74in, items[Welcome card and Purple Key][Keyboard stickers][Purple sticker set][Guide cards])
#at(right-col, lists-top, heading[Under this card:])
#at(right-col, 2.74in, items[Sticker sheets and][guide cards])

// Hand-drawn arrow from "guide cards" down toward what's under the card; x is from the column's left
#at(right-col, 0in, curve(stroke: (paint: purple, thickness: 1.3pt, cap: "round", join: "round"),
  curve.move((1.03in, 3.07in)),
  curve.cubic((1.36in, 3.12in), (1.53in, 3.4in), (1.41in, 3.74in)),
  curve.move((1.32in, 3.62in)), curve.line((1.41in, 3.74in)), curve.line((1.53in, 3.64in)),
))

#at(margin, 3.68in, t(1093 * px, fill: ink-dim)[We're a small family business. If you like Purple, please spread the word!])

// The fridge note: the full width of the "Under this card" column, held on with a magnet like the fridge page
#let note = 6in - margin - right-col
#let qr = 0.58in
#let pad = 8pt
#let text-w = note - 3 * pad - qr
#in-band(right-col, rotate(1.2deg, reflow: false, {
  block(width: note, inset: (x: pad, top: pad + 2pt, bottom: pad), radius: 3pt, fill: white, stroke: 0.6pt + hair,
    grid(columns: (qr, 1fr), column-gutter: pad, align: horizon,
      image("fridge-qr.svg", width: qr),
      stack(spacing: 9pt,
        t(0.9 * text-w, weight: "bold", fill: purple)[Show off what][your kid makes!],
        t(text-w)[purplecomputer.org/fridge],
      ),
    ))
  place(top + center, dy: -6pt, circle(radius: 6pt, fill: gradient.radial(rgb("#b88ae0"), purple, center: (35%, 30%))))
}))
