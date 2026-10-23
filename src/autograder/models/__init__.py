"""Typed data contracts used by the actual workflow (master spec section 3)."""

from autograder.models.analysis import AnalyzerResult, MissingReason, ResultStatus
from autograder.models.assignment import AssignmentSpec
from autograder.models.execution import ExecutionResult, ExecutionStatus
from autograder.models.report import EvaluationReport, MetricBreakdown, OverallStatus
from autograder.models.tests import ComparisonPolicy, TestCase, TrustStatus

__all__ = [
    "AnalyzerResult",
    "AssignmentSpec",
    "ComparisonPolicy",
    "EvaluationReport",
    "ExecutionResult",
    "ExecutionStatus",
    "MetricBreakdown",
    "MissingReason",
    "OverallStatus",
    "ResultStatus",
    "TestCase",
    "TrustStatus",
]
