# Conversation log

Key requests and decisions, newest last. Earlier history (2026-10-12) is reconstructed from Claude Code transcripts and git; it is a summary, not a verbatim record.

## Before this file (reconstructed)

- **2026-10-12** — Committed the initial project, added `justfile`, fixed tests, ruff-formatted. Placement now needs an explicit `y`/`n`; math placement scores for the student reviewed. Default student added to the CLI. Built the web app (FastAPI, then Django with login/CSRF), published to the public `daily_quiz` repo, deployed to quizzes.dayonetools.com via caddy-deploy. Data moved to `~/.dq` (symlinked as `data`). Added the web grading sheet. Ended with "merge, deploy, and put this to bed".
- **2026-10-27 (no transcript found)** — Four commits on `main` fixing quiz/worksheet numbering and word-problem layout (`dbe247e`…`8dfbaf0`). Then, uncommitted on `feature/spelling-fixes-and-puzzles`: word puzzles, off-target misspelling blame, review-word quiz priority, and a puzzle-answer judge.

## 2026-10-27 — Survey of the repo and in-progress work

**User:** Look at the dq directory and any build artifacts; create a CONVERSATION.md. Before starting anything, report what you find and any records of tasks in process.

**Claude:**

State
- Branch `feature/spelling-fixes-and-puzzles` has **no commits** of its own; it sits at `8dfbaf0`, same as `main` and `origin/main`. All new work is **uncommitted** (15 modified files, +444/−61, plus 4 new modules, 7 puzzle banks, 1 new test file).
- No plan, todo, memory, or notes files exist for this work. Neither earlier Claude Code transcript covers it, so it was written elsewhere (another tool or session).
- Build artifacts: `data -> ~/.dq` holds `dq.db`, a `dq.db.bak-2026-10-12`, and `out/`/`work/` from 2026-10-12 only. Nothing has been built against the new code.

Uncommitted work (inferred from the code)
1. **Word puzzles** (`puzzles.py`, `curriculum/puzzles/*.toml`): analogies, odd one out, word ladders, word building, homophones, spelling clues on the quiz; word scales in a worksheet "puzzle corner". Levels adapt per type; recent puzzles are not repeated.
2. **Off-target blame** (`blame.py`, `scheduler.py`, `db.py`): a misspelling outside the taught pattern brings the word back tomorrow without demoting it, and reteach goes to the skill covering the broken letters. New `result.on_target` / `blame_skill` columns with an in-place migration.
3. **Review-word priority** in quiz selection (reviews take all slots but one).
4. **Puzzle judge** (`judge.py`): OpenRouter decision model for unlisted puzzle answers, cached in `judgment_cache`.

Gaps
- Tests: **79 pass, 1 fails** — `test_first_week_with_pdfs`: the parent script is now 2 pages (the new puzzle table in `parent.typ` pushes it over).
- `judge.py` is not wired in: only its constants are imported (`grade.py`); `from_env` is never called. `OPENROUTER_API_KEY` is not in `.env.example`.
- `CHANGELOG.md` and `README.md` have no entries for any of this.
- `test_review_and_blame.py` exists; no tests found yet for `puzzles.py` or `judge.py`.
- Nothing committed; the DB schema change will migrate the live `~/.dq/dq.db` on first run.

## 2026-10-27 — Fix the failing test, pull the server DB, finish the puzzles work

**User:** Fix the failing test. Copy the database from dayonetools:dev/daily_quiz to the local version. Then complete the in-process work.

**Claude:**

Failing test
- The parent script ran to 2 pages because "☐ yes ☐ no" wrapped in the 18 mm "Right?" column, doubling every row. Widened it to 25 mm in all three tables of `templates/parent.typ`.
- A longer (25-day) simulated run then found worksheets spilling onto a second page. This also happens on `main`, without puzzles: only the puzzle corner shrank to fit, so long tips plus word problems pushed the story past the footer. The story and puzzle corner now share the leftover space in `templates/worksheet.typ`: puzzles go first, then story lines (down to one). All PDFs over 25 days are now one page.

Server database
- The server checkout is at `8dfbaf0` (same as `main`). Its `dq.db` (one student, 98 results 2026-10-13 to 10-25, last write Oct 25) was copied with SQLite's backup API (read-only), passed the integrity check, and replaced `~/.dq/dq.db`. The previous local DB (no results) is saved as `~/.dq/dq.db.bak-2026-10-27-local`. `web.sqlite3` was not copied.

Finishing the work
- Wired `judge.from_env` into the places that score answers before a human confirms them: `dq oral`, `dq grade` (photo and its manual fallback), and the web oral-entry and photo review. The web grading sheet and the final save keep the grown-up's verdict as final, so they don't call the model.
- Added `OPENROUTER_API_KEY` / `DQ_JUDGE_MODEL` to `.env.example`.
- Added `tests/test_puzzles.py` (19 tests): bank validation, stable ids, levels, picking, type rotation, puzzle verdicts with and without the checker, checker outage, caching, env handling, request/response parsing (HTTP mocked), and oral entry passing the checker through.
- Applied ruff format to the 9 files this work touched; CHANGELOG and README updated.
- Smoke test on a scratch copy of the server data: migration runs, `dq next` builds three one-page PDFs with puzzles, and grading the old-format Oct 26 quiz records an off-target blame correctly.

Result: **99 tests pass**, ruff clean, curriculum valid. Nothing committed.

Open issues
- **Unverified API:** OpenRouter's `/api/alpha/decisions` endpoint exists (401 without a key), but its model list shows `typesafe/jev-router`, not the default `typesafe/jev-1.14`, and the request/response shape is untested against the real service.
- `.env.example` is untracked: the global gitignore rule `.env.*` ignores it, so the README points to a file that isn't in the repo.
- On a crowded day the worksheet drops the puzzle corner entirely (e.g. the student's 2026-10-27 sheet had ~23 mm spare, not enough for one puzzle).
- The "Tricky yesterday" note always sits under "2 · Math", even when it's a spelling skill (pre-existing).

## 2026-10-27 — Track .env.example; live Jev test

**User:** Removed `.env.*` from the global gitignore; add `.env.example`. Added an OpenRouter key to `.env`; test Jev calls.

**Claude:**
- `.env.example` is now staged (`git add`); nothing committed.
- `op run --env-file=.env` fails on this Mac: `op://dev/dq-web/secret_key` (`DJANGO_SECRET_KEY`) isn't in the local vault. That's a pre-existing limitation of running `.env` locally, unrelated to OpenRouter.
- The OpenRouter line in `.env` (line 20) is still commented out (`# OPENROUTER_API_KEY=…`), so the app won't see it. For the test, only that line was passed to `op run` through a temporary uncommented copy; the key was never printed.
- Live results with `typesafe/jev-1.14` (served as `typesafe/jev-1.14-20261014`, provider TypeSafe, ~$0.000017 per call). The response shape matches `judge.py` exactly; no code change needed.

| Puzzle | Answer | p(yes) | Outcome (accept ≥ 0.8, flag > 0.3) |
|---|---|---|---|
| bird : nest :: bear : ? | cave | 0.80 | accepted, flagged |
| | hole | 0.61 | wrong, flagged |
| | tree | 0.14 | wrong |
| | honey | 0.03 | wrong |
| CAT → bed for camping | cot | 0.97 | (listed answer; check skipped in grading) |
| | hat | 0.03 | wrong |
| | cab | 0.07 | wrong |
| ___ + coat = jacket for wet days | rain | 0.96 | (listed) |
| | over | 0.32 | wrong, flagged |
| | snow | 0.07 | wrong |

- To turn it on for the app, uncomment line 20 of `.env`. The server's `.env` needs the same line for the web app to use it.
