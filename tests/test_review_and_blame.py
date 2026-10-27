"""Review words must reach the quiz, and a misspelling is blamed on the part that was wrong."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from dq import blame, curriculum, scheduler
from dq.db import DB, Unit

ON = date(2026, 10, 20)


@pytest.fixture(scope="module")
def cur() -> curriculum.Curriculum:
    return curriculum.load(Path(__file__).resolve().parents[1] / "curriculum")


def _student(tmp_path: Path) -> tuple[DB, object]:
    db = DB(tmp_path / "dq.db")
    db.add_student("Sam", ON - timedelta(days=10))
    return db, db.student("Sam")


def _missed(db: DB, sid: int, skill_id: str, word: str) -> None:
    db.upsert_unit(
        sid,
        Unit(
            skill_id,
            word,
            1,
            "2026-10-15",
            "2026-10-16",
            "2026-10-17",
            0,
            1,
            0,
            "taught",
        ),
    )


def test_missed_review_words_are_on_the_quiz_even_on_probe_days(tmp_path, cur) -> None:
    db, st = _student(tmp_path)
    _missed(db, st["id"], "sp.vt.ie", "chief")
    _missed(db, st["id"], "sp.vt.ie", "fried")
    sel, _ = scheduler.plan_day(db, cur, st, ON)
    assert sel.probing and sel.spell_probe, "this scenario needs a probe day"
    quizzed = {w["word"] for w in sel.quiz_spelling}
    assert "chief" in quizzed
    assert any(w["role"] == "new" for w in sel.quiz_spelling)


def test_quiz_left_column_holds_words_probes_and_puzzles(tmp_path, cur) -> None:
    db, st = _student(tmp_path)
    sel, _ = scheduler.plan_day(db, cur, st, ON)
    probes = len(sel.spell_probe["words"]) if sel.spell_probe else 0
    assert len(sel.quiz_spelling) + probes + sel.quiz_puzzles == scheduler.QUIZ_WORDS
    assert sel.quiz_puzzles == scheduler.QUIZ_PUZZLES
    assert len(sel.quiz_spelling) == (2 if probes else 4)


def test_a_review_word_not_being_dictated_is_asked_for_by_its_clue(
    tmp_path, cur
) -> None:
    db, st = _student(tmp_path)
    for w in ("chief", "fried", "field", "thief", "brief", "shield"):
        _missed(db, st["id"], "sp.vt.ie", w)
    sel, _ = scheduler.plan_day(db, cur, st, ON)
    dictated = {w["word"] for w in sel.quiz_spelling}
    assert sel.quiz_clue and sel.quiz_clue["word"] not in dictated
    assert sel.quiz_clue["word"].lower() in cur.clues


@pytest.mark.parametrize(
    "skill_id,word,wrote,on_target,blamed",
    [
        ("sp.vt.ie", "tried", "tride", True, "sp.vt.ie"),
        ("sp.vt.ie", "chief", "cheif", True, "sp.vt.ie"),
        ("sp.vt.ou", "found", "foud", False, "sp.blend.final.nd"),
        ("sp.vt.oi", "voice", "voise", False, "sp.other.soft-c"),
        ("sp.vt.oy", "loyal", "loyl", False, ""),
        ("sp.vt.oi", "moist", "moiste", False, ""),
        ("sp.vt.ie", "chief", "Chief", True, "sp.vt.ie"),
        ("sp.vt.ie", "chief", "", True, "sp.vt.ie"),
    ],
)
def test_misspellings_are_blamed_on_what_went_wrong(
    cur, skill_id, word, wrote, on_target, blamed
) -> None:
    assert blame.attribute(cur, skill_id, word, wrote) == (on_target, blamed)


def _row(skill_id: str, word: str, got: str, correct: bool) -> dict:
    return {
        "skill_id": skill_id,
        "item_key": word,
        "kind": "spelling",
        "prompt": word,
        "expected": word,
        "got": got,
        "correct": correct,
        "error_cat": None,
        "probe": False,
    }


def test_off_target_miss_brings_the_word_back_without_demoting_it(
    tmp_path, cur
) -> None:
    db, st = _student(tmp_path)
    sid = st["id"]
    db.upsert_unit(
        sid,
        Unit(
            "sp.vt.oy",
            "loyal",
            3,
            "2026-10-10",
            None,
            ON.isoformat(),
            2,
            0,
            1,
            "taught",
        ),
    )
    rows = [blame.annotate(cur, _row("sp.vt.oy", "loyal", "loyl", False))]
    db.add_results(sid, None, ON.isoformat(), rows, "manual")
    scheduler.apply_results(db, cur, sid, ON, rows)
    u = db.units(sid)[("sp.vt.oy", "loyal")]
    assert (u.box, u.lapses, u.last_correct) == (3, 0, 0)
    assert u.due_on == (ON + timedelta(days=1)).isoformat()


def test_off_target_misses_do_not_count_against_pace_and_reteach_the_blamed_skill(
    tmp_path, cur
) -> None:
    db, st = _student(tmp_path)
    sid = st["id"]
    rows = [
        blame.annotate(cur, _row("sp.vt.ou", "found", "foud", False)),
        blame.annotate(cur, _row("sp.vt.ou", "round", "round", True)),
    ]
    db.add_results(sid, None, ON.isoformat(), rows, "manual")
    assert scheduler.last_quiz_accuracy(db, sid) == 1.0
    assert [r["skill_id"] for r in scheduler._reteach(db, cur, sid, ON)] == [
        "sp.blend.final.nd"
    ]
