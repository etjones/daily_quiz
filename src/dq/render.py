"""Typst rendering. Templates live in templates/; data goes in as one JSON file.

Typst can only read files under its project root, so each render copies the
templates and the JSON into a work directory and compiles from there.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typst


def templates_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _prepare(home: Path, template: str, data: dict, tag: str) -> tuple[Path, str]:
    work = home / "work"
    (work / "templates").mkdir(parents=True, exist_ok=True)
    (work / "data").mkdir(parents=True, exist_ok=True)
    for f in templates_dir().glob("*.typ"):
        shutil.copyfile(f, work / "templates" / f.name)
    data_name = f"{tag}.json"
    (work / "data" / data_name).write_text(json.dumps(data, indent=1))
    return work, f"/data/{data_name}"


def render_pdf(
    home: Path, template: str, data: dict, out: Path, tag: str | None = None
) -> Path:
    tag = tag or out.stem
    work, data_path = _prepare(home, template, data, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    typst.compile(
        str(work / "templates" / f"{template}.typ"),
        output=str(out),
        root=str(work),
        sys_inputs={"data": data_path},
    )
    return out


def render_png(
    home: Path, template: str, data: dict, ppi: float = 150.0, tag: str = "png"
) -> bytes:
    """Render a single-page template to PNG bytes (used by tests and by the grader's self-check)."""
    work, data_path = _prepare(home, template, data, tag)
    out = typst.compile(
        str(work / "templates" / f"{template}.typ"),
        root=str(work),
        sys_inputs={"data": data_path},
        format="png",
        ppi=ppi,
    )
    return out[0] if isinstance(out, list) else out


def page_count(pdf: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)
