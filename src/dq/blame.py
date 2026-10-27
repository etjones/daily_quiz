"""Which part of a misspelled word was wrong, and which skill teaches that part.

A word is quizzed to test one pattern ("oy" in loyal). If the child gets that pattern
right and slips somewhere else ("loyl"), the miss says nothing about "oy": it is
off-target. Off-target misses still bring the word back, but they do not demote it,
do not count against the pace, and the reteach note goes to the skill that covers the
broken letters (the "n" in found -> Ending -nd), or to nobody if no skill does.
"""

import difflib

from . import answers
from .curriculum import Curriculum

Edit = tuple[
    str, int, int
]  # (replace | delete | insert, start, end) in the expected word


def edits(expected: str, got: str) -> list[Edit]:
    sm = difflib.SequenceMatcher(None, expected, got, autojunk=False)
    return [(op, i1, i2) for op, i1, i2, _, _ in sm.get_opcodes() if op != "equal"]


def touches(span: tuple[int, int], es: list[Edit]) -> bool:
    """An edit touches a span if it changes letters inside it, or inserts strictly inside it."""
    a, b = span
    for op, i1, i2 in es:
        if op == "insert":
            if a < i1 < b:
                return True
        elif i1 < b and a < i2:
            return True
    return False


def _covering_skill(
    cur: Curriculum, target: str, tspan: tuple[int, int], word: str, es: list[Edit]
) -> str:
    """The phonics skill whose pattern sits on the broken letters: ones that list this word
    first, then the tightest match. Patterns that match one letter or most of the word say
    nothing, and a pattern that reuses the target's letters (the i of "oi" read as i-e in
    "voice") is a misreading of the word."""
    hits = []
    for s in cur.subject("spelling"):
        if s.id == target or s.track != "phonics":
            continue
        span = cur.pattern_span(s, word)
        if not span or not 2 <= span[1] - span[0] <= 4 or not touches(span, es):
            continue
        if span[0] < tspan[1] and tspan[0] < span[1]:
            continue
        hits.append((word not in {w.lower() for w in s.words}, span[1] - span[0], s.id))
    return min(hits)[2] if hits else ""


def attribute(
    cur: Curriculum, skill_id: str, expected: str, got: str
) -> tuple[bool, str]:
    """(on_target, blamed skill id) for a wrong spelling. Unclear cases count as on-target:
    a blank, a case-only difference marked wrong by a parent, or a word with no pattern."""
    e, g = expected.lower(), (got or "").strip().lower()
    skill = cur.by_id.get(skill_id)
    span = cur.pattern_span(skill, e) if skill else None
    es = edits(e, g)
    if not g or not es or span is None or touches(span, es):
        return True, skill_id
    return False, _covering_skill(cur, skill_id, span, e, es)


def annotate(cur: Curriculum, row: dict) -> dict:
    """Add on_target / blame_skill to a result row (only wrong, non-probe spellings get them).
    A clue answer is a spelling test only if the child came up with the word: right, or a
    misspelling of it (`retrieved`). Another word or a blank says nothing about spelling."""
    out = {**row, "on_target": None, "blame_skill": None}
    if row["kind"] == "clue":
        out["retrieved"] = bool(row["correct"]) or answers.near_miss(
            row["expected"], row.get("got")
        )
        if not out["retrieved"]:
            return out
    elif row["kind"] != "spelling":
        return out
    if row["correct"] or row.get("probe"):
        return out
    on, sk = attribute(cur, row["skill_id"], row["expected"], row.get("got") or "")
    return {**out, "on_target": on, "blame_skill": sk}
