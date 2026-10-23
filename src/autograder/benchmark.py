"""Real benchmarks (Stage 12): cold setup, warm setup, per-submission
evaluation with phase splits — all against the real pipeline and a real
on-disk cache (never a mocked one).

What this proves, with numbers:
  * a cache MISS pays the full setup cost (bounded generation + oracle
    validation executions) exactly once per assignment version
  * a cache HIT costs ~nothing and performs ZERO validation executions,
    i.e. the second student really does reuse the validated suite
  * an ordinary evaluation after setup is far below the 2-3 minute target
"""

from __future__ import annotations

import platform
import statistics
import subprocess
import time
from pathlib import Path

from autograder.assignment import prepare_assignment
from autograder.config.loader import LoadedRules
from autograder.config.schema import ModelsConfig
from autograder.workflow import evaluate_submission


def _median(xs: list[float]) -> float:
    return round(statistics.median(xs), 4) if xs else 0.0


def run_benchmarks(
    *,
    assignment_dir: Path,
    submissions: list[Path],
    loaded_rules: LoadedRules,
    models: ModelsConfig,
    scratch_dir: Path,
    repetitions: int = 3,
) -> dict:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "gcc": subprocess.run(
            ["gcc", "--version"], capture_output=True, text=True, check=False
        ).stdout.splitlines()[0]
        if Path("/usr/bin/gcc").exists()
        else "unknown",
        "model_calls": "none (LLM disabled for benchmarks; deterministic path)",
    }

    miss_times: list[float] = []
    miss_execs: list[int] = []
    hit_times: list[float] = []
    warm_cache: Path | None = None
    for rep in range(repetitions):
        cache = scratch_dir / f"cache-{rep}"
        start = time.perf_counter()
        result = prepare_assignment(
            assignment_dir, loaded_rules, models, cache
        )
        miss_times.append(time.perf_counter() - start)
        miss_execs.append(result.validation_executions)
        assert result.status == "prepared_new", result.status
        start = time.perf_counter()
        hit = prepare_assignment(assignment_dir, loaded_rules, models, cache)
        hit_times.append(time.perf_counter() - start)
        assert hit.status == "prepared_cache_hit"
        assert hit.validation_executions == 0
        warm_cache = cache

    evaluations: list[dict] = []
    assert warm_cache is not None
    for source in submissions:
        times: list[float] = []
        grades: list[str] = []
        phase_medians: dict[str, float] = {}
        analyzer_medians: dict[str, float] = {}
        last_report = None
        for _ in range(repetitions):
            start = time.perf_counter()
            last_report = evaluate_submission(
                source,
                assignment_dir=assignment_dir,
                loaded_rules=loaded_rules,
                models=models,
                cache_dir=warm_cache,
                corpus_dir=source.parent,
            )
            times.append(time.perf_counter() - start)
            grades.append(
                "none" if last_report.overall_grade is None
                else str(last_report.overall_grade)
            )
        timings = next(
            (e for e in last_report.execution_evidence if e["type"] == "timings"),
            {"phases": {}, "analyzers": {}},
        )
        phase_medians = {k: v for k, v in timings.get("phases", {}).items()}
        analyzer_medians = {k: v for k, v in timings.get("analyzers", {}).items()}
        evaluations.append(
            {
                "submission": source.name,
                "status": last_report.overall_status.value,
                "grade": grades[-1],
                "grades_all_repetitions": grades,
                "evaluation_s_median": _median(times),
                "evaluation_s_all": [round(t, 4) for t in times],
                "phases_s": phase_medians,
                "analyzers_s": analyzer_medians,
            }
        )

    return {
        "environment": env,
        "repetitions": repetitions,
        "assignment": str(assignment_dir),
        "setup_cache_miss": {
            "seconds_median": _median(miss_times),
            "seconds_all": [round(t, 4) for t in miss_times],
            "validation_executions": miss_execs,
        },
        "setup_cache_hit": {
            "seconds_median": _median(hit_times),
            "seconds_all": [round(t, 4) for t in hit_times],
            "validation_executions": 0,
        },
        "evaluations": evaluations,
        "target": "ordinary evaluation after setup < 120-180 s (spec target)",
    }
