# dq — 30 Minute Education

A daily loop for a child in kindergarten through grade 5: a one-page worksheet (~5 min), a half-sheet quiz
for tomorrow, and a parent script. Spelling, vocabulary and arithmetic are broken into small skills in TOML
files, following the Texas TEKS from kindergarten to grade 5; a spaced-repetition
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
`dq oral`, photo grading, printable quiz and parent-script PDFs for any quiz (from the dashboard, the quiz
pages and History), placement (with undo), history, the progress report, skills, and dictation
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

## Grades
Each student can have a school grade (K or 1–5): `dq init Ben --grade 2`, `dq grade-level Ben --set 3`, or the
Students page. The grade only seeds things; results drive the rest:
- **Placement** starts just after the last skill from an earlier grade and gallops forward until a miss, then
  narrows down, so a kindergartner is never asked fractions first. Without a grade it is a plain binary search.
- **Puzzles** start at a level equal to the grade (levels 1–5), then move with results.
- **Kindergarten** quizzes have no read-it-yourself puzzles or clues; K items need only a letter, a short word
  or a numeral (count the dots, what comes after 7, VC/CVC words), and the parent reads everything aloud.
- Skills two or more grades below what a child has already made solid (for instance kindergarten skills for a
  child who started before they existed) are assumed known: they go into review spread over six weeks
  instead of being taught.

## Interests
Each student can have up to four interests (Students page → Interests, or `dq interests Ben --set space mario`).
Some word problems on the worksheet and quiz are then told as a story about one of them: about three in four
problems that are already stories, and one in four plain facts such as 7 × 8. Only the wording changes; the
numbers and the answer come from the math generator as before. Stories cover adding, taking away, comparing, equal
groups, sharing (with and without leftovers), a fraction of a group, adding and subtracting fractions and mixed
numbers, the four decimal operations, area, perimeter and volume, so about half or more of the math skills in
grades 1–5 can be themed (place value, rounding, comparing and order of operations stay plain). Kindergartners
get none, since their quiz is read aloud.

Sixteen interests are built in (`curriculum/interests/*.toml`, checked by `just validate`): Baseball, Basketball,
Football, Soccer, Gymnastics, Horses, Pokémon, Mario, Minecraft, Disney Princesses, Superheroes, Fashion,
Space, Dinosaurs, Ocean Animals and Baking. **New interest** on the same page asks Claude (`ANTHROPIC_API_KEY`,
model `DQ_INTEREST_MODEL`, default `claude-opus-5-5`) to write templates for a name you type, once; the result
is stored in `dq.db` and its stories are listed on the interest's page, where it can be deleted. The name is
limited to 32 letters, spaces, ' & and -, it reaches the model only as a topic label, and every template must
pass the same character allowlist (no digits or markup) before it is kept.

## The daily loop
Morning, once at the start: `dq init Ben --grade 1` then `dq placement Ben` (10 minutes, you ask, he answers; finds where he already is).

Each day D:
1. `dq oral Ben` — grade yesterday's quiz *with the child*, you read each word aloud, type only the mistakes. (Or `dq grade Ben photo.jpg` to have a vision model read a photographed paper quiz; you review and fix.)
2. `dq mood Ben ok --story done` — log how yesterday's worksheet went (easy/ok/hard/tears).
3. `dq next Ben` — prints the worksheet, tomorrow's quiz, and the parent script (PDFs in out/).
4. `dq report Ben --pdf` — on demand; same seven questions every time.
Other: `dq status`, `dq skills`, `dq sentences --fill` (optional model-written dictation sentences).

## Word puzzles
The quiz carries a couple of word puzzles (analogies, odd one out, change one letter, word building,
sound-alikes, and word meaning: synonyms, antonyms, prefixes, suffixes, Greek and Latin roots, context clues)
and sometimes a spelling word asked for by its clue; the worksheet
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
- Curriculum order and grade bands are my judgment from TEKS (ELAR §110.2–110.7, math §111.2–111.7, K–5).
  Specific TEKS numbers beyond Grade 3 fractions §111.5(b)(3) are unverified. Check them against tea.texas.gov
  before relying on them.
- Not covered: geometry beyond area, perimeter and volume, telling time, measurement units, data and graphs,
  and personal financial literacy. Reading comprehension and writing are outside the quiz.
- Never run on the child's machine yet; the code has been tested only in simulation with synthetic children.
- Photo grading depends on printing at 100% scale on US Letter and a reasonably flat, well-lit photo.

See docs/SCHEMA.md for the skill format, and [CHANGELOG.md](CHANGELOG.md) for changes.
