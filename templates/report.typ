// Progress report. Every report asks and answers the same questions (see report.py).
#import "common.typ": *

#let d = json(sys.inputs.data)

#set page(paper: "us-letter", margin: (x: 16mm, y: 14mm))
#set text(font: sans, size: 10pt, fill: ink)
#set par(leading: 0.6em, spacing: 0.8em)

#text(size: 17pt, weight: "bold")[Progress report · #d.student]
#h(3mm) #text(size: 9pt, fill: luma(110))[#d.period_label]
#v(1mm)
#line(length: 100%, stroke: 0.8pt + accent)
#v(2mm)

// headline numbers
#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  column-gutter: 3mm,
  ..d.headline.map(h => block(width: 100%, inset: 3mm, radius: 2mm, fill: pale, stroke: 0.5pt + accent, {
    text(size: 8pt, fill: luma(100))[#h.label]
    linebreak()
    text(size: 15pt, weight: "bold")[#h.value]
  })),
)
#v(3mm)

#for q in d.questions [
  #block(breakable: false, width: 100%, {
    text(size: 11.5pt, weight: "bold", fill: accent)[#q.question]
    v(0.5mm)
    if q.lines.len() == 0 { text(fill: luma(120))[Nothing to report yet.] } else { list(..q.lines.map(l => [#l])) }
  })
  #v(1.5mm)
]

#if d.skills.len() > 0 [
  #text(size: 11.5pt, weight: "bold", fill: accent)[Where each skill stands]
  #v(0.5mm)
  #table(
    columns: (1fr, 22mm, 34mm),
    stroke: 0.3pt + soft,
    inset: 1.8mm,
    table.header([*Skill*], [*Status*], [*Words / unit solid*]),
    ..d.skills.map(s => (
      text(size: 8.5pt)[#s.title],
      text(size: 8.5pt)[#s.label],
      text(size: 8.5pt)[#s.progress],
    )).flatten(),
  )
]
