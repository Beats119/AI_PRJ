"""Stage 9 workflow tests: full evaluations, D-5 branches, determinism."""

from decimal import Decimal
from pathlib import Path

import pytest

from autograder.config.loader import load_models_config, load_rules
from autograder.models.analysis import MissingReason
from autograder.workflow import evaluate_submission

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"
SUB = ROOT / "examples" / "submissions"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    cache = tmp_path_factory.mktemp("wf-cache")
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    models = load_models_config(ROOT / "configs" / "models.yaml")
    return loaded, models, cache


def _eval(env, source, assignment=EXAMPLE, corpus=SUB):
    loaded, models, cache = env
    return evaluate_submission(
        source, assignment_dir=assignment, loaded_rules=loaded, models=models,
        cache_dir=cache, corpus_dir=corpus,
    )


def _by_metric(report):
    return {r.metric_name: r for r in report.metric_results}


def test_correct_submission_complete(env):
    report = _eval(env, SUB / "correct.c")
    assert report.overall_status.value == "complete"
    assert report.overall_grade is not None and report.overall_grade >= Decimal(90)
    total = sum(
        (row.contribution for row in report.score_breakdown
         if row.contribution is not None),
        Decimal(0),
    )
    assert report.overall_grade == total  # breakdown adds up exactly
    assert report.metric_coverage == Decimal(1)
    prof = [e for e in report.execution_evidence if e["type"] == "profile"]
    assert prof and prof[0]["wall_time_ms"]["median"] is not None


def test_incorrect_submission_complete_but_lower(env):
    good = _eval(env, SUB / "correct.c")
    bad = _eval(env, SUB / "incorrect.c")
    assert bad.overall_status.value == "complete"
    assert bad.overall_grade < good.overall_grade
    assert _by_metric(bad)["correctness"].status.value == "failed"


def test_compile_error_takes_d5_partial_branch(env):
    report = _eval(env, SUB / "compile_error.c")
    assert report.overall_status.value == "partial"
    assert report.overall_grade is not None  # partial grade, disclosed as such
    assert "compile_error" in report.flags
    by = _by_metric(report)
    for name in ("correctness", "logical", "memory_safety"):
        assert by[name].status.value == "skipped"
        assert by[name].missing_reason is MissingReason.STUDENT_COMPILE_FAILURE
    # source-only analyzers still ran:
    assert by["structure"].score is not None
    assert by["readability"].score is not None
    assert any(
        e["type"] == "compilation" and e["success"] is False
        for e in report.execution_evidence
    )


def test_timeout_takes_smoke_branch(env):
    report = _eval(env, SUB / "timeout.c")
    assert report.overall_status.value == "partial"
    assert "suspected_infinite_loop" in report.flags
    by = _by_metric(report)
    assert by["correctness"].status.value == "skipped"
    assert by["correctness"].missing_reason is MissingReason.STUDENT_TIMEOUT
    assert by["syntax"].score is not None  # source-only metrics still graded


def test_insufficient_assignment_is_incomplete_with_no_grade(env, tmp_path):
    weak = tmp_path / "weak"
    weak.mkdir()
    (weak / "assignment.md").write_text(
        "# W\n\n## Problem\n\nAdd.\n\n## Input\n\nTwo ints.\n\n## Output\n\nSum.\n"
    )
    (weak / "spec.yaml").write_text("assignment_id: weak\ngenerator: none\n")
    (weak / "tests.yaml").write_text(
        'tests:\n  - input: "1 2\\n"\n    expected: "3"\n    category: ordinary_valid\n'
    )
    loaded, models, _cache = env
    report = evaluate_submission(
        SUB / "correct.c", assignment_dir=weak, loaded_rules=loaded,
        models=models, cache_dir=tmp_path / "fresh-cache", corpus_dir=SUB,
    )
    assert report.overall_status.value == "incomplete"
    assert report.overall_grade is None
    assert _by_metric(report)["correctness"].status.value == "insufficient_evidence"


def test_repeat_evaluation_is_deterministic(env):
    r1 = _eval(env, SUB / "incorrect.c")
    r2 = _eval(env, SUB / "incorrect.c")
    assert r1.overall_grade == r2.overall_grade
    assert [r.score for r in r1.metric_results] == [r.score for r in r2.metric_results]
    assert r1.evaluation_id == r2.evaluation_id
