"""Views for the dq web app: the same daily loop as the CLI, in a browser.

Data lives where the CLI keeps it ($DQ_HOME, default ~/.dq). The current student comes from a cookie,
then the CLI's default student. Every page except /health and /login needs a logged-in user.
"""

import functools
import json
import re
import sqlite3
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    QueryDict,
)
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .. import (
    build,
    curriculum,
    grade,
    llm,
    placement,
    scheduler,
    session,
)
from .. import (
    render as pdf,
)
from .. import report as report_mod
from ..cli import MOODS, default_student_path
from ..db import DB
from .middleware import PageError
from .theme import house_context

STUDENT_COOKIE = "dq_student"
COOKIE_AGE = 10 * 365 * 86400
FILE_NAME = re.compile(r"^[\w.-]+\.(pdf|png|json)$")


# --------------------------------------------------------------------------- plumbing


@functools.cache
def _curriculum(path: Path) -> curriculum.Curriculum:
    return curriculum.load(path)


def cur() -> curriculum.Curriculum:
    return _curriculum(settings.DQ_CURRICULUM)


def home() -> Path:
    return settings.DQ_HOME


def student_named(db: DB, name: str) -> sqlite3.Row:
    try:
        return db.student(name)
    except KeyError as e:
        raise PageError(str(e).strip("'\""), 404) from e


def current_student(request: HttpRequest) -> sqlite3.Row | None:
    """Cookie, then the CLI's default student, then None."""
    db: DB = request.db
    names = {s["name"] for s in db.students()}
    name = request.COOKIES.get(STUDENT_COOKIE)
    if name not in names:
        path = default_student_path(home())
        name = path.read_text().strip() if path.exists() else None
    return db.student(name) if name in names else None


def require_student(request: HttpRequest) -> sqlite3.Row:
    student = current_student(request)
    if student is None:
        raise PageError("Add or choose a student first.", 409)
    return student


def page(
    request: HttpRequest, name: str, status: int = 200, **ctx: object
) -> HttpResponse:
    ctx.setdefault("students", [s["name"] for s in request.db.students()])
    ctx.setdefault("msg", request.GET.get("msg"))
    ctx.setdefault("user", request.user)
    ctx.setdefault("data_home", str(home().resolve()))
    return render(request, name, {**house_context(request), **ctx}, status=status)


def go(url: str, msg: str | None = None) -> HttpResponseRedirect:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return HttpResponseRedirect(url)


def with_student_cookie(resp: HttpResponse, name: str) -> HttpResponse:
    resp.set_cookie(STUDENT_COOKIE, name, max_age=COOKIE_AGE, samesite="Lax")
    return resp


def out_dir(student: sqlite3.Row) -> Path:
    return home() / "out" / student["name"]


def _plan_data(db: DB, student: sqlite3.Row, on: str) -> dict:
    row = db.plan_for(student["id"], on)
    if row is None:
        raise PageError(f"No plan built for {on}.", 404)
    return json.loads(row["data"])


def _quiz_for(db: DB, student: sqlite3.Row, quiz_id: int) -> sqlite3.Row:
    q = db.conn.execute(
        "SELECT * FROM quiz WHERE id = ? AND student_id = ?", (quiz_id, student["id"])
    ).fetchone()
    if q is None:
        raise PageError("No such quiz for this student.", 404)
    return q


def _open_quiz(db: DB, student: sqlite3.Row, quiz_id: int) -> sqlite3.Row:
    q = _quiz_for(db, student, quiz_id)
    if q["status"] != "open":
        raise PageError("This quiz was already graded.", 409)
    return q


def _iso_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise PageError(f"Not a date: {s!r}") from e


@login_not_required
@require_GET
def health(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok", content_type="text/plain")


# --------------------------------------------------------------------------- students


@require_GET
def students(request: HttpRequest) -> HttpResponse:
    default = default_student_path(home())
    return page(
        request,
        "students.html",
        student=current_student(request),
        rows=request.db.students(),
        default=default.read_text().strip() if default.exists() else None,
        title="Students",
    )


@require_POST
def add_student(request: HttpRequest) -> HttpResponse:
    db: DB = request.db
    name = request.POST.get("name", "").strip()
    if not re.fullmatch(r"[\w-]+", name):
        raise PageError("Use letters, digits, - or _ for the name.")
    if name in {s["name"] for s in db.students()}:
        raise PageError(f"{name} already exists.")
    db.add_student(name, date.today(), pace_cap=int(request.POST.get("pace_cap", 2)))
    path = default_student_path(home())
    if not path.exists():
        path.write_text(name + "\n")
    resp = go("/placement", f"Added {name}. Placement finds where they already are.")
    return with_student_cookie(resp, name)


@require_http_methods(["GET", "POST"])
def students_view(request: HttpRequest) -> HttpResponse:
    return add_student(request) if request.method == "POST" else students(request)


@require_POST
def select_student(request: HttpRequest) -> HttpResponse:
    name = student_named(request.db, request.POST.get("name", ""))["name"]
    return with_student_cookie(go("/"), name)


@require_POST
def set_default(request: HttpRequest) -> HttpResponse:
    name = student_named(request.db, request.POST.get("name", ""))["name"]
    default_student_path(home()).write_text(name + "\n")
    return go("/students", f"{name} is now the default student (CLI too).")


# --------------------------------------------------------------------------- today


@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    student = current_student(request)
    if student is None:
        return go("/students", "Add a student to get started.")
    db: DB = request.db
    sid, today = student["id"], date.today()
    days = db.quiz_days(sid)
    yesterday = (today - timedelta(days=1)).isoformat()
    log = {r["on_date"]: r for r in db.day_logs(sid, yesterday)}.get(yesterday)
    return page(
        request,
        "dashboard.html",
        student=student,
        title=f"Today: {student['name']}",
        today=today.isoformat(),
        yesterday=yesterday,
        plan=db.plan_for(sid, today.isoformat()),
        open_quiz=db.latest_open_quiz(sid),
        last_quiz=days[-1] if days else None,
        streak=scheduler.clean_day_streak(db, sid),
        has_units=bool(db.units(sid)),
        log=log,
        moods=MOODS,
    )


@require_POST
def log_mood(request: HttpRequest) -> HttpResponse:
    student = require_student(request)
    on = _iso_date(request.POST.get("on", "")).isoformat()
    mood = request.POST.get("mood", "")
    if mood not in MOODS:
        raise PageError(f"mood must be one of {', '.join(MOODS)}")
    done = {"done": True, "skipped": False}.get(request.POST.get("story", ""))
    note = request.POST.get("note", "").strip() or None
    request.db.log_day(student["id"], on, mood=mood, composition_done=done, note=note)
    extra = (
        " If the next day also goes badly, the load lightens by itself."
        if mood in ("hard", "tears")
        else ""
    )
    return go("/", f"Logged {mood} for {on}.{extra}")


@require_POST
def build_day(request: HttpRequest) -> HttpResponse:
    student = require_student(request)
    day = _iso_date(request.POST.get("on", ""))
    force = request.POST.get("force") == "true"
    build.build_day(request.db, cur(), home(), student["name"], day, force=force)
    return go(f"/day/{day.isoformat()}", "Rebuilt." if force else None)


@require_GET
def day_page(request: HttpRequest, on: str) -> HttpResponse:
    student = require_student(request)
    data = _plan_data(request.db, student, on)
    sel = data["selection"]
    qd = data.get("quiz_date") or (_iso_date(on) + timedelta(days=1)).isoformat()
    folder = out_dir(student) / on
    files = [
        ("Worksheet", f"worksheet-{on}.pdf"),
        (f"Quiz for {qd}", f"quiz-{qd}.pdf"),
        ("Parent script", f"parent-script-{qd}.pdf"),
    ]
    return page(
        request,
        "day.html",
        student=student,
        title=f"Day {sel['day_no']}: {on}",
        on=on,
        quiz_date=qd,
        sel=sel,
        math=[(cur().by_id[m["skill_id"]].title, m) for m in sel["math"]],
        files=[(label, f"{on}/{f}", (folder / f).exists()) for label, f in files],
    )


@require_GET
def student_file(request: HttpRequest, rel: str) -> FileResponse:
    root = out_dir(require_student(request)).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not FILE_NAME.match(path.name):
        raise PageError("Not a file this app serves.", 404)
    if not path.exists():
        raise PageError("That file has not been made yet.", 404)
    return FileResponse(path.open("rb"))


# --------------------------------------------------------------------------- quizzes


def _say(c: curriculum.Curriculum, db: DB, item: dict) -> str:
    if item["kind_group"] == "spelling":
        w = item["expected"]
        has = c.sentences.get(w.lower()) or db.sentence(w.lower())
        return f'Say "{w}"' + (f": {build.dictation_sentence(c, db, w)}" if has else "")
    return item.get("speech") or item["prompt_text"]


def _entry_items(db: DB, manifest: dict, crops: dict[str, str]) -> list[dict]:
    c = cur()
    return [
        {**it, "say": _say(c, db, it), "crop": crops.get(it["id"])}
        for it in manifest["items"]
    ]


def _entry_page(
    request: HttpRequest,
    student: sqlite3.Row,
    q: sqlite3.Row,
    crops: dict,
    msg: str | None,
) -> HttpResponse:
    manifest = json.loads(q["manifest"])
    return page(
        request,
        "quiz_entry.html",
        student=student,
        title=f"Quiz for {q['for_date']}",
        quiz=q,
        items=_entry_items(request.db, manifest, crops),
        msg=msg or request.GET.get("msg"),
    )


@require_GET
def open_quiz(request: HttpRequest) -> HttpResponse:
    q = request.db.latest_open_quiz(require_student(request)["id"])
    if q is None:
        return go("/", "No open quiz. Build a day to make one.")
    return go(f"/quiz/{q['id']}")


@require_GET
def quiz_page(request: HttpRequest, quiz_id: int) -> HttpResponse:
    student = require_student(request)
    q = _quiz_for(request.db, student, quiz_id)
    if q["status"] == "graded":
        return _results_page(request, student, q)
    return _entry_page(request, student, q, {}, None)


def entered_answers(manifest: dict, form: QueryDict) -> dict[str, str]:
    """Typed text wins; otherwise right -> expected, blank -> '', wrong -> '?' (as `dq oral`)."""
    got: dict[str, str] = {}
    for it in manifest["items"]:
        text = (form.get(f"got_{it['id']}") or "").strip()
        verdict = form.get(f"verdict_{it['id']}", "right")
        if text:
            got[it["id"]] = text
        elif verdict == "right":
            got[it["id"]] = it["expected"]
        else:
            got[it["id"]] = "" if verdict == "blank" else "?"
    return got


def _review(
    request: HttpRequest,
    student: sqlite3.Row,
    q: sqlite3.Row,
    rows: list[grade.Scored],
    mode: str,
    crops: dict[str, str],
    msg: str | None = None,
) -> HttpResponse:
    return page(
        request,
        "quiz_review.html",
        student=student,
        title=f"Check the quiz for {q['for_date']}",
        quiz=q,
        rows=rows,
        mode=mode,
        crops=crops,
        msg=msg,
    )


def grader_rows(manifest: dict, sheet: dict) -> dict[str, list[dict]]:
    """The parent-script rows (what to say, the answer) with each item's form id attached."""
    ids = {it["n"]: it["id"] for it in manifest["items"]}
    return {
        "spelling": [{**w, "id": ids[w["n"]]} for w in sheet["spelling"]],
        "math": [{**m, "id": ids[m["n"]]} for m in sheet["math"]],
    }


def graded_rows(manifest: dict, form: QueryDict) -> list[grade.Scored]:
    """Checked = right. Unchecked = wrong, judged on what was typed (or '?' if nothing)."""
    got = {}
    for it in manifest["items"]:
        right = form.get(f"right_{it['id']}") == "on"
        typed = (form.get(f"got_{it['id']}") or "").strip()
        got[it["id"]] = it["expected"] if right else (typed or "?")
    rows = grade.score(manifest, got)
    for r in rows:
        want = form.get(f"right_{r.item_id}") == "on"
        if r.correct != want:
            grade.apply_override(r, correct=want)
    return rows


@require_http_methods(["GET", "POST"])
def grader(request: HttpRequest, quiz_id: int) -> HttpResponse:
    student = require_student(request)
    q = _quiz_for(request.db, student, quiz_id)
    if q["status"] == "graded":
        return go(f"/quiz/{quiz_id}")
    manifest = json.loads(q["manifest"])
    if request.method == "POST":
        rows = graded_rows(manifest, request.POST)
        summary = session.record_quiz(
            request.db, cur(), student, q, rows, "manual", date.today()
        )
        ok, n = summary["taught_correct"], summary["taught_items"]
        return go(f"/quiz/{quiz_id}", f"Saved: {ok} of {n} right on taught material.")
    sheet = build.parent_data(
        request.db, cur(), student, manifest, _iso_date(q["for_date"])
    )
    return page(
        request,
        "grader.html",
        student=student,
        title=f"Grade the quiz for {q['for_date']}",
        quiz=q,
        label=sheet["quiz_label"],
        **grader_rows(manifest, sheet),
    )


@require_POST
def review_entry(request: HttpRequest, quiz_id: int) -> HttpResponse:
    student = require_student(request)
    q = _open_quiz(request.db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    rows = grade.score(manifest, entered_answers(manifest, request.POST))
    return _review(request, student, q, rows, "oral", {})


def _read_photo(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PageError("Could not read that file as an image.")
    return img


def _save_crops(student: sqlite3.Row, crops: dict, quiz_id: int) -> dict[str, str]:
    rel = f"{date.today().isoformat()}/grading"
    folder = out_dir(student) / rel
    folder.mkdir(parents=True, exist_ok=True)
    urls = {}
    for k, c in crops.items():
        name = f"quiz{quiz_id}-{k}.png"
        cv2.imwrite(str(folder / name), c)
        urls[k] = f"/files/{rel}/{name}"
    return urls


def transcribe(
    backend_name: str, crops: dict, manifest: dict
) -> tuple[dict | None, str | None]:
    """Returns (transcriptions, None) or (None, reason the model could not be used)."""
    try:
        backend = llm.backend_from_name(backend_name)
    except ValueError as e:
        return None, str(e)
    if backend is None:
        return None, "No vision model configured (set DQ_BACKEND=lmstudio)."
    try:
        return grade.transcribe_all(crops, manifest, backend), None
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        return None, f"The vision model could not be reached or answered oddly: {e}"


@require_POST
def grade_photo(request: HttpRequest, quiz_id: int) -> HttpResponse:
    student = require_student(request)
    q = _open_quiz(request.db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    upload = request.FILES.get("photo")
    if upload is None:
        raise PageError("Choose a photo to upload.")
    try:
        page_img, info = grade.rectify(_read_photo(upload.read()), manifest)
    except grade.GradeError as e:
        raise PageError(f"Could not find the page in the photo: {e}") from e
    crops = grade.crop_items(page_img, manifest)
    urls = _save_crops(student, crops, quiz_id)
    trans, problem = transcribe(settings.DQ_BACKEND, crops, manifest)
    if trans is None:
        msg = f"{problem} Enter the answers by hand; the photo crops are beside each item."
        return _entry_page(request, student, q, urls, msg)
    warn = None if info["ok"] else "The page may be badly warped; check every row."
    rows = grade.score(manifest, trans)
    return _review(request, student, q, rows, "vlm", urls, warn)


@require_POST
def save_quiz(request: HttpRequest, quiz_id: int) -> HttpResponse:
    student = require_student(request)
    q = _open_quiz(request.db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    form = request.POST
    mode = form.get("mode", "oral")
    if mode not in ("oral", "vlm", "manual"):
        raise PageError("Unknown grading mode.")
    got = {
        it["id"]: (form.get(f"got_{it['id']}") or "").strip()
        for it in manifest["items"]
    }
    rows = grade.score(manifest, got)
    for r in rows:
        want = form.get(f"verdict_{r.item_id}") == "right"
        if r.correct != want:
            grade.apply_override(r, correct=want)
    summary = session.record_quiz(
        request.db, cur(), student, q, rows, mode, date.today()
    )
    ok, n = summary["taught_correct"], summary["taught_items"]
    return go(f"/quiz/{quiz_id}", f"Saved: {ok} of {n} right on taught material.")


def _results_page(
    request: HttpRequest, student: sqlite3.Row, q: sqlite3.Row
) -> HttpResponse:
    rows = request.db.results_for_quiz(q["id"])
    taught = [r for r in rows if not r["probe"]]
    probes: dict[str, list[bool]] = {}
    for r in rows:
        if r["probe"]:
            probes.setdefault(r["skill_id"], []).append(bool(r["correct"]))
    return page(
        request,
        "quiz_results.html",
        student=student,
        title=f"Quiz for {q['for_date']}",
        quiz=q,
        rows=rows,
        n=len(taught),
        right=sum(r["correct"] for r in taught),
        misses=[r["expected"] for r in taught if not r["correct"]],
        probes=[(cur().by_id[k].title, all(v)) for k, v in probes.items()],
    )


# --------------------------------------------------------------------------- progress


@require_GET
def history(request: HttpRequest) -> HttpResponse:
    sid = require_student(request)["id"]
    db: DB = request.db
    plans = db.conn.execute(
        "SELECT for_date, day_no FROM plan WHERE student_id = ? ORDER BY for_date DESC",
        (sid,),
    ).fetchall()
    return page(
        request,
        "history.html",
        student=current_student(request),
        title="History",
        quizzes=db.graded_quizzes(sid),
        logs=list(reversed(db.day_logs(sid))),
        plans=plans,
    )


def _days(raw: str | None) -> int:
    try:
        return max(1, min(3650, int(raw or 14)))
    except ValueError as e:
        raise PageError("days must be a number") from e


@require_GET
def report_page(request: HttpRequest) -> HttpResponse:
    student = require_student(request)
    days = _days(request.GET.get("days"))
    rep = report_mod.build_report(request.db, cur(), student, date.today(), days=days)
    return page(
        request, "report.html", student=student, title="Progress", rep=rep, days=days
    )


@require_POST
def report_pdf(request: HttpRequest) -> HttpResponse:
    student = require_student(request)
    days = _days(request.POST.get("days"))
    rep = report_mod.build_report(request.db, cur(), student, date.today(), days=days)
    name = f"report-{date.today().isoformat()}.pdf"
    pdf.render_pdf(home(), "report", rep, out_dir(student) / name)
    return go(f"/files/{name}")


@require_GET
def skills_page(request: HttpRequest) -> HttpResponse:
    student = current_student(request)
    subject = request.GET.get("subject", "")
    units = request.db.units(student["id"]) if student else {}
    wu = scheduler.word_units(units)
    c = cur()
    rows = [
        (s, scheduler.skill_progress(c, units, s, wu).label if student else "")
        for s in c.skills
        if not subject or s.subject == subject
    ]
    return page(
        request,
        "skills.html",
        student=student,
        title="Skills",
        rows=rows,
        subject=subject,
    )


# --------------------------------------------------------------------------- sentences


@require_GET
def sentences_page(request: HttpRequest) -> HttpResponse:
    include = request.GET.get("include_phonics") == "true"
    return page(
        request,
        "sentences.html",
        student=current_student(request),
        title="Dictation sentences",
        words=build.words_missing_sentences(cur(), request.db, include),
        include_phonics=include,
        backend=settings.DQ_BACKEND,
    )


@require_POST
def fill_sentences(request: HttpRequest) -> HttpResponse:
    backend = llm.backend_from_name(settings.DQ_BACKEND)
    if backend is None:
        raise PageError("No model configured (set DQ_BACKEND=lmstudio).")
    include = request.POST.get("include_phonics") == "true"
    done, failed = 0, []
    for w in build.words_missing_sentences(cur(), request.db, include):
        try:
            request.db.set_sentence(
                w.lower(), backend.dictation_sentence(w), source="llm"
            )
            done += 1
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(f"{w} ({e})")
    msg = f"Cached {done} sentences." + (
        f" Failed: {'; '.join(failed[:5])}" if failed else ""
    )
    return go("/sentences", msg)


@require_POST
def set_sentence(request: HttpRequest) -> HttpResponse:
    word = request.POST.get("word", "").strip()
    sentence = request.POST.get("sentence", "").strip()
    if not word or word.lower() not in sentence.lower():
        raise PageError(f"The sentence should contain the word {word!r}.")
    request.db.set_sentence(word.lower(), sentence, source="manual")
    return go("/sentences", f"Saved a sentence for {word}.")


# --------------------------------------------------------------------------- placement


def parse_answers(answers: str) -> list[bool]:
    if not re.fullmatch(r"[yn]*", answers):
        raise PageError("Bad placement state; start again.")
    return [a == "y" for a in answers]


def chosen_tracks(tracks: list[str]) -> tuple[str, ...]:
    chosen = tuple(t for t in placement.TRACKS if t in tracks)
    if not chosen:
        raise PageError("Pick at least one track.")
    return chosen


def _placement_step(request: HttpRequest) -> HttpResponse:
    student = require_student(request)
    form = request.POST
    chosen = chosen_tracks(form.getlist("tracks"))
    day = _iso_date(form["on"]) if form.get("on") else date.today()
    answers = form.get("answers", "") + form.get("answer", "")
    flags = parse_answers(answers)
    item = placement.next_question(cur(), student, day, flags, chosen)
    result = None
    if item is None:
        ask = placement.replay_ask(flags)
        result = placement.run_placement(request.db, cur(), student, day, ask, chosen)
    partial = request.headers.get("HX-Request") == "true"
    return page(
        request,
        "_placement_step.html" if partial else "placement.html",
        student=student,
        title="Placement",
        tracks=chosen,
        answers=answers,
        on=day.isoformat(),
        item=item,
        result=result,
    )


@require_http_methods(["GET", "POST"])
def placement_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        return _placement_step(request)
    return page(
        request,
        "placement.html",
        student=require_student(request),
        title="Placement",
        tracks=placement.TRACKS,
        item=None,
        result=None,
    )
