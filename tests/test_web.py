import json
from datetime import date, timedelta

import cv2
import helpers
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from dq import llm, render
from dq.db import DB
from dq.web.views import STUDENT_COOKIE

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def home(settings, tmp_path):
    settings.DQ_HOME = tmp_path
    return tmp_path


@pytest.fixture
def web(db, home, django_user_model) -> Client:
    user = django_user_model.objects.create_user("parent", password="pw-for-tests-only")
    c = Client()
    c.force_login(user)
    return c


def get(c: Client, url: str, **kw):
    return c.get(url, follow=True, **kw)


def post(c: Client, url: str, data: dict | None = None, **kw):
    return c.post(url, data or {}, follow=True, **kw)


def text(r) -> str:
    return r.content.decode()


def add(c, name="Sam"):
    return post(c, "/students", {"name": name, "pace_cap": "2"})


def built(c):
    add(c)
    r = post(c, "/day", {"on": TODAY})
    assert r.status_code == 200 and "Day 1" in text(r)
    return r


def open_manifest(home):
    db = DB(home / "dq.db")
    q = db.latest_open_quiz(db.student("Sam")["id"])
    return q, json.loads(q["manifest"])


# --------------------------------------------------------------------------- auth


def test_health_needs_no_login(db, home):
    r = Client().get("/health")
    assert r.status_code == 200 and r.content == b"ok"


@pytest.mark.parametrize(
    "url", ["/", "/students", "/quiz", "/history", "/report", "/files/x.pdf"]
)
def test_pages_need_login(db, home, url):
    r = Client().get(url)
    assert r.status_code == 302 and r["Location"].startswith("/login")


def test_login_and_logout(db, home, django_user_model):
    django_user_model.objects.create_user("parent", password="correct-horse")
    c = Client()
    r = c.post("/login", {"username": "parent", "password": "wrong"})
    assert r.status_code == 200 and "didn't match" in text(r)
    r = c.post(
        "/login", {"username": "parent", "password": "correct-horse", "next": "/skills"}
    )
    assert r.status_code == 302 and r["Location"] == "/skills"
    assert get(c, "/skills").status_code == 200
    c.post("/logout")
    assert c.get("/skills").status_code == 302


def test_session_lasts_thirty_days_and_renews(settings):
    assert settings.SESSION_COOKIE_AGE == 30 * 24 * 3600
    assert settings.SESSION_SAVE_EVERY_REQUEST


def test_posts_require_csrf_token(db, home, django_user_model):
    user = django_user_model.objects.create_user("parent", password="pw-for-tests-only")
    c = Client(enforce_csrf_checks=True)
    c.force_login(user)
    assert c.post("/students", {"name": "Sam"}).status_code == 403
    token = c.get("/students").cookies["csrftoken"].value
    r = c.post("/students", {"name": "Sam", "csrfmiddlewaretoken": token})
    assert r.status_code == 302


# --------------------------------------------------------------------------- students


def test_no_student_redirects_to_students_page(web):
    assert "Add a student" in text(get(web, "/"))


def test_add_student_sets_cookie_and_cli_default(web, home):
    assert "Placement" in text(add(web))
    assert web.cookies[STUDENT_COOKIE].value == "Sam"
    assert (home / "default_student").read_text().strip() == "Sam"
    assert "Today: Sam" in text(get(web, "/"))


def test_switch_student(web):
    add(web, "Sam")
    add(web, "Ann")
    assert "Today: Ann" in text(get(web, "/"))
    post(web, "/students/select", {"name": "Sam"})
    assert "Today: Sam" in text(get(web, "/"))


def test_unknown_student_is_a_404_page(web):
    r = post(web, "/students/select", {"name": "Nobody"})
    assert r.status_code == 404 and "no student named" in text(r)


def test_bad_student_name_is_rejected(web):
    assert post(web, "/students", {"name": "../x"}).status_code == 400


# --------------------------------------------------------------------------- days and files


def test_build_day_and_serve_pdfs(web):
    r = built(web)
    assert f"/files/{TODAY}/worksheet-{TODAY}.pdf" in text(r)
    pdf = web.get(f"/files/{TODAY}/worksheet-{TODAY}.pdf")
    assert pdf.status_code == 200
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


def test_files_route_refuses_paths_outside_the_student_folder(web, home):
    built(web)
    (home / "secret.pdf").write_bytes(b"%PDF")
    assert web.get("/files/../../secret.pdf").status_code == 404
    assert web.get("/files/%2e%2e/%2e%2e/secret.pdf").status_code == 404


def test_bad_date_is_a_400(web):
    add(web)
    assert post(web, "/day", {"on": "tomorrow"}).status_code == 400


# --------------------------------------------------------------------------- quizzes


def test_oral_entry_review_and_save(web, home):
    built(web)
    q, m = open_manifest(home)
    first = m["items"][0]
    form = {f"verdict_{it['id']}": "right" for it in m["items"]}
    form[f"got_{first['id']}"] = first["expected"] + "x"
    r = post(web, f"/quiz/{q['id']}/review", form)
    assert r.status_code == 200 and "Save results" in text(r)
    save = {"mode": "oral"}
    for it in m["items"]:
        wrong = it["id"] == first["id"]
        save[f"got_{it['id']}"] = it["expected"] + ("x" if wrong else "")
        save[f"verdict_{it['id']}"] = "wrong" if wrong else "right"
    r = post(web, f"/quiz/{q['id']}/save", save)
    assert r.status_code == 200 and "Saved:" in text(r)
    rows = DB(home / "dq.db").results_for_quiz(q["id"])
    assert len(rows) == len(m["items"])
    assert [r["correct"] for r in rows] == [0] + [1] * (len(rows) - 1)
    assert post(web, f"/quiz/{q['id']}/save", save).status_code == 409
    assert "Graded quizzes" in text(get(web, "/history"))


def test_verdict_overrides_the_automatic_judgement(web, home):
    built(web)
    q, m = open_manifest(home)
    save = {"mode": "oral"}
    for it in m["items"]:
        save[f"got_{it['id']}"] = "nonsense"
        save[f"verdict_{it['id']}"] = "right"
    post(web, f"/quiz/{q['id']}/save", save)
    rows = DB(home / "dq.db").results_for_quiz(q["id"])
    assert all(r["correct"] for r in rows)


def test_mood_is_logged(web, home):
    add(web)
    r = post(web, "/mood", {"on": YESTERDAY, "mood": "hard", "story": "done"})
    assert "Logged hard" in text(r)
    db = DB(home / "dq.db")
    log = db.day_logs(db.student("Sam")["id"])[0]
    assert log["mood"] == "hard" and log["composition_done"] == 1
    assert post(web, "/mood", {"on": YESTERDAY, "mood": "grumpy"}).status_code == 400


# --------------------------------------------------------------------------- placement


def test_placement_all_wrong_places_at_the_start(web):
    add(web)
    data = {"tracks": ["phonics", "sight", "math"], "answers": ""}
    r = post(web, "/placement", data)
    asked = 0
    while "Placement result" not in text(r):
        assert "Right" in text(r)
        asked += 1
        data["answers"] += "n"
        r = post(web, "/placement", data)
    assert asked > 0
    assert "0 / 77" in text(r) and "0 / 10" in text(r) and "0 / 61" in text(r)


def test_placement_undo_and_partial_for_htmx(web):
    add(web)
    data = {"tracks": ["math"], "answers": "", "answer": "y"}
    r = post(web, "/placement", data, headers={"HX-Request": "true"})
    assert text(r).lstrip().startswith('<section id="placement">')
    assert 'name="answers" value="y"' in text(r)
    assert "Undo last answer" in text(r)
    bad = {"tracks": ["math"], "answers": "yyn", "answer": "x"}
    assert post(web, "/placement", bad).status_code == 400


def test_placement_marks_known_math(web, home):
    add(web)
    data = {"tracks": ["math"], "answers": ""}
    r = post(web, "/placement", data)
    while "Placement result" not in text(r):
        data["answers"] += "y"
        r = post(web, "/placement", data)
    db = DB(home / "dq.db")
    units = db.units(db.student("Sam")["id"])
    assert len([k for k in units if k[0].startswith("m.")]) == 61
    assert not any(k[0].startswith("sp.") for k in units)


# --------------------------------------------------------------------------- progress and sentences


def test_report_history_skills_and_sentences_render(web):
    built(web)
    urls = (
        "/report",
        "/report?days=30",
        "/history",
        "/skills",
        "/skills?subject=math",
        "/sentences",
    )
    for url in urls:
        assert get(web, url).status_code == 200, url
    pdf = post(web, "/report/pdf", {"days": "14"})
    assert pdf.status_code == 200
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


def test_manual_sentence_must_contain_the_word(web, home):
    add(web)
    bad = {"word": "said", "sentence": "Hello."}
    assert post(web, "/sentences/set", bad).status_code == 400
    r = post(web, "/sentences/set", {"word": "said", "sentence": "She said hi."})
    assert "Saved a sentence for said" in text(r)
    assert DB(home / "dq.db").sentence("said") == "She said hi."


def test_sentence_fill_without_model_explains(web):
    add(web)
    r = post(web, "/sentences/fill", {"include_phonics": "false"})
    assert r.status_code == 400 and "DQ_BACKEND" in text(r)


# --------------------------------------------------------------------------- photo grading


def _photo(home, m, q):
    written = {it["id"]: it["expected"] for it in m["items"]}
    data = {
        "student": "Sam",
        "date": q["for_date"],
        "date_pretty": "x",
        "quiz_label": m["quiz_label"],
        "manifest": m,
    }
    png = render.render_png(home, "quiz", data, ppi=helpers.PPI)
    photo = helpers.photograph(helpers.write_answers(png, m, written), seed=21)
    ok, buf = cv2.imencode(".jpg", photo)
    assert ok
    return SimpleUploadedFile("q.jpg", buf.tobytes(), "image/jpeg"), written


def test_photo_without_model_falls_back_to_entry_with_crops(web, home):
    built(web)
    q, m = open_manifest(home)
    upload, _ = _photo(home, m, q)
    r = post(web, f"/quiz/{q['id']}/photo", {"photo": upload})
    assert r.status_code == 200 and "No vision model configured" in text(r)
    assert f"/files/{TODAY}/grading/quiz{q['id']}-" in text(r)


def test_photo_with_model_goes_to_review(web, home, settings, monkeypatch):
    settings.DQ_BACKEND = "fake"
    built(web)
    q, m = open_manifest(home)
    upload, written = _photo(home, m, q)
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
    r = post(web, f"/quiz/{q['id']}/photo", {"photo": upload})
    assert r.status_code == 200 and "Save results" in text(r)
    assert 'name="mode" value="vlm"' in text(r)


def test_photo_that_is_not_an_image(web, home):
    built(web)
    q, _ = open_manifest(home)
    bad = SimpleUploadedFile("q.jpg", b"nope", "image/jpeg")
    r = post(web, f"/quiz/{q['id']}/photo", {"photo": bad})
    assert r.status_code == 400 and "Could not read" in text(r)
