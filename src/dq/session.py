"""Recording a graded quiz: one function used by the CLI and by the tests."""

from __future__ import annotations

from datetime import date

from . import scheduler
from .curriculum import Curriculum
from .db import DB


def record_quiz(
    db: DB, cur: Curriculum, student, quiz_row, rows: list, mode: str, on: date
) -> dict:
    """Store results, update memory state, mark the quiz graded. `rows` are grade.Scored."""
    db_rows = [r.to_row() for r in rows]
    db.add_results(student["id"], quiz_row["id"], on.isoformat(), db_rows, mode)
    summary = scheduler.apply_results(db, cur, student["id"], on, db_rows)
    db.mark_graded(quiz_row["id"], on.isoformat())
    graded = [r for r in rows if not r.probe]
    summary["taught_items"] = len(graded)
    summary["taught_correct"] = sum(r.correct for r in graded)
    summary["misses"] = [r.expected for r in graded if not r.correct]
    return summary
