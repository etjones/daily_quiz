import builtins
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import cv2
import helpers
import pytest

from dq import cli, llm, render
from dq.db import DB

D1 = "2026-10-11"
D2 = "2026-10-12"
D3 = "2026-10-13"


def run(monkeypatch, tmp_path, argv, inputs=None, capsys=None):
    if inputs is not None:
        it = iter(inputs)
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(it, ""))
    code = cli.main(["--home", str(tmp_path)] + argv)
    out = capsys.readouterr().out if capsys else ""
    return code, out


def test_full_loop_by_oral_entry(monkeypatch, tmp_path, capsys):
    assert (
        run(
            monkeypatch,
            tmp_path,
            ["init", "Sam", "--date", "2026-10-10"],
            capsys=capsys,
        )[0]
        == 0
    )
    code, out = run(monkeypatch, tmp_path, ["next", "Sam", "--date", D1], capsys=capsys)
    assert code == 0 and "Built day 1" in out
    # grade tomorrow's quiz: all right except one typed wrong attempt for the first word
    code, out = run(
        monkeypatch,
        tmp_path,
        ["oral", "Sam", "--date", D2],
        inputs=["cut"] + [""] * 12,
        capsys=capsys,
    )
    assert code == 0 and "Saved." in out
    assert "To practise tonight: cat" in out
    code, out = run(
        monkeypatch,
        tmp_path,
        ["mood", "Sam", "ok", "--date", D1, "--story", "done"],
        capsys=capsys,
    )
    assert code == 0
    code, out = run(monkeypatch, tmp_path, ["next", "Sam", "--date", D2], capsys=capsys)
    assert code == 0 and "Built day 2" in out
    # the missed word is back on tonight's sheet, and the worksheet says what was tricky
    db = DB(tmp_path / "dq.db")
    plan = json.loads(db.plan_for(db.student("Sam")["id"], D2)["data"])
    assert plan["worksheet"]["reteach"]  # tonight's sheet explains the tricky pattern
    # the missed word itself is due the next day and leads that day's review
    assert db.units(db.student("Sam")["id"])[("sp.cvc.a", "cat")].due_on == D3
    run(
        monkeypatch,
        tmp_path,
        ["mood", "Sam", "ok", "--date", D2, "--story", "done"],
        capsys=capsys,
    )
    run(monkeypatch, tmp_path, ["next", "Sam", "--date", D3], inputs=[], capsys=capsys)
    plan3 = json.loads(db.plan_for(db.student("Sam")["id"], D3)["data"])
    assert "cat" in [w["word"] for w in plan3["worksheet"]["words"]]
    code, out = run(
        monkeypatch, tmp_path, ["status", "Sam", "--date", D2], capsys=capsys
    )
    assert "open quiz" in out
    code, out = run(
        monkeypatch,
        tmp_path,
        ["report", "Sam", "--date", D3, "--pdf", "--json"],
        capsys=capsys,
    )
    assert code == 0 and "What is shaky?" in out
    assert (tmp_path / "out" / "Sam" / f"report-{D3}.pdf").exists()


def test_unknown_student_is_a_clear_message(monkeypatch, tmp_path, capsys):
    code, out = run(
        monkeypatch, tmp_path, ["next", "Nobody", "--date", D1], capsys=capsys
    )
    assert code == 1 and "dq init" in out


class FakeBackend:
    """Reads boxes in order from a list of texts, one per non-blank box."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.kinds = []

    def transcribe_box(self, png, kind):
        self.kinds.append(kind)
        return {
            "text": self.texts.pop(0),
            "blank": False,
            "uncertain": False,
            "confidence": 0.9,
        }


def test_grade_a_photo(monkeypatch, tmp_path, capsys):
    run(monkeypatch, tmp_path, ["init", "Sam", "--date", "2026-10-10"], capsys=capsys)
    run(monkeypatch, tmp_path, ["next", "Sam", "--date", D1], capsys=capsys)
    db = DB(tmp_path / "dq.db")
    q = db.latest_open_quiz(db.student("Sam")["id"])
    manifest = json.loads(q["manifest"])
    # the child gets everything right except leaves the last box blank
    written = {it["id"]: it["expected"] for it in manifest["items"]}
    blank_id = manifest["items"][-1]["id"]
    written[blank_id] = ""
    data = {
        "student": "Sam",
        "date": D2,
        "date_pretty": "x",
        "quiz_label": manifest["quiz_label"],
        "manifest": manifest,
    }
    png = render.render_png(tmp_path, "quiz", data, ppi=helpers.PPI)
    photo = helpers.photograph(helpers.write_answers(png, manifest, written), seed=21)
    path = tmp_path / "photo.jpg"
    cv2.imwrite(str(path), photo)
    fake = FakeBackend(
        [written[i["id"]] for i in manifest["items"] if written[i["id"]]]
    )
    monkeypatch.setattr(
        llm, "backend_from_name", lambda name: fake if name == "fake" else None
    )
    code, out = run(
        monkeypatch,
        tmp_path,
        ["grade", "Sam", str(path), "--backend", "fake", "--yes", "--date", D2],
        capsys=capsys,
    )
    assert code == 0 and "Saved." in out
    rows = db.conn.execute(
        "SELECT expected, got, correct, error_cat FROM result"
    ).fetchall()
    assert len(rows) == len(manifest["items"])
    assert rows[-1]["error_cat"] == "blank" and rows[-1]["correct"] == 0
    assert all(r["correct"] for r in rows[:-1])
    assert (
        len(fake.kinds) == len(manifest["items"]) - 1
    )  # the blank box never went to the model


def test_grade_with_unreadable_page(monkeypatch, tmp_path, capsys):
    run(monkeypatch, tmp_path, ["init", "Sam", "--date", "2026-10-10"], capsys=capsys)
    run(monkeypatch, tmp_path, ["next", "Sam", "--date", D1], capsys=capsys)
    path = tmp_path / "bad.jpg"
    cv2.imwrite(str(path), 255 * __import__("numpy").ones((300, 400, 3), "uint8"))
    code, out = run(
        monkeypatch, tmp_path, ["grade", "Sam", str(path), "--date", D2], capsys=capsys
    )
    assert code == 1 and "dq oral" in out


# --- the OpenAI-compatible client, against a local fake server ---------------------------


class Handler(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.seen.append(body)
        text = body["messages"][0]["content"]
        if isinstance(text, list):  # vision request
            content = json.dumps(
                {"text": "cat", "blank": False, "uncertain": False, "confidence": 0.93}
            )
        elif "dictation sentence" in text.lower() or "dictation" in text.lower():
            content = json.dumps({"word": "jump", "sentence": "I can jump high."})
        else:
            content = "A short note."
        payload = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Sure! " + content if "{" in content else content
                        }
                    }
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    Handler.seen.clear()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_vlm_client_sends_image_and_parses_json(server):
    be = llm.OpenAICompat(base_url=server, model="test-vlm")
    png = cv2.imencode(".png", 255 * __import__("numpy").ones((20, 60, 3), "uint8"))[
        1
    ].tobytes()
    out = be.transcribe_box(png, "spelling")
    assert out == {
        "text": "cat",
        "blank": False,
        "uncertain": False,
        "confidence": 0.93,
    }
    req = Handler.seen[0]
    parts = req["messages"][0]["content"]
    assert any(
        p["type"] == "image_url"
        and p["image_url"]["url"].startswith("data:image/png;base64,")
        for p in parts
    )
    assert (
        "Do NOT correct spelling" in parts[0]["text"] and "spelling" in parts[0]["text"]
    )
    assert req["temperature"] == 0


def test_sentence_and_narrative_clients(server):
    be = llm.OpenAICompat(base_url=server, model="m")
    assert be.dictation_sentence("jump") == "I can jump high."
    with pytest.raises(ValueError):
        be.dictation_sentence("elephant")  # the sentence must contain the word
    assert be.narrate({"x": 1}) == "A short note."
