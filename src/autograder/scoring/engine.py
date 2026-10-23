"""Deterministic scoring engine (see scoring/policy.py for the D-3 matrix).

Pure function of (rules, analyzer results): same inputs -> same outcome.
All arithmetic is Decimal; grades round half-up to 1 decimal place.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from autograder.config.schema import Rules
from autograder.models.analysis import AnalyzerResult, MissingReason, ResultStatus
from autograder.models.report import MetricBreakdown, OverallStatus

POLICY_VERSION = "d3-v1"

_ONE_DP = Decimal("0.1")
_HUNDRED = Decimal(100)


class ScoringOutcome(BaseModel):
    overall_status: OverallStatus
    overall_grade: Decimal | None = None
    breakdown: list[MetricBreakdown] = Field(default_factory=list)
    metric_coverage: Decimal = Decimal(0)
    cases_applied: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    policy_version: str = POLICY_VERSION


def _is_scored(r: AnalyzerResult) -> bool:
    return r.status in (ResultStatus.PASSED, ResultStatus.FAILED) and r.score is not None


def score_results(rules: Rules, results: list[AnalyzerResult]) -> ScoringOutcome:
    by_metric: dict[str, AnalyzerResult] = {}
    for r in results:
        if r.metric_name in by_metric:
            raise ValueError(f"duplicate analyzer result for metric '{r.metric_name}'")
        by_metric[r.metric_name] = r
    unknown = set(by_metric) - {m.name for m in rules.metrics}
    if unknown:
        raise ValueError(f"analyzer results for metrics not in rules: {sorted(unknown)}")

    total_cfg = sum((m.weight for m in rules.metrics), Decimal(0))
    cases: set[int] = set()
    notes: list[str] = []

    # Partition every configured metric.
    scored: dict[str, AnalyzerResult] = {}
    optional_excluded: list[str] = []  # case 3
    student_skipped: list[str] = []  # case 4
    host_blocked_required: list[str] = []  # case 2
    inconclusive_required: list[str] = []  # case 5
    core_insufficient = False  # case 1

    for m in rules.metrics:
        r = by_metric.get(m.name)
        if r is None:
            # No result at all for a configured metric: an evaluation
            # integrity problem, treated as host/analyzer failure.
            if m.name == "correctness":
                core_insufficient = True
                cases.add(1)
            elif m.required:
                host_blocked_required.append(m.name)
                cases.add(2)
            else:
                optional_excluded.append(m.name)
                cases.add(3)
            continue
        if _is_scored(r):
            scored[m.name] = r
            continue
        reason = r.missing_reason
        if reason is MissingReason.INSUFFICIENT_EVIDENCE:
            if m.name == "correctness":
                core_insufficient = True
                cases.add(1)
            elif m.required:
                host_blocked_required.append(m.name)
                cases.add(2)
            else:
                optional_excluded.append(m.name)
                cases.add(3)
        elif reason.is_student_attributable:
            student_skipped.append(m.name)
            cases.add(4)
        elif reason is MissingReason.INCONCLUSIVE_EVIDENCE or (
            r.status is ResultStatus.INCONCLUSIVE
        ):
            if not m.required:
                optional_excluded.append(m.name)
                cases.add(3)
            elif m.inconclusive_treatment == "advisory_exclude":
                optional_excluded.append(m.name)
                cases.add(3)
                notes.append(
                    f"metric '{m.name}' inconclusive; excluded under its declared "
                    "inconclusive_treatment=advisory_exclude (D-3 case 3)"
                )
            else:
                inconclusive_required.append(m.name)
                cases.add(5)
        elif reason.is_host_attributable:
            if m.required:
                host_blocked_required.append(m.name)
                cases.add(2)
            else:
                optional_excluded.append(m.name)
                cases.add(3)
        else:  # pragma: no cover - model validation makes this unreachable
            raise ValueError(f"metric '{m.name}': unscored result without a known reason")

    graded_cfg = sum(
        (m.weight for m in rules.metrics if m.name in scored), Decimal(0)
    )
    coverage = (graded_cfg / total_cfg) if total_cfg else Decimal(0)

    def breakdown(effective: dict[str, Decimal | None], contributions: dict[str, Decimal | None]):
        rows = []
        for m in rules.metrics:
            r = by_metric.get(m.name)
            rows.append(
                MetricBreakdown(
                    name=m.name,
                    configured_weight=m.weight,
                    status=(r.status.value if r else "missing"),
                    score=(r.score if r else None),
                    contribution=contributions.get(m.name),
                    effective_weight=effective.get(m.name),
                    note=(r.feedback if r else "no analyzer result was produced"),
                )
            )
        return rows

    no_grade = dict.fromkeys([m.name for m in rules.metrics], None)

    # Case 1 and case 2 block any grade.
    if core_insufficient or host_blocked_required:
        if core_insufficient:
            notes.append("D-3 case 1: insufficient trusted correctness evidence")
        if host_blocked_required:
            notes.append(
                "D-3 case 2: required metrics unavailable due to host/tool: "
                + ", ".join(sorted(host_blocked_required))
            )
        return ScoringOutcome(
            overall_status=OverallStatus.INCOMPLETE,
            overall_grade=None,
            breakdown=breakdown(no_grade, no_grade),
            metric_coverage=coverage,
            cases_applied=sorted(cases),
            notes=notes,
        )

    # Case 5 blocks an ordinary grade.
    if inconclusive_required:
        notes.append(
            "D-3 case 5: required metrics inconclusive: "
            + ", ".join(sorted(inconclusive_required))
        )
        return ScoringOutcome(
            overall_status=OverallStatus.PROVISIONAL,
            overall_grade=None,
            breakdown=breakdown(no_grade, no_grade),
            metric_coverage=coverage,
            cases_applied=sorted(cases),
            notes=notes,
        )

    if not scored:
        notes.append("no metric produced a score; nothing can be graded")
        return ScoringOutcome(
            overall_status=OverallStatus.INCOMPLETE,
            overall_grade=None,
            breakdown=breakdown(no_grade, no_grade),
            metric_coverage=coverage,
            cases_applied=sorted(cases),
            notes=notes,
        )

    # A grade is presented. Two shapes:
    #  - case 4 present (student-attributable skips): PARTIAL, no
    #    renormalization; contributions use configured weights and
    #    student-skipped metrics contribute 0 under this disclosed policy.
    #  - otherwise: COMPLETE, with case-3 renormalization when optional
    #    metrics were excluded.
    if student_skipped:
        effective: dict[str, Decimal | None] = {}
        contributions: dict[str, Decimal | None] = {}
        total = Decimal(0)
        for m in rules.metrics:
            if m.name in scored:
                effective[m.name] = m.weight
                c = scored[m.name].score * m.weight * _HUNDRED
                contributions[m.name] = c
                total += c
            elif m.name in student_skipped:
                effective[m.name] = m.weight
                contributions[m.name] = Decimal(0)
            else:
                effective[m.name] = None
                contributions[m.name] = None
        notes.append(
            "D-3 case 4: partial grade; execution-dependent metrics skipped because of "
            "the submission contribute 0 under this disclosed policy"
        )
        status = OverallStatus.PARTIAL
    else:
        denom = graded_cfg  # scored metrics only; optional exclusions removed
        effective = {}
        contributions = {}
        total = Decimal(0)
        for m in rules.metrics:
            if m.name in scored:
                eff = (m.weight / denom) if denom else Decimal(0)
                effective[m.name] = eff
                c = scored[m.name].score * eff * _HUNDRED
                contributions[m.name] = c
                total += c
            else:
                effective[m.name] = None
                contributions[m.name] = None
        if optional_excluded:
            notes.append(
                "D-3 case 3: optional metrics excluded and weights renormalized over "
                "graded metrics: " + ", ".join(sorted(optional_excluded))
            )
        status = OverallStatus.COMPLETE

    grade = total.quantize(_ONE_DP, rounding=ROUND_HALF_UP)
    if not (Decimal(0) <= grade <= _HUNDRED):
        raise ValueError(f"computed grade {grade} outside [0, 100]")
    return ScoringOutcome(
        overall_status=status,
        overall_grade=grade,
        breakdown=breakdown(effective, contributions),
        metric_coverage=coverage,
        cases_applied=sorted(cases),
        notes=notes,
    )
