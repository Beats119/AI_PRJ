"""Data-contract tests (RTM E-16): invalid states must be unrepresentable."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from autograder.models.analysis import AnalyzerResult, MissingReason, ResultStatus
from autograder.models.tests import ComparisonPolicy, TestCase, TrustStatus


def test_scored_result_requires_score():
    with pytest.raises(ValidationError):
        AnalyzerResult(
            analyzer_id="io_tests", metric_name="correctness", status=ResultStatus.PASSED
        )


def test_unscored_result_must_not_carry_score():
    with pytest.raises(ValidationError):
        AnalyzerResult(
            analyzer_id="io_tests",
            metric_name="correctness",
            status=ResultStatus.SKIPPED,
            score=Decimal("0.5"),
            missing_reason=MissingReason.STUDENT_TIMEOUT,
        )


def test_unscored_result_must_state_reason():
    with pytest.raises(ValidationError):
        AnalyzerResult(
            analyzer_id="io_tests", metric_name="correctness", status=ResultStatus.SKIPPED
        )


def test_valid_scored_result():
    r = AnalyzerResult(
        analyzer_id="io_tests",
        metric_name="correctness",
        status=ResultStatus.FAILED,
        score=Decimal("0.8"),
        feedback="8/10 tests pass",
    )
    assert r.score == Decimal("0.8")


def test_trusted_test_requires_expected_and_method():
    untrusted = TestCase(
        test_id="t1",
        input_data="1 2",
        expected_output=None,
        category="ordinary_valid",
        trust_status=TrustStatus.UNTRUSTED,
        provenance="llm proposal",
        validation_method="none",
    )
    assert not untrusted.counts_as_trusted
    no_method = TestCase(
        test_id="t2",
        input_data="1 2",
        expected_output="3",
        category="ordinary_valid",
        trust_status=TrustStatus.TRUSTED,
        provenance="llm proposal",
        validation_method="none",
        comparison_policy=ComparisonPolicy.EXACT,
    )
    assert not no_method.counts_as_trusted
    trusted = TestCase(
        test_id="t3",
        input_data="1 2",
        expected_output="3",
        category="ordinary_valid",
        trust_status=TrustStatus.TRUSTED,
        provenance="instructor example",
        validation_method="instructor_example",
    )
    assert trusted.counts_as_trusted
