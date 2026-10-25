"""V2 API journey (prompt §10/§13): assignment -> version -> activate ->
batch -> evaluate -> results -> investigation -> report -> similarity
disposition, with the grade provably untouched by the disposition."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from autograder.api.app import create_api_app

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "examples" / "submissions"


@pytest.fixture()
def client(tmp_path):
    app = create_api_app(
        data_dir=tmp_path / "data",
        db_url=f"sqlite:///{tmp_path}/api.db",
        models_path=ROOT / "configs" / "models.yaml",
    )
    return TestClient(app)


def _payload() -> dict:
    rules = yaml.safe_load((ROOT / "configs/example_rules.yaml").read_text())
    tests = yaml.safe_load(
        (ROOT / "examples/assignments/add_two_integers/tests.yaml").read_text()
    )
    return {
        "problem": "Read two integers and print their sum.",
        "input": "Two integers on one line separated by whitespace.",
        "output": "The mathematically correct sum followed by a newline.",
        "constraints": ["Operands are signed 32-bit integers."],
        "examples": tests["tests"],
        "rules": rules,
    }


def _active_version(client) -> int:
    r = client.post("/api/assignments", json={"name": "Add two integers"})
    assert r.status_code == 201
    aid = r.json()["id"]
    r = client.post(f"/api/assignments/{aid}/versions", json=_payload())
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "validated"
    assert v["sufficiency"]["sufficient"] is True
    assert len([t for t in v["suite"] if t["trust_status"] == "trusted"]) == 24
    r = client.post(f"/api/assignments/{aid}/versions/{v['id']}/activate")
    assert r.status_code == 200 and r.json()["status"] == "active"
    return v["id"]


def test_health_and_dependencies(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    deps = client.get("/api/health/dependencies").json()
    assert deps["sandbox"]["docker_available"] is False  # honest on this box
    assert deps["sandbox"]["selected_backend"] == "process"
    assert "gcc" in deps and "13" in deps["gcc"]


def test_validate_rules_reports_problems(client):
    bad = client.post(
        "/api/assignments/validate-rules", json={"rules": {"metrics": []}}
    ).json()
    assert bad["valid"] is False and bad["problems"]
    good_rules = yaml.safe_load((ROOT / "configs/example_rules.yaml").read_text())
    good = client.post(
        "/api/assignments/validate-rules", json={"rules": good_rules}
    ).json()
    assert good["valid"] is True and good["rules_hash"].startswith("sha256:")


def test_full_journey(client):
    vid = _active_version(client)
    files = [
        ("files", ("correct.c", (SUB / "correct.c").read_bytes(), "text/plain")),
        ("files", ("incorrect.c", (SUB / "incorrect.c").read_bytes(), "text/plain")),
        ("files", ("wali.c", (SUB / "incorrect.c").read_bytes(), "text/plain")),
    ]
    r = client.post("/api/batches", data={"version_id": vid}, files=files)
    assert r.status_code == 201, r.text
    batch = r.json()
    by_name = {s["filename"]: s for s in batch["submissions"]}
    assert by_name["wali.c"]["status"] == "duplicate"

    r = client.post(f"/api/batches/{batch['id']}/evaluate", json={})
    assert r.status_code == 200
    rows = {s["filename"]: s for s in r.json()["submissions"]}
    assert rows["correct.c"]["grade"] == 100.0
    assert rows["correct.c"]["tests_passed"] == 24
    assert rows["incorrect.c"]["grade"] == 85.2
    assert rows["correct.c"]["run_state"] == "completed"

    # investigation: run detail carries report + evidence + breakdown
    run = client.get(f"/api/evaluations/{rows['correct.c']['run_id']}").json()
    assert float(run["report"]["overall_grade"]) == 100.0  # Decimal as string
    assert any(e["kind"] == "correctness" for e in run["evidence"])
    assert run["breakdown"] and run["breakdown"][0]["name"] == "correctness"

    # report downloads in all three formats from the same canonical report
    sid = rows["correct.c"]["submission_id"]
    assert client.get(f"/api/submissions/{sid}/report?format=json").status_code == 200
    html = client.get(f"/api/submissions/{sid}/report?format=html")
    assert "text/html" in html.headers["content-type"]
    detail = client.get(f"/api/submissions/{sid}").json()
    assert "long long add" in detail["source"]

    # retry creates a NEW run linked to the old one, same grade
    r = client.post(f"/api/evaluations/{run['id']}/retry", json={})
    assert r.status_code == 201
    assert r.json()["retry_of_run_id"] == run["id"]
    assert r.json()["grade"] == 100.0


def test_similarity_disposition_never_changes_grade(client):
    vid = _active_version(client)
    renamed = (
        (SUB / "correct.c").read_text()
        .replace("add(lhs, rhs)", "sum_pair(lhs, rhs)")
        .replace("static long long add(", "static long long sum_pair(")
        .replace("lhs", "left").replace("rhs", "right")
    )
    files = [
        ("files", ("original.c", (SUB / "correct.c").read_bytes(), "text/plain")),
        ("files", ("renamed.c", renamed.encode(), "text/plain")),
    ]
    batch = client.post("/api/batches", data={"version_id": vid}, files=files).json()
    client.post(f"/api/batches/{batch['id']}/evaluate", json={})
    findings = client.get(f"/api/similarity?batch_id={batch['id']}").json()
    assert findings and findings[0]["review_status"] == "pending"
    before = client.get(f"/api/batches/{batch['id']}").json()
    grades_before = {s["filename"]: s["grade"] for s in before["submissions"]}
    r = client.post(
        f"/api/similarity/{findings[0]['id']}/disposition",
        json={"status": "dismissed", "note": "pair work, declared"},
    )
    assert r.json()["review_status"] == "dismissed"
    after = client.get(f"/api/batches/{batch['id']}").json()
    assert {s["filename"]: s["grade"] for s in after["submissions"]} == grades_before
