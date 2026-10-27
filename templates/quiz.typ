// Daily quiz: a landscape half-sheet (5.5 x 8.5 in). Every answer box sits at a fixed
// position taken from the manifest, and four corner marks let the grader straighten
// and crop a photo of the page. The manifest in the JSON is the single source of truth
// for geometry: Python uses the same numbers to crop.
#import "common.typ": *

#let d = json(sys.inputs.data)
#let m = d.manifest
#let mm(x) = x * 1mm

#set page(width: mm(m.page.w), height: mm(m.page.h), margin: 0pt)
#set text(font: sans, size: 10pt, fill: ink)

// corner registration marks (the bottom-right one is larger, so rotation can be detected)
#for mk in m.marks {
  place(top + left, dx: mm(mk.cx - mk.size / 2), dy: mm(mk.cy - mk.size / 2),
    rect(width: mm(mk.size), height: mm(mk.size), fill: black, stroke: none))
}

// header
#place(top + left, dx: mm(m.header.x), dy: mm(m.header.y),
  box(width: mm(m.header.w), {
    grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
      [#text(size: 15pt, weight: "bold")[#d.student's quiz] #h(2mm) #text(size: 9pt, fill: luma(110))[#d.date_pretty]],
      text(size: 8pt, fill: luma(110))[Write one answer in each box. It's okay to leave one blank.])
  }))
#place(top + left, dx: mm(m.header.x), dy: mm(m.header.y + 9),
  line(length: mm(m.header.w), stroke: 0.7pt + accent))

// column labels
#place(top + left, dx: mm(m.cols.spelling.x), dy: mm(m.cols.label_y),
  text(size: 9pt, weight: "bold", fill: accent)[Words (listen)])
#place(top + left, dx: mm(m.cols.math.x), dy: mm(m.cols.label_y),
  text(size: 9pt, weight: "bold", fill: accent)[Math])

// items
#for it in m.items {
  // number: right-aligned in the gutter, so "1." and "10." both keep a gap before the item
  place(top + left, dx: mm(it.num_x), dy: mm(it.box.y),
    box(width: mm(it.num_w), height: mm(it.box.h),
      align(right + horizon, text(size: 9pt, weight: "bold", fill: luma(100))[#(str(it.n) + ".")])))
  if it.kind_group == "spelling" {
    place(top + left, dx: mm(it.box.x), dy: mm(it.box.y), guide(mm(it.box.w), mm(it.box.h)))
  } else {
    // prompt
    place(top + left, dx: mm(it.prompt_box.x), dy: mm(it.prompt_box.y),
      box(width: mm(it.prompt_box.w), height: mm(it.prompt_box.h),
        align(left + horizon, text(size: if it.kind == "text" { 8pt } else { 12pt })[#ev(it.prompt_text)])))
    // lead-in and answer box
    place(top + left, dx: mm(it.lead.x), dy: mm(it.lead.y),
      box(width: mm(it.lead.w), height: mm(it.lead.h), align(right + horizon, text(size: if it.kind == "symbol" { 9pt } else { 11pt })[#ev(it.lead_typ)])))
    place(top + left, dx: mm(it.box.x), dy: mm(it.box.y),
      rect(width: mm(it.box.w), height: mm(it.box.h), stroke: 0.8pt + ink, radius: 1mm))
  }
}

// footer: quiz id, so the right manifest is always findable
#place(top + left, dx: mm(m.footer.x), dy: mm(m.footer.y),
  text(size: 7pt, fill: luma(130))[#d.quiz_label · #d.student · #d.date])
