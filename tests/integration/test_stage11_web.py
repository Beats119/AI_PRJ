"""Stage 11 web UI tests (FastAPI TestClient; no live server needed).

Key acceptance: a UI evaluation and a direct workflow evaluation of the
same submission produce the SAME grade — the UI is a front door, not a
second grader.
"""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from autograder.config.loader import load_models_config, load_rules
from autograder.web.app import create_app
from autograder.workflow import evaluate_submission

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "examples" / "submissions"


@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    base = tmp_path_factory.mktemp("ui")
    app = create_app(
        rules_path=ROOT / "configs" / "example_rules.yaml",
        models_path=ROOT / "configs" / "models.yaml",
        cache_dir=base / "cache",
        assignments_dir=ROOT / "examples" / "assignments",
        reports_dir=base / "reports",
        corpus_dir=SUB,
    )
    return TestClient(app), base


def test_home_has_evaluate_form(ui):
    client, _ = ui
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Evaluate a submission" in resp.text
    assert "add_two_integers" in resp.text


def test_ui_grade_matches_workflow_grade(ui):
    client, base = ui
    code = (SUB / "correct.c").read_bytes()
    resp = client.post(
        "/evaluate",
        data={"assignment": "add_two_integers"},
        files={"file": ("correct.c", code, "text/x-c")},
    )
    assert resp.status_code == 200  # redirect followed to the report page
    assert "complete" in resp.text

    # Parity is judged on IDENTICAL inputs: the workflow evaluates the very
    # file the UI stored. (Evaluating examples/submissions/correct.c itself
    # would self-exclude it from the corpus by path; the uploaded copy is a
    # different path whose byte-identical corpus twin legitimately flags —
    # both front doors must agree on whichever input they are given.)
    uploaded = base / "reports" / "uploads" / "correct.c"
    assert uploaded.exists()
    direct = evaluate_submission(
        uploaded,
        assignment_dir=ROOT / "examples" / "assignments" / "add_two_integers",
        loaded_rules=load_rules(ROOT / "configs" / "example_rules.yaml"),
        models=load_models_config(ROOT / "configs" / "models.yaml"),
        cache_dir=base / "cache",
        corpus_dir=SUB,
    )
    api = client.get("/reports/correct.json")
    assert api.status_code == 200
    assert api.json()["overall_grade"] == str(direct.overall_grade)
    txt = client.get("/reports/correct.txt")
    assert txt.status_code == 200 and "AutoGrader evaluation report" in txt.text


def test_assignments_and_doctor_pages(ui):
    client, _ = ui
    resp = client.get("/assignments")
    assert resp.status_code == 200 and "add_two_integers" in resp.text
    resp = client.get("/doctor")
    assert resp.status_code == 200 and "gcc" in resp.text


def test_unknown_assignment_and_missing_report(ui):
    client, _ = ui
    resp = client.post(
        "/evaluate", data={"assignment": "nope"},
        files={"file": ("x.c", b"int main(void){return 0;}", "text/x-c")},
    )
    assert resp.status_code == 400
    assert client.get("/reports/ghost").status_code == 404
