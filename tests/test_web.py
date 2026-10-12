import json
from datetime import date, timedelta

import cv2
import helpers
import pytest
from fastapi.testclient import TestClient

from dq import llm, render
from dq.db import DB
from dq.web.app import STUDENT_COOKIE, create_app

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(home=tmp_path, backend="none"))


def add(client, name="Sam"):
    return client.post("/students", data={"name": name, "pace_cap": "2"})


def built(client):
    add(client)
    r = client.post("/day", data={"on": TODAY})
    assert r.status_code == 200 and "Day 1" in r.text
    return r


def open_manifest(tmp_path):
    db = DB(tmp_path / "dq.db")
    q = db.latest_open_quiz(db.student("Sam")["id"])
    return q, json.loads(q["manifest"])


def test_no_student_redirects_to_students_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Add a student" in r.text


def test_add_student_sets_cookie_and_cli_default(client, tmp_path):
    r = add(client)
    assert "Placement" in r.text
    assert client.cookies.get(STUDENT_COOKIE) == "Sam"
    assert (tmp_path / "default_student").read_text().strip() == "Sam"
    assert "Today: Sam" in client.get("/").text


def test_switch_student(client):
    add(client, "Sam")
    add(client, "Ann")
    assert "Today: Ann" in client.get("/").text
    client.post("/students/select", data={"name": "Sam"})
    assert "Today: Sam" in client.get("/").text


def test_unknown_student_is_a_404_page(client):
    r = client.post("/students/select", data={"name": "Nobody"})
    assert r.status_code == 404 and "no student named" in r.text


def test_build_day_and_serve_pdfs(client):
    r = built(client)
    assert f"/files/{TODAY}/worksheet-{TODAY}.pdf" in r.text
    pdf = client.get(f"/files/{TODAY}/worksheet-{TODAY}.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_files_route_refuses_paths_outside_the_student_folder(client, tmp_path):
    built(client)
    (tmp_path / "secret.pdf").write_bytes(b"%PDF")
    assert client.get("/files/../../secret.pdf").status_code == 404
    assert client.get("/files/%2e%2e/%2e%2e/secret.pdf").status_code == 404


def test_oral_entry_review_and_save(client, tmp_path):
    built(client)
    q, m = open_manifest(tmp_path)
    first = m["items"][0]
    form = {f"verdict_{it['id']}": "right" for it in m["items"]}
    form[f"got_{first['id']}"] = first["expected"] + "x"
    r = client.post(f"/quiz/{q['id']}/review", data=form)
    assert r.status_code == 200 and "Save results" in r.text
    save = {"mode": "oral"}
    for it in m["items"]:
        wrong = it["id"] == first["id"]
        save[f"got_{it['id']}"] = it["expected"] + ("x" if wrong else "")
        save[f"verdict_{it['id']}"] = "wrong" if wrong else "right"
    r = client.post(f"/quiz/{q['id']}/save", data=save)
    assert r.status_code == 200 and "Saved:" in r.text
    db = DB(tmp_path / "dq.db")
    rows = db.results_for_quiz(q["id"])
    assert len(rows) == len(m["items"])
    assert [r["correct"] for r in rows] == [0] + [1] * (len(rows) - 1)
    assert client.post(f"/quiz/{q['id']}/save", data=save).status_code == 409
    assert "Graded quizzes" in client.get("/history").text


def test_verdict_overrides_the_automatic_judgement(client, tmp_path):
    built(client)
    q, m = open_manifest(tmp_path)
    save = {"mode": "oral"}
    for it in m["items"]:
        save[f"got_{it['id']}"] = "nonsense"
        save[f"verdict_{it['id']}"] = "right"
    client.post(f"/quiz/{q['id']}/save", data=save)
    rows = DB(tmp_path / "dq.db").results_for_quiz(q["id"])
    assert all(r["correct"] for r in rows)


def test_mood_is_logged(client, tmp_path):
    add(client)
    r = client.post("/mood", data={"on": YESTERDAY, "mood": "hard", "story": "done"})
    assert "Logged hard" in r.text
    db = DB(tmp_path / "dq.db")
    log = db.day_logs(db.student("Sam")["id"])[0]
    assert log["mood"] == "hard" and log["composition_done"] == 1
    assert (
        client.post("/mood", data={"on": YESTERDAY, "mood": "grumpy"}).status_code
        == 400
    )


def test_placement_all_wrong_places_at_the_start(client):
    add(client)
    data = {"tracks": ["phonics", "sight", "math"], "answers": ""}
    r = client.post("/placement", data=data)
    asked = 0
    while "Placement result" not in r.text:
        assert "Right" in r.text
        asked += 1
        data["answers"] += "n"
        r = client.post("/placement", data=data)
    assert asked > 0
    assert "0 / 77" in r.text and "0 / 10" in r.text and "0 / 61" in r.text


def test_placement_undo_and_partial_for_htmx(client):
    add(client)
    data = {"tracks": ["math"], "answers": "", "answer": "y"}
    r = client.post("/placement", data=data, headers={"HX-Request": "true"})
    assert r.text.lstrip().startswith('<section id="placement">')
    assert 'name="answers" value="y"' in r.text
    assert "Undo last answer" in r.text
    r = client.post(
        "/placement", data={"tracks": ["math"], "answers": "yyn", "answer": "x"}
    )
    assert r.status_code == 400


def test_placement_marks_known_math(client, tmp_path):
    add(client)
    data = {"tracks": ["math"], "answers": ""}
    r = client.post("/placement", data=data)
    while "Placement result" not in r.text:
        data["answers"] += "y"
        r = client.post("/placement", data=data)
    db = DB(tmp_path / "dq.db")
    units = db.units(db.student("Sam")["id"])
    assert len([k for k in units if k[0].startswith("m.")]) == 61
    assert not any(k[0].startswith("sp.") for k in units)


def test_report_history_skills_and_sentences_render(client):
    built(client)
    for url in (
        "/report",
        "/report?days=30",
        "/history",
        "/skills",
        "/skills?subject=math",
        "/sentences",
    ):
        r = client.get(url)
        assert r.status_code == 200, url
    pdf = client.post("/report/pdf", data={"days": "14"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_manual_sentence_must_contain_the_word(client, tmp_path):
    add(client)
    assert (
        client.post(
            "/sentences/set", data={"word": "said", "sentence": "Hello."}
        ).status_code
        == 400
    )
    r = client.post("/sentences/set", data={"word": "said", "sentence": "She said hi."})
    assert "Saved a sentence for said" in r.text
    assert DB(tmp_path / "dq.db").sentence("said") == "She said hi."


def test_sentence_fill_without_model_explains(client):
    add(client)
    r = client.post("/sentences/fill", data={"include_phonics": "false"})
    assert r.status_code == 400 and "DQ_BACKEND" in r.text


def _photo(tmp_path, m, q):
    written = {it["id"]: it["expected"] for it in m["items"]}
    data = {
        "student": "Sam",
        "date": q["for_date"],
        "date_pretty": "x",
        "quiz_label": m["quiz_label"],
        "manifest": m,
    }
    png = render.render_png(tmp_path, "quiz", data, ppi=helpers.PPI)
    photo = helpers.photograph(helpers.write_answers(png, m, written), seed=21)
    ok, buf = cv2.imencode(".jpg", photo)
    assert ok
    return buf.tobytes(), written


def test_photo_without_model_falls_back_to_entry_with_crops(client, tmp_path):
    built(client)
    q, m = open_manifest(tmp_path)
    jpg, _ = _photo(tmp_path, m, q)
    r = client.post(
        f"/quiz/{q['id']}/photo", files={"photo": ("q.jpg", jpg, "image/jpeg")}
    )
    assert r.status_code == 200 and "No vision model configured" in r.text
    assert f"/files/{TODAY}/grading/quiz{q['id']}-" in r.text


def test_photo_with_model_goes_to_review(tmp_path, monkeypatch):
    client = TestClient(create_app(home=tmp_path, backend="fake"))
    built(client)
    q, m = open_manifest(tmp_path)
    jpg, written = _photo(tmp_path, m, q)

    texts = [written[it["id"]] for it in m["items"]]

    class Fake:
        def transcribe_box(self, png, kind):
            return {
                "text": texts.pop(0),
                "blank": False,
                "uncertain": False,
                "confidence": 0.9,
            }

    monkeypatch.setattr(
        llm, "backend_from_name", lambda name: Fake() if name == "fake" else None
    )
    r = client.post(
        f"/quiz/{q['id']}/photo", files={"photo": ("q.jpg", jpg, "image/jpeg")}
    )
    assert r.status_code == 200 and "Save results" in r.text
    assert 'name="mode" value="vlm"' in r.text


def test_photo_that_is_not_an_image(client, tmp_path):
    built(client)
    q, _ = open_manifest(tmp_path)
    r = client.post(
        f"/quiz/{q['id']}/photo", files={"photo": ("q.jpg", b"nope", "image/jpeg")}
    )
    assert r.status_code == 400 and "Could not read" in r.text
