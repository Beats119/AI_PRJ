"""Correctness + logical (edge-case) analysis over the TRUSTED suite only.

Per-test outcomes distinguish:
  pass / fail                  the student's program ran; outputs compared
  execution_failure            the student's program crashed, timed out, or
                               blew a resource/output limit on a trusted test
  infrastructure_error         OUR side failed (executor tool error) — never
                               reported as student incorrectness; it turns
                               the whole result into an environment error
Untrusted tests never run here and never affect the score.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from autograder.comparison import compare_outputs
from autograder.models.analysis import AnalyzerResult, MissingReason, ResultStatus
from autograder.models.execution import ExecutionStatus
from autograder.models.tests import TestCase
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits

LOGICAL_CATEGORIES = {"edge_values", "minimum_boundary", "maximum_boundary"}


def run_trusted_tests(
    binary_path: str | Path,
    suite: list[TestCase],
    *,
    submission_hash: str,
    sandbox: Sandbox,
    limits: ExecutionLimits,
) -> list[dict]:
    records: list[dict] = []
    for case in suite:
        if not case.counts_as_trusted:
            continue
        res = sandbox.run(
            binary_path,
            test_id=case.test_id,
            submission_hash=submission_hash,
            input_data=case.input_data,
            limits=limits,
        )
        record = {
            "test_id": case.test_id,
            "category": case.category,
            "input": case.input_data,
            "expected": case.expected_output,
            "actual": res.stdout,
            "execution_status": res.status.value,
            "exit_code": res.exit_code,
            "diagnostics": res.diagnostics,
        }
        if res.status is ExecutionStatus.TOOL_ERROR:
            record["outcome"] = "infrastructure_error"
        elif res.status is not ExecutionStatus.OK:
            record["outcome"] = "execution_failure"
            record["note"] = f"program {res.status.value} on this input"
        elif compare_outputs(case.expected_output or "", res.stdout, case.comparison_policy):
            record["outcome"] = "pass"
        else:
            record["outcome"] = "fail"
            record["note"] = "output does not match the trusted expected output"
        records.append(record)
    return records


def _result_from_records(
    records: list[dict],
    *,
    analyzer_id: str,
    metric_name: str,
    total_suite_size: int,
) -> AnalyzerResult:
    infra = [r for r in records if r["outcome"] == "infrastructure_error"]
    if infra:
        return AnalyzerResult(
            analyzer_id=analyzer_id,
            metric_name=metric_name,
            status=ResultStatus.ERROR,
            missing_reason=MissingReason.ANALYZER_ERROR,
            diagnostics=[
                (
                    f"{len(infra)} trusted test(s) could not be executed due to an "
                    "infrastructure error; this is not student incorrectness"
                )
            ],
            evidence={"records": records},
        )
    if not records:
        return AnalyzerResult(
            analyzer_id=analyzer_id,
            metric_name=metric_name,
            status=ResultStatus.INSUFFICIENT_EVIDENCE,
            missing_reason=MissingReason.INSUFFICIENT_EVIDENCE,
            diagnostics=["no trusted tests were available to run"],
            evidence={"records": []},
        )
    passed = sum(1 for r in records if r["outcome"] == "pass")
    total = len(records)
    failing = [r for r in records if r["outcome"] != "pass"]
    score = Decimal(passed) / Decimal(total)
    feedback = f"{passed}/{total} trusted tests pass."
    if failing:
        f0 = failing[0]
        feedback += (
            f" First failure: test {f0['test_id']} input {f0['input']!r} "
            f"expected {f0['expected']!r} got {f0['actual']!r}."
        )
    return AnalyzerResult(
        analyzer_id=analyzer_id,
        metric_name=metric_name,
        status=ResultStatus.PASSED if passed == total else ResultStatus.FAILED,
        score=score,
        feedback=feedback,
        evidence={
            "tests_passed": passed,
            "tests_total": total,
            "suite_size_including_untrusted": total_suite_size,
            "failing": failing,
            "records": records,
        },
    )


def analyze_correctness(
    binary_path: str | Path,
    suite: list[TestCase],
    *,
    submission_hash: str,
    sandbox: Sandbox,
    limits: ExecutionLimits,
) -> AnalyzerResult:
    records = run_trusted_tests(
        binary_path, suite, submission_hash=submission_hash,
        sandbox=sandbox, limits=limits,
    )
    return _result_from_records(
        records, analyzer_id="io_tests", metric_name="correctness",
        total_suite_size=len(suite),
    )


def analyze_logical(
    binary_path: str | Path,
    suite: list[TestCase],
    *,
    submission_hash: str,
    sandbox: Sandbox,
    limits: ExecutionLimits,
) -> AnalyzerResult:
    """The PDF's edge_case_runner metric: boundary/edge trusted tests only."""
    subset = [t for t in suite if t.category in LOGICAL_CATEGORIES]
    records = run_trusted_tests(
        binary_path, subset, submission_hash=submission_hash,
        sandbox=sandbox, limits=limits,
    )
    if not records:
        return AnalyzerResult(
            analyzer_id="edge_case_runner",
            metric_name="logical",
            status=ResultStatus.INCONCLUSIVE,
            missing_reason=MissingReason.INCONCLUSIVE_EVIDENCE,
            diagnostics=["no trusted boundary/edge tests exist for the logical metric"],
            evidence={"records": []},
        )
    return _result_from_records(
        records, analyzer_id="edge_case_runner", metric_name="logical",
        total_suite_size=len(subset),
    )
