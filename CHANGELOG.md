# Changelog

## Unreleased

**Breaking**
- The web app is now Django instead of FastAPI, and every page except `/health` needs a login; production needs `DJANGO_SECRET_KEY` and `DQ_ALLOWED_HOSTS`, and a user created with `just adduser`.
- Dev dependencies moved to a uv dependency group: `uv sync` replaces `uv sync --extra dev`.
- `just run` now starts the web app; the old dq pass-through recipe is `just dq`.

- Web accounts use Django's auth (argon2 hashes, admin at `/admin`); sessions last 30 days after the last visit and every form has CSRF protection.
- Added a web app (`just run`, Jinja templates) covering the daily loop, quiz entry, photo grading, placement, history, progress report, skills and dictation sentences.
- `python -m dq.web` runs the web app as a service (migrations, then gunicorn on 127.0.0.1:$PORT, `/health`), declared as a routinely service under `op run` for deploy-site.
- Placement can be replayed from recorded answers (`placement.next_question`), so it runs across web requests.
- `DB` gained `results_for_quiz` and `graded_quizzes`.
- `build.words_missing_sentences` is shared by `dq sentences` and the web app.

## 2026-10-12

- The student name is optional on every command and defaults to the recorded default student; `dq default [NAME]` shows or sets it, and the first `dq init` records it.
- Placement requires an explicit `y` or `n` for each question; an empty Enter no longer counts as right.
- Tests find a scalable font on macOS, so photo-grading tests pass there.
- Applied ruff lint fixes and formatting across the codebase.
