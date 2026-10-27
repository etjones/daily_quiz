"""Yes/no checks for puzzle answers that are not in the accepted list.

"bear : den" is the expected answer, but "cave" is right too. Listing every right answer
is impossible, so an unlisted answer goes to a decision model (TypeSafe's Jev through
OpenRouter's Decisions API), which returns the probability that it is right. Answers are
cached in the database, so each (puzzle, answer) pair is asked about once.

Configured by OPENROUTER_API_KEY (an op:// reference in .env, resolved by `op run`) and
optionally DQ_JUDGE_MODEL. Without a key, unlisted answers are simply marked wrong and the
grown-up can flip them.
"""

import json
import os
import urllib.request
from dataclasses import dataclass

from . import puzzles
from .db import DB

URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.14"
ACCEPT_AT = 0.8  # p(yes) at or above this: right
DOUBT_ABOVE = 0.3  # between this and ACCEPT_AT: wrong, but flagged for the grown-up


class JudgeError(RuntimeError):
    pass


def question(item: dict, answer: str) -> tuple[dict, dict] | None:
    """(state, noul question) for a puzzle manifest item, or None if no model should judge
    it. A ladder answer that is not one letter away is wrong without asking."""
    t = item["ptype"]
    if t not in puzzles.JUDGED_TYPES:
        return None
    if t == "ladder" and not puzzles.one_letter_apart(item["start"], answer):
        return None
    state = {
        "puzzle": item["prompt_text"],
        "expected_answer": item["expected"],
        "other_accepted_answers": item.get("accept", []),
        "child_answer": answer,
        "note": item.get("note", ""),
    }
    ask = {
        "analogy": (
            f"Does '{answer}' complete the analogy with the same relationship ({item.get('note', '')})?",
            "The child's word relates to the third word exactly as the second word relates to the first.",
            "The relationship is different, or the word does not fit.",
        ),
        "ladder": (
            f"Is '{answer}' a real word that matches the clue?",
            "It is a real English word a child would know, and it fits the clue.",
            "It is not a real word, or it does not fit the clue.",
        ),
        "build": (
            f"Does '{answer}' correctly fill the blank so the finished word matches the meaning given?",
            "Putting the parts together makes a real word with that meaning.",
            "The finished word is not real or does not have that meaning.",
        ),
    }[t]
    return state, {
        "type": "noul",
        "instructions": ask[0],
        "criteria": {"true": ask[1], "false": ask[2]},
    }


@dataclass
class JevJudge:
    api_key: str
    model: str = DEFAULT_MODEL
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "JevJudge | None":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            return None
        if key.startswith("op://"):
            raise JudgeError(
                "OPENROUTER_API_KEY is an unresolved 1Password reference; "
                "run under `op run --env-file=.env`"
            )
        return cls(key, os.environ.get("DQ_JUDGE_MODEL") or DEFAULT_MODEL)

    def ask(self, state: dict, q: dict) -> float:
        body = {"model": self.model, "state": state, "questions": {"ok": q}}
        req = urllib.request.Request(
            URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.load(resp)
            return float(out["answers"]["ok"]["noul"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise JudgeError(f"answer checker failed: {e}") from e


@dataclass
class CachedJudge:
    db: DB
    inner: JevJudge

    def p_yes(self, item: dict, answer: str) -> float | None:
        """Probability the answer is right, or None if this puzzle is not model-judged."""
        a = answer.strip().lower()
        qa = question(item, a)
        if qa is None:
            return None
        hit = self.db.judgment(item["puzzle_id"], a)
        if hit is not None:
            return hit
        p = self.inner.ask(*qa)
        self.db.set_judgment(item["puzzle_id"], a, p, self.inner.model)
        return p


def from_env(db: DB) -> CachedJudge | None:
    inner = JevJudge.from_env()
    return CachedJudge(db, inner) if inner else None
