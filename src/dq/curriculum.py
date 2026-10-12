"""Curriculum loading and validation.

A curriculum is a set of TOML files (see curriculum/*.toml). Skills are kept in
file order; that order is the default teaching sequence.
"""
from __future__ import annotations

import random
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import generators

CORE_DEFAULT = 10


@dataclass
class Strand:
    id: str
    subject: str
    title: str
    grade: int
    rationale: str = ""
    teach: str = ""
    watch_for: str = ""
    track: str = "main"          # spelling: "phonics" or "sight"
    teks: str = ""


@dataclass
class Skill:
    id: str
    subject: str
    strand: str
    title: str
    grade: int = 0
    tip: str = ""
    note: str = ""
    teks: str = ""
    prereqs: list[str] = field(default_factory=list)
    demo: list[dict] = field(default_factory=list)
    track: str = "main"
    # spelling
    pattern: str = ""
    hl: str = ""
    words: list[str] = field(default_factory=list)
    core: int = 0
    sentences: dict[str, str] = field(default_factory=dict)
    needs_sentence: bool = False
    # math
    generator: str = ""
    params: dict = field(default_factory=dict)
    min_distinct: int = 8       # smallest acceptable problem space (some skills are inherently small)

    @property
    def core_words(self) -> list[str]:
        return self.words[: self.core]

    @property
    def transfer_words(self) -> list[str]:
        return self.words[self.core:]


@dataclass
class Curriculum:
    skills: list[Skill]
    strands: dict[str, Strand]
    meta: dict[str, dict]
    sentences: dict[str, str] = field(default_factory=dict)   # lowercase word -> dictation sentence

    def __post_init__(self):
        self.by_id = {s.id: s for s in self.skills}
        self.index = {s.id: i for i, s in enumerate(self.skills)}

    def subject(self, name: str) -> list[Skill]:
        return [s for s in self.skills if s.subject == name]

    def strand_of(self, skill: Skill) -> Strand:
        return self.strands[f"{skill.subject}:{skill.strand}"]

    def pattern_span(self, skill: Skill, word: str) -> tuple[int, int] | None:
        """Where the taught pattern sits inside a word, for highlighting."""
        rx = skill.hl or skill.pattern
        if not rx or rx == ".":
            return None
        m = re.search(rx, word)
        if not m or m.end() == m.start():
            return None
        if m.end() - m.start() >= len(word):
            return None
        return m.start(), m.end()


def load(directory: str | Path) -> Curriculum:
    directory = Path(directory)
    skills: list[Skill] = []
    strands: dict[str, Strand] = {}
    meta: dict[str, dict] = {}
    for path in sorted(directory.glob("*.toml")):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data.get("meta", {})
        subject = m.get("subject")
        if not subject:
            raise ValueError(f"{path.name}: [meta].subject is required")
        meta[subject] = m
        for s in data.get("strand", []):
            st = Strand(subject=subject, **{k: v for k, v in s.items() if k in Strand.__dataclass_fields__ and k != "subject"})
            strands[f"{subject}:{st.id}"] = st
        for s in data.get("skill", []):
            kw = {k: v for k, v in s.items() if k in Skill.__dataclass_fields__}
            kw["subject"] = subject
            sk = Skill(**kw)
            if subject == "spelling":
                sk.core = min(len(sk.words), sk.core or CORE_DEFAULT)
                st = strands.get(f"{subject}:{sk.strand}")
                sk.track = st.track if st else "phonics"
            st = strands.get(f"{subject}:{sk.strand}")
            if st and not sk.grade:
                sk.grade = st.grade
            skills.append(sk)
    sentences: dict[str, str] = {}
    for path in sorted((directory / "sentences").glob("*.toml")) if (directory / "sentences").is_dir() else []:
        with open(path, "rb") as f:
            sentences.update({k.lower(): v for k, v in tomllib.load(f).get("sentences", {}).items()})
    for sk in skills:
        for w, sent in sk.sentences.items():
            sentences.setdefault(w.lower(), sent)
    return Curriculum(skills, strands, meta, sentences)


def validate(cur: Curriculum, smoke_seeds: int = 40) -> list[str]:
    """Return a list of human-readable problems. Empty list means valid."""
    errs: list[str] = []
    seen: set[str] = set()
    for i, s in enumerate(cur.skills):
        where = s.id
        if s.id in seen:
            errs.append(f"{where}: duplicate id")
        seen.add(s.id)
        if f"{s.subject}:{s.strand}" not in cur.strands:
            errs.append(f"{where}: unknown strand {s.strand!r}")
        if not s.title:
            errs.append(f"{where}: missing title")
        if not s.tip:
            errs.append(f"{where}: missing child-facing tip")
        for p in s.prereqs:
            if p not in cur.by_id:
                errs.append(f"{where}: prerequisite {p!r} does not exist")
            elif cur.index[p] >= i:
                errs.append(f"{where}: prerequisite {p!r} comes later in the file order")
        if s.subject == "spelling":
            errs.extend(_validate_spelling(s))
        elif s.subject == "math":
            errs.extend(_validate_math(s, smoke_seeds))
    return errs


def _validate_spelling(s: Skill) -> list[str]:
    errs = []
    if not s.words:
        return [f"{s.id}: no words"]
    if len(set(w.lower() for w in s.words)) != len(s.words):
        errs.append(f"{s.id}: duplicate words in pool")
    try:
        rx = re.compile(s.pattern)
    except re.error as e:
        return [f"{s.id}: bad pattern regex: {e}"]
    for w in s.words:
        if not rx.search(w):
            errs.append(f"{s.id}: word {w!r} does not match pattern {s.pattern!r}")
    if s.hl:
        try:
            re.compile(s.hl)
        except re.error as e:
            errs.append(f"{s.id}: bad hl regex: {e}")
    if s.needs_sentence:
        missing = [w for w in s.words if w not in s.sentences]
        if missing:
            errs.append(f"{s.id}: needs_sentence but no sentence for {missing}")
        for w, sent in s.sentences.items():
            if w not in s.words:
                errs.append(f"{s.id}: sentence given for {w!r}, which is not in the word list")
            elif not re.search(rf"\b{re.escape(w)}\b", sent, re.I):
                errs.append(f"{s.id}: sentence for {w!r} does not contain the word")
    if len(s.core_words) < 5:
        errs.append(f"{s.id}: fewer than 5 core words ({len(s.core_words)})")
    return errs


def _validate_math(s: Skill, smoke_seeds: int) -> list[str]:
    errs = []
    if s.generator not in generators.REGISTRY:
        return [f"{s.id}: unknown generator {s.generator!r}"]
    if not s.demo:
        errs.append(f"{s.id}: no demo problems")
    from . import answers
    keys = set()
    try:
        for seed in range(smoke_seeds):
            p = generators.generate_one(s.generator, s.params, random.Random(seed))
            keys.add(p.key)
            if not answers.match(p.kind, p.answer, p.answer):
                errs.append(f"{s.id}: generated answer {p.answer!r} does not match itself as kind {p.kind!r}")
                break
    except Exception as e:  # noqa: BLE001
        errs.append(f"{s.id}: generator failed: {e}")
    if len(keys) < s.min_distinct:
        errs.append(f"{s.id}: only {len(keys)} distinct problems in {smoke_seeds} samples; widen params")
    return errs
