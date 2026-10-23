"""Stage 10 renderer tests: one canonical report, three consistent formats."""

from decimal import Decimal

from autograder.models.analysis import AnalyzerResult, ResultStatus
from autograder.models.report import (
    EvaluationReport,
    MetricBreakdown,
    OverallStatus,
)
from autograder.reports import render_html, render_json, render_txt


def _report(feedback="ok"):
    result = AnalyzerResult(
        analyzer_id="io_tests", metric_name="correctness",
        status=ResultStatus.FAILED, score=Decimal("0.5"), feedback=feedback,
        evidence={"failing": [
            {"test_id": "gen-001", "input": "1 2\n", "expected": "3",
             "actual": "4\n", "outcome": "fail"}
        ]},
    )
    return EvaluationReport(
        evaluation_id="eval-test",
        submission_name="evil<b>.c",
        submission_hash="sha256:abc",
        assignment_hash="sha256:def",
        rules_hash="sha256:ghi",
        overall_status=OverallStatus.COMPLETE,
        overall_grade=Decimal("55.0"),
        metric_results=[result],
        score_breakdown=[
            MetricBreakdown(
                name="correctness", configured_weight=Decimal("0.2"),
                status="failed", score=Decimal("0.5"),
                contribution=Decimal("10.0"), effective_weight=Decimal("0.2"),
            )
        ],
        metric_coverage=Decimal(1),
        provenance={"rules_hash": "sha256:ghi"},
        limitations=["a limitation"],
    )


def test_all_formats_agree_on_the_grade():
    report = _report()
    assert "55.0" in render_txt(report)
    assert "55.0" in render_html(report)
    assert '"overall_grade": "55.0"' in render_json(report)


def test_txt_discloses_weights_contributions_and_counterexamples():
    txt = render_txt(_report())
    assert "weight 0.2" in txt and "contribution 10.0" in txt
    assert "gen-001" in txt and "expected '3'" in txt
    assert "Limitations" in txt


def test_html_escapes_untrusted_content():
    page = render_html(_report(feedback="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "evil&lt;b&gt;.c" in page


def test_json_round_trips_to_the_same_report():
    report = _report()
    again = EvaluationReport.model_validate_json(render_json(report))
    assert again == report
