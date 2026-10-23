"""AnalyzerResult: the structured result every analyzer must return."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ResultStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"
    ERROR = "error"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MissingReason(str, Enum):
    """Why a metric has no score. Drives the D-3 scoring matrix."""

    NONE = "none"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # core setup/trust failure
    HOST_TOOL_UNAVAILABLE = "host_tool_unavailable"  # environment's fault
    ANALYZER_ERROR = "analyzer_error"  # environment/analyzer fault
    STUDENT_COMPILE_FAILURE = "student_compile_failure"  # submission's fault
    STUDENT_TIMEOUT = "student_timeout"  # submission's fault
    INCONCLUSIVE_EVIDENCE = "inconclusive_evidence"  # evidence genuinely ambiguous

    @property
    def is_student_attributable(self) -> bool:
        return self in (MissingReason.STUDENT_COMPILE_FAILURE, MissingReason.STUDENT_TIMEOUT)

    @property
    def is_host_attributable(self) -> bool:
        return self in (MissingReason.HOST_TOOL_UNAVAILABLE, MissingReason.ANALYZER_ERROR)


class AnalyzerResult(BaseModel):
    analyzer_id: str
    metric_name: str
    status: ResultStatus
    # Score is a fraction in [0, 1]; present exactly when the metric was scored.
    score: Decimal | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    feedback: str = ""
    confidence: Decimal | None = None
    missing_reason: MissingReason = MissingReason.NONE
    diagnostics: list[str] = Field(default_factory=list)
    tool_metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _score_consistency(self) -> AnalyzerResult:
        scored = self.status in (ResultStatus.PASSED, ResultStatus.FAILED)
        if scored and self.score is None:
            raise ValueError(f"{self.metric_name}: scored status {self.status} requires a score")
        if not scored and self.score is not None:
            raise ValueError(f"{self.metric_name}: status {self.status} must not carry a score")
        if self.score is not None and not (Decimal(0) <= self.score <= Decimal(1)):
            raise ValueError(f"{self.metric_name}: score {self.score} outside [0, 1]")
        if scored and self.missing_reason is not MissingReason.NONE:
            raise ValueError(f"{self.metric_name}: scored result cannot have a missing_reason")
        if not scored and self.missing_reason is MissingReason.NONE:
            raise ValueError(f"{self.metric_name}: unscored result must state a missing_reason")
        return self
