# Skill schema

Files: `curriculum/spelling.toml`, `curriculum/math.toml`, `curriculum/sentences/*.toml`.

Each file has `[[strand]]` tables (id, title, subject, grade, teks) containing `[[strand.skill]]` tables.

Common skill fields: `id` (unique, prefixed `sp.` or `m.`), `title`, `grade` (inherits strand), `prereqs` (ids that must
be started first; order in file is teaching order), `teks` (standard reference), `rationale` (why it matters, for the adult),
`tip` (one-line teaching hint shown on the worksheet), `demo` (worked examples).

Spelling skills: `track` (`phonics` or `sight`), `core` (first words taught, ~10), `transfer` (words that test
generalization), `pattern` (regex every word must match; validated), `hl` (portion to highlight).

Math skills: `generator` (name in `dq.generators.REGISTRY`), `params` (generator arguments), `min_distinct` (smallest
acceptable problem space), `mode`. Problems carry prompt, answer, kind, optional spoken form.

Scheduling: Leitner box 0–6, intervals 0/1/2/4/8/16/32 days. Right: box 2 if new else +1. Wrong: box 1 (or −2 when above 3), due next day.
`dq validate` checks ids, prerequisite order, regex matches, demos, and generates sample problems for every math skill.
