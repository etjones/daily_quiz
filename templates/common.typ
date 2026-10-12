// Shared helpers for all dq templates.
// Problem prompts from the Python generators are Typst markup; `ev` evaluates them
// with the drawing helpers below in scope.

#let ink = rgb("#222222")
#let accent = rgb("#2f6fdb")
#let hilite = rgb("#d6336c")
#let soft = luma(190)
#let pale = rgb("#eef3fb")
#let sans = ("Inter", "DejaVu Sans", "Liberation Sans", "Libertinus Serif")

// A small answer box, for use inside prompts.
#let qbox = box(width: 7mm, height: 7mm, stroke: 0.8pt + ink)

// A bar divided into d equal parts with n shaded.
#let fracbar(n, d, w: 42mm, h: 6mm) = box(width: w, height: h, stroke: 0.8pt + ink, {
  grid(
    columns: range(d).map(_ => 1fr),
    rows: h,
    ..range(d).map(i => rect(width: 100%, height: 100%, stroke: 0.5pt + ink,
      fill: if i < n { rgb("#9ec5fe") } else { white })),
  )
})

// A number line from 0 to 1 cut into d jumps, with a dot at n/d.
#let numline(d, n, w: 52mm) = box(width: w + 10mm, height: 10mm, {
  place(top + left, dx: 5mm, dy: 4mm, line(length: w, stroke: 0.8pt + ink))
  for i in range(d + 1) {
    place(top + left, dx: 5mm + w * i / d, dy: 2.4mm,
      line(start: (0pt, 0pt), end: (0pt, 3.2mm), stroke: 0.8pt + ink))
  }
  place(top + left, dx: 5mm - 1mm, dy: 6.4mm, text(size: 7pt)[0])
  place(top + left, dx: 5mm + w - 1mm, dy: 6.4mm, text(size: 7pt)[1])
  place(top + left, dx: 5mm + w * n / d - 1.3mm, dy: 4mm - 1.3mm,
    circle(radius: 1.3mm, fill: accent, stroke: none))
})

// r rows by c columns of dots.
#let dots(r, c, size: 2.2mm, gap: 0.9mm) = grid(
  columns: range(c).map(_ => size),
  rows: range(r).map(_ => size),
  column-gutter: gap,
  row-gutter: gap,
  ..range(r * c).map(_ => circle(radius: size / 2, fill: accent, stroke: none)),
)

#let scope = (qbox: qbox, fracbar: fracbar, numline: numline, dots: dots)
#let ev(s) = eval(s, mode: "markup", scope: scope)

// A writing box with light handwriting guides: dashed midline and a solid baseline.
#let guide(w, h, border: true) = box(
  width: w, height: h,
  stroke: if border { 0.7pt + ink } else { none },
  {
    place(top + left, dy: h * 0.32, line(length: w, stroke: (paint: soft, thickness: 0.4pt, dash: "dashed")))
    place(top + left, dy: h * 0.72, line(length: w, stroke: 0.5pt + soft))
  },
)

// A word split into before / pattern / after, with the pattern highlighted.
#let hlword(parts, size: 20pt) = {
  text(size: size, weight: "medium", fill: ink)[#parts.at(0)]
  if parts.at(1) != "" { text(size: size, weight: "bold", fill: hilite)[#parts.at(1)] }
  text(size: size, weight: "medium", fill: ink)[#parts.at(2)]
}

#let boxed-note(title, body, color: accent) = block(
  width: 100%, inset: 2.5mm, radius: 2mm, fill: pale, stroke: 0.6pt + color,
  [#text(weight: "bold", fill: color)[#title] #h(1mm) #body],
)
