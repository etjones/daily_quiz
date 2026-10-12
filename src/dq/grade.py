"""Photo of a quiz -> per-box crops -> transcription -> deterministic scoring.

Pipeline
  1. find the four black registration squares and straighten the page (homography)
  2. crop each answer box using the quiz manifest's own coordinates
  3. decide blank/not-blank from the pixels (no model needed)
  4. ask a VLM (optional) to transcribe each non-blank box LITERALLY
  5. judge correctness with answers.match(). The model never decides what is right.

Why per-box and literal: a VLM asked "is this right?" or shown a whole page tends to read
what the child meant. Spelling errors are exactly what we want to catch.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import cv2
import numpy as np

from . import answers

PPM = 8  # pixels per millimetre in the straightened page
INSET_MM = 1.3  # crop inside the box border
INK_GRAY = 130  # pixels darker than this count as ink (guide lines are lighter)
BLANK_FRACTION = 0.003


class GradeError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# registration marks
# --------------------------------------------------------------------------


def _binarize(gray: np.ndarray) -> np.ndarray:
    """Dark things -> 255. Divide out the paper's lighting first so shadows on a phone photo
    do not matter, then Otsu."""
    h, w = gray.shape
    k = max(31, (min(h, w) // 8) | 1)
    bg = cv2.medianBlur(gray, k)
    norm = cv2.divide(gray, bg, scale=255)
    norm = cv2.GaussianBlur(norm, (3, 3), 0)
    _, bw = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def detect_marks(img_bgr: np.ndarray) -> list[tuple[float, float, float]]:
    """Return (cx, cy, area) for solid dark squares, largest first."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    bw = _binarize(gray)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    img_area = float(h * w)
    out = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 6 or ch < 6:
            continue
        aspect = cw / float(ch)
        if not 0.7 <= aspect <= 1.43:
            continue
        frac = cw * ch / img_area
        if not 0.0002 <= frac <= 0.012:
            continue
        fill = cv2.countNonZero(bw[y : y + ch, x : x + cw]) / float(cw * ch)
        if fill < 0.82:  # outlines and text are far less filled than a solid square
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        out.append(
            (m["m10"] / m["m00"], m["m01"] / m["m00"], float(cv2.contourArea(c)))
        )
    out.sort(key=lambda t: -t[2])
    return out


def _order_corners(pts: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    """Order four marks as TL, TR, BR, BL. BR is the largest mark, which also fixes rotation."""
    areas = [p[2] for p in pts]
    br_i = int(np.argmax(areas))
    others = [i for i in range(4) if i != br_i]
    if areas[br_i] < 1.25 * np.mean([areas[i] for i in others]):
        raise GradeError(
            "cannot tell which corner mark is the large one (bottom right); retake the photo "
            "with the whole page in view"
        )
    br = np.array(pts[br_i][:2])
    # TL is the farthest from BR
    far_i = max(others, key=lambda i: np.linalg.norm(np.array(pts[i][:2]) - br))
    tl = np.array(pts[far_i][:2])
    rest = [i for i in others if i != far_i]
    v = tl - br

    def cross(p):
        a = np.array(p[:2]) - br
        return v[0] * a[1] - v[1] * a[0]

    # TR has positive cross product (see layout: TL, TR, BR, BL run clockwise on screen)
    a, b = rest
    tr_i, bl_i = (a, b) if cross(pts[a]) > cross(pts[b]) else (b, a)
    return [tuple(tl), tuple(pts[tr_i][:2]), tuple(br), tuple(pts[bl_i][:2])]


def find_corners(img_bgr: np.ndarray) -> list[tuple[float, float]]:
    cands = detect_marks(img_bgr)[:7]
    if len(cands) < 4:
        raise GradeError(
            f"found only {len(cands)} of 4 corner marks; make sure all four black squares are "
            "visible and the page is flat and well lit"
        )
    best, best_area = None, -1.0
    for combo in itertools.combinations(cands, 4):
        hull = cv2.convexHull(np.array([[p[0], p[1]] for p in combo], dtype=np.float32))
        area = cv2.contourArea(hull)
        if len(hull) == 4 and area > best_area:
            best, best_area = combo, area
    if best is None:
        raise GradeError("corner marks do not form a rectangle; retake the photo")
    return _order_corners(list(best))


def rectify(
    img_bgr: np.ndarray, manifest: dict, ppm: int = PPM
) -> tuple[np.ndarray, dict]:
    """Straighten the page so that 1 mm = ppm pixels and the origin is the page's top-left."""
    corners = find_corners(img_bgr)
    names = ["tl", "tr", "br", "bl"]
    mk = {m["name"]: m for m in manifest["marks"]}
    dst = np.array(
        [[mk[n]["cx"] * ppm, mk[n]["cy"] * ppm] for n in names], dtype=np.float32
    )
    src = np.array(corners, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    W, H = round(manifest["page"]["w"] * ppm), round(manifest["page"]["h"] * ppm)
    page = cv2.warpPerspective(
        img_bgr, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
    )
    # self-check: the marks must now be where the manifest says, and solid black
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    fills = []
    for n in names:
        m = mk[n]
        s = m["size"] * 0.7 * ppm
        x0, y0 = int(m["cx"] * ppm - s / 2), int(m["cy"] * ppm - s / 2)
        patch = gray[y0 : int(y0 + s), x0 : int(x0 + s)]
        fills.append(float((patch < 110).mean()) if patch.size else 0.0)
    info = {"mark_fill": fills, "ok": min(fills) > 0.8}
    return page, info


def crop_items(
    page: np.ndarray, manifest: dict, ppm: int = PPM, inset_mm: float = INSET_MM
) -> dict[str, np.ndarray]:
    crops = {}
    H, W = page.shape[:2]
    for it in manifest["items"]:
        b = it["box"]
        x0 = int((b["x"] + inset_mm) * ppm)
        y0 = int((b["y"] + inset_mm) * ppm)
        x1 = int((b["x"] + b["w"] - inset_mm) * ppm)
        y1 = int((b["y"] + b["h"] - inset_mm) * ppm)
        crops[it["id"]] = page[max(0, y0) : min(H, y1), max(0, x0) : min(W, x1)].copy()
    return crops


def ink_fraction(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    # normalise for lighting, then count clearly dark pixels
    bg = cv2.medianBlur(gray, 31 if min(gray.shape) > 31 else 3)
    norm = cv2.divide(gray, bg, scale=255)
    return float((norm < 150).mean())


def is_blank(crop: np.ndarray) -> bool:
    return ink_fraction(crop) < BLANK_FRACTION


def png_bytes(crop: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise GradeError("could not encode crop")
    return buf.tobytes()


# --------------------------------------------------------------------------
# transcription and scoring
# --------------------------------------------------------------------------


@dataclass
class Transcription:
    text: str = ""
    blank: bool = False
    uncertain: bool = False
    confidence: float = 1.0
    source: str = "vlm"


def transcribe_all(
    crops: dict[str, np.ndarray], manifest: dict, backend
) -> dict[str, Transcription]:
    """backend needs `.transcribe_box(png_bytes, kind) -> dict`. Blank boxes are decided from pixels."""
    out: dict[str, Transcription] = {}
    for it in manifest["items"]:
        crop = crops[it["id"]]
        if is_blank(crop):
            out[it["id"]] = Transcription(
                text="", blank=True, confidence=1.0, source="pixels"
            )
            continue
        r = backend.transcribe_box(png_bytes(crop), it["kind"])
        out[it["id"]] = Transcription(
            text=r["text"],
            blank=bool(r.get("blank")),
            uncertain=bool(r.get("uncertain")),
            confidence=float(r.get("confidence", 0.0)),
        )
        if out[it["id"]].blank:
            # the model says blank but pixels show ink: keep the ink, flag it
            out[it["id"]].uncertain = True
    return out


@dataclass
class Scored:
    item_id: str
    n: int
    skill_id: str
    item_key: str
    kind: str
    prompt: str
    expected: str
    got: str
    correct: bool
    error_cat: str | None
    probe: bool
    needs_review: bool
    reason: str = ""

    def to_row(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "item_key": self.item_key,
            "kind": self.kind,
            "prompt": self.prompt,
            "expected": self.expected,
            "got": self.got,
            "correct": self.correct,
            "error_cat": self.error_cat,
            "probe": self.probe,
        }


def score(manifest: dict, got_by_id: dict[str, Transcription | str]) -> list[Scored]:
    rows: list[Scored] = []
    for it in manifest["items"]:
        g = got_by_id.get(it["id"], "")
        t = (
            g
            if isinstance(g, Transcription)
            else Transcription(text=str(g), source="manual")
        )
        kind = it["kind"]
        ok = answers.match(kind, it["expected"], t.text)
        cat = None if ok else answers.classify_error(kind, it["expected"], t.text)
        # flag for a human glance: model unsure, or a wrong answer that looks like a mirrored/ambiguous glyph
        review = False
        reason = ""
        if t.source == "vlm":
            if t.uncertain:
                review, reason = True, "model unsure what was written"
            elif t.confidence < 0.6:
                review, reason = True, "low confidence"
            elif not ok and cat in ("reversal", "transposition"):
                review, reason = True, f"looks like a {cat}: check the handwriting"
        rows.append(
            Scored(
                item_id=it["id"],
                n=it["n"],
                skill_id=it["skill_id"],
                item_key=it.get("item_key", ""),
                kind=kind,
                prompt=it["prompt_text"],
                expected=it["expected"],
                got=t.text,
                correct=ok,
                error_cat=cat,
                probe=bool(it.get("probe")),
                needs_review=review,
                reason=reason,
            )
        )
    return rows


def apply_override(
    row: Scored, correct: bool | None = None, got: str | None = None
) -> Scored:
    """Parent correction: flip the verdict and/or fix the transcription."""
    if got is not None:
        row.got = got
        row.correct = answers.match(row.kind, row.expected, got)
        row.error_cat = (
            None if row.correct else answers.classify_error(row.kind, row.expected, got)
        )
    if correct is not None:
        row.correct = correct
        row.error_cat = (
            None
            if correct
            else (
                row.error_cat
                or answers.classify_error(row.kind, row.expected, row.got)
                or "other"
            )
        )
    row.needs_review = False
    return row
