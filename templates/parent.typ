// Grown-up script for tomorrow's quiz: what to say, and the answers. Keep this sheet out of sight.
#import "common.typ": *

#let d = json(sys.inputs.data)

#set page(paper: "us-letter", margin: (x: 16mm, y: 14mm))
#set text(font: sans, size: 10pt, fill: ink)
#set par(leading: 0.55em, spacing: 0.7em)

#text(size: 16pt, weight: "bold")[Quiz script · #d.student · #d.date_pretty]
#h(3mm) #text(size: 9pt, fill: luma(110))[#d.quiz_label]
#v(1mm)
#line(length: 100%, stroke: 0.8pt + accent)
#v(2mm)

#boxed-note("How to run it (about 3 minutes)", [
  Keep it light: "let's see what to practice tonight." Do not show your reaction to wrong answers.
  *Words:* say the word, read the sentence, say the word again. Wait. Do not help or correct.
  *Puzzles:* the child reads them alone. A clue answer is also a spelling check of that word.
  *Math:* the child reads each problem and writes the answer. Afterwards show the correct spelling
  of any missed word and have the child fix it in a different colour. That immediate feedback is what makes the quiz teach.
  Items marked "check" are on something not taught yet. Missing them costs nothing; getting both right lets the program skip ahead.
])
#v(3mm)

#text(size: 12pt, weight: "bold", fill: accent)[Words (dictate)]
#v(1mm)
#table(
  columns: (8mm, 24mm, 1fr, 25mm),
  stroke: 0.4pt + soft,
  inset: 2.2mm,
  align: (center, left, left, center),
  table.header([*\#*], [*Say*], [*Sentence*], [*Right?*]),
  ..d.spelling.map(w => (
    [#w.n],
    [#text(size: 12pt, weight: "bold")[#w.word]#if w.probe [ #text(size: 7.5pt, fill: luma(120))[(new pattern check)]]],
    [#w.sentence],
    [☐ yes  ☐ no],
  )).flatten(),
)
#v(4mm)

#if d.at("puzzles", default: ()).len() > 0 [
  #text(size: 12pt, weight: "bold", fill: accent)[Puzzles (child reads and writes)]
  #v(1mm)
  #table(
    columns: (8mm, 1fr, 38mm, 25mm),
    stroke: 0.4pt + soft,
    inset: 2.2mm,
    align: (center, left, left, center),
    table.header([*\#*], [*Puzzle*], [*Answer*], [*Right?*]),
    ..d.puzzles.map(p => (
      [#p.n],
      [#p.prompt#if p.note != "" [ #text(size: 8pt, fill: luma(110))[(#p.note)]]],
      [#text(weight: "bold")[#p.answer]#if p.also.len() > 0 [ #text(size: 8pt, fill: luma(110))[also: #p.also.join(", ")]]#if p.clue [ #text(size: 7.5pt, fill: luma(120))[(spelling counts)]]],
      [☐ yes  ☐ no],
    )).flatten(),
  )
  #v(4mm)
]

#text(size: 12pt, weight: "bold", fill: accent)[Math (child reads and writes)]
#v(1mm)
#table(
  columns: (8mm, 1fr, 28mm, 25mm),
  stroke: 0.4pt + soft,
  inset: 2.2mm,
  align: (center, left, center, center),
  table.header([*\#*], [*Problem (read aloud if needed)*], [*Answer*], [*Right?*]),
  ..d.math.map(m => (
    [#m.n],
    [#m.speech#if m.probe [ #text(size: 7.5pt, fill: luma(120))[(new skill check)]]],
    [#text(weight: "bold")[#m.answer]],
    [☐ yes  ☐ no],
  )).flatten(),
)
#v(4mm)

#text(size: 12pt, weight: "bold", fill: accent)[After the quiz]
#v(1mm)
#list(
  [Grade it: take a photo and run `dq grade`, or run `dq oral` and type the results (about 20 seconds).],
  [Log the mood from yesterday's worksheet: `dq mood easy|ok|hard|tears`. Two hard days in a row make the next day lighter automatically.],
  [Run `dq next` to print today's worksheet and tomorrow's quiz.],
)
