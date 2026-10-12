"""SQLite persistence. One file per household; plain tables so it is easy to inspect
or export (`sqlite3 dq.db '.dump'`)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS student (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created TEXT NOT NULL,
    composition_stage INTEGER NOT NULL DEFAULT 1,
    pace_cap INTEGER NOT NULL DEFAULT 2,
    probe_days INTEGER NOT NULL DEFAULT 10
);

-- One row per (student, skill, item). Spelling: item_key is the word.
-- Math: item_key is the empty string (skill-level unit).
CREATE TABLE IF NOT EXISTS unit_state (
    student_id INTEGER NOT NULL REFERENCES student(id),
    skill_id TEXT NOT NULL,
    item_key TEXT NOT NULL DEFAULT '',
    box INTEGER NOT NULL DEFAULT 0,
    introduced_on TEXT NOT NULL,
    last_seen TEXT,
    due_on TEXT NOT NULL,
    streak INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    last_correct INTEGER,
    origin TEXT NOT NULL DEFAULT 'taught',     -- taught | probed | transfer
    PRIMARY KEY (student_id, skill_id, item_key)
);

CREATE TABLE IF NOT EXISTS plan (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id),
    for_date TEXT NOT NULL,
    day_no INTEGER NOT NULL,
    data TEXT NOT NULL,            -- JSON: worksheet + quiz content as generated
    UNIQUE (student_id, for_date)
);

CREATE TABLE IF NOT EXISTS quiz (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id),
    plan_id INTEGER REFERENCES plan(id),
    for_date TEXT NOT NULL,
    manifest TEXT NOT NULL,        -- JSON: items with expected answers and box geometry
    status TEXT NOT NULL DEFAULT 'open',   -- open | graded
    graded_on TEXT
);

CREATE TABLE IF NOT EXISTS result (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id),
    quiz_id INTEGER REFERENCES quiz(id),
    on_date TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    item_key TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    expected TEXT NOT NULL,
    got TEXT,
    correct INTEGER NOT NULL,
    error_cat TEXT,
    probe INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'manual'    -- vlm | oral | manual
);

CREATE TABLE IF NOT EXISTS day_log (
    student_id INTEGER NOT NULL REFERENCES student(id),
    on_date TEXT NOT NULL,
    mood TEXT,                 -- easy | ok | hard | tears
    composition_done INTEGER,  -- 1 / 0 / NULL
    note TEXT,
    PRIMARY KEY (student_id, on_date)
);

CREATE TABLE IF NOT EXISTS probe_state (
    student_id INTEGER NOT NULL REFERENCES student(id),
    skill_id TEXT NOT NULL,
    outcome TEXT NOT NULL,     -- passed | failed
    on_date TEXT NOT NULL,
    PRIMARY KEY (student_id, skill_id)
);

CREATE TABLE IF NOT EXISTS sentence_cache (
    word TEXT PRIMARY KEY,
    sentence TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);
"""


@dataclass
class Unit:
    skill_id: str
    item_key: str
    box: int
    introduced_on: str
    last_seen: str | None
    due_on: str
    streak: int
    lapses: int
    last_correct: int | None
    origin: str


class DB:
    def __init__(self, path: str | Path, check_same_thread: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- students -----------------------------------------------------------

    def add_student(self, name: str, today: date, pace_cap: int = 2) -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO student(name, created, pace_cap) VALUES (?,?,?)",
                (name, today.isoformat(), pace_cap),
            )
            return cur.lastrowid

    def student(self, name: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM student WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no student named {name!r}; run `dq init {name}` first")
        return row

    def students(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM student ORDER BY name").fetchall()

    def set_student_field(self, student_id: int, field: str, value) -> None:
        assert field in {"composition_stage", "pace_cap", "probe_days"}
        with self.tx() as c:
            c.execute(
                f"UPDATE student SET {field} = ? WHERE id = ?", (value, student_id)
            )

    # -- unit state ---------------------------------------------------------

    def units(self, student_id: int) -> dict[tuple[str, str], Unit]:
        rows = self.conn.execute(
            "SELECT skill_id, item_key, box, introduced_on, last_seen, due_on, streak, lapses,"
            " last_correct, origin FROM unit_state WHERE student_id = ?",
            (student_id,),
        ).fetchall()
        return {(r["skill_id"], r["item_key"]): Unit(**dict(r)) for r in rows}

    def upsert_unit(self, student_id: int, u: Unit) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO unit_state(student_id, skill_id, item_key, box, introduced_on, last_seen,"
                " due_on, streak, lapses, last_correct, origin) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(student_id, skill_id, item_key) DO UPDATE SET box=excluded.box,"
                " last_seen=excluded.last_seen, due_on=excluded.due_on, streak=excluded.streak,"
                " lapses=excluded.lapses, last_correct=excluded.last_correct, origin=excluded.origin",
                (
                    student_id,
                    u.skill_id,
                    u.item_key,
                    u.box,
                    u.introduced_on,
                    u.last_seen,
                    u.due_on,
                    u.streak,
                    u.lapses,
                    u.last_correct,
                    u.origin,
                ),
            )

    def delete_units_introduced_on(self, student_id: int, on: str) -> None:
        """Used when a day's plan is regenerated: forget units that day introduced and
        that have never been tested."""
        with self.tx() as c:
            c.execute(
                "DELETE FROM unit_state WHERE student_id = ? AND introduced_on = ? AND box = 0"
                " AND last_seen IS NULL AND origin = 'taught'",
                (student_id, on),
            )

    # -- plans & quizzes ----------------------------------------------------

    def plan_for(self, student_id: int, on: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM plan WHERE student_id = ? AND for_date = ?", (student_id, on)
        ).fetchone()

    def save_plan(self, student_id: int, on: str, day_no: int, data: dict) -> int:
        with self.tx() as c:
            c.execute(
                "DELETE FROM plan WHERE student_id = ? AND for_date = ?",
                (student_id, on),
            )
            cur = c.execute(
                "INSERT INTO plan(student_id, for_date, day_no, data) VALUES (?,?,?,?)",
                (student_id, on, day_no, json.dumps(data)),
            )
            return cur.lastrowid

    def plan_count(self, student_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM plan WHERE student_id = ?", (student_id,)
        ).fetchone()[0]

    def last_plan(
        self, student_id: int, before: str | None = None
    ) -> sqlite3.Row | None:
        if before:
            return self.conn.execute(
                "SELECT * FROM plan WHERE student_id = ? AND for_date < ? ORDER BY for_date DESC LIMIT 1",
                (student_id, before),
            ).fetchone()
        return self.conn.execute(
            "SELECT * FROM plan WHERE student_id = ? ORDER BY for_date DESC LIMIT 1",
            (student_id,),
        ).fetchone()

    def save_quiz(
        self, student_id: int, plan_id: int | None, for_date: str, manifest: dict
    ) -> int:
        with self.tx() as c:
            c.execute(
                "DELETE FROM quiz WHERE student_id = ? AND for_date = ? AND status = 'open'",
                (student_id, for_date),
            )
            cur = c.execute(
                "INSERT INTO quiz(student_id, plan_id, for_date, manifest) VALUES (?,?,?,?)",
                (student_id, plan_id, for_date, json.dumps(manifest)),
            )
            return cur.lastrowid

    def quiz(self, quiz_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM quiz WHERE id = ?", (quiz_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no quiz with id {quiz_id}")
        return row

    def latest_open_quiz(
        self, student_id: int, on_or_before: str | None = None
    ) -> sqlite3.Row | None:
        q = "SELECT * FROM quiz WHERE student_id = ? AND status = 'open'"
        args: list = [student_id]
        if on_or_before:
            q += " AND for_date <= ?"
            args.append(on_or_before)
        q += " ORDER BY for_date DESC, id DESC LIMIT 1"
        return self.conn.execute(q, args).fetchone()

    def mark_graded(self, quiz_id: int, on: str) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE quiz SET status = 'graded', graded_on = ? WHERE id = ?",
                (on, quiz_id),
            )

    # -- results ------------------------------------------------------------

    def add_results(
        self, student_id: int, quiz_id: int | None, on: str, rows: list[dict], mode: str
    ) -> None:
        with self.tx() as c:
            for r in rows:
                c.execute(
                    "INSERT INTO result(student_id, quiz_id, on_date, skill_id, item_key, kind, prompt,"
                    " expected, got, correct, error_cat, probe, mode) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        student_id,
                        quiz_id,
                        on,
                        r["skill_id"],
                        r.get("item_key", ""),
                        r["kind"],
                        r["prompt"],
                        r["expected"],
                        r.get("got"),
                        1 if r["correct"] else 0,
                        r.get("error_cat"),
                        1 if r.get("probe") else 0,
                        mode,
                    ),
                )

    def results_since(
        self, student_id: int, since: str, include_probes: bool = True
    ) -> list[sqlite3.Row]:
        q = "SELECT * FROM result WHERE student_id = ? AND on_date >= ?"
        if not include_probes:
            q += " AND probe = 0"
        q += " ORDER BY on_date, id"
        return self.conn.execute(q, (student_id, since)).fetchall()

    def results_for_quiz(self, quiz_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM result WHERE quiz_id = ? ORDER BY id", (quiz_id,)
        ).fetchall()

    def graded_quizzes(self, student_id: int) -> list[sqlite3.Row]:
        """Graded quizzes, newest first, with counts over non-probe items."""
        return self.conn.execute(
            "SELECT q.id, q.for_date, q.graded_on,"
            " SUM(CASE WHEN r.probe = 0 THEN 1 ELSE 0 END) AS n,"
            " SUM(CASE WHEN r.probe = 0 THEN r.correct ELSE 0 END) AS n_right,"
            " MAX(r.mode) AS mode"
            " FROM quiz q LEFT JOIN result r ON r.quiz_id = q.id"
            " WHERE q.student_id = ? AND q.status = 'graded'"
            " GROUP BY q.id ORDER BY q.for_date DESC, q.id DESC",
            (student_id,),
        ).fetchall()

    def quiz_days(self, student_id: int) -> list[tuple[str, float, int]]:
        """(date, accuracy over non-probe items, item count), oldest first."""
        rows = self.conn.execute(
            "SELECT on_date, AVG(correct) AS acc, COUNT(*) AS n FROM result"
            " WHERE student_id = ? AND probe = 0 GROUP BY on_date ORDER BY on_date",
            (student_id,),
        ).fetchall()
        return [(r["on_date"], r["acc"], r["n"]) for r in rows]

    # -- day log ------------------------------------------------------------

    def log_day(
        self,
        student_id: int,
        on: str,
        mood: str | None = None,
        composition_done: bool | None = None,
        note: str | None = None,
    ) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO day_log(student_id, on_date) VALUES (?,?)",
                (student_id, on),
            )
            if mood is not None:
                c.execute(
                    "UPDATE day_log SET mood = ? WHERE student_id = ? AND on_date = ?",
                    (mood, student_id, on),
                )
            if composition_done is not None:
                c.execute(
                    "UPDATE day_log SET composition_done = ? WHERE student_id = ? AND on_date = ?",
                    (1 if composition_done else 0, student_id, on),
                )
            if note is not None:
                c.execute(
                    "UPDATE day_log SET note = ? WHERE student_id = ? AND on_date = ?",
                    (note, student_id, on),
                )

    def day_logs(self, student_id: int, since: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM day_log WHERE student_id = ?"
        args: list = [student_id]
        if since:
            q += " AND on_date >= ?"
            args.append(since)
        return self.conn.execute(q + " ORDER BY on_date", args).fetchall()

    # -- probes -------------------------------------------------------------

    def probes(self, student_id: int) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT skill_id, outcome FROM probe_state WHERE student_id = ?",
            (student_id,),
        ).fetchall()
        return {r["skill_id"]: r["outcome"] for r in rows}

    def set_probe(self, student_id: int, skill_id: str, outcome: str, on: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO probe_state(student_id, skill_id, outcome, on_date) VALUES (?,?,?,?)"
                " ON CONFLICT(student_id, skill_id) DO UPDATE SET outcome=excluded.outcome,"
                " on_date=excluded.on_date",
                (student_id, skill_id, outcome, on),
            )

    # -- sentences ----------------------------------------------------------

    def sentence(self, word: str) -> str | None:
        r = self.conn.execute(
            "SELECT sentence FROM sentence_cache WHERE word = ?", (word,)
        ).fetchone()
        return r["sentence"] if r else None

    def set_sentence(self, word: str, sentence: str, source: str = "manual") -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO sentence_cache(word, sentence, source) VALUES (?,?,?)"
                " ON CONFLICT(word) DO UPDATE SET sentence=excluded.sentence, source=excluded.source",
                (word, sentence, source),
            )
