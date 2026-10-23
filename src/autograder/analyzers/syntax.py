"""Syntax metric (compiler_warnings): warning/error evidence from gcc.

Scoring (deterministic): compile once with the rules' strict flags
(-Werror: a clean strict compile scores 1.0) and once without -Werror to
count warnings and true errors.
  * any true error          -> 0.0
  * w warnings, no errors    -> max(0, 1 - 0.2*w)
  * clean                    -> 1.0
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from autograder.models.analysis import AnalyzerResult, ResultStatus
from autograder.sandbox.compiler import compile_source

_DEFAULT_FLAGS = "-Wall -Wextra -Werror -std=c11"


def analyze_syntax(
    source_path: str | Path, *, work_dir: str | Path, flags: str = _DEFAULT_FLAGS
) -> AnalyzerResult:
    work = Path(work_dir)
    strict = compile_source(source_path, work / "strict", flags=flags)
    relaxed_flags = flags.replace("-Werror", "").strip()
    relaxed = compile_source(source_path, work / "relaxed", flags=relaxed_flags or "-std=c11")
    diag = relaxed.diagnostics
    warnings = re.findall(r"warning:", diag)
    errors = re.findall(r"(?<!W)error:", diag)
    warning_lines = [
        line.strip() for line in diag.splitlines() if "warning:" in line
    ][:10]
    if errors:
        score, status = Decimal(0), ResultStatus.FAILED
        feedback = f"compilation produces {len(errors)} error(s) under {flags}"
    elif warnings:
        score = max(Decimal(0), Decimal(1) - Decimal("0.2") * len(warnings))
        status = ResultStatus.FAILED
        feedback = (
            f"{len(warnings)} compiler warning(s) under {flags}: "
            + "; ".join(warning_lines[:3])
        )
    else:
        score, status = Decimal(1), ResultStatus.PASSED
        feedback = f"clean compile under {flags} (warnings are errors)"
    return AnalyzerResult(
        analyzer_id="compiler_warnings",
        metric_name="syntax",
        status=status,
        score=score,
        feedback=feedback,
        evidence={
            "flags": flags,
            "strict_werror_compile_passed": strict.success,
            "warnings": len(warnings),
            "errors": len(errors),
            "warning_lines": warning_lines,
            "diagnostics_excerpt": diag[:2000],
        },
    )
