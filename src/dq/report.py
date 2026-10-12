"""Progress reports with a fixed set of questions.

Every report asks and answers the same questions in the same order, from the database, with
no model involved. A model may optionally turn the finished data structure into a short note
(prompts/report_narrative.md), but it never computes anything. To improve the report, edit
QUESTIONS and the functions below; every future report changes with it.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import scheduler
from .curriculum import Curriculum
from .db import DB

QUESTIONS = [
    ("learned", "What did we learn in this period?"),
    ("solid", "What is solid?"),
    ("shaky", "What is shaky?"),
    ("mistakes", "What kinds of mistakes is he making?"),
    ("pace", "How is the pace?"),
    ("mood", "How are mood and load?"),
    ("next", "What happens next?"),
]

ERROR_EXPLAINED = {
    "blank": "left blank",
    "reversal": "reversed letters or digits (b/d, p/q, 2/5, 6/9). Very common at this age; not a knowledge gap",
    "transposition": "letters or digits swapped",
    "omission": "dropped a letter (often one letter of a blend, as in lamp -> lap)",
    "insertion": "added an extra letter",
    "vowel_pattern": "right consonants, wrong vowel spelling (a pattern to learn, not carelessness)",
    "off_by_one": "answer one away (counting slip)",
    "sign": "< and > swapped",
    "capitalization": "capital letter missing where required",
    "other": "something else",
}

ADVICE = {
    "reversal": "Mirror-letter errors usually fade on their own. Write b and d on a card (bed: the 'bed' shape) and don't mark them as spelling failures.",
    "omission": "Dropped letters: have him tap one finger per sound before writing, and say the word slowly, stretching the blends.",
    "vowel_pattern": "He hears the sound but picks the wrong spelling. Sort word cards by pattern for a minute before the worksheet.",
    "transposition": "Say the letters in order out loud as he writes them.",
    "off_by_one": "Counting slips: let him use a number line or fingers without comment until facts are automatic.",
    "sign": "Teach the alligator: the mouth opens toward the bigger number.",
    "blank": "Blank answers: check whether it is difficulty or fatigue. If fatigue, the worksheet may be too long today.",
}


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def build_report(db: DB, cur: Curriculum, student, on: date, days: int = 14) -> dict:
    sid = student["id"]
    since = (on - timedelta(days=days)).isoformat()
    units = db.units(sid)
    wu = scheduler.word_units(units)
    results = db.results_since(sid, since, include_probes=False)
    logs = db.day_logs(sid, since)
    quiz_days = [(d, a, n) for d, a, n in db.quiz_days(sid) if d >= since]
    total = len(results)
    acc = sum(r["correct"] for r in results) / total if total else None

    progress = {s.id: scheduler.skill_progress(cur, units, s, wu) for s in cur.skills}
    started = [s for s in cur.skills if progress[s.id].label != "new"]
    solid = [s for s in started if progress[s.id].label in ("solid", "mastered")]
    sp_all = cur.subject("spelling")
    math_all = cur.subject("math")

    # ---- 1. learned -----------------------------------------------------------
    new_units = [u for u in units.values() if u.introduced_on >= since and u.origin == "taught"]
    new_words = sorted({u.item_key.lower() for u in new_units if u.skill_id.startswith("sp.")})
    new_math = [cur.by_id[u.skill_id].title for u in new_units if u.skill_id.startswith("m.")]
    probed = [u for u in units.values() if u.introduced_on >= since and u.origin == "probed"]
    learned = []
    if new_words:
        learned.append(f"{len(new_words)} new spelling words: " + ", ".join(new_words[:15]) + ("…" if len(new_words) > 15 else ""))
    if new_math:
        learned.append("New math skills: " + "; ".join(new_math))
    pskills = sorted({cur.by_id[u.skill_id].title for u in probed})
    if pskills:
        learned.append(f"Skipped ahead (already knew): {len(pskills)} skill(s), e.g. " + "; ".join(pskills[:4]))

    # ---- 2. solid -------------------------------------------------------------------
    n_words_solid = sum(1 for u in wu.values() if u.box >= scheduler.SOLID_BOX)
    solid_lines = [f"{n_words_solid} spelling words at 'solid' or better; "
                   f"{sum(1 for s in math_all if progress[s.id].label in ('solid', 'mastered'))} of {len(math_all)} math skills."]
    mastered_recent = [s.title for s in solid if progress[s.id].label == "mastered"][-6:]
    if mastered_recent:
        solid_lines.append("Mastered most recently: " + "; ".join(mastered_recent))

    # ---- 3. shaky ---------------------------------------------------------------------
    per_skill: dict[str, list[int]] = defaultdict(list)
    for r in results:
        per_skill[r["skill_id"]].append(r["correct"])
    shaky = []
    for sk, flags in per_skill.items():
        if len(flags) >= 2 and sum(flags) / len(flags) < 0.7:
            shaky.append((sum(flags) / len(flags), len(flags), cur.by_id[sk].title))
    shaky.sort()
    shaky_lines = [f"{t}: {_pct(a)} over {n} items" for a, n, t in shaky[:6]]
    missed_words = Counter(r["item_key"].lower() for r in results if r["kind"] == "spelling" and not r["correct"])
    repeat = [f"{w} (missed {c} times)" for w, c in missed_words.most_common(6) if c >= 2]
    if repeat:
        shaky_lines.append("Words missed repeatedly: " + ", ".join(repeat))

    # ---- 4. mistakes -------------------------------------------------------------------
    wrong = [r for r in results if not r["correct"]]
    cats = Counter(r["error_cat"] or "other" for r in wrong)
    mistake_lines = [f"{c} × {ERROR_EXPLAINED.get(k, k)}" for k, c in cats.most_common(5)]
    ex = [f"{r['expected']} → {r['got'] or '(blank)'}" for r in wrong if r["got"]][:6]
    if ex:
        mistake_lines.append("Examples: " + ", ".join(ex))

    # ---- 5. pace ------------------------------------------------------------------------
    sp_phon = [s for s in sp_all if s.track == "phonics"]
    sp_sight = [s for s in sp_all if s.track == "sight"]
    reached = lambda skills: sum(1 for s in skills if progress[s.id].label != "new")
    clean = scheduler.clean_day_streak(db, sid)
    weeks = max(days / 7.0, 1e-9)
    pace_lines = [
        f"Phonics: {reached(sp_phon)} of {len(sp_phon)} patterns started; "
        f"sight words: {reached(sp_sight)} of {len(sp_sight)} lists; math: {reached(math_all)} of {len(math_all)} skills.",
        f"New words per week: {len(new_words) / weeks:.1f}. New math skills per week: {len(new_math) / weeks:.1f}.",
        f"Clean-quiz streak: {clean} day(s). Pace speeds up after {scheduler.PACE_AFTER_CLEAN_DAYS[2]} clean days "
        f"(currently capped at {student['pace_cap']} new skills per day).",
    ]

    # ---- 6. mood and load -------------------------------------------------------------
    moods = Counter(r["mood"] for r in logs if r["mood"])
    done = [r["composition_done"] for r in logs if r["composition_done"] is not None]
    plans = db.conn.execute("SELECT data FROM plan WHERE student_id = ? AND for_date >= ?", (sid, since)).fetchall()
    reductions = sum(1 for p in plans if json.loads(p["data"])["selection"]["load"] < 1.0)
    mood_lines = []
    if moods:
        mood_lines.append("Mood log: " + ", ".join(f"{k} × {v}" for k, v in moods.most_common()))
    if done:
        mood_lines.append(f"Story finished on {sum(done)} of {len(done)} logged days; current story stage {student['composition_stage']} of 5.")
    mood_lines.append(f"Days the load was automatically lightened: {reductions}.")

    # ---- 7. next --------------------------------------------------------------------------
    exclude: set[str] = set()
    nxt_words = scheduler._spelling_candidates(cur, units, wu, "phonics", 3, exclude) + \
        scheduler._spelling_candidates(cur, units, wu, "sight", 1, exclude)
    nxt_math = scheduler._math_candidates(cur, units)[:2]
    next_lines = []
    if nxt_words:
        next_lines.append("Next words: " + ", ".join(w for _, w in nxt_words))
    if nxt_math:
        next_lines.append("Next math: " + "; ".join(s.title for s in nxt_math))
    recs: list[str] = []
    tears = moods.get("tears", 0)
    if tears >= 2:
        recs.append("Tears on 2 or more days: keep the habit short and sit with him for the worksheet; do not add anything.")
    if acc is not None and acc < 0.7:
        recs.append("Accuracy under 70%: the program is already re-teaching; consider doing the worksheet together for a few days.")
    elif clean >= 3 and clean < scheduler.PACE_AFTER_CLEAN_DAYS[2]:
        recs.append(f"{clean} clean days so far: pace increases after {scheduler.PACE_AFTER_CLEAN_DAYS[2]}.")
    if cats:
        top, c = cats.most_common(1)[0]
        if c >= max(3, 0.4 * len(wrong)) and top in ADVICE:
            recs.append(ADVICE[top])
    next_lines.extend(recs)

    lines = {"learned": learned, "solid": solid_lines, "shaky": shaky_lines,
             "mistakes": mistake_lines, "pace": pace_lines, "mood": mood_lines, "next": next_lines}
    questions = [{"id": qid, "question": text, "lines": lines[qid]} for qid, text in QUESTIONS]

    headline = [
        {"label": "Quiz accuracy", "value": _pct(acc) if acc is not None else "—"},
        {"label": "Quiz days", "value": str(len({r['on_date'] for r in results}))},
        {"label": "Words solid", "value": str(n_words_solid)},
        {"label": "Clean streak", "value": f"{clean} d"},
    ]
    skills = []
    for s in started:
        pr = progress[s.id]
        prog = (f"{pr.solid}/{pr.total} words solid" if s.subject == "spelling" else
                f"box {units[(s.id, '')].box}")
        skills.append({"title": s.title, "label": pr.label, "progress": prog})
    return {
        "student": student["name"], "date": on.isoformat(),
        "period_label": f"last {days} days to {on.isoformat()}",
        "headline": headline, "questions": questions, "skills": skills,
        "accuracy": acc, "tears_days": tears, "load_reductions": reductions,
        "recommendations": recs,
    }


def format_text(report: dict) -> str:
    out = [f"Progress report: {report['student']} ({report['period_label']})", ""]
    out.append("  ".join(f"{h['label']}: {h['value']}" for h in report["headline"]))
    for q in report["questions"]:
        out += ["", q["question"]]
        out += [f"  - {l}" for l in q["lines"]] or ["  (nothing to report yet)"]
    return "\n".join(out)
