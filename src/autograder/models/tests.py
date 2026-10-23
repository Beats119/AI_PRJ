"""TestCase: one test in an assignment test suite, with its trust record."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class TrustStatus(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"  # invalid: bad input, contradiction, broken oracle


class ComparisonPolicy(str, Enum):
    EXACT = "exact"
    WHITESPACE_NORMALIZED = "whitespace_normalized"
    NUMERIC_TOLERANCE = "numeric_tolerance"


class TestCase(BaseModel):
    __test__ = False  # data contract, not a pytest test class

    test_id: str
    input_data: str
    expected_output: str | None = None  # None when not established
    category: str  # e.g. ordinary_valid, minimum_boundary, edge_values
    trust_status: TrustStatus
    provenance: str  # where the input + expected output came from
    validation_method: str  # e.g. instructor_example, reference_run, derivation, none
    comparison_policy: ComparisonPolicy = ComparisonPolicy.WHITESPACE_NORMALIZED
    requirement_coverage: str = ""

    @property
    def counts_as_trusted(self) -> bool:
        """Only a trusted case with an established expected output may score."""
        return (
            self.trust_status is TrustStatus.TRUSTED
            and self.expected_output is not None
            and self.validation_method != "none"
        )
