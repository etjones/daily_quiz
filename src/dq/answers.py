"""Answer normalisation, matching and error classification.

Everything here is deterministic. No model is involved in deciding whether an
answer is right: models only transcribe what the child wrote, and this module
judges it.
"""

from __future__ import annotations

import re
from fractions import Fraction

# Error categories recorded in the database and shown in reports.
ERROR_CATEGORIES = (
    "blank",  # nothing written
    "reversal",  # b/d, p/q letter or digit flips (normal at this age)
    "transposition",  # adjacent letters/digits swapped
    "omission",  # one letter/digit missing (dropped blend letters)
    "insertion",  # one extra letter/digit
    "vowel_pattern",  # right consonants, wrong vowel(s): wrong pattern chosen
    "off_by_one",  # numeric answer one away (counting slip)
    "sign",  # < and > swapped
    "capitalization",
    "other",
)

_REVERSIBLE_PAIRS = [("b", "d"), ("p", "q"), ("n", "u"), ("m", "w")]
_SYMBOL_MAP = {
    "<": "<",
    ">": ">",
    "=": "=",
    "less": "<",
    "less than": "<",
    "lt": "<",
    "greater": ">",
    "greater than": ">",
    "more": ">",
    "more than": ">",
    "gt": ">",
    "equal": "=",
    "equals": "=",
    "same": "=",
}


def _clean(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def normalize(kind: str, s: str | None) -> str:
    """Canonical form of an answer string for comparison."""
    s = _clean(s)
    if kind == "spelling":
        return s.replace("’", "'").replace("`", "'")
    if kind == "int":
        s = s.replace(",", "").rstrip(".")
        s = re.sub(r"\s+", "", s)
        return s
    if kind == "int_rem":
        m = re.fullmatch(r"(\d+)\s*(?:r|R|rem|remainder)?\s*(\d+)?", s)
        if not m:
            return s.lower()
        q, r = m.group(1), m.group(2) or "0"
        return f"{int(q)} R {int(r)}"
    if kind == "frac":
        t = re.sub(r"\s+", "", s).replace("\\", "/").replace("⁄", "/").replace("∕", "/")
        m = re.fullmatch(r"(\d+)/(\d+)", t)
        return f"{int(m.group(1))}/{int(m.group(2))}" if m else t
    if kind == "symbol":
        key = s.lower().strip()
        return _SYMBOL_MAP.get(key, key)
    return s.lower()


def match(kind: str, expected: str, got: str | None) -> bool:
    """True if `got` is a correct answer for `expected` of the given kind."""
    g = normalize(kind, got)
    e = normalize(kind, expected)
    if not g:
        return False
    if kind == "spelling":
        if g == e:
            return True
        # Case is ignored except for the pronoun I and its contractions,
        # where a lowercase i is a real error at this age.
        if g.lower() == e.lower():
            return not (e == "I" or e.startswith("I'"))
        return False
    if kind == "frac":
        try:
            gn, gd = (int(x) for x in g.split("/"))
            en, ed = (int(x) for x in e.split("/"))
            if gd == 0 or ed == 0:
                return False
            return Fraction(gn, gd) == Fraction(en, ed)
        except (ValueError, ZeroDivisionError):
            return False
    return g == e


# ---------------------------------------------------------------------------
# error classification
# ---------------------------------------------------------------------------


def _single_edit(a: str, b: str) -> str | None:
    """Classify the one-edit relation from expected `a` to written `b`."""
    if a == b:
        return None
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            x, y = a[diffs[0]], b[diffs[0]]
            for p, q in _REVERSIBLE_PAIRS:
                if {x, y} == {p, q}:
                    return "reversal"
            return None
        if (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        ):
            return "transposition"
        return None
    if len(b) == len(a) - 1:
        for i in range(len(a)):
            if a[:i] + a[i + 1 :] == b:
                return "omission"
    if len(b) == len(a) + 1:
        for i in range(len(b)):
            if b[:i] + b[i + 1 :] == a:
                return "insertion"
    return None


def _consonant_skeleton(w: str) -> str:
    return re.sub(r"[aeiouy]", "", w.lower())


def classify_error(kind: str, expected: str, got: str | None) -> str | None:
    """Return an error category for a wrong answer, or None if it is correct."""
    if match(kind, expected, got):
        return None
    g = normalize(kind, got)
    e = normalize(kind, expected)
    if not g:
        return "blank"
    if kind == "spelling":
        if g.lower() == e.lower():
            return "capitalization"
        cat = _single_edit(e.lower(), g.lower())
        if cat:
            return cat
        if _consonant_skeleton(e) == _consonant_skeleton(g) and e.lower() != g.lower():
            return "vowel_pattern"
        return "other"
    if kind in ("int", "int_rem"):
        try:
            ge, ee = int(re.sub(r"\D.*", "", g)), int(re.sub(r"\D.*", "", e))
            if abs(ge - ee) == 1:
                return "off_by_one"
        except ValueError:
            pass
        if len(g) == len(e) and sorted(g) == sorted(e):
            return "transposition" if len(g) > 1 else "other"
        cat = _single_edit(e, g)
        if cat in ("omission", "insertion"):
            return cat
        # digit mirror flips: 2/5, 6/9 are common at this age
        flips = {"2": "5", "5": "2", "6": "9", "9": "6", "3": "8"}
        if len(g) == len(e):
            diffs = [i for i in range(len(g)) if g[i] != e[i]]
            if len(diffs) == 1 and flips.get(e[diffs[0]]) == g[diffs[0]]:
                return "reversal"
        return "other"
    if kind == "symbol":
        if {g, e} == {"<", ">"}:
            return "sign"
        return "other"
    return "other"
