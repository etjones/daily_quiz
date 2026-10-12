"""Turn a day's Selection into concrete content and PDFs.

One call to `build_day` produces three files:
  worksheet-<date>.pdf         tonight's practice sheet (one side)
  quiz-<next date>.pdf         tomorrow morning's quiz (half sheet, with registration marks)
  parent-script-<next date>.pdf   what to say, and the answers
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from . import generators, layout, render, scheduler
from .curriculum import Curriculum
from .db import DB

STORY_STAGES = {
    1: {
        "instruction": "Draw a picture of one of your words. Then write one sentence about it.",
        "lines": 2,
        "draw": True,
        "n_words": 1,
    },
    2: {
        "instruction": "Write one sentence. Use two of your words.",
        "lines": 2,
        "draw": False,
        "n_words": 2,
    },
    3: {
        "instruction": "Write two sentences. Use at least two of your words.",
        "lines": 3,
        "draw": False,
        "n_words": 3,
    },
    4: {
        "instruction": "Write three sentences. Use at least three of your words.",
        "lines": 4,
        "draw": False,
        "n_words": 3,
    },
    5: {
        "instruction": "Write a short story with four or five sentences. Use at least three of your words.",
        "lines": 5,
        "draw": False,
        "n_words": 3,
    },
}


@dataclass
class Built:
    selection: scheduler.Selection
    created: bool
    worksheet: Path
    quiz: Path
    parent: Path
    quiz_id: int
    quiz_date: str


def pretty(on: date) -> str:
    return on.strftime("%a %b ") + str(on.day)


def _split_word(cur: Curriculum, skill_id: str, word: str) -> list[str]:
    skill = cur.by_id.get(skill_id)
    span = cur.pattern_span(skill, word) if skill else None
    if not span:
        return ["", "", word]
    a, b = span
    return [word[:a], word[a:b], word[b:]]


def _demo_example(skill) -> str:
    if not skill.demo:
        return ""
    d0 = skill.demo[0]
    return f"{d0['q']} = {d0['a']}"


def dictation_sentence(cur: Curriculum, db: DB, word: str) -> str:
    return (
        cur.sentences.get(word.lower())
        or db.sentence(word.lower())
        or "(just say the word clearly)"
    )


def words_missing_sentences(
    cur: Curriculum, db: DB, include_phonics: bool = False
) -> list[str]:
    """Spelling words that need a dictation sentence and have none, sorted."""
    want = set()
    for s in cur.subject("spelling"):
        if not (include_phonics or s.track == "sight" or s.needs_sentence):
            continue
        for w in s.words:
            if w.lower() not in cur.sentences and not db.sentence(w.lower()):
                want.add(w)
    return sorted(want)


def _build_content(
    db: DB,
    cur: Curriculum,
    student,
    sel: scheduler.Selection,
    on: date,
    quiz_date: date,
):
    rng = random.Random(
        scheduler.stable_seed(student["name"], on.isoformat(), "content")
    )
    used_keys: set[str] = set()

    # ---- spelling ----------------------------------------------------------
    words = []
    for it in sel.spelling:
        words.append(
            {
                "word": it["word"],
                "role": it["role"],
                "skill_id": it["skill_id"],
                "parts": _split_word(cur, it["skill_id"], it["word"]),
            }
        )
    tips, seen = [], set()
    for it in sel.spelling:
        if it["role"] == "new" and it["skill_id"] not in seen:
            seen.add(it["skill_id"])
            sk = cur.by_id[it["skill_id"]]
            if sk.track == "phonics":
                tips.append({"title": sk.title, "tip": sk.tip})
    word_tips = tips[:2]

    # ---- math practice --------------------------------------------------------
    problems = []
    for slot in sel.math:
        sk = cur.by_id[slot["skill_id"]]
        for p in generators.generate(
            sk.generator, sk.params, rng, slot["n"], exclude=used_keys
        ):
            used_keys.add(p.key)
            problems.append({**p.to_dict(), "skill_id": sk.id, "role": slot["role"]})
    math_tips = []
    for slot in sel.math:
        if slot["role"] == "new":
            sk = cur.by_id[slot["skill_id"]]
            math_tips.append(
                {"title": sk.title, "tip": sk.tip, "example": _demo_example(sk)}
            )

    reteach = []
    for r in sel.reteach:
        sk = cur.by_id[r["skill_id"]]
        if sk.subject == "math":
            reteach.append(
                {"title": sk.title, "tip": sk.tip, "example": _demo_example(sk)}
            )
        else:
            reteach.append(
                {"title": sk.title, "tip": sk.tip, "example": r.get("word", "")}
            )

    # ---- story --------------------------------------------------------------
    cfg = STORY_STAGES[max(1, min(5, sel.story_stage))]
    phonics_words = [
        w["word"] for w in words if cur.by_id[w["skill_id"]].track == "phonics"
    ]
    sight_words = [
        w["word"] for w in words if cur.by_id[w["skill_id"]].track != "phonics"
    ]
    story_words = (phonics_words + sight_words)[: cfg["n_words"]]
    story = {
        "stage": sel.story_stage,
        "instruction": cfg["instruction"],
        "lines": cfg["lines"],
        "draw": cfg["draw"],
        "words": story_words,
    }

    worksheet = {
        "student": student["name"],
        "date": on.isoformat(),
        "date_pretty": pretty(on),
        "day_no": sel.day_no,
        "words": words,
        "word_tips": word_tips,
        "reteach": reteach,
        "math_tips": math_tips,
        "problems": problems,
        "story": story,
        "quiz_for": pretty(quiz_date),
        "load_note": sel.load_reason,
    }

    # ---- quiz (tomorrow) ----------------------------------------------------------
    quiz_items: list[dict] = []
    for it in sel.quiz_spelling:
        quiz_items.append(
            {
                "group": "spelling",
                "kind": "spelling",
                "skill_id": it["skill_id"],
                "item_key": it["word"],
                "expected": it["word"],
                "probe": False,
            }
        )
    if sel.spell_probe:
        for w in sel.spell_probe["words"]:
            quiz_items.append(
                {
                    "group": "spelling",
                    "kind": "spelling",
                    "skill_id": sel.spell_probe["skill_id"],
                    "item_key": w,
                    "expected": w,
                    "probe": True,
                }
            )

    quiz_rng = random.Random(
        scheduler.stable_seed(student["name"], on.isoformat(), "quiz")
    )
    for slot in sel.quiz_math:
        sk = cur.by_id[slot["skill_id"]]
        ps = generators.generate(
            sk.generator, sk.params, quiz_rng, slot["n"], exclude=used_keys
        )
        for p in ps:
            used_keys.add(p.key)
            quiz_items.append(
                {
                    "group": "math",
                    "kind": p.kind,
                    "skill_id": sk.id,
                    "item_key": "",
                    "expected": p.answer,
                    "prompt": p.prompt,
                    "lead": p.lead,
                    "probe": False,
                    "speech": p.speech,
                }
            )
    if sel.math_probe:
        sk = cur.by_id[sel.math_probe["skill_id"]]
        for p in generators.generate(
            sk.generator, sk.params, quiz_rng, sel.math_probe["n"], exclude=used_keys
        ):
            used_keys.add(p.key)
            quiz_items.append(
                {
                    "group": "math",
                    "kind": p.kind,
                    "skill_id": sk.id,
                    "item_key": "",
                    "expected": p.answer,
                    "prompt": p.prompt,
                    "lead": p.lead,
                    "probe": True,
                    "speech": p.speech,
                }
            )

    manifest = layout.build_manifest(
        quiz_items,
        student["name"],
        quiz_date.isoformat(),
        f"Quiz {quiz_date.isoformat()}",
    )
    # carry speech text for the parent script (not needed for geometry)
    speech_by_key = {
        (i["skill_id"], i["expected"], i["prompt"]): i.get("speech", "")
        for i in quiz_items
        if i["group"] == "math"
    }
    for it in manifest["items"]:
        if it["kind_group"] == "math":
            it["speech"] = speech_by_key.get(
                (it["skill_id"], it["expected"], it["prompt_text"]), ""
            )
    return worksheet, manifest


def parent_data(
    db: DB, cur: Curriculum, student, manifest: dict, quiz_date: date
) -> dict:
    spelling, math = [], []
    for it in manifest["items"]:
        if it["kind_group"] == "spelling":
            spelling.append(
                {
                    "n": it["n"],
                    "word": it["expected"],
                    "probe": it["probe"],
                    "sentence": dictation_sentence(cur, db, it["expected"]),
                }
            )
        else:
            math.append(
                {
                    "n": it["n"],
                    "speech": it.get("speech") or it["prompt_text"],
                    "answer": it["expected"],
                    "probe": it["probe"],
                }
            )
    return {
        "student": student["name"],
        "date_pretty": pretty(quiz_date),
        "quiz_label": manifest["quiz_label"],
        "spelling": spelling,
        "math": math,
    }


def build_day(
    db: DB,
    cur: Curriculum,
    home: Path,
    student_name: str,
    on: date,
    force: bool = False,
    quiz_date: date | None = None,
) -> Built:
    student = db.student(student_name)
    quiz_date = quiz_date or on + timedelta(days=1)
    sel, created = scheduler.plan_day(db, cur, student, on, force=force)
    out_dir = home / "out" / student_name / on.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    if created:
        worksheet, manifest = _build_content(db, cur, student, sel, on, quiz_date)
        plan_id = db.save_plan(
            student["id"],
            on.isoformat(),
            sel.day_no,
            {
                "selection": sel.to_dict(),
                "worksheet": worksheet,
                "manifest": manifest,
                "quiz_date": quiz_date.isoformat(),
            },
        )
        quiz_id = db.save_quiz(student["id"], plan_id, quiz_date.isoformat(), manifest)
    else:
        import json

        row = db.plan_for(student["id"], on.isoformat())
        data = json.loads(row["data"])
        worksheet, manifest = data["worksheet"], data["manifest"]
        quiz_date = date.fromisoformat(data.get("quiz_date", quiz_date.isoformat()))
        q = db.conn.execute(
            "SELECT id FROM quiz WHERE student_id = ? AND for_date = ? ORDER BY id DESC LIMIT 1",
            (student["id"], quiz_date.isoformat()),
        ).fetchone()
        quiz_id = (
            q["id"]
            if q
            else db.save_quiz(student["id"], row["id"], quiz_date.isoformat(), manifest)
        )

    ws = render.render_pdf(
        home, "worksheet", worksheet, out_dir / f"worksheet-{on.isoformat()}.pdf"
    )
    qz = render.render_pdf(
        home,
        "quiz",
        {
            "student": student["name"],
            "date": quiz_date.isoformat(),
            "date_pretty": pretty(quiz_date),
            "quiz_label": manifest["quiz_label"],
            "manifest": manifest,
        },
        out_dir / f"quiz-{quiz_date.isoformat()}.pdf",
    )
    pr = render.render_pdf(
        home,
        "parent",
        parent_data(db, cur, student, manifest, quiz_date),
        out_dir / f"parent-script-{quiz_date.isoformat()}.pdf",
    )
    return Built(sel, created, ws, qz, pr, quiz_id, quiz_date.isoformat())
