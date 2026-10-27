"""Word puzzles: the banks are clean, selection rotates and adapts, and unlisted answers
go to the answer checker only when one is configured (never a real API call here)."""

import io
import json
import random
from pathlib import Path

import pytest

from dq import curriculum, entry, grade, judge, puzzles
from dq.db import DB

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cur() -> curriculum.Curriculum:
    return curriculum.load(ROOT / "curriculum")


def _item(ptype: str = "analogy", **kw) -> dict:
    return {
        "id": "q1",
        "n": 1,
        "kind_group": "puzzle",
        "kind": "puzzle",
        "ptype": ptype,
        "puzzle_id": f"{ptype}:x",
        "skill_id": f"wp.{ptype}",
        "item_key": "",
        "expected": "den",
        "accept": ["lair"],
        "note": "animal and its home",
        "start": "",
        "prompt_text": "bird is to nest as bear is to ___",
        "probe": False,
    } | kw


class FakeJudge:
    def __init__(self, p: float | None = None, error: Exception | None = None):
        self.p, self.error, self.calls = p, error, []

    def p_yes(self, item: dict, answer: str) -> float | None:
        self.calls.append(answer)
        if self.error:
            raise self.error
        return self.p


def test_banks_validate(cur):
    words = {w.lower() for s in cur.subject("spelling") for w in s.words}
    assert puzzles.validate(cur.puzzles, cur.clues, words) == []
    assert {p.type for p in cur.puzzles} >= set(puzzles.QUIZ_TYPES) | {"scale"}


def test_ids_survive_reordering(tmp_path):
    a = '[[analogy]]\na="bird"\nb="nest"\nc="bear"\nanswer="den"\nrelation="home"\n'
    b = '[[analogy]]\na="cow"\nb="calf"\nc="dog"\nanswer="puppy"\nrelation="young"\n'
    (tmp_path / "a.toml").write_text(a + b)
    first = [p.id for p in puzzles.load(tmp_path)[0]]
    (tmp_path / "a.toml").write_text(b + a)
    assert sorted(first) == sorted(p.id for p in puzzles.load(tmp_path)[0])


def test_levels_rise_and_fall():
    assert puzzles.levels([("odd", True)] * 3) == {"odd": 2}
    assert puzzles.levels([("odd", True)] * 3 + [("odd", False)] * 2) == {"odd": 1}
    assert puzzles.levels([("odd", True)] * 20)["odd"] == puzzles.MAX_LEVEL
    assert puzzles.levels([("odd", False)] * 5) == {"odd": 1}


def test_pick_prefers_unused_then_level():
    mk = lambda i, lv: puzzles.Puzzle(
        id=f"o{i}", type="odd", prompt="", answer="", level=lv
    )
    bank = [mk(1, 1), mk(2, 2), mk(3, 3)]
    rng = random.Random(0)
    assert puzzles.pick(bank, "odd", 2, {}, rng, set()).id == "o2"
    assert puzzles.pick(bank, "odd", 2, {"o2": "2026-10-20"}, rng, set()).id == "o1"
    assert puzzles.pick(bank, "odd", 2, {}, rng, {"o1", "o2", "o3"}) is None


def test_next_types_rotates():
    recent = list(puzzles.QUIZ_TYPES)
    assert puzzles.next_types(recent, random.Random(0), 2) == list(
        puzzles.QUIZ_TYPES[:2]
    )
    assert len(set(puzzles.next_types([], random.Random(0), 5))) == 5


def test_listed_answer_is_right_without_asking():
    j = FakeJudge(0.0)
    (row,) = grade.score({"items": [_item()]}, {"q1": "Lair"}, j)
    assert row.correct and not row.needs_review and j.calls == []


@pytest.mark.parametrize(
    ("p", "correct", "review"),
    [(0.95, True, True), (0.5, False, True), (0.1, False, False), (None, False, False)],
)
def test_unlisted_answer_follows_checker(p, correct, review):
    (row,) = grade.score({"items": [_item()]}, {"q1": "cave"}, FakeJudge(p))
    assert (row.correct, row.needs_review) == (correct, review)


def test_no_checker_marks_unlisted_wrong():
    (row,) = grade.score({"items": [_item()]}, {"q1": "cave"})
    assert not row.correct and not row.needs_review and row.error_cat == "other"


def test_checker_outage_flags_for_review():
    (row,) = grade.score(
        {"items": [_item()]}, {"q1": "cave"}, FakeJudge(error=judge.JudgeError("down"))
    )
    assert not row.correct and row.needs_review and "unavailable" in row.reason


def test_blank_is_not_sent_to_checker():
    j = FakeJudge(1.0)
    (row,) = grade.score({"items": [_item()]}, {"q1": ""}, j)
    assert row.error_cat == "blank" and j.calls == []


def test_question_skips_unjudged_types_and_far_ladders():
    assert judge.question(_item("odd"), "cat") is None
    ladder = _item("ladder", start="cat", expected="cot")
    assert judge.question(ladder, "dog") is None
    assert judge.question(ladder, "cut") is not None


class StubInner:
    model = "stub"

    def __init__(self, p: float):
        self.p, self.calls = p, 0

    def ask(self, state: dict, q: dict) -> float:
        self.calls += 1
        return self.p


def test_cached_judge_asks_once(tmp_path):
    db = DB(tmp_path / "dq.db")
    inner = StubInner(0.9)
    cj = judge.CachedJudge(db, inner)
    assert cj.p_yes(_item(), " Cave ") == 0.9
    assert cj.p_yes(_item(), "cave") == 0.9
    assert inner.calls == 1
    assert db.judgment("analogy:x", "cave") == 0.9


def test_from_env(monkeypatch, tmp_path):
    db = DB(tmp_path / "dq.db")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert judge.from_env(db) is None
    monkeypatch.setenv("OPENROUTER_API_KEY", "op://dev/openrouter/credential")
    with pytest.raises(judge.JudgeError, match="op run"):
        judge.from_env(db)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("DQ_JUDGE_MODEL", "m")
    j = judge.from_env(db)
    assert j is not None and j.inner.model == "m"


def test_jev_ask_parses_response(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data)
        sent["auth"] = req.headers["Authorization"]
        return io.BytesIO(json.dumps({"answers": {"ok": {"noul": 0.83}}}).encode())

    monkeypatch.setattr(judge.urllib.request, "urlopen", fake_urlopen)
    state, q = judge.question(_item(), "cave")
    assert judge.JevJudge("sk-test", "m").ask(state, q) == pytest.approx(0.83)
    assert sent["auth"] == "Bearer sk-test"
    assert (
        sent["body"]["model"] == "m"
        and sent["body"]["questions"]["ok"]["type"] == "noul"
    )


def test_jev_ask_wraps_bad_response(monkeypatch):
    monkeypatch.setattr(
        judge.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(b"{}")
    )
    with pytest.raises(judge.JudgeError):
        judge.JevJudge("sk-test").ask(*judge.question(_item(), "cave"))


def test_oral_entry_uses_checker():
    j = FakeJudge(0.95)
    (row,) = entry.run_entry(
        {"items": [_item()]},
        input_fn=lambda _: "cave",
        print_fn=lambda *a: None,
        judge=j,
    )
    assert row.correct and row.needs_review and j.calls == ["cave"]
