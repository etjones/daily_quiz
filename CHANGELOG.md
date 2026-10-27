# Changelog

## Unreleased

**Breaking**
- The web app is now Django instead of FastAPI, and every page except `/health` needs a login; production needs `DJANGO_SECRET_KEY` and `DQ_ALLOWED_HOSTS`, and a user created with `just adduser`.
- Dev dependencies moved to a uv dependency group: `uv sync` replaces `uv sync --extra dev`.
- `just run` now starts the web app; the old dq pass-through recipe is `just dq`.

- Word problems on the quiz no longer spill over neighbouring rows and off the page: generators mark them `prose`, which gives them a wider prompt box with a short lead-in and 3.5mm clear between rows, and every quiz prompt now shrinks to fit its box (word problems 11pt down to 8pt), including days rebuilt from older stored manifests.
- Quiz and worksheet item numbers now read "1." and are right-aligned in their gutter, so there is always a visible gap before the word box or the math prompt (two-digit numbers used to crowd it). Days already in the database re-render from their stored manifest, which predates the new gutter width, so the template measures the gutter back from the item in that case.
- Added a web grading sheet (`/quiz/<id>/grade`): the parent script with a live “right” checkbox per item and a running tally; saving records the quiz directly. The dashboard's “Grade it” opens it.
- `dq status` and the web footer print the data directory; the README documents where data lives on the Mac and the server.
- Pages set `<meta name="referrer" content="same-origin">` so logins work behind Caddy's `Referrer-Policy: no-referrer` (which made browsers post `Origin: null` and fail CSRF).
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
