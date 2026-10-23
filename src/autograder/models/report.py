"""EvaluationReport: the canonical result that all report formats render from."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from autograder.models.analysis import AnalyzerResult


class OverallStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PROVISIONAL = "provisional"
    INCOMPLETE = "incomplete"


class MetricBreakdown(BaseModel):
    """One row of the mandatory scoring disclosure (D-3)."""

    name: str
    configured_weight: Decimal
    status: str
    score: Decimal | None = None
    contribution: Decimal | None = None  # grade points actually contributed
    effective_weight: Decimal | None = None  # weight used in the presented total
    note: str = ""


class EvaluationReport(BaseModel):
    evaluation_id: str
    submission_name: str = ""
    submission_hash: str
    assignment_hash: str
    rules_hash: str
    overall_status: OverallStatus
    overall_grade: Decimal | None = None  # None unless a grade is justified (D-3)
    metric_results: list[AnalyzerResult] = Field(default_factory=list)
    score_breakdown: list[MetricBreakdown] = Field(default_factory=list)
    metric_coverage: Decimal = Decimal(0)  # graded configured weight / total configured weight
    execution_evidence: list[dict[str, Any]] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
