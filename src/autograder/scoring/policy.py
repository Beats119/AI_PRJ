"""D-3 missing-evidence policy (approved by Khushi, 2026-10-22).

There is NO universal weight redistribution. Treatment depends on why a
metric has no score and on whether the metric is CORE or OPTIONAL:

  case 1  CORE (correctness) evidence insufficient -> incomplete, no grade
  case 2  REQUIRED metric blocked by the host/tool environment
          -> incomplete (environment), no grade, no redistribution
  case 3  OPTIONAL metric unavailable -> excluded; effective weights are
          renormalized over the graded metrics ONLY in this case, disclosed
  case 4  Metric skipped because of the STUDENT's submission (compile
          failure, smoke timeout) -> partial grade from contributions
          actually earned; achievable maximum and coverage disclosed
  case 5  REQUIRED metric inconclusive -> provisional, no ordinary grade,
          unless its rules entry declares advisory_exclude (then case 3)

Every outcome discloses configured weights, actual contributions, effective
weights where applicable, and metric coverage.
"""

from __future__ import annotations

CASE_DESCRIPTIONS = {
    1: "insufficient trusted correctness evidence",
    2: "required metric unavailable due to host/tool environment",
    3: "optional metric unavailable and excluded",
    4: "metric skipped due to the submission (partial result)",
    5: "required metric inconclusive",
}
