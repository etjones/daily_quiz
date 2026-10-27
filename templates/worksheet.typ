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
#let story(n) = {
  text(size: 12pt, weight: "bold", fill: accent)[3 · My story]
  v(0.5mm)
  text(size: 10.5pt)[#d.story.instruction]
  v(0.5mm)
  if d.story.words.len() > 0 {
    text(size: 9pt, fill: luma(100))[Use: ]
    for w in d.story.words [#box(inset: (x: 2mm, y: 0.8mm), radius: 1.5mm, fill: pale, stroke: 0.5pt + accent, text(size: 11pt, weight: "bold")[#w]) #h(1mm)]
  }
  v(1mm)
  let lines = stack(spacing: 1.5mm, ..range(n).map(_ => guide(100%, 11mm, border: false)))
  if d.story.draw {
    grid(
      columns: (38mm, 1fr),
      column-gutter: 3mm,
      box(width: 38mm, height: 24mm, stroke: (paint: soft, thickness: 0.7pt, dash: "dashed"), align(center + horizon, text(size: 8pt, fill: soft)[draw here])),
      lines,
    )
  } else { lines }
}

// --- puzzle corner -----------------------------------------------------------
#let puzzle-names = (analogy: "Analogy", odd: "Odd one out", ladder: "Change one letter", build: "Build a word", homophone: "Sound-alikes", scale: "Word scale", clue: "Clue")
#let blank(w) = box(width: w, height: 5mm, stroke: (bottom: 0.7pt + ink))
#let corner(ps) = {
  v(2.5mm)
  text(size: 12pt, weight: "bold", fill: accent)[4 · Puzzle corner]
  h(2mm)
  text(size: 9pt, fill: luma(100))[Think it through. Answers are upside down at the bottom.]
  v(1mm)
  for (i, p) in ps.enumerate() {
    block(spacing: 2.2mm, [
      #box(width: 5mm, text(size: 8.5pt, fill: luma(120))[#(str(i + 1) + ".")])#text(size: 8.5pt, weight: "bold", fill: accent)[#puzzle-names.at(p.type)] #h(1.5mm)
      #if p.type == "scale" [
        #text(size: 11pt)[#p.prompt: #p.shuffled.join(", ")] \
        #h(5mm) #for _ in p.shuffled [#blank(24mm) #h(2mm)]
      ] else [
        #text(size: 11pt)[#p.prompt] #h(2mm) #blank(30mm)
      ]
    ])
  }
  v(1fr)
  align(right, rotate(180deg, reflow: true, text(size: 7.5pt, fill: luma(120))[Answers: #ps.enumerate().map(((i, p)) => str(i + 1) + ". " + p.answer).join("   ")]))
}

// Story and puzzles share whatever room is left above the footer. When it is short,
// puzzles go first (from the end), then story lines, down to one.
#block(width: 100%, height: 1fr, layout(size => {
  let ps = d.at("puzzles", default: ())
  let h(n, k) = measure(block(width: size.width, { story(n); if k > 0 { corner(ps.slice(0, k)) } })).height
  let n = d.story.lines
  let k = range(ps.len() + 1).rev().find(k => h(n, k) <= size.height)
  if k == none {
    k = 0
    n = range(1, n + 1).rev().find(n => h(n, 0) <= size.height)
    if n == none { n = 1 }
  }
  block(width: 100%, height: size.height, {
    story(n)
    if k > 0 { corner(ps.slice(0, k)) }
  })
}))
#line(length: 100%, stroke: 0.4pt + soft)
#text(size: 8pt, fill: luma(120))[Grown-up: how did today go? Circle one: *easy · ok · hard · tears* #h(6mm) Story finished? *yes · no* #h(1fr) Quiz is #d.quiz_for]
