"""Complexity metric (complexity_estimator).

Two evidence legs, both deterministic:
  * static: heuristic loop-nesting / recursion analysis of the source.
    A loop counts toward the estimate only when its header references a
    variable (constant-bound loops are O(1) work). Nesting depth d maps to
    O(n^d); a self-recursive function is at least O(n).
  * empirical: growth classification of measured runtimes, when a caller
    supplies timings (log-log slope + model residuals). Timings below the
    reliable timer resolution, or fits with poor R^2, are INCONCLUSIVE —
    the analyzer never fabricates a class from noise.
If both legs exist and disagree, the result is INCONCLUSIVE with both
recorded. Scoring vs the required class: equal-or-better = 1.0, each class
step worse deducts 0.25 (floor 0).
"""

from __future__ import annotations

import math
import re
import statistics
from decimal import Decimal
from pathlib import Path

from autograder.analyzers.c_source import parse_source
from autograder.models.analysis import (
    AnalyzerResult,
    MissingReason,
    ResultStatus,
)

CLASS_ORDER = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)"]
_MIN_RELIABLE_S = 1e-4  # 0.1 ms: below this, wall timings are noise here


def static_estimate(source_text: str) -> tuple[str, dict]:
    info = parse_source(source_text)
    max_var_depth = 0
    recursion = False
    details: list[dict] = []
    for fn in info.functions:
        depth = _max_variable_loop_depth(fn.body)
        max_var_depth = max(max_var_depth, depth)
        self_call = re.search(rf"\b{re.escape(fn.name)}\s*\(", fn.body) is not None
        recursion = recursion or self_call
        details.append(
            {"function": fn.name, "loop_depth": depth, "recursive": self_call}
        )
    if max_var_depth >= 3:
        estimate = "O(n^3)"
    elif max_var_depth == 2:
        estimate = "O(n^2)"
    elif max_var_depth == 1 or recursion:
        estimate = "O(n)"
    else:
        estimate = "O(1)"
    return estimate, {"functions": details, "method": "static loop-nesting heuristic"}


def _max_variable_loop_depth(body: str) -> int:
    """Max nesting of loops whose header mentions a variable (not literals only)."""
    max_depth = 0
    # tokenize crudely: loop keywords with their parenthesized header, and braces
    token_re = re.compile(r"\b(for|while)\s*\(([^)]*)\)|[{}]|\bdo\b")
    loop_stack: list[bool] = []  # per open brace: did a loop start it?
    pending_loop_var = False
    for m in token_re.finditer(body):
        tok = m.group(0)
        if m.group(1):
            header = m.group(2)
            pending_loop_var = bool(
                re.search(r"[A-Za-z_]", header)
            )  # any identifier => treated as size-dependent
        elif tok == "do":
            pending_loop_var = True
        elif tok == "{":
            loop_stack.append(pending_loop_var)
            if pending_loop_var:
                depth_now = sum(1 for x in loop_stack if x)
                max_depth = max(max_depth, depth_now)
            pending_loop_var = False
        elif tok == "}":
            if loop_stack:
                loop_stack.pop()
    return max_depth


def classify_growth(sizes: list[int], times: list[float]) -> tuple[str | None, dict]:
    """Empirical class from measured times, or (None, evidence) if unreliable."""
    evidence: dict = {"sizes": sizes, "times_s": times}
    if len(sizes) < 3 or len(sizes) != len(times):
        evidence["reason"] = "need at least 3 (size, time) points"
        return None, evidence
    if max(times) < _MIN_RELIABLE_S:
        evidence["reason"] = (
            f"all runtimes below the reliable timer resolution "
            f"({_MIN_RELIABLE_S}s); empirical classification would be noise"
        )
        return None, evidence
    if min(times) <= 0:
        evidence["reason"] = "non-positive timing recorded"
        return None, evidence
    xs = [math.log(s) for s in sizes]
    ys = [math.log(t) for t in times]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sxy / sxx if sxx else 0.0
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum(
        (y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys, strict=True)
    )
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    evidence.update({"loglog_slope": slope, "fit_r2": r2})
    if ss_tot == 0:
        return "O(1)", evidence  # perfectly constant timings
    mean_t = sum(times) / len(times)
    cv = (statistics.pstdev(times) / mean_t) if mean_t else 0.0
    if slope <= 0.3 and cv < 0.05:
        return "O(1)", evidence  # flat within measurement noise
    if r2 < 0.8:
        evidence["reason"] = "growth fit too noisy (R^2 < 0.8)"
        return None, evidence
    if slope <= 0.3:
        return "O(1)", evidence
    if slope <= 1.3:
        # O(n) vs O(n log n): compare relative residuals of the two models
        def _rel_resid(model):
            errs = [
                abs((t - model(s)) / t) for s, t in zip(sizes, times, strict=True)
            ]
            return sum(errs) / len(errs)

        c_n = times[0] / sizes[0]
        c_nl = times[0] / (sizes[0] * math.log2(sizes[0]))
        if _rel_resid(lambda s: c_n * s) <= _rel_resid(
            lambda s: c_nl * s * math.log2(s)
        ):
            return "O(n)", evidence
        return "O(n log n)", evidence
    if 1.7 <= slope <= 2.3:
        return "O(n^2)", evidence
    evidence["reason"] = f"slope {slope:.2f} does not match a modelled class"
    return None, evidence


def _score_vs_required(estimate: str, required: str) -> Decimal:
    try:
        diff = CLASS_ORDER.index(estimate) - CLASS_ORDER.index(required)
    except ValueError:
        return Decimal(0)
    if diff <= 0:
        return Decimal(1)
    return max(Decimal(0), Decimal(1) - Decimal("0.25") * diff)


def analyze_complexity(
    source_path: str | Path,
    *,
    required: str = "O(1)",
    timings: tuple[list[int], list[float]] | None = None,
) -> AnalyzerResult:
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    static_class, static_ev = static_estimate(text)
    evidence: dict = {"static": static_ev, "required": required}
    estimate = static_class
    if timings is not None:
        emp_class, emp_ev = classify_growth(timings[0], timings[1])
        evidence["empirical"] = emp_ev
        if emp_class is None:
            evidence["empirical_note"] = (
                "empirical leg inconclusive; static estimate used, "
                "empirical limitation recorded"
            )
        elif emp_class != static_class:
            return AnalyzerResult(
                analyzer_id="complexity_estimator",
                metric_name="complexity",
                status=ResultStatus.INCONCLUSIVE,
                missing_reason=MissingReason.INCONCLUSIVE_EVIDENCE,
                feedback=(
                    f"static analysis suggests {static_class} but measured growth "
                    f"suggests {emp_class}; refusing to pick one"
                ),
                evidence=evidence,
            )
    score = _score_vs_required(estimate, required)
    return AnalyzerResult(
        analyzer_id="complexity_estimator",
        metric_name="complexity",
        status=ResultStatus.PASSED if score == 1 else ResultStatus.FAILED,
        score=score,
        feedback=(
            f"estimated complexity {estimate} (static heuristic"
            + (", confirmed empirically" if timings and "empirical" in evidence
               and evidence.get("empirical", {}).get("reason") is None else "")
            + f"); required {required}"
        ),
        evidence={**evidence, "estimated": estimate},
    )
