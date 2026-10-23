"""Readability metric (llm_review id) — deterministic scored core (D-4).

The SCORE comes only from deterministic code-quality checks below; each
deducts a fixed, documented amount and emits a finding with a fix. An LLM
may optionally add advisory prose (configs: llm_advisory), which is stored
in the evidence labelled advisory-only and can never change the score.

Deterministic rubric (start 1.0):
  * lines longer than 100 chars          -0.05 each, capped at -0.20
  * comment ratio < 5% on >20 code lines -0.20
  * >half of variable identifiers are
    single letters                       -0.20
  * magic numbers (literals other than
    0/1/2/-1), beyond 3                  -0.05 each beyond 3, capped -0.20
  * no function carries any comment and
    there are >=2 functions              -0.10
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from autograder.analyzers.c_source import identifiers, numeric_literals, parse_source
from autograder.llm.client import LLMClient, LLMUnavailable
from autograder.models.analysis import AnalyzerResult, ResultStatus

_ALLOWED_LITERALS = {"0", "1", "2"}


def analyze_readability(
    source_path: str | Path,
    *,
    llm_client: LLMClient | None = None,
    llm_advisory: bool = False,
) -> AnalyzerResult:
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    info = parse_source(text)
    findings: list[dict] = []
    deductions = Decimal(0)

    long_lines = [i + 1 for i, line in enumerate(text.splitlines()) if len(line) > 100]
    if long_lines:
        d = min(Decimal("0.20"), Decimal("0.05") * len(long_lines))
        deductions += d
        findings.append(
            {
                "check": "line_length",
                "detail": f"{len(long_lines)} line(s) over 100 chars: {long_lines[:5]}",
                "fix": "wrap long expressions; one statement per line",
                "deduction": str(d),
            }
        )

    code_lines = info.code_lines
    comment_ratio = (info.comment_lines / code_lines) if code_lines else 0.0
    if code_lines > 20 and comment_ratio < 0.05:
        deductions += Decimal("0.20")
        findings.append(
            {
                "check": "comments",
                "detail": f"comment ratio {comment_ratio:.0%} over {code_lines} code lines",
                "fix": "add brief comments explaining intent at function heads "
                "and non-obvious blocks",
                "deduction": "0.20",
            }
        )

    ids = identifiers(info.stripped)
    var_ids = [i for i in ids if i not in {f.name for f in info.functions}]
    single = [i for i in var_ids if len(i) == 1]
    if var_ids and len(single) / len(var_ids) > 0.5:
        deductions += Decimal("0.20")
        findings.append(
            {
                "check": "naming",
                "detail": f"{len(single)}/{len(var_ids)} variables have single-letter "
                f"names ({sorted(set(single))[:6]})",
                "fix": "use descriptive names (e.g. lhs/rhs or first/second) so "
                "the code reads without a legend",
                "deduction": "0.20",
            }
        )

    magic = [n for n in numeric_literals(info.stripped) if n not in _ALLOWED_LITERALS]
    if len(magic) > 3:
        d = min(Decimal("0.20"), Decimal("0.05") * (len(magic) - 3))
        deductions += d
        findings.append(
            {
                "check": "magic_numbers",
                "detail": f"{len(magic)} unexplained numeric literals ({magic[:6]})",
                "fix": "name repeated constants with #define or const so their "
                "meaning is visible",
                "deduction": str(d),
            }
        )

    if len(info.functions) >= 2 and info.comment_lines == 0:
        deductions += Decimal("0.10")
        findings.append(
            {
                "check": "function_comments",
                "detail": "no comments anywhere in a multi-function file",
                "fix": "one short comment per function stating what it does",
                "deduction": "0.10",
            }
        )

    score = max(Decimal(0), Decimal(1) - deductions)
    evidence: dict = {
        "rubric": "deterministic deductions, documented in analyzers/readability.py",
        "findings": findings,
        "code_lines": code_lines,
        "comment_lines": info.comment_lines,
    }
    feedback = (
        "deterministic readability checks: "
        + ("; ".join(f["detail"] for f in findings[:3])
           if findings else "no issues found")
    )
    if llm_advisory and llm_client is not None:
        try:
            advisory = llm_client.generate(
                "readability",
                "Review this C code briefly for readability; list the three "
                "most useful improvements. Code:\n" + text[:6000],
            )
            evidence["llm_advisory"] = {
                "text": advisory[:2000],
                "note": "ADVISORY ONLY (D-4): this text never affects the score",
                "transport": llm_client.usage.calls[-1].transport
                if llm_client.usage.calls else "unknown",
            }
        except LLMUnavailable as exc:
            evidence["llm_advisory"] = {"unavailable": str(exc)}
    return AnalyzerResult(
        analyzer_id="llm_review",
        metric_name="readability",
        status=ResultStatus.PASSED if score == 1 else ResultStatus.FAILED,
        score=score,
        feedback=feedback,
        evidence=evidence,
    )
