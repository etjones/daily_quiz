// Daily worksheet: one side of US Letter. Study aid only: never collected, never graded.
#import "common.typ": *

#let d = json(sys.inputs.data)

#set page(paper: "us-letter", margin: (x: 13mm, top: 11mm, bottom: 10mm))
#set text(font: sans, size: 10.5pt, fill: ink)
#set par(leading: 0.55em, spacing: 0.7em)

// --- header -------------------------------------------------------------
#grid(
  columns: (1fr, auto),
  align: (left + horizon, right + horizon),
  [#text(size: 17pt, weight: "bold")[#d.student's practice] #h(2mm) #text(size: 9pt, fill: luma(110))[#d.date_pretty · Day #d.day_no · about 5 minutes]],
  text(size: 8.5pt, fill: luma(110))[Quiz tomorrow morning: study = success],
)
#v(1mm)
#line(length: 100%, stroke: 0.8pt + accent)
#v(1.5mm)

// --- words -------------------------------------------------------------
#text(size: 12pt, weight: "bold", fill: accent)[1 · Words] #h(2mm)
#text(size: 9pt, fill: luma(100))[Look. Say it. Cover it. Write it.]
#v(0.5mm)

#for t in d.word_tips [
  #boxed-note(t.title, t.tip)
  #v(0.8mm)
]

#for (i, w) in d.words.enumerate() {
  grid(
    columns: (6mm, 44mm, 1fr, 1fr),
    column-gutter: 2.5mm,
    align: horizon,
    text(size: 9pt, fill: luma(120))[#(str(i + 1) + ".")],
    {
      hlword(w.parts)
      if w.role == "review" { h(1.5mm); text(size: 7.5pt, fill: luma(130))[again] }
    },
    guide(100%, 10.5mm),
    guide(100%, 10.5mm),
  )
  v(0.9mm)
}
#text(size: 7.5pt, fill: luma(130))[Left box: copy it. Right box: fold or cover the word, then write it from memory.]

#v(2mm)

// --- math --------------------------------------------------------------
#text(size: 12pt, weight: "bold", fill: accent)[2 · Math]
#v(0.5mm)

#for t in d.reteach [
  #boxed-note("Tricky yesterday: " + t.title, [#t.tip #if t.example != "" [ #text(weight: "bold")[Example: #t.example]]], color: hilite)
  #v(0.8mm)
]
#for t in d.math_tips [
  #boxed-note("New: " + t.title, [#t.tip #if t.example != "" [ #text(weight: "bold")[Example: #t.example]]])
  #v(0.8mm)
]

#let answer-line(w: 22mm) = box(width: w, height: 7.5mm, stroke: (bottom: 0.8pt + ink))

#grid(
  columns: (1fr, 1fr),
  column-gutter: 8mm,
  row-gutter: 3.2mm,
  ..d.problems.enumerate().map(((i, p)) => {
    let wide = p.kind == "text"
    box(width: 100%, {
      grid(
        columns: (5mm, 1fr, auto, auto),
        column-gutter: 1.5mm,
        align: horizon,
        text(size: 8.5pt, fill: luma(120))[#(str(i + 1) + ".")],
        text(size: 12.5pt)[#ev(p.prompt)],
        text(size: 12.5pt)[#ev(p.lead)],
        answer-line(w: if p.kind == "frac" { 16mm } else if p.kind == "int_rem" { 26mm } else { 18mm }),
      )
    })
  }),
)

#v(2.5mm)

// --- story -------------------------------------------------------------
#text(size: 12pt, weight: "bold", fill: accent)[3 · My story]
#v(0.5mm)
#text(size: 10.5pt)[#d.story.instruction]
#v(0.5mm)
#if d.story.words.len() > 0 [
  #text(size: 9pt, fill: luma(100))[Use: ]
  #for w in d.story.words [#box(inset: (x: 2mm, y: 0.8mm), radius: 1.5mm, fill: pale, stroke: 0.5pt + accent, text(size: 11pt, weight: "bold")[#w]) #h(1mm)]
]
#v(1mm)
#if d.story.draw [
  #grid(
    columns: (38mm, 1fr),
    column-gutter: 3mm,
    box(width: 38mm, height: 24mm, stroke: (paint: soft, thickness: 0.7pt, dash: "dashed"), align(center + horizon, text(size: 8pt, fill: soft)[draw here])),
    stack(spacing: 1.5mm, ..range(d.story.lines).map(_ => guide(100%, 11mm, border: false))),
  )
] else [
  #stack(spacing: 1.5mm, ..range(d.story.lines).map(_ => guide(100%, 11mm, border: false)))
]

#v(1fr)
#line(length: 100%, stroke: 0.4pt + soft)
#text(size: 8pt, fill: luma(120))[Grown-up: how did today go? Circle one: *easy · ok · hard · tears* #h(6mm) Story finished? *yes · no* #h(1fr) Quiz is #d.quiz_for]
