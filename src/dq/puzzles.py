"""Word puzzles: analogies, odd one out, change-one-letter, word building, sound-alikes,
clues for spelling words (quiz and worksheet), and word scales (worksheet only).

Banks live in curriculum/puzzles/*.toml. Every puzzle has a stable id derived from its
content, so editing or reordering a file does not make old puzzles look new.
"""

import random
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

QUIZ_TYPES = ("analogy", "odd", "ladder", "build", "homophone")
JUDGED_TYPES = ("analogy", "ladder", "build")  # open answers a model may accept
MAX_LEVEL = 3


@dataclass
class Puzzle:
    id: str
    type: str
    prompt: str  # what the child reads (plain text)
    answer: str
    accept: list[str] = field(default_factory=list)
    level: int = 1
    note: str = ""  # for the grown-up and the answer checker: relation, reason, clue
    words: list[str] = field(default_factory=list)  # scale: the right order
    start: str = ""  # ladder: the word to change

    def accepts(self, got: str) -> bool:
        g = got.strip().lower()
        return bool(g) and g in {a.lower() for a in [self.answer, *self.accept]}


def _analogy(d: dict) -> Puzzle:
    return Puzzle(
        id=f"an:{d['a']}:{d['b']}:{d['c']}".lower(),
        type="analogy",
        prompt=f"{d['a']} is to {d['b']}, as {d['c']} is to",
        answer=d["answer"],
        accept=d.get("accept", []),
        level=d.get("level", 1),
        note=d["relation"],
    )


def _odd(d: dict) -> Puzzle:
    return Puzzle(
        id="odd:" + ":".join(sorted(w.lower() for w in d["words"])),
        type="odd",
        prompt="Which one does not belong? " + ", ".join(d["words"]),
        answer=d["answer"],
        level=d.get("level", 1),
        note=d["reason"],
        words=d["words"],
    )


def _ladder(d: dict) -> Puzzle:
    return Puzzle(
        id=f"lad:{d['start']}:{d['answer']}".lower(),
        type="ladder",
        prompt=f"Change one letter in {d['start'].upper()}: {d['clue']}",
        answer=d["answer"],
        accept=d.get("accept", []),
        level=d.get("level", 1),
        note=d["clue"],
        start=d["start"],
    )


def _build(d: dict) -> Puzzle:
    return Puzzle(
        id="bld:" + re.sub(r"[^a-z]+", "-", d["prompt"].lower()).strip("-"),
        type="build",
        prompt=d["prompt"],
        answer=d["answer"],
        accept=d.get("accept", []),
        level=d.get("level", 1),
        note=d["prompt"],
    )


def _homophone(d: dict) -> Puzzle:
    return Puzzle(
        id="hom:" + re.sub(r"[^a-z]+", "-", d["sentence"].lower()).strip("-"),
        type="homophone",
        prompt=f"{d['sentence']} ({' or '.join(d['choices'])})",
        answer=d["answer"],
        level=d.get("level", 1),
        note="choices: " + ", ".join(d["choices"]),
        words=d["choices"],
    )


def _scale(d: dict) -> Puzzle:
    return Puzzle(
        id="sc:" + ":".join(w.lower() for w in d["words"]),
        type="scale",
        prompt=f"Put in order {d['prompt']}",
        answer=", ".join(d["words"]),
        level=d.get("level", 1),
        note=d["prompt"],
        words=d["words"],
    )


_MAKERS = {
    "analogy": _analogy,
    "odd": _odd,
    "ladder": _ladder,
    "build": _build,
    "homophone": _homophone,
    "scale": _scale,
}


def load(directory: Path) -> tuple[list[Puzzle], dict[str, str]]:
    """All puzzles in file order, and the clue table (lowercase word -> clue)."""
    puzzles: list[Puzzle] = []
    clues: dict[str, str] = {}
    for path in sorted(directory.glob("*.toml")) if directory.is_dir() else []:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        clues.update({k.lower(): v for k, v in data.get("clues", {}).items()})
        for kind, make in _MAKERS.items():
            puzzles += [make(d) for d in data.get(kind, [])]
    return puzzles, clues


def clue_puzzle(word: str, clue: str) -> Puzzle:
    return Puzzle(
        id=f"clue:{word.lower()}",
        type="clue",
        prompt=f"{clue[0].upper()}{clue[1:]} ({len(word)} letters)",
        answer=word,
        note=clue,
    )


def one_letter_apart(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a.lower(), b.lower())) == 1


def validate(
    puzzles: list[Puzzle], clues: dict[str, str], words: set[str]
) -> list[str]:
    """Problems in the banks. `words` is every spelling word (lowercase)."""
    errs: list[str] = []
    seen: set[str] = set()
    for p in puzzles:
        if p.id in seen:
            errs.append(f"{p.id}: duplicate puzzle")
        seen.add(p.id)
        if not 1 <= p.level <= MAX_LEVEL:
            errs.append(f"{p.id}: level must be 1..{MAX_LEVEL}")
        if p.type in ("odd", "homophone") and p.answer not in p.words:
            errs.append(f"{p.id}: answer {p.answer!r} is not one of the choices")
        if p.type == "ladder":
            for a in [p.answer, *p.accept]:
                if not one_letter_apart(p.start, a):
                    errs.append(
                        f"{p.id}: {a!r} is not one letter away from {p.start!r}"
                    )
        if p.type == "analogy" and p.answer.lower() in p.id.split(":")[1:]:
            errs.append(f"{p.id}: the answer appears in the question")
        if p.type == "scale" and len(p.words) < 3:
            errs.append(f"{p.id}: a scale needs at least three words")
    for w, c in clues.items():
        if w not in words:
            errs.append(f"clue for {w!r}: not a spelling word")
        if re.search(rf"\b{re.escape(w)}\b", c, re.IGNORECASE):
            errs.append(f"clue for {w!r} gives the word away")
    return errs


def levels(history: list[tuple[str, bool]]) -> dict[str, int]:
    """Per puzzle type: start at 1, up a level after three right in a row, down after two
    wrong in a row. `history` is (type, correct), oldest first."""
    out: dict[str, int] = {}
    run: dict[str, int] = {}
    for t, ok in history:
        lv, r = out.get(t, 1), run.get(t, 0)
        r = max(1, r + 1) if ok else min(-1, r - 1)
        if r >= 3:
            lv, r = min(MAX_LEVEL, lv + 1), 0
        elif r <= -2:
            lv, r = max(1, lv - 1), 0
        out[t], run[t] = lv, r
    return out


def pick(
    puzzles: list[Puzzle],
    ptype: str,
    level: int,
    last_used: dict[str, str],
    rng: random.Random,
    exclude: set[str],
) -> Puzzle | None:
    """A puzzle of this type: never-used before least-recently-used, then closest to the
    level (at or below it before above it)."""
    pool = [p for p in puzzles if p.type == ptype and p.id not in exclude]
    if not pool:
        return None

    def key(p: Puzzle) -> tuple:
        lv = p.level - level
        return (last_used.get(p.id, ""), abs(lv) + (0.5 if lv > 0 else 0), rng.random())

    return min(pool, key=key)


def next_types(recent: list[str], rng: random.Random, n: int) -> list[str]:
    """n different quiz puzzle types, the ones used longest ago first."""
    last = {t: i for i, t in enumerate(recent)}
    order = sorted(QUIZ_TYPES, key=lambda t: (last.get(t, -1), rng.random()))
    return order[:n]
