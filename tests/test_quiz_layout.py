import random
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

from dq import generators, layout, render

PPI = 200.0
PX_MM = PPI / 25.4


def _longest_word_problems(n: int) -> list[generators.Problem]:
    rng = random.Random(7)
    ps = [generators.gen_word_addsub(rng, max=20) for _ in range(200)]
    ps += [
        generators.gen_share(rng, [2, 3, 4, 5, 10], [2, 10], mode="mix")
        for _ in range(200)
    ]
    return sorted(ps, key=lambda p: len(p.prompt), reverse=True)[:n]


def _math_item(p: generators.Problem) -> dict:
    return {
        "group": "math",
        "kind": p.kind,
        "skill_id": "m.word",
        "expected": p.answer,
        "prompt": p.prompt,
        "lead": p.lead,
        "prose": p.prose,
    }


def _manifest(problems: list[generators.Problem]) -> dict:
    return layout.build_manifest(
        [_math_item(p) for p in problems], "Test", "2026-10-12", "Quiz test"
    )


def _render(tmp_path: Path, m: dict) -> np.ndarray:
    data = {
        "student": "Test",
        "date": "2026-10-12",
        "date_pretty": "Mon Oct 12",
        "quiz_label": "Quiz test",
        "manifest": m,
    }
    png = render.render_png(tmp_path, "quiz", data, ppi=PPI)
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)


def _px(mm: float) -> int:
    return round(mm * PX_MM)


def test_word_problem_generators_mark_prose() -> None:
    rng = random.Random(1)
    assert generators.gen_word_addsub(rng).prose
    assert generators.gen_share(rng, [2, 5], [2, 5]).prose
    assert not generators.gen_mul(rng, [7], [2, 9]).prose


def test_prose_prompt_gets_more_room_without_moving_the_answer_box() -> None:
    p = _longest_word_problems(1)[0]
    plain = dict(_math_item(p), prose=False)
    prose = _math_item(p)
    a = layout.build_manifest([plain], "T", "2026-10-12", "Q")["items"][0]
    b = layout.build_manifest([prose], "T", "2026-10-12", "Q")["items"][0]
    assert b["box"] == a["box"]
    assert b["prompt_box"]["w"] > a["prompt_box"]["w"]
    assert b["prompt_box"]["h"] > a["prompt_box"]["h"]
    assert b["prompt_box"]["x"] + b["prompt_box"]["w"] < b["lead"]["x"]


def test_prose_prompt_boxes_do_not_overlap_between_rows() -> None:
    m = _manifest(_longest_word_problems(layout.MAX_ROWS))
    boxes = [it["prompt_box"] for it in m["items"]]
    for upper, lower in pairwise(boxes):
        assert upper["y"] + upper["h"] < lower["y"]
    assert boxes[0]["y"] > m["cols"]["label_y"] + 3
    assert boxes[-1]["y"] + boxes[-1]["h"] < m["footer"]["y"]


def test_longest_word_problems_stay_inside_their_prompt_boxes(tmp_path: Path) -> None:
    m = _manifest(_longest_word_problems(layout.MAX_ROWS))
    page = _render(tmp_path, m)
    items = m["items"]
    pb = items[0]["prompt_box"]
    x0, x1 = _px(pb["x"]), _px(pb["x"] + pb["w"])
    inside = np.zeros(page.shape[0], bool)
    for it in items:
        b = it["prompt_box"]
        inside[_px(b["y"]) : _px(b["y"] + b["h"])] = True
    top, bottom = _px(m["cols"]["label_y"] + 4), _px(m["footer"]["y"] - 1)
    rows = [y for y in range(top, bottom) if not inside[y]]
    assert (page[rows, x0:x1] > 200).all(), "prompt text spills above or below its box"
    for it in items:
        b, lead = it["prompt_box"], it["lead"]
        gap = page[
            _px(b["y"]) : _px(b["y"] + b["h"]),
            _px(b["x"] + b["w"]) + 1 : _px(lead["x"]) - 1,
        ]
        assert (gap > 200).all(), f"{it['id']} prompt runs into its lead-in"
