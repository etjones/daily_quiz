import cv2
import helpers
import numpy as np
import pytest

from dq import answers, grade, layout, render


def _manifest():
    items = [
        {
            "group": "spelling",
            "kind": "spelling",
            "skill_id": "sp.cvc.a",
            "item_key": w,
            "expected": w,
        }
        for w in ["cat", "ship", "jump", "bridge", "the"]
    ] + [
        {
            "group": "math",
            "kind": "int",
            "skill_id": "m.add.within-10",
            "expected": "7",
            "prompt": "$3 + 4$",
            "lead": "$=$",
        },
        {
            "group": "math",
            "kind": "frac",
            "skill_id": "m.frac.name-2-4",
            "expected": "3/4",
            "prompt": "#fracbar(3, 4)",
            "lead": "$=$",
        },
        {
            "group": "math",
            "kind": "symbol",
            "skill_id": "m.num.compare-100",
            "expected": "<",
            "prompt": "#box[$34$] #h(2.2em) #box[$43$]",
            "lead": "Write < or >",
        },
        {
            "group": "math",
            "kind": "int_rem",
            "skill_id": "m.div.remainder",
            "expected": "3 R 2",
            "prompt": "$17 div 5$",
            "lead": "$=$",
        },
        {
            "group": "math",
            "kind": "int",
            "skill_id": "m.mul.x7",
            "expected": "56",
            "prompt": "$7 times 8$",
            "lead": "$=$",
        },
    ]
    return layout.build_manifest(items, "Test", "2026-10-12", "Quiz test")


@pytest.fixture(scope="module")
def page_png(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    m = _manifest()
    data = {
        "student": "Test",
        "date": "2026-10-12",
        "date_pretty": "Mon Oct 12",
        "quiz_label": "Quiz test",
        "manifest": m,
    }
    return m, render.render_png(home, "quiz", data, ppi=helpers.PPI)


WRITTEN = {
    "q1": "cat",
    "q2": "ship",
    "q3": "jup",
    "q4": "",
    "q5": "the",
    "q6": "7",
    "q7": "3/4",
    "q8": "<",
    "q9": "",
    "q10": "56",
}


@pytest.mark.parametrize("rotate", [0, 180, 90])
def test_rectify_and_crop_alignment(page_png, rotate):
    m, png = page_png
    page = helpers.write_answers(png, m, WRITTEN)
    photo = helpers.photograph(page, rotate=rotate, seed=3 + rotate)
    straight, info = grade.rectify(photo, m)
    assert info["ok"], info
    crops = grade.crop_items(straight, m)
    for it in m["items"]:
        blank = grade.is_blank(crops[it["id"]])
        assert blank == (WRITTEN[it["id"]] == ""), (
            it["id"],
            grade.ink_fraction(crops[it["id"]]),
        )


def test_crops_contain_whole_answer(page_png):
    """The ink we drew inside each box must lie inside the crop, not be cut off by it."""
    m, png = page_png
    page = helpers.write_answers(png, m, WRITTEN)
    photo = helpers.photograph(page, seed=11)
    straight, _ = grade.rectify(photo, m)
    gray = cv2.cvtColor(straight, cv2.COLOR_BGR2GRAY)
    for it in m["items"]:
        if not WRITTEN[it["id"]]:
            continue
        b = it["box"]
        ppm = grade.PPM
        # ink in the whole box interior vs ink in the crop region
        full = gray[
            int((b["y"] + 0.6) * ppm) : int((b["y"] + b["h"] - 0.6) * ppm),
            int((b["x"] + 0.6) * ppm) : int((b["x"] + b["w"] - 0.6) * ppm),
        ]
        inner = grade.crop_items(straight, m)[it["id"]]
        gi = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
        assert (gi < 110).sum() >= 0.9 * (full < 110).sum() - 5, it["id"]


class FakeVLM:
    def __init__(self, truth):
        self.truth = truth
        self.calls = []

    def transcribe_box(self, png, kind):
        self.calls.append(kind)
        i = len(self.calls)
        return {
            "text": self.truth[f"q{i}"],
            "blank": False,
            "uncertain": False,
            "confidence": 0.95,
        }


def test_blank_boxes_never_reach_the_model(page_png):
    m, png = page_png
    page = helpers.write_answers(png, m, WRITTEN)
    straight, _ = grade.rectify(helpers.photograph(page, seed=5), m)
    crops = grade.crop_items(straight, m)
    nonblank = [k for k in WRITTEN if WRITTEN[k]]

    class Seq:
        def __init__(self):
            self.n = 0

        def transcribe_box(self, png, kind):
            key = nonblank[self.n]
            self.n += 1
            return {
                "text": WRITTEN[key],
                "blank": False,
                "uncertain": False,
                "confidence": 0.9,
            }

    be = Seq()
    tr = grade.transcribe_all(crops, m, be)
    assert be.n == len(nonblank)
    assert tr["q4"].blank and tr["q9"].blank
    rows = grade.score(m, tr)
    by = {r.item_id: r for r in rows}
    assert by["q1"].correct and by["q2"].correct and by["q5"].correct
    assert not by["q3"].correct and by["q3"].error_cat == "omission"  # jup for jump
    assert by["q4"].error_cat == "blank"
    assert by["q7"].correct and by["q8"].correct and by["q10"].correct
    assert by["q9"].error_cat == "blank"


def test_missing_marks_gives_clear_error():
    blank = np.full((400, 600, 3), 255, np.uint8)
    with pytest.raises(grade.GradeError):
        grade.find_corners(blank)


def test_answers_matching():
    assert answers.match("spelling", "cat", "Cat")
    assert not answers.match("spelling", "I", "i")
    assert answers.match("frac", "1/2", "2 / 4")
    assert answers.match("symbol", "<", "less than")
    assert answers.match("int_rem", "3 R 2", "3r2")
    assert answers.classify_error("spelling", "bed", "ded") == "reversal"
    assert answers.classify_error("spelling", "form", "from") == "transposition"
    assert answers.classify_error("spelling", "lamp", "lap") == "omission"
    assert answers.classify_error("spelling", "bird", "berd") == "vowel_pattern"
    assert answers.classify_error("int", "12", "21") == "transposition"
    assert answers.classify_error("int", "7", "8") == "off_by_one"
    assert answers.classify_error("symbol", "<", ">") == "sign"
