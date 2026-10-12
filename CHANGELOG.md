# Changelog

## Unreleased

**Breaking**
- `just run` now starts the web app; the old dq pass-through recipe is `just dq`.

- Added a web app (`just run`, FastAPI + Jinja) covering the daily loop, quiz entry, photo grading, placement, history, progress report, skills and dictation sentences.
- `python -m dq.web` runs the web app as a service (reads `PORT` and `.env`, binds 127.0.0.1, `/health`), declared as a routinely service for deploy-site.
- Placement can be replayed from recorded answers (`placement.next_question`), so it runs across web requests.
- `DB` accepts `check_same_thread`, and gained `results_for_quiz` and `graded_quizzes`.
- `build.words_missing_sentences` is shared by `dq sentences` and the web app.

## 2026-10-12

- The student name is optional on every command and defaults to the recorded default student; `dq default [NAME]` shows or sets it, and the first `dq init` records it.
- Placement requires an explicit `y` or `n` for each question; an empty Enter no longer counts as right.
- Tests find a scalable font on macOS, so photo-grading tests pass there.
- Applied ruff lint fixes and formatting across the codebase.
