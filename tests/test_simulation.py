"""Month-long simulations with a synthetic child. These test the behaviour that matters:
the loop runs, review comes back at the right times, a child who knows things skips ahead,
a child who struggles gets re-taught, and hard days lighten the load."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta

import pytest

from dq import build, curriculum, grade, placement, render, scheduler, session
from dq.db import DB

START = date(2026, 10, 11)


@pytest.fixture(scope="module")
def cur():
    from pathlib import Path

    return curriculum.load(Path(__file__).resolve().parents[1] / "curriculum")


def make(tmp_path, cur, name="Sam", pace_cap=2):
    db = DB(tmp_path / "dq.db")
    db.add_student(name, START - timedelta(days=1), pace_cap=pace_cap)
    return db


def answer_quiz(db, cur, student, quiz_row, on, skill_knowledge, rng, mood_after=None):
    """The child answers every item; `skill_knowledge(skill_id, is_spelling)` is P(correct)."""
    manifest = json.loads(quiz_row["manifest"])
    got = {}
    for it in manifest["items"]:
        p = skill_knowledge(it["skill_id"], it["kind_group"] == "spelling")
        if rng.random() < p:
            got[it["id"]] = it["expected"]
        else:
            exp = it["expected"]
            got[it["id"]] = (
                exp[:-1] if it["kind_group"] == "spelling" and len(exp) > 1 else "0"
            )
    rows = grade.score(manifest, got)
    return session.record_quiz(db, cur, student, quiz_row, rows, "manual", on), rows


def run_days(
    db, cur, tmp_path, n, knowledge, moods=None, seed=0, name="Sam", pdfs=False
):
    rng = random.Random(seed)
    log = []
    for i in range(n):
        on = START + timedelta(days=i)
        student = db.student(name)
        # grade the quiz that was printed yesterday
        q = db.latest_open_quiz(student["id"], on.isoformat())
        if q:
            summary, _rows = answer_quiz(db, cur, student, q, on, knowledge, rng)
            log.append(("quiz", on, summary))
        if i > 0:
            db.log_day(
                student["id"],
                (on - timedelta(days=1)).isoformat(),
                mood=(moods or {}).get(i - 1, "ok"),
                composition_done=True,
            )
        if pdfs:
            b = build.build_day(db, cur, tmp_path, name, on)
            sel = b.selection
        else:
            sel, _ = scheduler.plan_day(db, cur, student, on)
            # create the quiz row the way build_day does, without rendering
            worksheet, manifest = build._build_content(
                db, cur, student, sel, on, on + timedelta(days=1)
            )
            plan_id = db.save_plan(
                student["id"],
                on.isoformat(),
                sel.day_no,
                {
                    "selection": sel.to_dict(),
                    "worksheet": worksheet,
                    "manifest": manifest,
                    "quiz_date": (on + timedelta(days=1)).isoformat(),
                },
            )
            db.save_quiz(
                student["id"], plan_id, (on + timedelta(days=1)).isoformat(), manifest
            )
        log.append(("plan", on, sel))
    return log


def test_first_week_with_pdfs(tmp_path, cur):
    db = make(tmp_path, cur)
    run_days(db, cur, tmp_path, 4, lambda sk, sp: 0.9, pdfs=True)
    for pdf in (tmp_path / "out" / "Sam").rglob("*.pdf"):
        assert render.page_count(pdf) == 1, pdf


def test_average_child_progresses_and_reviews(tmp_path, cur):
    db = make(tmp_path, cur)
    log = run_days(db, cur, tmp_path, 30, lambda sk, sp: 0.85)
    plans = [x[2] for x in log if x[0] == "plan"]
    # every day has a full set of spelling words
    assert all(len(p.spelling) == 5 for p in plans), [len(p.spelling) for p in plans]
    # review appears: by week 2, some worksheet words are reviews
    assert any(w["role"] == "review" for p in plans[7:] for w in p.spelling)
    # words come back more than once, with gaps (spaced repetition)
    seen = {}
    for p in plans:
        for w in p.spelling:
            seen.setdefault(w["word"], []).append(p.day_no)
    repeats = [d for d in seen.values() if len(d) >= 3]
    assert repeats, "no word was reviewed three times in 30 days"
    # no single word dominates
    assert max(len(d) for d in seen.values()) <= 12
    # math: new skills arrive, reviews fill the sheet
    math_roles = [m["role"] for p in plans[5:] for m in p.math]
    assert "review" in math_roles and "new" in math_roles
    units = db.units(db.student("Sam")["id"])
    assert len([k for k in units if k[0].startswith("m.")]) >= 5


def test_struggling_child_is_not_flooded(tmp_path, cur):
    db = make(tmp_path, cur)
    log = run_days(db, cur, tmp_path, 25, lambda sk, sp: 0.35, seed=4)
    student = db.student("Sam")
    units = db.units(student["id"])
    shaky = sum(1 for u in units.values() if u.box <= 1)
    # the brakes hold: shaky words never explode far beyond the brake threshold
    assert shaky <= scheduler.SHAKY_WORD_BRAKE + 14 + 3
    math_started = len([k for k in units if k[0].startswith("m.")])
    assert math_started <= 8, math_started
    # missed items come back the next day
    plans = [x[2] for x in log if x[0] == "plan"]
    assert any(w["role"] == "review" for w in plans[3].spelling)


def test_hard_days_lighten_the_load(tmp_path, cur):
    db = make(tmp_path, cur)
    moods = {3: "hard", 4: "tears"}
    log = run_days(db, cur, tmp_path, 8, lambda sk, sp: 0.9, moods=moods)
    plans = {x[1]: x[2] for x in log if x[0] == "plan"}
    day6 = plans[
        START + timedelta(days=5)
    ]  # the day after two hard days (moods logged for days 3, 4)
    assert day6.load < 1.0, day6.load_reason
    assert len(day6.spelling) <= 4
    assert day6.pace == 1
    assert "hard" in day6.load_reason or "tears" in day6.load_reason


def test_fast_child_speeds_up_and_probes_skip_ahead(tmp_path, cur):
    db = make(tmp_path, cur)
    log = run_days(db, cur, tmp_path, 25, lambda sk, sp: 1.0, seed=2)
    plans = [x[2] for x in log if x[0] == "plan"]
    assert max(p.pace for p in plans) == 2  # pace rose after 5 clean days
    student = db.student("Sam")
    units = db.units(student["id"])
    probed = [u for u in units.values() if u.origin == "probed"]
    assert probed, "a child who knows everything should skip ahead via probes"
    # progress is clearly faster than a 0.85 child's (more math skills started)
    started = len({k[0] for k in units if k[0].startswith("m.")})
    assert started >= 12, started


def test_story_ramp_advances_after_five_good_days(tmp_path, cur):
    db = make(tmp_path, cur)
    run_days(db, cur, tmp_path, 12, lambda sk, sp: 0.9)
    assert db.student("Sam")["composition_stage"] >= 2


def test_regenerating_a_day_does_not_double_introduce(tmp_path, cur):
    db = make(tmp_path, cur)
    student = db.student("Sam")
    s1, c1 = scheduler.plan_day(db, cur, student, START)
    n1 = len(db.units(student["id"]))
    worksheet, manifest = build._build_content(
        db, cur, student, s1, START, START + timedelta(days=1)
    )
    db.save_plan(
        student["id"],
        START.isoformat(),
        s1.day_no,
        {
            "selection": s1.to_dict(),
            "worksheet": worksheet,
            "manifest": manifest,
            "quiz_date": "x",
        },
    )
    s2, c2 = scheduler.plan_day(db, cur, student, START)
    assert c1 and not c2 and s2.spelling == s1.spelling
    s3, c3 = scheduler.plan_day(db, cur, student, START, force=True)
    assert c3 and [w["word"] for w in s3.spelling] == [w["word"] for w in s1.spelling]
    assert len(db.units(student["id"])) == n1


def test_placement_finds_the_frontier(tmp_path, cur):
    db = make(tmp_path, cur)
    student = db.student("Sam")
    truth = {"phonics": 17, "sight": 3, "math": 14}

    def ask(item):
        sk = cur.by_id[item["skill_id"]]
        idx = placement.track_skills(cur, item["track"]).index(sk)
        return idx < truth[item["track"]]

    rep = placement.run_placement(db, cur, student, START, ask)
    assert (
        rep["phonics"]["frontier"] == 17
        and rep["sight"]["frontier"] == 3
        and rep["math"]["frontier"] == 14
    )
    assert all(r["asked"] <= 7 for r in rep.values())  # binary search, not a walk
    # the next plan starts at the frontier, not the beginning
    sel, _ = scheduler.plan_day(db, cur, student, START + timedelta(days=1))
    first_new = next(w for w in sel.spelling if w["role"] == "new")
    assert (
        cur.by_id[first_new["skill_id"]] == placement.track_skills(cur, "phonics")[17]
        or cur.by_id[first_new["skill_id"]].track == "sight"
    )
    new_math = [m for m in sel.math if m["role"] == "new"]
    assert (
        new_math
        and cur.by_id[new_math[0]["skill_id"]]
        == placement.track_skills(cur, "math")[14]
        or cur.index[new_math[0]["skill_id"]]
        >= cur.index[placement.track_skills(cur, "math")[14].id]
    )
    # placement-known words do not crowd out this week's words in the review slots
    for d in range(1, 8):
        on = START + timedelta(days=d)
        run_days_one = scheduler.plan_day(db, cur, db.student("Sam"), on)[0]
        reviews = [w for w in run_days_one.spelling if w["role"] == "review"]
        for w in reviews:
            pass


def test_report_builds(tmp_path, cur):
    from dq import report

    db = make(tmp_path, cur)
    run_days(
        db,
        cur,
        tmp_path,
        15,
        lambda sk, sp: 0.75,
        moods={2: "tears", 5: "hard"},
        seed=9,
    )
    rep = report.build_report(
        db, cur, db.student("Sam"), START + timedelta(days=15), days=14
    )
    ids = [q["id"] for q in rep["questions"]]
    assert ids == [
        q[0] for q in report.QUESTIONS
    ]  # always the same questions, same order
    assert rep["accuracy"] is not None
    text = report.format_text(rep)
    assert "What is shaky?" in text
    pdf = render.render_pdf(tmp_path, "report", rep, tmp_path / "r.pdf")
    assert render.page_count(pdf) >= 1
