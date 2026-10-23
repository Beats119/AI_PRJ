"""Structure (static_analysis) and modularity (function_split) metrics.

Both use the deterministic heuristic C parser in c_source.py (cppcheck and
lizard are not required; when absent, that absence is recorded, not hidden).

Structure scoring: the fraction of functions violating neither the
cyclomatic nor the length threshold. Every violation produces a per-function
finding with a concrete fix suggestion (the handwritten 'Extras' requirement:
per-function review with fixes).

Modularity scoring: min(1, function_count / min_functions) — main() alone
cannot reach 1.0 when the rules expect helper functions.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from autograder.analyzers.c_source import parse_source
from autograder.models.analysis import (
    AnalyzerResult,
    MissingReason,
    ResultStatus,
)


def _read(source_path: str | Path) -> str:
    return Path(source_path).read_text(encoding="utf-8", errors="replace")


def analyze_structure(
    source_path: str | Path, *, max_cyclomatic: int = 8, max_function_length: int = 40
) -> AnalyzerResult:
    info = parse_source(_read(source_path))
    if not info.functions:
        return AnalyzerResult(
            analyzer_id="static_analysis",
            metric_name="structure",
            status=ResultStatus.INCONCLUSIVE,
            missing_reason=MissingReason.INCONCLUSIVE_EVIDENCE,
            diagnostics=[
                (
                    "no function definitions could be identified by the heuristic "
                    "parser; structure cannot be assessed"
                )
            ],
            evidence={"parser": "builtin-heuristic", "functions": []},
        )
    findings: list[dict] = []
    clean = 0
    for fn in info.functions:
        problems: list[str] = []
        fixes: list[str] = []
        if fn.cyclomatic > max_cyclomatic:
            problems.append(f"cyclomatic complexity {fn.cyclomatic} > {max_cyclomatic}")
            fixes.append(
                f"reduce branching in {fn.name}: extract conditions into helper "
                "functions or a lookup table"
            )
        if fn.line_count > max_function_length:
            problems.append(f"length {fn.line_count} lines > {max_function_length}")
            fixes.append(
                f"split {fn.name} ({fn.line_count} lines) into smaller helpers, "
                "e.g. separate input, computation and output"
            )
        if not problems:
            clean += 1
        findings.append(
            {
                "function": fn.name,
                "lines": fn.line_count,
                "cyclomatic": fn.cyclomatic,
                "problems": problems,
                "suggested_fixes": fixes,
            }
        )
    score = Decimal(clean) / Decimal(len(info.functions))
    worst = max(findings, key=lambda f: f["cyclomatic"])
    feedback = (
        f"{clean}/{len(info.functions)} functions within thresholds "
        f"(cyclomatic <= {max_cyclomatic}, length <= {max_function_length} lines). "
        f"Most complex: {worst['function']} (cyclomatic {worst['cyclomatic']})."
    )
    return AnalyzerResult(
        analyzer_id="static_analysis",
        metric_name="structure",
        status=ResultStatus.PASSED if score == 1 else ResultStatus.FAILED,
        score=score,
        feedback=feedback,
        evidence={
            "parser": "builtin-heuristic (cppcheck/lizard not required)",
            "max_cyclomatic": max_cyclomatic,
            "max_function_length": max_function_length,
            "functions": findings,
        },
    )


def analyze_modularity(
    source_path: str | Path, *, min_functions: int = 2, expect_helpers: bool = True
) -> AnalyzerResult:
    info = parse_source(_read(source_path))
    names = [f.name for f in info.functions]
    helpers = [n for n in names if n != "main"]
    total = len(names)
    score = min(Decimal(1), Decimal(total) / Decimal(max(1, min_functions)))
    if expect_helpers and total > 0 and not helpers:
        score = min(score, Decimal("0.5"))
    feedback = (
        f"found {total} function(s) ({', '.join(names) or 'none'}); "
        f"the rules expect at least {min_functions}"
        + (" including helper functions." if expect_helpers else ".")
    )
    if total == 0:
        return AnalyzerResult(
            analyzer_id="function_split",
            metric_name="modularity",
            status=ResultStatus.FAILED,
            score=Decimal(0),
            feedback="no functions could be identified in the submission",
            evidence={"functions": [], "helpers": []},
        )
    return AnalyzerResult(
        analyzer_id="function_split",
        metric_name="modularity",
        status=ResultStatus.PASSED if score == 1 else ResultStatus.FAILED,
        score=score,
        feedback=feedback,
        evidence={"functions": names, "helpers": helpers, "min_functions": min_functions},
    )
