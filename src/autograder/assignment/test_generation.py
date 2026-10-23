"""Bounded test-candidate generation (D-2: 1 round, <=40 candidates, <=2 LLM calls).

Candidates are NOT trusted tests. Expected outputs are deliberately left
empty here; the oracle (oracle.py) establishes — or refuses — trust.
Sources:
  * a deterministic generator registered for the assignment's generator id
  * optionally, ONE bounded LLM test-proposal call; the LLM's proposed
    expected outputs are recorded as unverified and never become trust
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from autograder.assignment.specification import AssignmentPackage
from autograder.config.schema import GenerationConfig
from autograder.llm.client import LLMClient, LLMUnavailable
from autograder.models.tests import TestCase, TrustStatus

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


@dataclass
class GenerationReport:
    rounds: int = 1
    generated: int = 0
    kept: int = 0
    discarded_duplicates: int = 0
    discarded_invalid: int = 0
    discarded_over_cap: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    llm_candidates_proposed: int = 0
    notes: list[str] = field(default_factory=list)


def _int_pair_inputs(lo: int, hi: int) -> list[tuple[str, str]]:
    """(category, input) pairs for two-integer problems, fixed + deterministic."""
    pairs: list[tuple[str, str]] = []
    ordinary = [(7, 5), (2, 3), (10, 20), (100, 250), (1, 1), (42, 58)]
    minimum = [(lo, lo), (lo, 0), (lo, 1)]
    maximum = [(hi, hi), (hi, 0), (hi, -1)]
    edge = [(0, 0), (0, 5), (-1, 1), (-7, -8), (5, -5), (-100, 100)]
    large = [(2_000_000_000, 2_000_000_000), (hi, 1), (lo, -1)]
    for a, b in ordinary:
        pairs.append(("ordinary_valid", f"{a} {b}\n"))
    for a, b in minimum:
        pairs.append(("minimum_boundary", f"{a} {b}\n"))
    for a, b in maximum:
        pairs.append(("maximum_boundary", f"{a} {b}\n"))
    for a, b in edge:
        pairs.append(("edge_values", f"{a} {b}\n"))
    for text in ("7    5\n", "  12   30  \n", "9\t4\n"):
        pairs.append(("parsing_whitespace", text))
    for a, b in large:
        pairs.append(("large_operands", f"{a} {b}\n"))
    return pairs


def parse_int_pair(input_data: str, lo: int, hi: int) -> tuple[int, int] | None:
    parts = input_data.split()
    if len(parts) != 2:
        return None
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (lo <= a <= hi and lo <= b <= hi):
        return None
    return a, b


def _llm_candidates(
    client: LLMClient, package: AssignmentPackage, report: GenerationReport
) -> list[tuple[str, str, str | None]]:
    """One bounded proposal call -> (category, input, llm_expected_or_None).

    The returned expected values are the LLM's claims. They are carried as
    unverified data only; the oracle never trusts them directly.
    """
    prompt = (
        "You are proposing test INPUTS for a programming assignment.\n"
        f"Problem: {package.statement_sections.get('problem', '')}\n"
        f"Input format: {package.statement_sections.get('input', '')}\n"
        "Reply with a JSON array of objects {\"input\": \"...\", "
        "\"expected\": \"...\", \"category\": \"edge_values\"} with at most 5 items. "
        "JSON only, no commentary."
    )
    try:
        text = client.generate("test_proposal", prompt)
    except LLMUnavailable as exc:
        report.notes.append(f"LLM test proposal unavailable: {exc}")
        return []
    try:
        items = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        report.notes.append("LLM test proposal was not valid JSON; discarded")
        return []
    out: list[tuple[str, str, str | None]] = []
    for item in items[:5]:
        if isinstance(item, dict) and isinstance(item.get("input"), str):
            out.append(
                (
                    str(item.get("category", "edge_values")),
                    item["input"],
                    item.get("expected") if isinstance(item.get("expected"), str) else None,
                )
            )
    report.llm_candidates_proposed = len(out)
    return out


def generate_candidates(
    package: AssignmentPackage,
    gen_cfg: GenerationConfig,
    llm_client: LLMClient | None = None,
    use_llm: bool = False,
    existing_inputs: set[str] | None = None,
) -> tuple[list[TestCase], GenerationReport]:
    report = GenerationReport(rounds=1)
    lo = package.config.input_min if package.config.input_min is not None else INT32_MIN
    hi = package.config.input_max if package.config.input_max is not None else INT32_MAX
    raw: list[tuple[str, str, str | None, str]] = []  # category, input, llm_expected, source

    if package.config.generator == "int_pair_v1":
        for category, text in _int_pair_inputs(lo, hi):
            raw.append((category, text, None, "deterministic_generator:int_pair_v1"))
    if use_llm and llm_client is not None:
        for category, text, expected in _llm_candidates(llm_client, package, report):
            raw.append((category, text, expected, "llm_proposal"))

    seen: set[str] = set(existing_inputs or set())
    candidates: list[TestCase] = []
    per_category: dict[str, int] = {}
    seq = 0
    for category, text, llm_expected, source in raw:
        report.generated += 1
        normalized = " ".join(text.split())
        if normalized in seen:
            report.discarded_duplicates += 1
            continue
        if package.config.generator == "int_pair_v1" and parse_int_pair(text, lo, hi) is None:
            report.discarded_invalid += 1
            continue
        if len(candidates) >= gen_cfg.max_candidates:
            report.discarded_over_cap += 1
            continue
        if per_category.get(category, 0) >= gen_cfg.max_candidates_per_category:
            report.discarded_over_cap += 1
            continue
        seen.add(normalized)
        seq += 1
        per_category[category] = per_category.get(category, 0) + 1
        report.by_category[category] = per_category[category]
        candidates.append(
            TestCase(
                test_id=f"gen-{seq:03d}",
                input_data=text,
                expected_output=llm_expected,  # unverified claim, if any
                category=category,
                trust_status=TrustStatus.UNTRUSTED,
                provenance=source,
                validation_method="llm_unverified" if source == "llm_proposal" else "none",
                comparison_policy=package.config.comparison_policy,
                requirement_coverage=category,
            )
        )
    report.kept = len(candidates)
    return candidates, report
