"""Profiling + cache-miss measurement (spec F5 / handwritten 'Extras').

This returns a ProfileReport (measurements), not a scored AnalyzerResult:
timings describe the program, they are not by themselves a grade.

Two layers, kept strictly separate in the report:
  * wall-time: always measured by really running the program N times
    through the Stage 5 executor (median/min/max reported).
  * hardware counters (cycles, instructions, cache references/misses):
    attempted only when `perf` is installed AND the kernel lets an
    unprivileged user read counters. The report distinguishes
    measured-zero from unreadable: if perf is missing or the counters come
    back '<not counted>' / permission-denied, cache_counters is None and
    perf_note says exactly why. Nothing is ever estimated or fabricated.
"""

from __future__ import annotations

import re
import shutil
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from autograder.models.execution import ExecutionStatus
from autograder.sandbox.executor import run_program
from autograder.sandbox.limits import ExecutionLimits


@dataclass
class ProfileReport:
    runs: int
    wall_time_ms_median: float | None
    wall_time_ms_min: float | None
    wall_time_ms_max: float | None
    run_statuses: list[str] = field(default_factory=list)
    cache_counters: dict | None = None  # None => unreadable (see perf_note)
    perf_note: str = ""
    input_description: str = ""

    def as_dict(self) -> dict:
        return {
            "runs": self.runs,
            "wall_time_ms": {
                "median": self.wall_time_ms_median,
                "min": self.wall_time_ms_min,
                "max": self.wall_time_ms_max,
            },
            "run_statuses": self.run_statuses,
            "cache_counters": self.cache_counters,
            "perf_note": self.perf_note,
            "input": self.input_description,
        }


def _perf_counters(binary: Path, input_data: str, workspace: Path) -> tuple[dict | None, str]:
    perf = shutil.which("perf")
    if perf is None:
        return None, "perf is not installed on this machine; counters unreadable"
    events = "cycles,instructions,cache-references,cache-misses"
    inp = workspace / "perf_input.txt"
    inp.write_text(input_data)
    try:
        with inp.open("rb") as fin:
            proc = subprocess.run(
                [perf, "stat", "-x,", "-e", events, "--", str(binary)],
                stdin=fin, capture_output=True, text=True, timeout=30, check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"perf invocation failed: {exc}"
    counters: dict[str, int] = {}
    for line in proc.stderr.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if (
            len(parts) >= 3
            and parts[1]
            in {"cycles", "instructions", "cache-references", "cache-misses"}
            and re.fullmatch(r"\d+", parts[0] or "")
        ):
            counters[parts[1]] = int(parts[0])
    if proc.returncode != 0 or not counters:
        tail = (proc.stderr.strip().splitlines() or [""])[-1]
        return None, f"perf could not read counters here (rc={proc.returncode}): {tail}"
    if counters.get("cache-references"):
        counters["cache_miss_rate"] = (
            counters.get("cache-misses", 0) / counters["cache-references"]
        )
    return counters, "perf counters measured directly (not estimated)"


def measure_profile(
    binary_path: str | Path,
    *,
    workspace: str | Path,
    input_data: str = "",
    runs: int = 5,
    submission_hash: str = "sha256:profile",
) -> ProfileReport:
    workspace = Path(workspace)
    durations: list[float] = []
    statuses: list[str] = []
    limits = ExecutionLimits(wall_time_s=10.0, memory_mb=None)
    for i in range(runs):
        res = run_program(
            binary_path, workspace=workspace, test_id=f"prof-{i}",
            submission_hash=submission_hash, input_data=input_data, limits=limits,
        )
        statuses.append(res.status.value)
        if res.status is ExecutionStatus.OK:
            durations.append(res.duration_ms)
    counters, note = _perf_counters(Path(binary_path), input_data, workspace)
    return ProfileReport(
        runs=runs,
        wall_time_ms_median=statistics.median(durations) if durations else None,
        wall_time_ms_min=min(durations) if durations else None,
        wall_time_ms_max=max(durations) if durations else None,
        run_statuses=statuses,
        cache_counters=counters,
        perf_note=note,
        input_description=f"{len(input_data)} bytes of stdin",
    )
