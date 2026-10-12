"""Instant adult grading: oral quizzes, and entering results by hand.

For a six-year-old, the parent is sitting right there. An adult can judge a spoken answer or a
written word in a second, with perfect reliability, so this path is faster and more trustworthy
than a model. The VLM path (grade.py) exists for convenience and as an audit trail.
"""
from __future__ import annotations

from typing import Callable

from . import grade


def run_entry(manifest: dict, input_fn: Callable[[str], str] | None = None,
              print_fn: Callable[..., None] | None = None, sentence_fn: Callable[[str], str] | None = None
              ) -> list[grade.Scored]:
    """Walk through the quiz items. For each:
         Enter        = correct
         text         = what the child wrote or said (judged automatically)
         -            = left blank
         x            = wrong, no details
    """
    input_fn = input_fn or input
    print_fn = print_fn or print
    print_fn("")
    print_fn("For each item press Enter if it was right.")
    print_fn("Otherwise type what the child wrote or said, '-' for blank, or 'x' for wrong.")
    print_fn("")
    got: dict[str, str] = {}
    for it in manifest["items"]:
        n = it["n"]
        if it["kind_group"] == "spelling":
            sent = sentence_fn(it["expected"]) if sentence_fn else ""
            print_fn(f"{n}. SAY: \"{it['expected']}\"" + (f"   ({sent})" if sent else ""))
        else:
            speech = it.get("speech") or it["prompt_text"]
            print_fn(f"{n}. {speech}   [answer: {it['expected']}]")
        raw = input_fn("   right? > ").strip()
        if raw == "":
            got[it["id"]] = it["expected"]
        elif raw == "-":
            got[it["id"]] = ""
        elif raw.lower() == "x":
            got[it["id"]] = "?"
        else:
            got[it["id"]] = raw
    return grade.score(manifest, got)


def review_loop(rows: list[grade.Scored], input_fn: Callable[[str], str] | None = None,
                print_fn: Callable[..., None] | None = None) -> list[grade.Scored]:
    """Let the parent correct any row: type the item number, then what was actually written,
    or press Enter to flip right/wrong. Empty line to finish."""
    input_fn = input_fn or input
    print_fn = print_fn or print
    while True:
        print_fn("")
        for r in rows:
            mark = "ok " if r.correct else "WRONG"
            flag = f"  <- {r.reason}" if r.needs_review else ""
            shown = r.got if r.got else "(blank)"
            print_fn(f"  {r.n:>2}. {r.expected:<10} wrote: {shown:<12} {mark}{flag}")
        raw = input_fn("Fix an item? (number, or Enter to accept all) > ").strip()
        if not raw:
            return rows
        try:
            n = int(raw)
            row = next(r for r in rows if r.n == n)
        except (ValueError, StopIteration):
            print_fn("  no such item")
            continue
        txt = input_fn(f"  what did the child actually write for {n}? (Enter = flip right/wrong) > ").strip()
        if txt:
            grade.apply_override(row, got=txt)
        else:
            grade.apply_override(row, correct=not row.correct)
