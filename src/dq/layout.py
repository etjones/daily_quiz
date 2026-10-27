"""Quiz sheet geometry. Everything is in millimetres, origin at the top-left of the page.

The same numbers drive the Typst template (which draws the boxes) and the grader
(which crops them), so the two can never drift apart.
"""

from __future__ import annotations

PAGE_W = 215.9  # 8.5 in
PAGE_H = 139.7  # 5.5 in (half of a US Letter page, landscape)

MARK_SIZE = 7.0
MARK_BIG = 9.0

MARGIN_X = 22.0
ROW_TOP = 26.0
ROW_PITCH = 19.5
BOX_H = 15.0
MAX_ROWS = 5

SPELL_NUM_X = MARGIN_X
SPELL_BOX_X = MARGIN_X + 7.0
SPELL_BOX_W = 74.0

MATH_X = PAGE_W / 2 + 2.0
MATH_RIGHT = PAGE_W - MARGIN_X
MATH_PROMPT_DX = 8.0  # prompt starts this far right of the item number

NUM_GAP = 1.8  # blank space between "7." and whatever follows it

BOX_W = {"int": 18.0, "int_rem": 26.0, "frac": 20.0, "symbol": 14.0, "text": 18.0}
LEAD_W = {"symbol": 33.0}
LEAD_W_DEFAULT = 22.0


def marks() -> list[dict]:
    return [
        {"name": "tl", "cx": 9.0, "cy": 9.0, "size": MARK_SIZE},
        {"name": "tr", "cx": PAGE_W - 9.0, "cy": 9.0, "size": MARK_SIZE},
        {"name": "br", "cx": PAGE_W - 10.0, "cy": PAGE_H - 10.0, "size": MARK_BIG},
        {"name": "bl", "cx": 9.0, "cy": PAGE_H - 9.0, "size": MARK_SIZE},
    ]


def build_manifest(items: list[dict], student: str, on: str, quiz_label: str) -> dict:
    """items: dicts with group ('spelling'|'math'), kind, skill_id, item_key, prompt, lead,
    expected, probe. Returns the manifest, with `items` carrying box geometry."""
    spell = [i for i in items if i["group"] == "spelling"][:MAX_ROWS]
    math = [i for i in items if i["group"] == "math"][:MAX_ROWS]
    out: list[dict] = []
    n = 0
    for row, it in enumerate(spell):
        n += 1
        y = ROW_TOP + row * ROW_PITCH
        out.append(
            {
                "id": f"q{n}",
                "n": n,
                "kind_group": "spelling",
                "kind": "spelling",
                "skill_id": it["skill_id"],
                "item_key": it["item_key"],
                "expected": it["expected"],
                "probe": bool(it.get("probe")),
                "prompt_text": it.get("prompt", it["expected"]),
                "lead_typ": "",
                "num_x": SPELL_NUM_X,
                "num_w": SPELL_BOX_X - SPELL_NUM_X - NUM_GAP,
                "box": {"x": SPELL_BOX_X, "y": y, "w": SPELL_BOX_W, "h": BOX_H},
            }
        )
    for row, it in enumerate(math):
        n += 1
        y = ROW_TOP + row * ROW_PITCH
        kind = it["kind"]
        bw = BOX_W.get(kind, 18.0)
        bx = MATH_RIGHT - bw
        lw = LEAD_W.get(kind, LEAD_W_DEFAULT)
        lx = bx - lw - 1.0
        px = MATH_X + MATH_PROMPT_DX
        pw = max(18.0, lx - px - 1.0)
        out.append(
            {
                "id": f"q{n}",
                "n": n,
                "kind_group": "math",
                "kind": kind,
                "skill_id": it["skill_id"],
                "item_key": it.get("item_key", ""),
                "expected": it["expected"],
                "probe": bool(it.get("probe")),
                "prompt_text": it["prompt"],
                "lead_typ": it["lead"],
                "num_x": MATH_X,
                "num_w": MATH_PROMPT_DX - NUM_GAP,
                "box": {"x": bx, "y": y, "w": bw, "h": BOX_H},
                "prompt_box": {"x": px, "y": y, "w": pw, "h": BOX_H},
                "lead": {"x": lx, "y": y, "w": lw, "h": BOX_H},
            }
        )
    return {
        "version": 1,
        "student": student,
        "date": on,
        "quiz_label": quiz_label,
        "page": {"w": PAGE_W, "h": PAGE_H},
        "marks": marks(),
        "header": {"x": MARGIN_X, "y": 8.0, "w": PAGE_W - 2 * MARGIN_X},
        "cols": {
            "label_y": 19.0,
            "spelling": {"x": SPELL_NUM_X},
            "math": {"x": MATH_X},
        },
        "footer": {"x": MARGIN_X, "y": PAGE_H - 9.0},
        "items": out,
    }
