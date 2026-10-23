"""Deterministic output comparison policies (shared by oracle + analyzers)."""

from __future__ import annotations

from autograder.models.tests import ComparisonPolicy


def _normalize_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def compare_outputs(
    expected: str, actual: str, policy: ComparisonPolicy, tolerance: float = 1e-6
) -> bool:
    if policy is ComparisonPolicy.EXACT:
        return expected == actual
    if policy is ComparisonPolicy.WHITESPACE_NORMALIZED:
        return _normalize_whitespace(expected) == _normalize_whitespace(actual)
    if policy is ComparisonPolicy.NUMERIC_TOLERANCE:
        try:
            e = [float(x) for x in expected.split()]
            a = [float(x) for x in actual.split()]
        except ValueError:
            return False
        if len(e) != len(a):
            return False
        return all(
            abs(x - y) <= tolerance * max(1.0, abs(x), abs(y)) for x, y in zip(e, a, strict=True)
        )
    raise ValueError(f"unknown comparison policy {policy}")
