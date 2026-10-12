"""Web front end for dq: the same daily loop as the CLI, in a browser.

Run with `just run` (uvicorn, hot reload). Data lives in the same place as the CLI's: $DQ_HOME or ~/.dq.
The current student comes from a cookie, then the CLI's default student.
"""

import json
import os
import re
import sqlite3
import urllib.error
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import APIRouter, Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from .. import build, curriculum, grade, llm, placement, render, scheduler, session
from .. import report as report_mod
from ..cli import MOODS, PROJECT_ROOT, default_home, default_student_path
from ..db import DB
from .house_style import HouseStyle, mount

WEB_DIR = Path(__file__).resolve().parent
STUDENT_COOKIE = "dq_student"
FILE_NAME = re.compile(r"^[\w.-]+\.(pdf|png|json)$")

templates = Jinja2Templates(directory=WEB_DIR / "templates")
house = HouseStyle(
    static_url="/static/house-style",
    themes=(
        "swiss",
        "drafting",
        "brutalist",
        "secession",
        "destijl",
        "proun",
        "setback",
        "piranesi",
        "capsule",
        "brion",
        "memphis",
        "plugin",
        "wasmuth",
    ),
    default_theme="wasmuth",
    picker=True,
    key="dq",
)
router = APIRouter()


class PageError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def create_app(
    home: Path | None = None,
    curriculum_dir: Path | None = None,
    backend: str | None = None,
) -> FastAPI:
    app = FastAPI(title="dq")
    app.state.home = Path(home) if home else default_home()
    app.state.home.mkdir(parents=True, exist_ok=True)
    cdir = curriculum_dir or os.environ.get(
        "DQ_CURRICULUM", PROJECT_ROOT / "curriculum"
    )
    app.state.cur = curriculum.load(Path(cdir))
    app.state.backend = (
        backend if backend is not None else os.environ.get("DQ_BACKEND", "lmstudio")
    )
    mount(app, house, WEB_DIR / "static" / "house-style")
    app.include_router(router)
    app.add_exception_handler(PageError, _page_error)
    app.add_exception_handler(KeyError, _missing)
    return app


# --------------------------------------------------------------------------- plumbing


def get_db(request: Request) -> Iterator[DB]:
    # One connection per request; async routes use it on a different thread than the dependency.
    db = DB(request.app.state.home / "dq.db", check_same_thread=False)
    try:
        yield db
    finally:
        db.close()


def get_cur(request: Request) -> curriculum.Curriculum:
    return request.app.state.cur


DBDep = Annotated[DB, Depends(get_db)]


def current_student(request: Request, db: DBDep) -> sqlite3.Row | None:
    """Cookie, then the CLI's default student, then None."""
    names = {s["name"] for s in db.students()}
    name = request.cookies.get(STUDENT_COOKIE)
    if name not in names:
        path = default_student_path(request.app.state.home)
        name = path.read_text().strip() if path.exists() else None
    return db.student(name) if name in names else None


MaybeStudentDep = Annotated[sqlite3.Row | None, Depends(current_student)]


def require_student(student: MaybeStudentDep) -> sqlite3.Row:
    if student is None:
        raise PageError("Add or choose a student first.", 409)
    return student


StudentDep = Annotated[sqlite3.Row, Depends(require_student)]
CurDep = Annotated[curriculum.Curriculum, Depends(get_cur)]


def page(
    request: Request, name: str, db: DB | None = None, **ctx: object
) -> HTMLResponse:
    if db is not None and "students" not in ctx:
        ctx["students"] = [s["name"] for s in db.students()]
    ctx.setdefault("msg", request.query_params.get("msg"))
    return templates.TemplateResponse(request, name, house.context(request, **ctx))


def go(url: str, msg: str | None = None) -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return RedirectResponse(url, status_code=303)


async def _page_error(request: Request, exc: PageError) -> HTMLResponse:
    resp = page(request, "error.html", message=exc.message, students=[])
    resp.status_code = exc.status
    return resp


async def _missing(request: Request, exc: KeyError) -> HTMLResponse:
    return await _page_error(request, PageError(str(exc).strip("'\""), 404))


def out_dir(request: Request, student: sqlite3.Row) -> Path:
    return request.app.state.home / "out" / student["name"]


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


@router.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


# --------------------------------------------------------------------------- students


@router.get("/students")
def students_page(
    request: Request,
    db: DBDep,
    student: MaybeStudentDep,
) -> Response:
    default = default_student_path(request.app.state.home)
    return page(
        request,
        "students.html",
        db,
        student=student,
        rows=db.students(),
        default=default.read_text().strip() if default.exists() else None,
        title="Students",
    )


@router.post("/students")
def add_student(
    request: Request,
    name: Annotated[str, Form()],
    db: DBDep,
    pace_cap: Annotated[int, Form()] = 2,
) -> Response:
    name = name.strip()
    if not re.fullmatch(r"[\w-]+", name):
        raise PageError("Use letters, digits, - or _ for the name.")
    if name in {s["name"] for s in db.students()}:
        raise PageError(f"{name} already exists.")
    db.add_student(name, date.today(), pace_cap=pace_cap)
    path = default_student_path(request.app.state.home)
    if not path.exists():
        path.write_text(name + "\n")
    resp = go("/placement", f"Added {name}. Placement finds where they already are.")
    resp.set_cookie(STUDENT_COOKIE, name, max_age=10 * 365 * 86400)
    return resp


@router.post("/students/select")
def select_student(name: Annotated[str, Form()], db: DBDep) -> Response:
    db.student(name)
    resp = go("/")
    resp.set_cookie(STUDENT_COOKIE, name, max_age=10 * 365 * 86400)
    return resp


@router.post("/students/default")
def set_default(request: Request, name: Annotated[str, Form()], db: DBDep) -> Response:
    db.student(name)
    default_student_path(request.app.state.home).write_text(name + "\n")
    return go("/students", f"{name} is now the default student (CLI too).")


# --------------------------------------------------------------------------- today


@router.get("/")
def dashboard(
    request: Request,
    db: DBDep,
    student: MaybeStudentDep,
) -> Response:
    if student is None:
        return go("/students", "Add a student to get started.")
    sid, today = student["id"], date.today()
    days = db.quiz_days(sid)
    yesterday = (today - timedelta(days=1)).isoformat()
    log = {r["on_date"]: r for r in db.day_logs(sid, yesterday)}.get(yesterday)
    return page(
        request,
        "dashboard.html",
        db,
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


@router.post("/mood")
def log_mood(
    on: Annotated[str, Form()],
    mood: Annotated[str, Form()],
    db: DBDep,
    student: StudentDep,
    story: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    if mood not in MOODS:
        raise PageError(f"mood must be one of {', '.join(MOODS)}")
    done = {"done": True, "skipped": False}.get(story)
    db.log_day(
        student["id"], on, mood=mood, composition_done=done, note=note.strip() or None
    )
    extra = (
        " If the next day also goes badly, the load lightens by itself."
        if mood in ("hard", "tears")
        else ""
    )
    return go("/", f"Logged {mood} for {on}.{extra}")


@router.post("/day")
def build_day(
    request: Request,
    on: Annotated[str, Form()],
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
    force: Annotated[bool, Form()] = False,
) -> Response:
    day = date.fromisoformat(on)
    build.build_day(db, cur, request.app.state.home, student["name"], day, force=force)
    return go(f"/day/{day.isoformat()}", "Rebuilt." if force else None)


@router.get("/day/{on}")
def day_page(
    request: Request,
    on: str,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
) -> Response:
    data = _plan_data(db, student, on)
    sel = data["selection"]
    qd = (
        data.get("quiz_date")
        or (date.fromisoformat(on) + timedelta(days=1)).isoformat()
    )
    folder = out_dir(request, student) / on
    files = [
        ("Worksheet", f"worksheet-{on}.pdf"),
        (f"Quiz for {qd}", f"quiz-{qd}.pdf"),
        ("Parent script", f"parent-script-{qd}.pdf"),
    ]
    return page(
        request,
        "day.html",
        db,
        student=student,
        title=f"Day {sel['day_no']}: {on}",
        on=on,
        quiz_date=qd,
        sel=sel,
        math=[(cur.by_id[m["skill_id"]].title, m) for m in sel["math"]],
        files=[(label, f"{on}/{f}", (folder / f).exists()) for label, f in files],
    )


@router.get("/files/{rel:path}")
def student_file(request: Request, rel: str, student: StudentDep) -> FileResponse:
    root = out_dir(request, student).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not FILE_NAME.match(path.name):
        raise PageError("Not a file this app serves.", 404)
    if not path.exists():
        raise PageError("That file has not been made yet.", 404)
    return FileResponse(path)


# --------------------------------------------------------------------------- quizzes


def _say(cur: curriculum.Curriculum, db: DB, item: dict) -> str:
    if item["kind_group"] == "spelling":
        w = item["expected"]
        has = cur.sentences.get(w.lower()) or db.sentence(w.lower())
        return f'Say "{w}"' + (
            f": {build.dictation_sentence(cur, db, w)}" if has else ""
        )
    return item.get("speech") or item["prompt_text"]


def _entry_items(
    cur: curriculum.Curriculum, db: DB, manifest: dict, crops: dict[str, str]
) -> list[dict]:
    return [
        {**it, "say": _say(cur, db, it), "crop": crops.get(it["id"])}
        for it in manifest["items"]
    ]


@router.get("/quiz")
def open_quiz(db: DBDep, student: StudentDep) -> Response:
    q = db.latest_open_quiz(student["id"])
    if q is None:
        return go("/", "No open quiz. Build a day to make one.")
    return go(f"/quiz/{q['id']}")


@router.get("/quiz/{quiz_id}")
def quiz_page(
    request: Request,
    quiz_id: int,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
) -> Response:
    q = _quiz_for(db, student, quiz_id)
    if q["status"] == "graded":
        return _results_page(request, db, cur, student, q)
    manifest = json.loads(q["manifest"])
    return page(
        request,
        "quiz_entry.html",
        db,
        student=student,
        title=f"Quiz for {q['for_date']}",
        quiz=q,
        items=_entry_items(cur, db, manifest, {}),
    )


def _entered_answers(manifest: dict, form: FormData) -> dict[str, str]:
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
    request: Request,
    db: DB,
    student: sqlite3.Row,
    q: sqlite3.Row,
    rows: list[grade.Scored],
    mode: str,
    crops: dict[str, str],
    msg: str | None = None,
) -> HTMLResponse:
    return page(
        request,
        "quiz_review.html",
        db,
        student=student,
        title=f"Check the quiz for {q['for_date']}",
        quiz=q,
        rows=rows,
        mode=mode,
        crops=crops,
        msg=msg,
    )


@router.post("/quiz/{quiz_id}/review")
async def review_entry(
    request: Request,
    quiz_id: int,
    db: DBDep,
    student: StudentDep,
) -> Response:
    q = _open_quiz(db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    rows = grade.score(manifest, _entered_answers(manifest, await request.form()))
    return _review(request, db, student, q, rows, "oral", {})


def _open_quiz(db: DB, student: sqlite3.Row, quiz_id: int) -> sqlite3.Row:
    q = _quiz_for(db, student, quiz_id)
    if q["status"] != "open":
        raise PageError("This quiz was already graded.", 409)
    return q


def _read_photo(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PageError("Could not read that file as an image.")
    return img


def _save_crops(
    request: Request, student: sqlite3.Row, crops: dict, quiz_id: int
) -> dict[str, str]:
    rel = f"{date.today().isoformat()}/grading"
    folder = out_dir(request, student) / rel
    folder.mkdir(parents=True, exist_ok=True)
    urls = {}
    for k, c in crops.items():
        name = f"quiz{quiz_id}-{k}.png"
        cv2.imwrite(str(folder / name), c)
        urls[k] = f"/files/{rel}/{name}"
    return urls


def _transcribe(
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


@router.post("/quiz/{quiz_id}/photo")
async def grade_photo(
    request: Request,
    quiz_id: int,
    photo: UploadFile,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
) -> Response:
    q = _open_quiz(db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    try:
        page_img, info = grade.rectify(_read_photo(await photo.read()), manifest)
    except grade.GradeError as e:
        raise PageError(f"Could not find the page in the photo: {e}") from e
    crops = grade.crop_items(page_img, manifest)
    urls = _save_crops(request, student, crops, quiz_id)
    trans, problem = _transcribe(request.app.state.backend, crops, manifest)
    if trans is None:
        msg = (
            problem
            + " Enter the answers by hand; the photo crops are beside each item."
        )
        return page(
            request,
            "quiz_entry.html",
            db,
            student=student,
            title=f"Quiz for {q['for_date']}",
            quiz=q,
            items=_entry_items(cur, db, manifest, urls),
            msg=msg,
        )
    warn = None if info["ok"] else "The page may be badly warped; check every row."
    rows = grade.score(manifest, trans)
    return _review(request, db, student, q, rows, "vlm", urls, warn)


@router.post("/quiz/{quiz_id}/save")
async def save_quiz(
    request: Request,
    quiz_id: int,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
) -> Response:
    q = _open_quiz(db, student, quiz_id)
    manifest = json.loads(q["manifest"])
    form = await request.form()
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
    summary = session.record_quiz(db, cur, student, q, rows, mode, date.today())
    ok, n = summary["taught_correct"], summary["taught_items"]
    return go(f"/quiz/{quiz_id}", f"Saved: {ok} of {n} right on taught material.")


def _results_page(
    request: Request,
    db: DB,
    cur: curriculum.Curriculum,
    student: sqlite3.Row,
    q: sqlite3.Row,
) -> HTMLResponse:
    rows = db.results_for_quiz(q["id"])
    taught = [r for r in rows if not r["probe"]]
    probes: dict[str, list[bool]] = {}
    for r in rows:
        if r["probe"]:
            probes.setdefault(r["skill_id"], []).append(bool(r["correct"]))
    return page(
        request,
        "quiz_results.html",
        db,
        student=student,
        title=f"Quiz for {q['for_date']}",
        quiz=q,
        rows=rows,
        n=len(taught),
        right=sum(r["correct"] for r in taught),
        misses=[r["expected"] for r in taught if not r["correct"]],
        probes=[(cur.by_id[k].title, all(v)) for k, v in probes.items()],
    )


# --------------------------------------------------------------------------- progress


@router.get("/history")
def history(request: Request, db: DBDep, student: StudentDep) -> Response:
    sid = student["id"]
    plans = db.conn.execute(
        "SELECT for_date, day_no FROM plan WHERE student_id = ? ORDER BY for_date DESC",
        (sid,),
    ).fetchall()
    return page(
        request,
        "history.html",
        db,
        student=student,
        title="History",
        quizzes=db.graded_quizzes(sid),
        logs=list(reversed(db.day_logs(sid))),
        plans=plans,
    )


@router.get("/report")
def report_page(
    request: Request,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
    days: int = 14,
) -> Response:
    rep = report_mod.build_report(db, cur, student, date.today(), days=days)
    return page(
        request,
        "report.html",
        db,
        student=student,
        title="Progress",
        rep=rep,
        days=days,
    )


@router.post("/report/pdf")
def report_pdf(
    request: Request,
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
    days: Annotated[int, Form()] = 14,
) -> Response:
    today = date.today().isoformat()
    rep = report_mod.build_report(db, cur, student, date.today(), days=days)
    name = f"report-{today}.pdf"
    render.render_pdf(
        request.app.state.home, "report", rep, out_dir(request, student) / name
    )
    return go(f"/files/{name}")


@router.get("/skills")
def skills_page(
    request: Request,
    db: DBDep,
    cur: CurDep,
    student: MaybeStudentDep,
    subject: str = "",
) -> Response:
    units = db.units(student["id"]) if student else {}
    wu = scheduler.word_units(units)
    rows = [
        (s, scheduler.skill_progress(cur, units, s, wu).label if student else "")
        for s in cur.skills
        if not subject or s.subject == subject
    ]
    return page(
        request,
        "skills.html",
        db,
        student=student,
        title="Skills",
        rows=rows,
        subject=subject,
    )


# --------------------------------------------------------------------------- sentences


@router.get("/sentences")
def sentences_page(
    request: Request,
    db: DBDep,
    cur: CurDep,
    student: MaybeStudentDep,
    include_phonics: bool = False,
) -> Response:
    return page(
        request,
        "sentences.html",
        db,
        student=student,
        title="Dictation sentences",
        words=build.words_missing_sentences(cur, db, include_phonics),
        include_phonics=include_phonics,
        backend=request.app.state.backend,
    )


@router.post("/sentences/fill")
def fill_sentences(
    request: Request,
    db: DBDep,
    cur: CurDep,
    include_phonics: Annotated[bool, Form()] = False,
) -> Response:
    backend = llm.backend_from_name(request.app.state.backend)
    if backend is None:
        raise PageError("No model configured (set DQ_BACKEND=lmstudio).")
    done, failed = 0, []
    for w in build.words_missing_sentences(cur, db, include_phonics):
        try:
            db.set_sentence(w.lower(), backend.dictation_sentence(w), source="llm")
            done += 1
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(f"{w} ({e})")
    msg = f"Cached {done} sentences." + (
        f" Failed: {'; '.join(failed[:5])}" if failed else ""
    )
    return go("/sentences", msg)


@router.post("/sentences/set")
def set_sentence(
    word: Annotated[str, Form()], sentence: Annotated[str, Form()], db: DBDep
) -> Response:
    if word.lower() not in sentence.lower():
        raise PageError(f"The sentence should contain the word {word!r}.")
    db.set_sentence(word.lower(), sentence.strip(), source="manual")
    return go("/sentences", f"Saved a sentence for {word}.")


# --------------------------------------------------------------------------- placement


def _parse_answers(answers: str) -> list[bool]:
    if not re.fullmatch(r"[yn]*", answers):
        raise PageError("Bad placement state; start again.")
    return [a == "y" for a in answers]


def _tracks(tracks: list[str]) -> tuple[str, ...]:
    chosen = tuple(t for t in placement.TRACKS if t in tracks)
    if not chosen:
        raise PageError("Pick at least one track.")
    return chosen


@router.get("/placement")
def placement_start(request: Request, db: DBDep, student: StudentDep) -> Response:
    return page(
        request,
        "placement.html",
        db,
        student=student,
        title="Placement",
        tracks=placement.TRACKS,
        item=None,
        result=None,
    )


@router.post("/placement")
def placement_step(
    request: Request,
    tracks: Annotated[list[str], Form()],
    db: DBDep,
    cur: CurDep,
    student: StudentDep,
    answers: Annotated[str, Form()] = "",
    answer: Annotated[str, Form()] = "",
    on: Annotated[str, Form()] = "",
) -> Response:
    chosen = _tracks(tracks)
    day = date.fromisoformat(on) if on else date.today()
    answers += answer
    flags = _parse_answers(answers)
    item = placement.next_question(cur, student, day, flags, chosen)
    result = None
    if item is None:
        result = placement.run_placement(
            db, cur, student, day, placement.replay_ask(flags), chosen
        )
    name = (
        "_placement_step.html"
        if request.headers.get("HX-Request")
        else "placement.html"
    )
    return page(
        request,
        name,
        db,
        student=student,
        title="Placement",
        tracks=chosen,
        answers=answers,
        on=day.isoformat(),
        item=item,
        result=result,
    )
