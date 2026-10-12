"""Command-line interface:  python -m dq <command>   (or `dq <command>` after `pip install -e .`)

A normal day, in this order:
    1. quiz (printed yesterday)           parent reads words, child writes
    2. dq grade photo.jpg                 or  dq oral
    3. dq mood ok                         how last night's worksheet went
    4. dq next                            prints tonight's worksheet and tomorrow's quiz

NAME is optional everywhere: commands use the default student (set by the first `dq init`, or `dq default NAME`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from . import (
    build,
    curriculum,
    entry,
    grade,
    llm,
    placement,
    render,
    scheduler,
    session,
)
from . import report as report_mod
from .db import DB

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOODS = ("easy", "ok", "hard", "tears")


def default_home() -> Path:
    return Path(os.environ.get("DQ_HOME", "~/.dq")).expanduser()


def parse_date(s: str | None) -> date:
    return date.fromisoformat(s) if s else date.today()


def load_curriculum(args) -> curriculum.Curriculum:
    path = Path(
        args.curriculum or os.environ.get("DQ_CURRICULUM", PROJECT_ROOT / "curriculum")
    )
    return curriculum.load(path)


def open_db(args) -> tuple[DB, Path]:
    home = Path(args.home) if args.home else default_home()
    return DB(home / "dq.db"), home


def default_student_path(home: Path) -> Path:
    return home / "default_student"


def resolve_student(name: str | None, home: Path) -> str:
    if name:
        return name
    path = default_student_path(home)
    if path.exists() and path.read_text().strip():
        return path.read_text().strip()
    raise KeyError("no student given and no default recorded; run `dq default NAME`")


def split_positionals(words: list[str], n_tail: int) -> tuple[str | None, list[str]]:
    """Split `[NAME] tail...` into (name or None, tail)."""
    if len(words) == n_tail:
        return None, words
    if len(words) == n_tail + 1:
        return words[0], words[1:]
    raise KeyError(f"expected [NAME] plus {n_tail} more argument(s), got {len(words)}")


def open_for_student(args) -> tuple[DB, Path]:
    db, home = open_db(args)
    args.name = resolve_student(args.name, home)
    return db, home


# --------------------------------------------------------------------------- commands


def cmd_validate(args) -> int:
    cur = load_curriculum(args)
    errs = curriculum.validate(cur)
    n_sp = len(cur.subject("spelling"))
    n_m = len(cur.subject("math"))
    words = sum(len(s.words) for s in cur.subject("spelling"))
    print(
        f"{len(cur.skills)} skills ({n_sp} spelling with {words} words, {n_m} math), "
        f"{len(cur.strands)} strands, {len(cur.sentences)} dictation sentences"
    )
    for e in errs:
        print("  ERROR:", e)
    print("curriculum is valid" if not errs else f"{len(errs)} problem(s) found")
    return 1 if errs else 0


def cmd_skills(args) -> int:
    cur = load_curriculum(args)
    units, wu = {}, None
    if args.student:
        db, _ = open_db(args)
        units = db.units(db.student(args.student)["id"])
        wu = scheduler.word_units(units)
    for s in cur.skills:
        if args.subject and s.subject != args.subject:
            continue
        status = ""
        if args.student:
            p = scheduler.skill_progress(cur, units, s, wu)
            status = f"  [{p.label}]"
        print(f"{s.id:<28} g{s.grade}  {s.title}{status}")
    return 0


def cmd_init(args) -> int:
    db, home = open_db(args)
    try:
        db.add_student(args.name, parse_date(args.date), pace_cap=args.pace_cap)
    except Exception as e:  # noqa: BLE001
        print(f"could not add student: {e}")
        return 1
    print(f"Added {args.name}. Data lives in {home / 'dq.db'}")
    if not default_student_path(home).exists():
        default_student_path(home).write_text(args.name + "\n")
        print(f"{args.name} is now the default student.")
    print(
        f"Recommended next step: dq placement {args.name}   (about 10 minutes, you ask and he answers aloud)"
    )
    print(f"Or skip placement and start from the beginning with: dq next {args.name}")
    return 0


def ask_yes_no(prompt: str) -> bool:
    while True:
        reply = input(prompt).strip().lower()
        if reply in ("y", "n"):
            return reply == "y"
        print("   please type y or n")


def cmd_default(args) -> int:
    db, home = open_db(args)
    if args.name:
        db.student(args.name)
        default_student_path(home).write_text(args.name + "\n")
        print(f"Default student is now {args.name}.")
        return 0
    print(resolve_student(None, home))
    return 0


def cmd_placement(args) -> int:
    db, _ = open_for_student(args)
    cur = load_curriculum(args)
    student = db.student(args.name)
    on = parse_date(args.date)
    print(
        "Placement: ask each item aloud. Type y if he got it right, n if not, then Enter."
    )
    print("Don't help. Stop whenever he is tired; you can rerun later.\n")

    def ask(item: dict) -> bool:
        if item["kind"] == "word":
            extra = f"  ({item['sentence']})" if item["sentence"] else ""
            print(
                f'[{item["title"]}] Say the word: "{item["say"]}"{extra}   (he writes or spells it aloud)'
            )
        else:
            print(f"[{item['title']}] {item['say']}   [answer: {item['expected']}]")
        return ask_yes_no("   right? (y/n) > ")

    tracks = tuple(args.tracks) if args.tracks else placement.TRACKS
    rep = placement.run_placement(db, cur, student, on, ask, tracks)
    print("\nPlacement result")
    for t, r in rep.items():
        print(
            f"  {t:<8} starts at: {r['starts_at']}  ({r['frontier']}/{r['total']} skills already known, {r['asked']} checks)"
        )
    print(f"\nNext: dq next {args.name}")
    return 0


def cmd_next(args) -> int:
    db, home = open_for_student(args)
    cur = load_curriculum(args)
    on = parse_date(args.date)
    qd = parse_date(args.quiz_date) if args.quiz_date else None
    b = build.build_day(db, cur, home, args.name, on, force=args.force, quiz_date=qd)
    s = b.selection
    print(
        f"{'Built' if b.created else 'Already built'} day {s.day_no} for {args.name} ({on.isoformat()})"
    )
    print(f"  worksheet : {b.worksheet}")
    print(f"  quiz      : {b.quiz}   (for {b.quiz_date})")
    print(f"  script    : {b.parent}")
    words = ", ".join(
        f"{x['word']}{'*' if x['role'] == 'new' else ''}" for x in s.spelling
    )
    print(f"  words     : {words}   (* = new)")
    print(
        "  math      : "
        + "; ".join(f"{cur.by_id[m['skill_id']].title} ×{m['n']}" for m in s.math)
    )
    print(
        f"  pace {s.pace}, clean-quiz streak {s.clean_days}"
        + (", probing for skills he may already know" if s.probing else "")
    )
    if s.load_reason:
        print(f"  note      : {s.load_reason}")
    if s.consolidating:
        print(
            "  note      : last quiz was hard, so no new math today and fewer new words; reviewing instead"
        )
    return 0


def _finish(
    db: DB, cur, home: Path, student, quiz_row, rows: list, mode: str, on: date
) -> None:
    summary = session.record_quiz(db, cur, student, quiz_row, rows, mode, on)
    ok, n = summary["taught_correct"], summary["taught_items"]
    print(
        f"\nSaved. {ok} of {n} right on taught material ({round(100 * ok / max(1, n))}%)."
    )
    for sk in summary["probes_passed"]:
        print(f"  He already knew '{cur.by_id[sk].title}': skipping ahead.")
    for sk in summary["probes_failed"]:
        print(f"  '{cur.by_id[sk].title}' isn't known yet; it will be taught normally.")
    if summary["misses"]:
        print("  To practise tonight: " + ", ".join(summary["misses"]))
    print(
        f"\nNext: dq mood {student['name']} <easy|ok|hard|tears>   then   dq next {student['name']}"
    )


def _pick_quiz(db: DB, student, args, on: date):
    if args.quiz:
        return db.quiz(args.quiz)
    q = db.latest_open_quiz(student["id"], on.isoformat())
    if q is None:
        raise SystemExit(
            "No open quiz to grade. (A quiz is created by `dq next` the day before.)"
        )
    return q


def cmd_oral(args) -> int:
    db, home = open_for_student(args)
    cur = load_curriculum(args)
    student = db.student(args.name)
    on = parse_date(args.date)
    q = _pick_quiz(db, student, args, on)
    manifest = json.loads(q["manifest"])
    print(f"Quiz for {q['for_date']} ({len(manifest['items'])} items)")
    rows = entry.run_entry(
        manifest,
        sentence_fn=lambda w: (
            build.dictation_sentence(cur, db, w)
            if cur.sentences.get(w.lower()) or db.sentence(w.lower())
            else ""
        ),
    )
    rows = entry.review_loop(rows)
    _finish(db, cur, home, student, q, rows, "oral", on)
    return 0


def cmd_grade(args) -> int:
    import cv2

    args.name, (args.photo,) = split_positionals(args.words, 1)
    db, home = open_for_student(args)
    cur = load_curriculum(args)
    student = db.student(args.name)
    on = parse_date(args.date)
    q = _pick_quiz(db, student, args, on)
    manifest = json.loads(q["manifest"])
    img = cv2.imread(args.photo)
    if img is None:
        print(f"Could not read image {args.photo}")
        return 1
    try:
        page, info = grade.rectify(img, manifest)
    except grade.GradeError as e:
        print(f"Could not read the page: {e}")
        print("Tip: use `dq oral` to enter results by hand instead.")
        return 1
    if not info["ok"]:
        print("Warning: the page may be badly warped; double-check the results below.")
    crops = grade.crop_items(page, manifest)
    audit = home / "out" / args.name / on.isoformat() / "grading"
    audit.mkdir(parents=True, exist_ok=True)
    for k, c in crops.items():
        cv2.imwrite(str(audit / f"{k}.png"), c)
    backend = llm.backend_from_name(args.backend)
    if backend is None:
        print(
            "No vision model configured (use --backend lmstudio). Crops saved to", audit
        )
        print("Falling back to quick manual entry.\n")
        rows = entry.run_entry(manifest)
        mode = "manual"
    else:
        trans = grade.transcribe_all(crops, manifest, backend)
        rows = grade.score(manifest, trans)
        mode = "vlm"
    if not args.yes or mode == "manual":
        rows = entry.review_loop(rows)
    _finish(db, cur, home, student, q, rows, mode, on)
    return 0


def cmd_mood(args) -> int:
    args.name, (args.mood,) = split_positionals(args.words, 1)
    if args.mood not in MOODS:
        raise KeyError(f"mood must be one of {', '.join(MOODS)}; got {args.mood!r}")
    db, _ = open_for_student(args)
    student = db.student(args.name)
    on = parse_date(args.date) if args.date else date.today() - timedelta(days=1)
    done = {"done": True, "skipped": False, None: None}[args.story]
    db.log_day(
        student["id"],
        on.isoformat(),
        mood=args.mood,
        composition_done=done,
        note=args.note,
    )
    print(
        f"Logged: {args.name} {on.isoformat()} mood={args.mood}"
        + (f", story {args.story}" if args.story else "")
    )
    if args.mood in ("hard", "tears"):
        print(
            "Noted. If tomorrow also goes badly, the program will lighten the load by itself."
        )
    return 0


def cmd_report(args) -> int:
    db, home = open_for_student(args)
    cur = load_curriculum(args)
    student = db.student(args.name)
    on = parse_date(args.date)
    rep = report_mod.build_report(db, cur, student, on, days=args.days)
    print(report_mod.format_text(rep))
    out_dir = home / "out" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.narrate:
        backend = llm.backend_from_name(args.backend or "lmstudio")
        try:
            note = backend.narrate(
                {
                    k: rep[k]
                    for k in (
                        "questions",
                        "accuracy",
                        "tears_days",
                        "load_reductions",
                        "recommendations",
                    )
                }
            )
            print("\n" + note)
            rep["narrative"] = note
        except Exception as e:  # noqa: BLE001
            print(f"\n(could not reach the model for a narrative: {e})")
    if args.json:
        p = out_dir / f"report-{on.isoformat()}.json"
        p.write_text(json.dumps(rep, indent=1))
        print(f"\nJSON: {p}")
    if args.pdf:
        p = render.render_pdf(
            home, "report", rep, out_dir / f"report-{on.isoformat()}.pdf"
        )
        print(f"\nPDF: {p}")
    return 0


def cmd_sentences(args) -> int:
    db, _ = open_db(args)
    cur = load_curriculum(args)
    want = []
    for s in cur.subject("spelling"):
        if not (args.all or s.track == "sight" or s.needs_sentence):
            continue
        for w in s.words:
            if w.lower() not in cur.sentences and not db.sentence(w.lower()):
                want.append(w)
    want = sorted(set(want))
    print(f"{len(want)} words without a dictation sentence")
    if not args.fill:
        print("Run with --fill --backend lmstudio to generate and cache them.")
        return 0
    backend = llm.backend_from_name(args.backend or "lmstudio")
    done = 0
    for w in want:
        try:
            db.set_sentence(w.lower(), backend.dictation_sentence(w), source="llm")
            done += 1
        except Exception as e:  # noqa: BLE001
            print(f"  {w}: {e}")
    print(f"cached {done} sentences")
    return 0


def cmd_status(args) -> int:
    db, _ = open_for_student(args)
    student = db.student(args.name)
    on = parse_date(args.date)
    plan = db.plan_for(student["id"], on.isoformat())
    q = db.latest_open_quiz(student["id"])
    print(
        f"{args.name}: story stage {student['composition_stage']}, pace cap {student['pace_cap']}"
    )
    print(f"  plan for {on.isoformat()}: {'built' if plan else 'not built yet'}")
    print(f"  open quiz: {q['for_date'] if q else 'none'}")
    days = db.quiz_days(student["id"])
    if days:
        d, a, n = days[-1]
        print(f"  last graded quiz: {d}, {round(100 * a)}% of {n}")
    print(f"  clean-quiz streak: {scheduler.clean_day_streak(db, student['id'])}")
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dq", description="Daily quiz and worksheet system"
    )
    p.add_argument("--home", help="data directory (default $DQ_HOME or ~/.dq)")
    p.add_argument(
        "--curriculum", help="curriculum directory (default: the project's curriculum/)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="check the curriculum files").set_defaults(
        fn=cmd_validate
    )

    sp = sub.add_parser("skills", help="list skills")
    sp.add_argument("--subject", choices=["spelling", "math"])
    sp.add_argument("--student")
    sp.set_defaults(fn=cmd_skills)

    sp = sub.add_parser("default", help="show or set the default student")
    sp.add_argument("name", nargs="?")
    sp.set_defaults(fn=cmd_default)

    sp = sub.add_parser("init", help="add a student")
    sp.add_argument("name")
    sp.add_argument("--pace-cap", type=int, default=2, choices=[1, 2, 3])
    sp.add_argument("--date")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser(
        "placement", help="find where the student already is (oral, ~10 minutes)"
    )
    sp.add_argument("name", nargs="?")
    sp.add_argument("--tracks", nargs="*", choices=list(placement.TRACKS))
    sp.add_argument("--date")
    sp.set_defaults(fn=cmd_placement)

    sp = sub.add_parser(
        "next", help="grade nothing; build tonight's worksheet and tomorrow's quiz"
    )
    sp.add_argument("name", nargs="?")
    sp.add_argument("--date")
    sp.add_argument(
        "--quiz-date", help="when the quiz will be taken (default: tomorrow)"
    )
    sp.add_argument(
        "--force", action="store_true", help="rebuild today's plan from scratch"
    )
    sp.set_defaults(fn=cmd_next)

    sp = sub.add_parser(
        "oral", help="enter quiz results by hand (fastest, most reliable)"
    )
    sp.add_argument("name", nargs="?")
    sp.add_argument("--quiz", type=int)
    sp.add_argument("--date")
    sp.set_defaults(fn=cmd_oral)

    sp = sub.add_parser("grade", help="grade a photo of the quiz")
    sp.add_argument("words", nargs="+", metavar="[NAME] PHOTO")
    sp.add_argument("--backend", default=None, help="vision model: lmstudio | none")
    sp.add_argument("--quiz", type=int)
    sp.add_argument("--date")
    sp.add_argument("--yes", action="store_true", help="accept without the review step")
    sp.set_defaults(fn=cmd_grade)

    sp = sub.add_parser("mood", help="log how the last worksheet went")
    sp.add_argument("words", nargs="+", metavar="[NAME] MOOD")
    sp.add_argument("--story", choices=["done", "skipped"])
    sp.add_argument("--date", help="the day of the worksheet (default: yesterday)")
    sp.add_argument("--note")
    sp.set_defaults(fn=cmd_mood)

    sp = sub.add_parser("report", help="progress report")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--days", type=int, default=14)
    sp.add_argument("--date")
    sp.add_argument("--pdf", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument(
        "--narrate",
        action="store_true",
        help="ask a model to write a short note from the report data",
    )
    sp.add_argument("--backend", default=None)
    sp.set_defaults(fn=cmd_report)

    sp = sub.add_parser(
        "sentences", help="dictation sentences for words that need them"
    )
    sp.add_argument("--fill", action="store_true")
    sp.add_argument("--all", action="store_true", help="include phonics words too")
    sp.add_argument("--backend", default=None)
    sp.set_defaults(fn=cmd_sentences)

    sp = sub.add_parser("status", help="where things stand")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--date")
    sp.set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyError as e:
        print(str(e).strip("'\""))
        return 1


if __name__ == "__main__":
    sys.exit(main())
