# dq — 30 Minute Education

A daily loop for a young child: a one-page worksheet (~5 min), a half-sheet quiz for tomorrow, and a
parent script. Spelling and arithmetic are broken into small skills in TOML files; a spaced-repetition
scheduler (Leitner boxes) decides what appears each day. No model is needed for any decision.

## Install (on a computer)
    uv sync
    just test                 # pytest
    just validate             # checks the curriculum files
    just adduser NAME         # a login for the web app (once)
    just run                  # web app at http://localhost:8000 (hot reload)

## Web app
`just run` serves the same daily loop in a browser (Django), on the same data as the CLI: today's steps
(grade the quiz, log the mood, build and print the worksheet and quiz), per-item quiz entry like
`dq oral`, photo grading, placement (with undo), history, the progress report, skills, and dictation
sentences. Switch students from the header; the choice is a cookie, falling back to the CLI's default
student. Every page needs a login (Django accounts, argon2 hashes); a device stays signed in for 30 days
after its last visit. Accounts and sessions live in `~/.dq/web.sqlite3`, apart from `dq.db`. Add users with
`just adduser NAME`, reset with `just passwd NAME`, or use `/admin`. Photo grading and sentence writing use `DQ_BACKEND` (default `lmstudio`,
`none` to disable) and `DQ_LLM_URL` / `DQ_LLM_MODEL`. Styling is the house style, exported into
`src/dq/web/static/house-style`; pick a theme with the control at the top right.

Production runs `python -m dq.web` (migrations, then gunicorn on 127.0.0.1:$PORT) under
`op run --env-file=.env`; see `.env.example` for settings. On the server, add a user with
`just with-secrets adduser NAME`.

## Data
Everything the app keeps is in one directory, `DQ_HOME` (default `~/.dq`; `--home` overrides it for the CLI):
`dq.db` (students, quizzes, results, sentences), `web.sqlite3` (web logins and sessions),
`default_student`, `out/<student>/<date>/*.pdf`, and `work/` (render scratch). Back it up; it is the
child's whole history. `dq status` and the web footer print its path.

- **Mac:** `~/.dq`, with a gitignored symlink `data -> ~/.dq` in the project. The live SQLite files stay
  out of Dropbox, which can sync a database mid-write into a corrupt or conflicted copy.
- **Server:** `/home/deploy/dev/daily_quiz/data` (gitignored), set by `DQ_HOME` in that checkout's `.env`.
  Deleting or `git clean -fdx`-ing the checkout deletes the data.

To copy the learning data up, replace only `dq.db` (never `web.sqlite3`), using SQLite's backup so a
running app can't leave a half-written copy, then restart the service.

The first `dq init` records the default student (`~/.dq/default_student`); every command that takes a NAME can omit it. Change it with `dq default NAME`.

## The daily loop
Morning, once at the start: `dq init Ben` then `dq placement Ben` (10 minutes, you ask, he answers; finds where he already is).

Each day D:
1. `dq oral Ben` — grade yesterday's quiz *with the child*, you read each word aloud, type only the mistakes. (Or `dq grade Ben photo.jpg` to have a vision model read a photographed paper quiz; you review and fix.)
2. `dq mood Ben ok --story done` — log how yesterday's worksheet went (easy/ok/hard/tears).
3. `dq next Ben` — prints the worksheet, tomorrow's quiz, and the parent script (PDFs in out/).
4. `dq report Ben --pdf` — on demand; same seven questions every time.
Other: `dq status`, `dq skills`, `dq sentences --fill` (optional model-written dictation sentences).

## Word puzzles
The quiz carries a couple of word puzzles and sometimes a spelling word asked for by its clue; the worksheet
ends with a puzzle corner when there is room. Banks are TOML files in `curriculum/puzzles/` (checked by
`just validate`). A puzzle answer that is not in the list can be checked by a decision model through
OpenRouter if `OPENROUTER_API_KEY` is set (an `op://` reference in `.env`); otherwise it is marked wrong and
you can flip it.

## Optional model use
Three touchpoints, all optional, prompts in `prompts/`: transcribe_box (read one handwriting box literally),
dictation_sentence, report_narrative. The model never judges spelling or math; `answers.match` does. The one
exception is the optional puzzle-answer check above, for open-ended puzzles only.
Default backend: any OpenAI-compatible server (LM Studio at localhost:1234/v1). The live-model path has only
been tested against a mock server, not a real model.

## Caveats
- Curriculum order and grade bands are my judgment from TEKS (ELAR §110.3, math §111.3–111.6). Specific TEKS
  numbers beyond Grade 3 fractions §111.5(b)(3) are unverified. Check them against tea.texas.gov before relying on them.
- Never run on the child's machine yet; the code has been tested only in simulation with synthetic children.
- Photo grading depends on printing at 100% scale on US Letter and a reasonably flat, well-lit photo.

See docs/SCHEMA.md for the skill format, and [CHANGELOG.md](CHANGELOG.md) for changes.
