"""Stage 6-7 integration: prepare (miss -> hit), correctness, reproducibility,
D-3 scoring integration, and the CLI — all against the real pipeline."""

import json
from decimal import Decimal
from pathlib import Path

from autograder.analyzers.correctness import analyze_correctness, analyze_logical
from autograder.assignment import prepare_assignment
from autograder.cli import main
from autograder.config.loader import load_models_config, load_rules
from autograder.models.analysis import AnalyzerResult, ResultStatus
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits
from autograder.scoring.engine import score_results

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"
SUBMISSIONS = ROOT / "examples" / "submissions"
LIMITS = ExecutionLimits(wall_time_s=2.0, memory_mb=64)


def _prepare(cache_dir):
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    models = load_models_config(ROOT / "configs" / "models.yaml")
    return prepare_assignment(EXAMPLE, loaded, models, cache_dir)


def _analyze(source: Path, suite, limits=LIMITS):
    with Sandbox() as sb:
        comp = sb.compile(source)
        assert comp.success, comp.diagnostics
        return analyze_correctness(
            comp.binary_path, suite, submission_hash=comp.source_hash,
            sandbox=sb, limits=limits,
        )


def test_cache_miss_then_hit_with_identical_suite(tmp_path):
    first = _prepare(tmp_path / "cache")
    assert first.status == "prepared_new"
    # oracle-v2: trust is computational (derivation), so setup performs no
    # sandbox executions at all — on a miss OR a hit.
    assert first.validation_executions == 0
    second = _prepare(tmp_path / "cache")
    assert second.status == "prepared_cache_hit"
    assert second.validation_executions == 0  # setup work was skipped
    assert second.cache_key == first.cache_key
    assert [t.model_dump() for t in second.suite] == [
        t.model_dump() for t in first.suite
    ]
    trusted = [t for t in first.suite if t.counts_as_trusted]
    assert len(trusted) == 24


def test_correct_submission_passes_everything(tmp_path):
    prep = _prepare(tmp_path / "cache")
    result = _analyze(SUBMISSIONS / "correct.c", prep.suite)
    assert result.status is ResultStatus.PASSED
    assert result.score == Decimal(1)


def test_incorrect_submission_produces_a_counterexample(tmp_path):
    prep = _prepare(tmp_path / "cache")
    result = _analyze(SUBMISSIONS / "incorrect.c", prep.suite)
    assert result.status is ResultStatus.FAILED
    assert result.score < Decimal(1)
    failing = result.evidence["failing"]
    assert failing, "expected at least one counterexample"
    big = [f for f in failing if f["expected"] == "4000000000"]
    assert big, f"expected a large-operands counterexample, got {failing}"
    assert big[0]["input"] == "2000000000 2000000000\n"
    assert big[0]["actual"].strip() != "4000000000"


def test_logical_metric_uses_boundary_and_edge_tests(tmp_path):
    prep = _prepare(tmp_path / "cache")
    with Sandbox() as sb:
        comp = sb.compile(SUBMISSIONS / "incorrect.c")
        result = analyze_logical(
            comp.binary_path, prep.suite, submission_hash=comp.source_hash,
            sandbox=sb, limits=LIMITS,
        )
    assert result.evidence["tests_total"] > 0
    assert result.status is ResultStatus.FAILED  # INT_MAX+1 edge case fails


def test_crash_and_timeout_are_student_execution_failures(tmp_path):
    prep = _prepare(tmp_path / "cache")
    crash = tmp_path / "crash.c"
    crash.write_text("int main(void){ int *p=0; *p=1; return 0; }\n")
    result = _analyze(crash, prep.suite)
    assert result.status is ResultStatus.FAILED
    outcomes = {r["outcome"] for r in result.evidence["records"]}
    assert outcomes == {"execution_failure"}

    loop = tmp_path / "loop.c"
    loop.write_text("int main(void){ for(;;){} }\n")
    subset = [t for t in prep.suite if t.counts_as_trusted][:2]
    result = _analyze(loop, subset, limits=ExecutionLimits(wall_time_s=1.0))
    statuses = {r["execution_status"] for r in result.evidence["records"]}
    assert statuses == {"timeout"}


def test_infrastructure_error_is_not_student_incorrectness(tmp_path):
    prep = _prepare(tmp_path / "cache")
    with Sandbox() as sb:
        result = analyze_correctness(
            tmp_path / "no-such-binary", prep.suite, submission_hash="sha256:x",
            sandbox=sb, limits=LIMITS,
        )
    assert result.status is ResultStatus.ERROR
    assert result.score is None  # never scored as a student failure


def test_correctness_is_repeatable(tmp_path):
    prep = _prepare(tmp_path / "cache")
    r1 = _analyze(SUBMISSIONS / "incorrect.c", prep.suite)
    r2 = _analyze(SUBMISSIONS / "incorrect.c", prep.suite)

    def signature(r):
        return [
            (rec["test_id"], rec["outcome"], rec["actual"])
            for rec in r.evidence["records"]
        ]

    assert signature(r1) == signature(r2)
    assert r1.score == r2.score


def test_insufficient_setup_blocks_evaluation(tmp_path):
    weak = tmp_path / "weak"
    weak.mkdir()
    (weak / "assignment.md").write_text(
        "# W\n\n## Problem\n\nAdd.\n\n## Input\n\nTwo ints.\n\n## Output\n\nSum.\n"
    )
    (weak / "spec.yaml").write_text("assignment_id: weak\ngenerator: none\n")
    (weak / "tests.yaml").write_text(
        'tests:\n  - input: "1 2\\n"\n    expected: "3"\n    category: ordinary_valid\n'
    )
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    models = load_models_config(ROOT / "configs" / "models.yaml")
    result = prepare_assignment(weak, loaded, models, tmp_path / "cache")
    assert result.status == "insufficient_evidence"
    assert result.suite is None
    entries = list((tmp_path / "cache").glob("*/metadata.json")) if (
        tmp_path / "cache"
    ).exists() else []
    assert entries == []  # nothing was cached


def test_scoring_integration_with_real_correctness_result(tmp_path):
    prep = _prepare(tmp_path / "cache")
    correctness = _analyze(SUBMISSIONS / "incorrect.c", prep.suite)
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    others = [
        AnalyzerResult(
            analyzer_id=m.analyzer, metric_name=m.name, status=ResultStatus.PASSED,
            score=Decimal(1),
        )
        for m in loaded.rules.metrics
        if m.name != "correctness"
    ]
    outcome = score_results(loaded.rules, [correctness, *others])
    assert outcome.overall_status.value == "complete"
    expected_grade = (
        (Decimal("0.20") * correctness.score + Decimal("0.80")) * 100
    ).quantize(Decimal("0.1"))
    assert outcome.overall_grade == expected_grade  # both Decimal: exact


def test_cli_prepare_hit_and_evaluate_counterexample(tmp_path, capsys):
    cache_dir = tmp_path / "cache"
    base = [
        "--assignment", str(EXAMPLE),
        "--rules", str(ROOT / "configs" / "example_rules.yaml"),
        "--models", str(ROOT / "configs" / "models.yaml"),
        "--cache-dir", str(cache_dir),
    ]
    assert main(["prepare-assignment", *base]) == 0
    out1 = capsys.readouterr().out
    assert "prepared_new" in out1
    assert main(["prepare-assignment", *base]) == 0
    out2 = capsys.readouterr().out
    assert "prepared_cache_hit" in out2

    assert main(["cache", "--cache-dir", str(cache_dir), "list"]) == 0
    listing = capsys.readouterr().out
    assert "add_two_integers" in listing

    # Stage 9 supersedes the correctness-only CLI: evaluate now runs the
    # full workflow and writes the canonical report in three formats.
    code = main([
        "evaluate", "--source", str(SUBMISSIONS / "incorrect.c"),
        "--corpus-dir", str(SUBMISSIONS),
        "--out", str(tmp_path / "reports"), *base,
    ])
    assert code == 0  # a completed evaluation; the grade carries the bad news
    out3 = capsys.readouterr().out
    assert "counterexample" in out3
    report = json.loads((tmp_path / "reports" / "incorrect.json").read_text())
    assert report["overall_grade"] is not None
    correctness = next(
        r for r in report["metric_results"] if r["metric_name"] == "correctness"
    )
    assert correctness["status"] == "failed"
    failing = correctness["evidence"]["failing"]
    assert any(f["expected"] == "4000000000" for f in failing)
    assert (tmp_path / "reports" / "incorrect.html").exists()
    assert (tmp_path / "reports" / "incorrect.txt").exists()
