# dq — 30 Minute Education

A daily loop for a young child: a one-page worksheet (~5 min), a half-sheet quiz for tomorrow, and a
parent script. Spelling and arithmetic are broken into small skills in TOML files; a spaced-repetition
scheduler (Leitner boxes) decides what appears each day. No model is needed for any decision.

## Install (on a computer)
    python3 -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'
    pytest -q                 # 22 tests
    dq validate               # checks the curriculum files

Data lives in `~/.dq` (override with `--home` or `DQ_HOME`): `dq.db` (SQLite) and `out/<student>/<date>/*.pdf`.
Back up that folder; it is the child's whole history.

## The daily loop
Morning, once at the start: `dq init Ben` then `dq placement Ben` (10 minutes, you ask, he answers; finds where he already is).

Each day D:
1. `dq oral Ben` — grade yesterday's quiz *with the child*, you read each word aloud, type only the mistakes. (Or `dq grade Ben photo.jpg` to have a vision model read a photographed paper quiz; you review and fix.)
2. `dq mood Ben ok --story done` — log how yesterday's worksheet went (easy/ok/hard/tears).
3. `dq next Ben` — prints the worksheet, tomorrow's quiz, and the parent script (PDFs in out/).
4. `dq report Ben --pdf` — on demand; same seven questions every time.
Other: `dq status`, `dq skills`, `dq sentences --fill` (optional model-written dictation sentences).

## Optional model use
Three touchpoints, all optional, prompts in `prompts/`: transcribe_box (read one handwriting box literally),
dictation_sentence, report_narrative. The model never judges correctness; `answers.match` does.
Default backend: any OpenAI-compatible server (LM Studio at localhost:1234/v1). The live-model path has only
been tested against a mock server, not a real model.

## Caveats
- Curriculum order and grade bands are my judgment from TEKS (ELAR §110.3, math §111.3–111.6). Specific TEKS
  numbers beyond Grade 3 fractions §111.5(b)(3) are unverified. Check them against tea.texas.gov before relying on them.
- Never run on the child's machine yet; the code has been tested only in simulation with synthetic children.
- Photo grading depends on printing at 100% scale on US Letter and a reasonably flat, well-lit photo.

See docs/SCHEMA.md for the skill format.
