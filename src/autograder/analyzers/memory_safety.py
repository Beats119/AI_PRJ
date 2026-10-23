"""Memory safety metric (sanitizer_run): ASan + UBSan over trusted tests.

Honesty rules:
  * The sanitizer toolchain is probed first (compile + run a trivial
    program). If it does not work on this host, the result is an
    ENVIRONMENT error (host tool unavailable) — the student is never
    scored for our missing tools.
  * Instrumented binaries reserve a huge virtual address space, so the
    address-space limit is explicitly disabled for these runs; CPU time,
    wall-clock timeout, output caps and the process-group kill still apply.
    Leak detection runs with ASan defaults (leaks are findings).
  * A test counts clean only if its run finishes without any sanitizer
    report. Findings quote the sanitizer's own summary lines.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from autograder.models.analysis import (
    AnalyzerResult,
    MissingReason,
    ResultStatus,
)
from autograder.models.execution import ExecutionStatus
from autograder.models.tests import TestCase
from autograder.sandbox.executor import Sandbox, run_program
from autograder.sandbox.limits import ExecutionLimits

_PROBE = "int main(void){ return 0; }\n"
_SANITIZER_MARKS = ("AddressSanitizer", "LeakSanitizer", "runtime error:", "UndefinedBehaviorSanitizer")


def _probe(sandbox: Sandbox, flags: str) -> tuple[bool, str]:
    probe_src = sandbox.workspace / "probe_src.c"
    probe_src.write_text(_PROBE)
    comp = sandbox.compile(probe_src, flags=f"-O1 -g {flags}", binary_name="probe")
    if not comp.success:
        return False, f"sanitizer probe failed to compile: {comp.diagnostics[:300]}"
    res = sandbox.run(
        comp.binary_path, test_id="probe", submission_hash=comp.source_hash,
        limits=ExecutionLimits(
            wall_time_s=5.0, apply_memory_limit=False
        ),
    )
    if res.status is not ExecutionStatus.OK or res.exit_code != 0:
        return False, f"sanitizer probe run failed: status={res.status.value} {res.stderr[:200]}"
    return True, "asan/ubsan probe compiled and ran cleanly"


def analyze_memory_safety(
    source_path: str | Path,
    suite: list[TestCase],
    *,
    sandbox: Sandbox,
    flags: str = "-fsanitize=address,undefined",
) -> AnalyzerResult:
    ok, probe_note = _probe(sandbox, flags)
    if not ok:
        return AnalyzerResult(
            analyzer_id="sanitizer_run",
            metric_name="memory_safety",
            status=ResultStatus.ERROR,
            missing_reason=MissingReason.HOST_TOOL_UNAVAILABLE,
            diagnostics=[probe_note],
            evidence={"probe": probe_note},
        )
    comp = sandbox.compile(
        source_path, flags=f"-O1 -g {flags} -std=c11", binary_name="program_san"
    )
    if not comp.success:
        return AnalyzerResult(
            analyzer_id="sanitizer_run",
            metric_name="memory_safety",
            status=ResultStatus.ERROR,
            missing_reason=MissingReason.ANALYZER_ERROR,
            diagnostics=[
                (
                    "submission could not be built with sanitizers although the "
                    f"probe succeeded: {comp.diagnostics[:300]}"
                )
            ],
            evidence={"probe": probe_note},
        )
    trusted = [t for t in suite if t.counts_as_trusted]
    if not trusted:
        return AnalyzerResult(
            analyzer_id="sanitizer_run",
            metric_name="memory_safety",
            status=ResultStatus.INSUFFICIENT_EVIDENCE,
            missing_reason=MissingReason.INSUFFICIENT_EVIDENCE,
            diagnostics=["no trusted tests available for sanitizer runs"],
            evidence={"probe": probe_note},
        )
    limits = ExecutionLimits(wall_time_s=5.0, apply_memory_limit=False)
    records: list[dict] = []
    infra_errors = 0
    for case in trusted:
        res = run_program(
            comp.binary_path,
            workspace=sandbox.workspace,
            test_id=f"san-{case.test_id}",
            submission_hash=comp.source_hash,
            input_data=case.input_data,
            limits=limits,
        )
        combined = res.stderr + res.stdout
        findings = [
            line.strip()
            for line in combined.splitlines()
            if any(mark in line for mark in _SANITIZER_MARKS)
        ][:4]
        if res.status is ExecutionStatus.TOOL_ERROR:
            infra_errors += 1
            outcome = "infrastructure_error"
        elif findings:
            outcome = "sanitizer_finding"
        elif res.status is not ExecutionStatus.OK:
            outcome = "execution_failure"
            findings = [f"program {res.status.value} under sanitizers"]
        elif res.exit_code not in (0, None):
            outcome = "sanitizer_finding"
            findings = [f"non-zero exit ({res.exit_code}) under sanitizers"]
        else:
            outcome = "clean"
        records.append(
            {
                "test_id": case.test_id,
                "outcome": outcome,
                "findings": findings,
                "summary": _sanitizer_summary(combined),
            }
        )
    if infra_errors == len(records):
        return AnalyzerResult(
            analyzer_id="sanitizer_run",
            metric_name="memory_safety",
            status=ResultStatus.ERROR,
            missing_reason=MissingReason.ANALYZER_ERROR,
            diagnostics=["every sanitizer run failed to execute (infrastructure)"],
            evidence={"probe": probe_note, "records": records},
        )
    clean = sum(1 for r in records if r["outcome"] == "clean")
    total = len(records)
    score = Decimal(clean) / Decimal(total)
    first_bad = next((r for r in records if r["outcome"] != "clean"), None)
    feedback = f"{clean}/{total} trusted tests run clean under ASan+UBSan."
    if first_bad:
        feedback += (
            f" First finding on {first_bad['test_id']}: "
            + ("; ".join(first_bad["findings"]) or first_bad["outcome"])
        )
    return AnalyzerResult(
        analyzer_id="sanitizer_run",
        metric_name="memory_safety",
        status=ResultStatus.PASSED if score == 1 else ResultStatus.FAILED,
        score=score,
        feedback=feedback,
        evidence={
            "probe": probe_note,
            "address_space_limit": "disabled for instrumented runs (ASan "
            "reserves large virtual memory); CPU/wall/output limits still apply",
            "records": records,
        },
    )


def _sanitizer_summary(output: str) -> str | None:
    m = re.search(r"SUMMARY:.*", output)
    return m.group(0).strip() if m else None
