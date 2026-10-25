"""V2 services: state machine, assignment lifecycle with activation
gating, batch evaluation end-to-end on real fixtures (Agent 5)."""

from pathlib import Path

import pytest
import yaml

from autograder.db.models import EvaluationRun, SimilarityFinding
from autograder.db.session import make_engine, make_session_factory
from autograder.services import assignments as asvc
from autograder.services import evaluations as esvc
from autograder.services.state_machine import IllegalTransition, transition

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "examples" / "submissions"


@pytest.fixture()
def env(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    factory = make_session_factory(engine)
    session = factory()
    return session, tmp_path / "data"


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


def _validated_version(env):
    session, data = env
    a = asvc.create_assignment(session, "Add two integers")
    v = asvc.create_version(session, data, a, _payload())
    assert v.status == "validated"
    return asvc.activate_version(session, v)


def test_state_machine_rejects_illegal_transitions(env):
    session, _ = env
    run = EvaluationRun(submission_id=1, version_id=1, state="queued")
    session.add(run)
    session.commit()
    transition(session, run, "preparing")
    with pytest.raises(IllegalTransition):
        transition(session, run, "completed")  # skipping the pipeline
    with pytest.raises(IllegalTransition):
        transition(session, run, "queued")  # backwards


def test_draft_version_cannot_be_activated(env):
    session, data = env
    a = asvc.create_assignment(session, "Vague assignment")
    payload = _payload()
    payload["examples"] = [
        {"input": "1 2\n", "expected": "3", "category": "ordinary_valid"}
    ]
    payload["generator"] = "none"  # no derivation path -> bar cannot be met
    v = asvc.create_version(session, data, a, payload)
    assert v.status == "draft"
    assert json_unresolved(v)
    with pytest.raises(asvc.ServiceError):
        asvc.activate_version(session, v)


def json_unresolved(v) -> bool:
    import json

    return len(json.loads(v.unresolved_json)) > 0


def test_batch_evaluation_end_to_end(env):
    session, data = env
    v = _validated_version(env)
    files = [
        ("correct.c", (SUB / "correct.c").read_bytes(), None),
        ("incorrect.c", (SUB / "incorrect.c").read_bytes(), None),
        ("timeout.c", (SUB / "timeout.c").read_bytes(), None),
        ("copy_of_correct.c", (SUB / "correct.c").read_bytes(), None),
    ]
    batch = esvc.create_batch(session, data, v, files)
    subs = {s.filename: s for s in session.query(esvc.Submission).filter_by(batch_id=batch.id)}
    assert subs["copy_of_correct.c"].status == "duplicate"  # exact dup detected
    esvc.evaluate_batch(session, data, batch)
    rows = {r["filename"]: r for r in
            (esvc.result_row(session, s) for s in subs.values())}
    assert rows["correct.c"]["grade"] == 100.0
    assert rows["correct.c"]["run_state"] == "completed"
    assert rows["incorrect.c"]["grade"] == 85.2  # peers corpus: no twin flag
    assert rows["timeout.c"]["overall_status"] == "partial"
    assert "suspected_infinite_loop" in rows["timeout.c"]["flags"]
    # duplicate submission is not evaluated (no run)
    assert rows["copy_of_correct.c"]["run_id"] is None


def test_batch_similarity_finding_for_renamed_copy(env, tmp_path):
    session, data = env
    v = _validated_version(env)
    renamed = (
        (SUB / "correct.c").read_text()
        .replace("add(lhs, rhs)", "sum_pair(lhs, rhs)")
        .replace("static long long add(", "static long long sum_pair(")
        .replace("lhs", "left").replace("rhs", "right")
    )
    assert renamed != (SUB / "correct.c").read_text()  # really a variant
    files = [
        ("original.c", (SUB / "correct.c").read_bytes(), None),
        ("renamed.c", renamed.encode(), None),
        ("different.c", (SUB / "incorrect.c").read_bytes(), None),
    ]
    batch = esvc.create_batch(session, data, v, files)
    esvc.evaluate_batch(session, data, batch)
    findings = session.query(SimilarityFinding).filter_by(batch_id=batch.id).all()
    assert findings, "renamed copy should be flagged for review"
    assert all(f.review_status == "pending" for f in findings)
    assert max(f.score for f in findings) >= 0.85


def test_run_fails_closed_when_docker_required_but_absent(env):
    session, data = env
    v = _validated_version(env)
    batch = esvc.create_batch(
        session, data, v, [("correct.c", (SUB / "correct.c").read_bytes(), None)]
    )
    esvc.evaluate_batch(session, data, batch, backend="docker")
    run = session.query(EvaluationRun).first()
    assert run.state == "failed"
    assert "fail-closed" in run.error or "sandbox unavailable" in run.error


def test_batch_rejects_non_c_and_oversize(env):
    session, data = env
    v = _validated_version(env)
    with pytest.raises(asvc.ServiceError):
        esvc.create_batch(session, data, v, [("evil.py", b"print(1)", None)])
    with pytest.raises(asvc.ServiceError):
        esvc.create_batch(
            session, data, v, [("big.c", b"x" * (esvc.MAX_FILE_BYTES + 1), None)]
        )
