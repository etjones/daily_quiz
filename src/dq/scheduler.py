"""Deterministic scheduling: what to teach and review today, and how results update memory.

No model is involved. The rules are deliberately boring (a Leitner-style box system per
unit), and every threshold is a named constant below so they are easy to tune.

Units
-----
Spelling: one unit per word.  Math: one unit per skill.
Each unit has a box 0..6.  Box 0 = introduced but not yet tested.  A correct answer
moves it up; a wrong answer drops it back and brings it back tomorrow.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .curriculum import Curriculum, Skill
from .db import DB, Unit

# --- tunable constants ------------------------------------------------------

INTERVALS = {
    0: 0,
    1: 1,
    2: 2,
    3: 4,
    4: 8,
    5: 16,
    6: 32,
}  # days until next review, by box
MASTERED_BOX = 4  # box at which a unit counts as mastered
SOLID_BOX = 3  # box at which a unit counts as solid
PREREQ_BOX = (
    2  # a prerequisite counts as satisfied at this box (spelling: 70% of core words)
)

WORDS_PER_DAY = 5
MATH_PRACTICE = 8  # problems on the worksheet
QUIZ_WORDS = 5
QUIZ_MATH = 5
NEW_WORDS_BY_PACE = {
    1: (3, 1),
    2: (4, 1),
    3: (4, 2),
}  # (phonics, sight) new words per day
NEW_MATH_PROBLEMS = 3  # worksheet problems for each new math skill
SHAKY_WORD_BRAKE = 12  # too many shaky words -> slow down new words
SHAKY_SKILL_BRAKE = 3  # too many shaky math skills -> no new math skill
CLEAN_ACCURACY = 0.9  # a quiz day at or above this counts toward speeding up
PACE_AFTER_CLEAN_DAYS = {2: 5, 3: 10}
PROBE_ACTIVE_CLEAN_DAYS = 2
CONSOLIDATE_BELOW = (
    0.6  # last quiz under this accuracy: stop adding new math, trim new words
)

HARD_MOODS = {"hard", "tears"}


# --- helpers ----------------------------------------------------------------


def stable_seed(*parts) -> int:
    h = hashlib.sha1(":".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def d(s: str) -> date:
    return date.fromisoformat(s)


def word_units(units: dict[tuple[str, str], Unit]) -> dict[str, Unit]:
    """Best unit per lowercase word. A word that appears in two skills (the 'mixed'
    review skills reuse words) counts as known once, anywhere."""
    best: dict[str, Unit] = {}
    for (skill_id, key), u in units.items():
        if not skill_id.startswith("sp."):
            continue
        w = key.lower()
        if w not in best or u.box > best[w].box:
            best[w] = u
    return best


@dataclass
class SkillProgress:
    skill_id: str
    total: int
    introduced: int
    solid: int
    mastered: int
    label: str  # new | learning | solid | mastered


def skill_progress(
    cur: Curriculum,
    units: dict[tuple[str, str], Unit],
    skill: Skill,
    wu: dict[str, Unit] | None = None,
) -> SkillProgress:
    if skill.subject == "spelling":
        wu = wu if wu is not None else word_units(units)
        us = [wu.get(w.lower()) for w in skill.core_words]
        total = len(us)
        intro = sum(1 for u in us if u is not None)
        solid = sum(1 for u in us if u and u.box >= SOLID_BOX)
        mast = sum(1 for u in us if u and u.box >= MASTERED_BOX)
    else:
        u = units.get((skill.id, ""))
        total, intro = 1, 1 if u else 0
        solid = 1 if u and u.box >= SOLID_BOX else 0
        mast = 1 if u and u.box >= MASTERED_BOX else 0
    if intro == 0:
        label = "new"
    elif mast == total:
        label = "mastered"
    elif solid == total:
        label = "solid"
    else:
        label = "learning"
    return SkillProgress(skill.id, total, intro, solid, mast, label)


def prereqs_ready(cur: Curriculum, units, skill: Skill, wu=None) -> bool:
    for pid in skill.prereqs:
        p = cur.by_id[pid]
        if p.subject == "spelling":
            wu = wu if wu is not None else word_units(units)
            core = p.core_words
            ok = sum(
                1
                for w in core
                if (wu.get(w.lower()) and wu[w.lower()].box >= PREREQ_BOX)
            )
            if ok < 0.7 * len(core):
                return False
        else:
            u = units.get((pid, ""))
            if u is None or u.box < PREREQ_BOX:
                return False
    return True


# --- load, pace, composition --------------------------------------------------


def compute_load(db: DB, student_id: int, on: date) -> tuple[float, str]:
    """Shrink tomorrow's work after hard days. The habit matters more than the content."""
    logs = [
        r
        for r in db.day_logs(student_id)
        if r["mood"] and r["on_date"] < on.isoformat()
    ]
    if (
        len(logs) >= 2
        and logs[-1]["mood"] in HARD_MOODS
        and logs[-2]["mood"] in HARD_MOODS
    ):
        return 0.6, "two hard days in a row: lighter load today"
    if logs and logs[-1]["mood"] == "tears":
        return 0.8, "tears yesterday: slightly lighter load today"
    return 1.0, ""


def clean_day_streak(db: DB, student_id: int) -> int:
    n = 0
    for _, acc, _ in reversed(db.quiz_days(student_id)):
        if acc >= CLEAN_ACCURACY:
            n += 1
        else:
            break
    return n


def compute_pace(db: DB, student, clean_days: int, load: float) -> int:
    if load < 1.0:
        return 1
    pace = 1
    for p in (2, 3):
        if clean_days >= PACE_AFTER_CLEAN_DAYS[p]:
            pace = p
    return min(pace, student["pace_cap"])


def last_quiz_accuracy(db: DB, student_id: int) -> float | None:
    days = db.quiz_days(student_id)
    return days[-1][1] if days else None


def maybe_advance_composition(db: DB, student, day_no: int) -> int:
    """Story ramp: move up one stage after five consecutive finished stories with no tears."""
    stage = student["composition_stage"]
    if stage >= 5 or day_no % 5 != 0:
        return stage
    logs = [r for r in db.day_logs(student["id"]) if r["composition_done"] is not None][
        -5:
    ]
    if (
        len(logs) == 5
        and all(r["composition_done"] == 1 for r in logs)
        and not any(r["mood"] == "tears" for r in logs)
    ):
        db.set_student_field(student["id"], "composition_stage", stage + 1)
        return stage + 1
    return stage


# --- selection --------------------------------------------------------------


@dataclass
class Selection:
    on: str
    day_no: int
    load: float
    load_reason: str
    pace: int
    clean_days: int
    probing: bool
    consolidating: bool = False
    spelling: list[dict] = field(default_factory=list)  # {skill_id, word, role}
    math: list[dict] = field(default_factory=list)  # {skill_id, n, role}
    spell_probe: dict | None = None  # {skill_id, words}
    math_probe: dict | None = None  # {skill_id, n}
    quiz_spelling: list[dict] = field(default_factory=list)
    quiz_math: list[dict] = field(default_factory=list)
    reteach: list[dict] = field(default_factory=list)
    story_stage: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _review_key(u: Unit, today: date):
    """Missed items first, then the least-learned (lowest box), then the most overdue.
    Lowest box before overdue-ness matters: a backlog of placement-known words must never
    crowd out words taught this week."""
    overdue = (today - d(u.due_on)).days
    missed = 1 if u.last_correct == 0 else 0
    return (-missed, u.box, -overdue, u.skill_id, u.item_key)


def _spelling_candidates(
    cur: Curriculum, units, wu, track: str, n: int, exclude: set[str]
) -> list[tuple[Skill, str]]:
    """Next unseen core words in a track, in order. Stops at the first skill whose
    prerequisites are not yet satisfied."""
    out: list[tuple[Skill, str]] = []
    for s in cur.subject("spelling"):
        if s.track != track:
            continue
        remaining = [
            w for w in s.core_words if w.lower() not in wu and w.lower() not in exclude
        ]
        if not remaining:
            continue
        started = any(w.lower() in wu for w in s.core_words)
        if not started and not prereqs_ready(cur, units, s, wu):
            break
        for w in remaining:
            out.append((s, w))
            exclude.add(w.lower())
            if len(out) >= n:
                return out
    return out


def _spelling_frontier(
    cur: Curriculum, wu, track: str, probes: dict[str, str]
) -> list[Skill]:
    """Skills in this track that still have unseen core words, in order, not yet probed."""
    out = []
    for s in cur.subject("spelling"):
        if s.track != track:
            continue
        if any(w.lower() not in wu for w in s.core_words) and s.id not in probes:
            out.append(s)
    return out


def _math_candidates(cur: Curriculum, units) -> list[Skill]:
    return [
        s
        for s in cur.subject("math")
        if (s.id, "") not in units and prereqs_ready(cur, units, s)
    ]


def plan_day(
    db: DB, cur: Curriculum, student, on: date, force: bool = False
) -> tuple[Selection, bool]:
    """Pick the day's content. Returns (selection, created). If a plan already exists for
    the date and `force` is false, returns the stored plan's selection with created=False."""
    sid = student["id"]
    existing = db.plan_for(sid, on.isoformat())
    if existing and not force:
        import json

        sel = Selection(**json.loads(existing["data"])["selection"])
        return sel, False
    if existing and force:
        db.delete_units_introduced_on(sid, on.isoformat())

    rng = random.Random(stable_seed(student["name"], on.isoformat()))
    units = db.units(sid)
    wu = word_units(units)
    probes = db.probes(sid)

    day_no = db.plan_count(sid) + (0 if existing else 1)
    load, load_reason = compute_load(db, sid, on)
    clean = clean_day_streak(db, sid)
    pace = compute_pace(db, student, clean, load)
    story_stage = maybe_advance_composition(db, db.student(student["name"]), day_no)
    probing = load >= 1.0 and (
        day_no <= student["probe_days"] or clean >= PROBE_ACTIVE_CLEAN_DAYS
    )

    last_acc = last_quiz_accuracy(db, sid)
    consolidating = last_acc is not None and last_acc < CONSOLIDATE_BELOW
    if consolidating:
        probing = False
    sel = Selection(
        on=on.isoformat(),
        day_no=day_no,
        load=load,
        load_reason=load_reason,
        pace=pace,
        clean_days=clean,
        probing=probing,
        consolidating=consolidating,
        story_stage=max(1, story_stage - 1) if load < 1.0 else story_stage,
    )

    # ---- spelling ----------------------------------------------------------
    n_words = max(3, round(WORDS_PER_DAY * load))
    due_words = sorted(
        [
            u
            for u in units.values()
            if u.skill_id.startswith("sp.") and d(u.due_on) <= on
        ],
        key=lambda u: _review_key(u, on),
    )
    seen_words: set[str] = set()
    review_pool: list[Unit] = []
    for u in due_words:
        w = u.item_key.lower()
        if w in seen_words:
            continue
        seen_words.add(w)
        review_pool.append(u)

    shaky_words = sum(1 for u in wu.values() if u.box <= 1)
    min_rev = 1 if review_pool else 0
    new_cap = n_words - min_rev
    if shaky_words >= SHAKY_WORD_BRAKE or consolidating:
        new_cap = min(new_cap, 2)
    ph_q, si_q = NEW_WORDS_BY_PACE[pace]

    exclude = set(seen_words)
    new_list: list[tuple[Skill, str]] = []
    new_list += _spelling_candidates(
        cur, units, wu, "phonics", min(ph_q, new_cap), exclude
    )
    room = new_cap - len(new_list)
    if room > 0:
        new_list += _spelling_candidates(
            cur, units, wu, "sight", min(si_q, room), exclude
        )

    spelling: list[dict] = [
        {"skill_id": s.id, "word": w, "role": "new"} for s, w in new_list
    ]
    for u in review_pool:
        if len(spelling) >= n_words:
            break
        spelling.append({"skill_id": u.skill_id, "word": u.item_key, "role": "review"})
    # not enough reviews: add more new words (phonics first)
    if len(spelling) < n_words:
        cap_extra = n_words - len(spelling)
        if shaky_words >= SHAKY_WORD_BRAKE or consolidating:
            cap_extra = 0
        extra = _spelling_candidates(cur, units, wu, "phonics", cap_extra, exclude)
        if len(extra) < cap_extra:
            extra += _spelling_candidates(
                cur, units, wu, "sight", cap_extra - len(extra), exclude
            )
        spelling += [{"skill_id": s.id, "word": w, "role": "new"} for s, w in extra]
    # still short: one transfer word from a skill whose core words are all solid
    if len(spelling) < n_words:
        for s in cur.subject("spelling"):
            if skill_progress(cur, units, s, wu).label in ("solid", "mastered"):
                fresh = [
                    w
                    for w in s.transfer_words
                    if w.lower() not in wu and w.lower() not in exclude
                ]
                if fresh:
                    spelling.append(
                        {
                            "skill_id": s.id,
                            "word": rng.choice(fresh),
                            "role": "transfer",
                        }
                    )
                    break
    sel.spelling = spelling

    # ---- spelling probe (next phonics skill we have not taught) ---------------
    if probing:
        frontier = _spelling_frontier(cur, wu, "phonics", probes)
        taught_ids = {x["skill_id"] for x in spelling if x["role"] == "new"}
        targets = [s for s in frontier if s.id not in taught_ids]
        # skip the skill currently being taught (first in frontier)
        if (
            frontier
            and targets
            and frontier[0].id == targets[0].id
            and len(targets) > 1
            and taught_ids
        ):
            targets = targets[1:]
        if targets and len(targets[0].core_words) >= 2:
            t = targets[0]
            pw = rng.sample([w for w in t.core_words if w.lower() not in wu], 2)
            sel.spell_probe = {"skill_id": t.id, "words": pw}

    # ---- math ----------------------------------------------------------------
    math_units = {sk: u for (sk, key), u in units.items() if sk.startswith("m.")}
    shaky_skills = sum(1 for u in math_units.values() if u.box <= 1)
    candidates = _math_candidates(cur, units)
    n_new = 0 if (shaky_skills >= SHAKY_SKILL_BRAKE or consolidating) else pace
    new_skills = candidates[:n_new]
    n_practice = max(5, round(MATH_PRACTICE * load))
    math_slots: list[dict] = []
    total = 0
    for s in new_skills:
        k = min(NEW_MATH_PROBLEMS, max(1, n_practice - total))
        math_slots.append({"skill_id": s.id, "n": k, "role": "new"})
        total += k
    due_math = sorted(
        [u for u in math_units.values() if d(u.due_on) <= on],
        key=lambda u: _review_key(u, on),
    )
    for u in due_math:
        if total >= n_practice:
            break
        k = 2 if u.last_correct == 0 else 1
        k = min(k, n_practice - total)
        math_slots.append({"skill_id": u.skill_id, "n": k, "role": "review"})
        total += k
    # nothing due (very early days): pad with the skills already chosen, but keep the sheet short
    if not due_math:
        n_practice = min(n_practice, 5)
    if total < n_practice:
        pad_pool = [s["skill_id"] for s in math_slots] or sorted(
            math_units, key=lambda sk: math_units[sk].introduced_on, reverse=True
        )[:3]
        i = 0
        while total < n_practice and pad_pool:
            sk = pad_pool[i % len(pad_pool)]
            slot = next((m for m in math_slots if m["skill_id"] == sk), None)
            if slot:
                slot["n"] += 1
            else:
                math_slots.append({"skill_id": sk, "n": 1, "role": "review"})
            total += 1
            i += 1
    sel.math = math_slots

    # ---- math probe ------------------------------------------------------------
    if probing:
        new_ids = {m["skill_id"] for m in math_slots if m["role"] == "new"}
        later = [s for s in candidates if s.id not in new_ids and s.id not in probes]
        if later:
            sel.math_probe = {"skill_id": later[0].id, "n": 2}

    # ---- quiz composition (tomorrow morning) --------------------------------------
    n_quiz_w = max(3, round(QUIZ_WORDS * load))
    n_quiz_m = max(3, round(QUIZ_MATH * load))
    probe_w = 2 if sel.spell_probe else 0
    probe_m = 2 if sel.math_probe else 0
    sel.quiz_spelling = spelling[: max(1, n_quiz_w - probe_w)]
    quiz_math: list[dict] = []
    for m in math_slots:
        if len(quiz_math) >= max(1, n_quiz_m - probe_m):
            break
        quiz_math.append({"skill_id": m["skill_id"], "n": 1})
    sel.quiz_math = quiz_math

    # ---- reteach: what was missed in the last graded quiz -----------------------------
    sel.reteach = _reteach(db, cur, sid, on)

    # ---- commit introductions ---------------------------------------------------------
    for item in spelling:
        if item["role"] in ("new", "transfer"):
            db.upsert_unit(
                sid,
                Unit(
                    skill_id=item["skill_id"],
                    item_key=item["word"],
                    box=0,
                    introduced_on=on.isoformat(),
                    last_seen=None,
                    due_on=on.isoformat(),
                    streak=0,
                    lapses=0,
                    last_correct=None,
                    origin="transfer" if item["role"] == "transfer" else "taught",
                ),
            )
    for m in math_slots:
        if m["role"] == "new":
            db.upsert_unit(
                sid,
                Unit(
                    skill_id=m["skill_id"],
                    item_key="",
                    box=0,
                    introduced_on=on.isoformat(),
                    last_seen=None,
                    due_on=on.isoformat(),
                    streak=0,
                    lapses=0,
                    last_correct=None,
                    origin="taught",
                ),
            )
    return sel, True


def _reteach(db: DB, cur: Curriculum, sid: int, on: date) -> list[dict]:
    q = db.conn.execute(
        "SELECT on_date FROM result WHERE student_id = ? AND probe = 0 ORDER BY on_date DESC LIMIT 1",
        (sid,),
    ).fetchone()
    if not q:
        return []
    rows = db.conn.execute(
        "SELECT skill_id, item_key, COUNT(*) n FROM result WHERE student_id = ? AND on_date = ?"
        " AND probe = 0 AND correct = 0 GROUP BY skill_id ORDER BY n DESC, skill_id LIMIT 2",
        (sid, q["on_date"]),
    ).fetchall()
    return [{"skill_id": r["skill_id"], "word": r["item_key"]} for r in rows]


# --- results -------------------------------------------------------------------


def advance(u: Unit, correct: bool, on: date) -> Unit:
    if correct:
        u.box = 2 if u.box == 0 else min(6, u.box + 1)
        u.streak += 1
    else:
        u.box = 1 if u.box <= 3 else u.box - 2
        u.streak = 0
        u.lapses += 1
    u.last_correct = 1 if correct else 0
    u.last_seen = on.isoformat()
    u.due_on = (on + timedelta(days=1 if not correct else INTERVALS[u.box])).isoformat()
    return u


def fast_track(
    db: DB,
    cur: Curriculum,
    sid: int,
    skill: Skill,
    on: date,
    box: int,
    stagger: int = 1,
    origin: str = "probed",
    offset: int = 0,
) -> int:
    """Mark a skill as already known. Review dates are staggered so they do not all fall on the same day."""
    units = db.units(sid)
    wu = word_units(units)
    n = 0
    if skill.subject == "spelling":
        for i, w in enumerate(skill.core_words):
            if w.lower() in wu and (skill.id, w) not in units:
                continue  # known through another skill
            existing = units.get((skill.id, w))
            if existing and existing.box >= box:
                continue
            due = on + timedelta(days=INTERVALS[box] + ((offset + i) % max(1, stagger)))
            db.upsert_unit(
                sid,
                Unit(
                    skill.id,
                    w,
                    box,
                    existing.introduced_on if existing else on.isoformat(),
                    on.isoformat(),
                    due.isoformat(),
                    1,
                    existing.lapses if existing else 0,
                    1,
                    origin,
                ),
            )
            n += 1
    else:
        existing = units.get((skill.id, ""))
        if not (existing and existing.box >= box):
            due = on + timedelta(days=INTERVALS[box] + (offset % max(1, stagger)))
            db.upsert_unit(
                sid,
                Unit(
                    skill.id,
                    "",
                    box,
                    existing.introduced_on if existing else on.isoformat(),
                    on.isoformat(),
                    due.isoformat(),
                    1,
                    existing.lapses if existing else 0,
                    1,
                    origin,
                ),
            )
            n = 1
    return n


def apply_results(
    db: DB, cur: Curriculum, sid: int, on: date, rows: list[dict]
) -> dict:
    """Update memory state from graded rows. Returns a small summary."""
    units = db.units(sid)
    wu = word_units(units)
    summary = {"updated": 0, "probes_passed": [], "probes_failed": []}

    # ordinary items: aggregate per unit (a math skill with 2 problems succeeds only if both are right)
    per_unit: dict[tuple[str, str], list[bool]] = {}
    for r in rows:
        if r.get("probe"):
            continue
        per_unit.setdefault((r["skill_id"], r.get("item_key", "")), []).append(
            bool(r["correct"])
        )
    for (skill_id, key), flags in per_unit.items():
        u = units.get((skill_id, key))
        if u is None and skill_id.startswith("sp."):
            u0 = wu.get(key.lower())  # tested under an alias skill
            u = u0
        if u is None:
            continue
        db.upsert_unit(sid, advance(u, all(flags), on))
        summary["updated"] += 1

    # probes: all correct -> fast track; any wrong -> never probe this skill again
    per_probe: dict[str, list[bool]] = {}
    for r in rows:
        if r.get("probe"):
            per_probe.setdefault(r["skill_id"], []).append(bool(r["correct"]))
    for skill_id, flags in per_probe.items():
        skill = cur.by_id[skill_id]
        if all(flags) and len(flags) >= 2:
            fast_track(db, cur, sid, skill, on, box=3, stagger=3)
            db.set_probe(sid, skill_id, "passed", on.isoformat())
            summary["probes_passed"].append(skill_id)
        else:
            db.set_probe(sid, skill_id, "failed", on.isoformat())
            summary["probes_failed"].append(skill_id)
    return summary
