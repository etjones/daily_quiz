"""Test helpers: fake 'handwriting' and fake phone photos of a quiz page."""

from __future__ import annotations

import io
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PPI = 200
PX_MM = PPI / 25.4


def _font(size_px: int):
    for name in (
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size_px)
        except OSError:
            continue
    return ImageFont.load_default(size_px)


def write_answers(
    png: bytes, manifest: dict, answers_by_id: dict[str, str], seed: int = 0
) -> np.ndarray:
    """Draw dark 'handwriting' into the answer boxes of a rendered quiz page. Returns BGR image."""
    rng = random.Random(seed)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    dr = ImageDraw.Draw(im)
    for it in manifest["items"]:
        txt = answers_by_id.get(it["id"], "")
        if not txt:
            continue
        b = it["box"]
        size = int(min(b["h"] * 0.62, 11) * PX_MM)
        f = _font(size)
        x = (b["x"] + 3 + rng.uniform(0, 2)) * PX_MM
        y = (
            b["y"] + (b["h"] - size / PX_MM) / 2 - 1.5 + rng.uniform(-0.8, 0.8)
        ) * PX_MM
        dr.text((x, y), txt, fill=(25, 25, 40), font=f)
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def photograph(
    page_bgr: np.ndarray, rotate: int = 0, seed: int = 1, shadow: bool = True
) -> np.ndarray:
    """Pretend to take a phone photo: perspective skew, optional 90/180 degree rotation, uneven
    lighting, noise, on a darker background."""
    rng = np.random.default_rng(seed)
    h, w = page_bgr.shape[:2]
    if rotate:
        k = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }[rotate]
        page_bgr = cv2.rotate(page_bgr, k)
        h, w = page_bgr.shape[:2]
    pad = int(0.18 * max(h, w))
    W, H = w + 2 * pad, h + 2 * pad
    jitter = lambda s: rng.uniform(-s, s)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32(
        [
            [pad + jitter(0.03 * w), pad + jitter(0.04 * h)],
            [pad + w - jitter(0.03 * w), pad + jitter(0.06 * h)],
            [pad + w - jitter(0.05 * w), pad + h + jitter(0.04 * h)],
            [pad + jitter(0.04 * w), pad + h - jitter(0.04 * h)],
        ]
    )
    M = cv2.getPerspectiveTransform(src, dst)
    canvas = np.full((H, W, 3), (70, 80, 95), np.uint8)
    warped = cv2.warpPerspective(
        page_bgr,
        M,
        (W, H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_TRANSPARENT,
        dst=canvas,
    )
    img = warped.astype(np.float32)
    if shadow:
        yy, xx = np.mgrid[0:H, 0:W]
        grad = 0.78 + 0.22 * (xx / W) + 0.05 * np.sin(yy / 40.0)
        img *= grad[..., None]
    img += rng.normal(0, 3.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)
