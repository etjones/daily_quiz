"""School grades K-5: the curriculum's grade bands, grade-seeded placement, kindergarten
quizzes without puzzles, and the new answer kinds for grades 4 and 5."""

import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from dq import answers, build, curriculum, generators, placement, scheduler
from dq.db import DB

START = date(2026, 11, 2)


@pytest.fixture(scope="module")
def cur():
    return curriculum.load(Path(__file__).resolve().parents[1] / "curriculum")


def make(tmp_path, grade=None, name="Kit"):
    db = DB(tmp_path / "dq.db")
    db.add_student(name, START - timedelta(days=1), grade=grade)
    return db, db.student(name)


# --------------------------------------------------------------------------- curriculum


@pytest.mark.parametrize("track", placement.TRACKS)
def test_every_track_spans_kindergarten_to_grade_5(cur, track):
    grades = {s.grade for s in placement.track_skills(cur, track)}
    if track == "sight":
        assert min(grades) <= 1 and max(grades) >= 3
    else:
        assert min(grades) == 0 and max(grades) == 5


def test_parse_and_label_grades():
    assert curriculum.parse_grade("K") == 0 and curriculum.parse_grade("4") == 4
    assert (
        curriculum.grade_label(0) == "K" and curriculum.grade_label(None) == "not set"
    )
    with pytest.raises(ValueError):
        curriculum.parse_grade("6")


# --------------------------------------------------------------------------- answers


def test_decimal_and_mixed_number_answers():
    assert answers.match("dec", "0.5", ".50")
    assert answers.match("dec", "3.25", "$3.250")
    assert answers.match("dec", "12", "12.0")
    assert not answers.match("dec", "0.5", "0.05")
    assert answers.match("frac", "3/2", "1 1/2")
    assert answers.match("frac", "8 7/8", "71/8")
    assert answers.match("frac", "2", "4/2")
    assert not answers.match("frac", "3/2", "1 1/3")


def test_say_reads_large_numbers_and_decimals():
    assert (
        generators.say(482_915)
        == "four hundred eighty-two thousand nine hundred fifteen"
    )
    assert generators.say(2_000_000) == "two million"
    assert generators.say_dec("3.25") == "three and twenty-five hundredths"
    assert generators.say_dec("0.7") == "seven tenths"


def test_new_math_skills_produce_self_consistent_problems(cur):
    for s in cur.subject("math"):
        if s.grade not in (0, 4, 5):
            continue
        rng = random.Random(s.id)
        for _ in range(30):
            p = generators.generate_one(s.generator, s.params, rng)
            assert answers.match(p.kind, p.answer, p.answer), (s.id, p)


def test_mixed_numbers_keep_unreduced_parts():
    rng = random.Random(3)
    for _ in range(50):
        p = generators.gen_frac_mixed_addsub(rng, dens=[4, 8], op="mix")
        assert p.answer != "0" and "0 " not in p.prompt


# --------------------------------------------------------------------------- placement


def _truth_ask(cur, frontier: dict[str, int], asked: list[str]):
    def ask(item):
        asked.append(item["skill_id"])
        sk = cur.by_id[item["skill_id"]]
        return (
            placement.track_skills(cur, item["track"]).index(sk)
            < frontier[item["track"]]
        )

    return ask


def test_grade_start_follows_the_last_lower_grade_skill(cur):
    math = placement.track_skills(cur, "math")
    start = placement.grade_start(math, 4)
    assert all(s.grade >= 4 for s in math[start:])
    assert math[start - 1].grade < 4
    assert placement.grade_start(math, 0) == 0
    assert placement.grade_start(math, None) is None


def test_kindergartner_is_asked_kindergarten_math_first(tmp_path, cur):
    db, student = make(tmp_path, grade=0)
    asked: list[str] = []
    rep = placement.run_placement(
        db,
        cur,
        student,
        START,
        _truth_ask(cur, {"phonics": 0, "sight": 0, "math": 2}, asked),
        ("math",),
    )
    assert rep["math"]["frontier"] == 2
    assert all(cur.by_id[a].grade == 0 for a in asked)


@pytest.mark.parametrize("frontier_grade", [2, 4, 5])
def test_grade_4_placement_finds_any_frontier(tmp_path, cur, frontier_grade):
    db, student = make(tmp_path, grade=4)
    math = placement.track_skills(cur, "math")
    truth = next(i for i, s in enumerate(math) if s.grade == frontier_grade) + 1
    asked: list[str] = []
    ask = _truth_ask(cur, {"phonics": 0, "sight": 0, "math": truth}, asked)
    rep = placement.run_placement(db, cur, student, START, ask, ("math",))
    assert rep["math"]["frontier"] == truth
    assert cur.by_id[asked[0]].grade == 4
    assert rep["math"]["asked"] <= 2 * len(math).bit_length() + 2


def test_web_replay_matches_the_grade_seeded_search(tmp_path, cur):
    _db, student = make(tmp_path, grade=3)
    item = placement.next_question(cur, student, START, [], ("math",))
    math = placement.track_skills(cur, "math")
    assert item["skill_id"] == math[placement.grade_start(math, 3)].id


# --------------------------------------------------------------------------- scheduling


def test_kindergarten_quiz_has_no_puzzles(tmp_path, cur):
    db, student = make(tmp_path, grade=0)
    b = build.build_day(db, cur, tmp_path, "Kit", START)
    q = db.latest_open_quiz(student["id"])
    items = json.loads(q["manifest"])["items"]
    assert not [i for i in items if i["kind_group"] == "puzzle"]
    assert b.selection.quiz_puzzles == 0
    new_math = [m for m in b.selection.math if m["role"] == "new"]
    assert new_math and all(cur.by_id[m["skill_id"]].grade == 0 for m in new_math)


def test_skills_two_grades_below_solid_work_are_backfilled(tmp_path, cur):
    db, student = make(tmp_path)
    sid = student["id"]
    for s in placement.track_skills(cur, "math"):
        if s.grade == 2:
            scheduler.fast_track(db, cur, sid, s, START, scheduler.SOLID_BOX)
    added = scheduler.backfill_below(db, cur, sid, START)
    units = db.units(sid)
    k = [s for s in cur.subject("math") if s.grade == 0]
    g1 = [s for s in cur.subject("math") if s.grade == 1]
    assert added and all((s.id, "") in units for s in k)
    assert not any((s.id, "") in units for s in g1)
    assert scheduler.backfill_below(db, cur, sid, START) == 0


def test_puzzles_start_at_the_school_grade(tmp_path, cur):
    db, student = make(tmp_path, grade=5)
    sel, _ = scheduler.plan_day(db, cur, student, START)
    sel.quiz_puzzles = 2
    quiz, _corner = build._choose_puzzles(db, cur, student, sel, random.Random(1))
    by_id = {p.id: p for p in cur.puzzles}
    top = {}
    for p in cur.puzzles:
        top[p.type] = max(top.get(p.type, 1), p.level)
    picked = [by_id[q["puzzle_id"]] for q in quiz if q["kind"] == "puzzle"]
    assert picked and all(p.level >= min(4, top[p.type]) for p in picked)


# --------------------------------------------------------------------------- database


def test_old_databases_gain_a_grade_column(tmp_path):
    con = sqlite3.connect(tmp_path / "dq.db")
    con.execute(
        "CREATE TABLE student (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,"
        " created TEXT NOT NULL, composition_stage INTEGER NOT NULL DEFAULT 1,"
        " pace_cap INTEGER NOT NULL DEFAULT 2, probe_days INTEGER NOT NULL DEFAULT 10)"
    )
    con.execute("INSERT INTO student(name, created) VALUES ('Old', '2026-10-01')")
    con.commit()
    con.close()
    db = DB(tmp_path / "dq.db")
    assert db.student("Old")["grade"] is None
    db.set_student_field(db.student("Old")["id"], "grade", 2)
    assert db.student("Old")["grade"] == 2
