"""Scoring engine tests: one per D-3 matrix case, plus determinism (P-02).

Rules fixture mirrors the PDF example proportions in miniature:
correctness 0.50 (core), complexity 0.30 (required),
readability 0.20 (optional, so D-3 case 3 can be exercised).
"""

from decimal import Decimal

import pytest

from autograder.config.schema import Rules
from autograder.models.analysis import AnalyzerResult, MissingReason, ResultStatus
from autograder.models.report import OverallStatus
from autograder.scoring.engine import score_results

RULES = Rules.model_validate(
    {
        "problem": "demo",
        "metrics": [
            {"name": "correctness", "analyzer": "io_tests", "weight": "0.50"},
            {"name": "complexity", "analyzer": "complexity_estimator", "weight": "0.30"},
            {
                "name": "readability",
                "analyzer": "llm_review",
                "weight": "0.20",
                "required": False,
            },
        ],
    }
)

ANALYZER = {
    "correctness": "io_tests",
    "complexity": "complexity_estimator",
    "readability": "llm_review",
}


def scored(metric: str, value: str) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_id=ANALYZER[metric],
        metric_name=metric,
        status=ResultStatus.PASSED,
        score=Decimal(value),
    )


def unscored(metric: str, status: ResultStatus, reason: MissingReason) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_id=ANALYZER[metric],
        metric_name=metric,
        status=status,
        missing_reason=reason,
    )


def test_complete_grade_is_weighted_sum():
    out = score_results(
        RULES, [scored("correctness", "0.8"), scored("complexity", "1.0"),
                scored("readability", "0.5")]
    )
    assert out.overall_status is OverallStatus.COMPLETE
    # 0.8*50 + 1.0*30 + 0.5*20 = 80.0
    assert out.overall_grade == Decimal("80.0")
    assert out.metric_coverage == Decimal(1)
    assert out.cases_applied == []
    row = {b.name: b for b in out.breakdown}
    assert row["correctness"].contribution == Decimal("40.0")
    assert row["correctness"].effective_weight == Decimal("0.50")


def test_reproducible_same_inputs_same_grade():
    args = [scored("correctness", "0.9"), scored("complexity", "0.7"),
            scored("readability", "0.3")]
    assert score_results(RULES, args) == score_results(RULES, list(args))


def test_case1_insufficient_correctness_blocks_grade():
    out = score_results(
        RULES,
        [unscored("correctness", ResultStatus.INSUFFICIENT_EVIDENCE,
                  MissingReason.INSUFFICIENT_EVIDENCE),
         scored("complexity", "1.0"), scored("readability", "1.0")],
    )
    assert out.overall_status is OverallStatus.INCOMPLETE
    assert out.overall_grade is None
    assert 1 in out.cases_applied


def test_case2_required_metric_host_blocked_blocks_grade_no_redistribution():
    out = score_results(
        RULES,
        [scored("correctness", "1.0"),
         unscored("complexity", ResultStatus.ERROR, MissingReason.HOST_TOOL_UNAVAILABLE),
         scored("readability", "1.0")],
    )
    assert out.overall_status is OverallStatus.INCOMPLETE
    assert out.overall_grade is None
    assert 2 in out.cases_applied
    # no redistribution happened: nothing carries an effective weight
    assert all(b.effective_weight is None for b in out.breakdown)


def test_case3_optional_unavailable_excluded_and_renormalized():
    out = score_results(
        RULES,
        [scored("correctness", "1.0"), scored("complexity", "0.5"),
         unscored("readability", ResultStatus.SKIPPED,
                  MissingReason.HOST_TOOL_UNAVAILABLE)],
    )
    assert out.overall_status is OverallStatus.COMPLETE
    assert 3 in out.cases_applied
    # graded configured = 0.8; correctness effective = 0.5/0.8 = 0.625
    # grade = 1.0*62.5 + 0.5*37.5 = 81.25 -> 81.3 (half-up, 1dp)... check below
    row = {b.name: b for b in out.breakdown}
    assert row["correctness"].effective_weight == Decimal("0.625")
    assert row["readability"].effective_weight is None
    assert out.metric_coverage == Decimal("0.8")
    assert out.overall_grade == Decimal("81.3")


def test_case4_student_skip_gives_partial_grade_without_renormalization():
    out = score_results(
        RULES,
        [unscored("correctness", ResultStatus.SKIPPED,
                  MissingReason.STUDENT_COMPILE_FAILURE),
         unscored("complexity", ResultStatus.SKIPPED,
                  MissingReason.STUDENT_COMPILE_FAILURE),
         scored("readability", "0.5")],
    )
    assert out.overall_status is OverallStatus.PARTIAL
    assert 4 in out.cases_applied
    # only readability contributes: 0.5 * 0.20 * 100 = 10.0, weights NOT renormalized
    assert out.overall_grade == Decimal("10.0")
    row = {b.name: b for b in out.breakdown}
    assert row["correctness"].contribution == Decimal(0)
    assert row["correctness"].effective_weight == Decimal("0.50")
    assert out.metric_coverage == Decimal("0.2")


def test_case5_required_inconclusive_is_provisional():
    out = score_results(
        RULES,
        [scored("correctness", "1.0"),
         unscored("complexity", ResultStatus.INCONCLUSIVE,
                  MissingReason.INCONCLUSIVE_EVIDENCE),
         scored("readability", "1.0")],
    )
    assert out.overall_status is OverallStatus.PROVISIONAL
    assert out.overall_grade is None
    assert 5 in out.cases_applied


def test_case5_advisory_exclude_declaration_behaves_like_case3():
    rules = Rules.model_validate(
        {
            "problem": "demo",
            "metrics": [
                {"name": "correctness", "analyzer": "io_tests", "weight": "0.50"},
                {"name": "complexity", "analyzer": "complexity_estimator",
                 "weight": "0.30", "inconclusive_treatment": "advisory_exclude"},
                {"name": "readability", "analyzer": "llm_review",
                 "weight": "0.20", "required": False},
            ],
        }
    )
    out = score_results(
        rules,
        [scored("correctness", "1.0"),
         unscored("complexity", ResultStatus.INCONCLUSIVE,
                  MissingReason.INCONCLUSIVE_EVIDENCE),
         scored("readability", "0.0")],
    )
    assert out.overall_status is OverallStatus.COMPLETE
    assert 3 in out.cases_applied
    # graded = correctness + readability = 0.7 cfg; eff correctness = 5/7
    # grade = 1.0 * (0.5/0.7) * 100 = 71.428... -> 71.4
    assert out.overall_grade == Decimal("71.4")


def test_duplicate_result_rejected():
    with pytest.raises(ValueError):
        score_results(RULES, [scored("correctness", "1.0"), scored("correctness", "0.5")])


def test_disclosure_rows_always_complete():
    out = score_results(
        RULES, [scored("correctness", "0.8"), scored("complexity", "1.0"),
                scored("readability", "0.5")]
    )
    assert {b.name for b in out.breakdown} == {"correctness", "complexity", "readability"}
    for b in out.breakdown:
        assert b.configured_weight > 0
        assert b.contribution is not None
