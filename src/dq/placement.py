"""Placement: find where a student already is, in about ten minutes, with an adult asking the questions.

Each track (phonics spelling, sight words, math) is an ordered list of skills. We binary-search for the
first skill the child cannot do, then mark everything before it as known. Known skills are NOT trusted
blindly: they enter the review schedule at a moderate box with due dates spread over weeks, so any hole
shows up as a quiz error and gets re-taught.
"""
from __future__ import annotations

import random
from datetime import date
from typing import Callable

from . import generators, scheduler
from .curriculum import Curriculum, Skill
from .db import DB

TRACKS = ("phonics", "sight", "math")
KNOWN_BOX = 3
SPREAD_DAYS = 45

# ask(item) -> bool.  item = {"track", "skill_id", "title", "kind": "word"|"problem",
#                              "say": text to say, "expected": answer, "sentence": str}
Ask = Callable[[dict], bool]


def track_skills(cur: Curriculum, track: str) -> list[Skill]:
    if track == "math":
        return cur.subject("math")
    return [s for s in cur.subject("spelling") if s.track == track]


def _probe_skill(cur: Curriculum, skill: Skill, rng: random.Random, ask: Ask) -> bool:
    """Ask 3 words (spelling) or 2 problems (math). Pass = at least 2 of 3 words, or both problems."""
    if skill.subject == "spelling":
        words = rng.sample(skill.core_words, min(3, len(skill.core_words)))
        right = 0
        for w in words:
            right += bool(ask({"track": skill.track, "skill_id": skill.id, "title": skill.title,
                               "kind": "word", "say": w, "expected": w,
                               "sentence": cur.sentences.get(w.lower(), "")}))
        return right >= max(1, len(words) - 1)
    probs = generators.generate(skill.generator, skill.params, rng, 2)
    right = 0
    for p in probs:
        right += bool(ask({"track": "math", "skill_id": skill.id, "title": skill.title,
                           "kind": "problem", "say": p.speech or p.prompt, "expected": p.answer,
                           "sentence": ""}))
    return right == len(probs)


def find_frontier(cur: Curriculum, skills: list[Skill], rng: random.Random, ask: Ask) -> tuple[int, int]:
    """Return (frontier_index, probes_asked). Skills before the index are known."""
    lo, hi = 0, len(skills)
    asked = 0
    while lo < hi:
        mid = (lo + hi) // 2
        asked += 1
        if _probe_skill(cur, skills[mid], rng, ask):
            lo = mid + 1
        else:
            hi = mid
    return lo, asked


def run_placement(db: DB, cur: Curriculum, student, on: date, ask: Ask,
                  tracks: tuple[str, ...] = TRACKS) -> dict:
    sid = student["id"]
    rng = random.Random(scheduler.stable_seed(student["name"], on.isoformat(), "placement"))
    report: dict[str, dict] = {}
    offset = 0
    for track in tracks:
        skills = track_skills(cur, track)
        f, asked = find_frontier(cur, skills, rng, ask)
        marked = 0
        for s in skills[:f]:
            marked += scheduler.fast_track(db, cur, sid, s, on, box=KNOWN_BOX, stagger=SPREAD_DAYS,
                                           origin="probed", offset=offset)
            offset += len(s.core_words) if s.subject == "spelling" else 1
        report[track] = {
            "frontier": f, "total": len(skills), "asked": asked, "marked_known": marked,
            "starts_at": skills[f].title if f < len(skills) else "(end of curriculum)",
        }
    return report
