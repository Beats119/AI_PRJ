"""Evaluation workflow (Stage 9): one submission end to end.

Pipeline (mirrors the assignment PDF's first pass):
  1. assignment setup (cache) — insufficient evidence ends the evaluation
     as INCOMPLETE before the submission is even compiled (D-1/D-3 case 1)
  2. compile under sandbox control — failure takes the D-5 branch:
     source-only analyzers run, execution metrics are SKIPPED as
     student-attributable, and scoring produces a disclosed partial grade
  3. smoke run on the first trusted input — a timeout flags
     suspected_infinite_loop and likewise skips execution metrics
  4. every analyzer configured in the rules runs exactly once; an analyzer
     that raises is converted into an ERROR result, never a crashed
     evaluation
  5. deterministic D-3 scoring assembles the canonical EvaluationReport,
     which is the ONLY thing the JSON/HTML/TXT renderers and the UI read
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from autograder.analyzers.complexity import analyze_complexity
from autograder.analyzers.correctness import analyze_correctness, analyze_logical
from autograder.analyzers.memory_safety import analyze_memory_safety
from autograder.analyzers.profiling import measure_profile
from autograder.analyzers.readability import analyze_readability
from autograder.analyzers.similarity import analyze_originality
from autograder.analyzers.structure import analyze_modularity, analyze_structure
from autograder.analyzers.syntax import analyze_syntax
from autograder.assignment.setup import prepare_assignment
from autograder.config.loader import LoadedRules
from autograder.config.schema import ModelsConfig
from autograder.llm.client import LLMClient
from autograder.models.analysis import (
    AnalyzerResult,
    MissingReason,
    ResultStatus,
)
from autograder.models.execution import ExecutionStatus
from autograder.models.report import EvaluationReport
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits
from autograder.scoring.engine import score_results

FIRST_PASS_FLAGS = "-O2 -Wall -Wextra -std=c11"
_EXEC_METRICS = {"correctness", "logical", "memory_safety"}


def _skipped(analyzer_id: str, metric: str, reason: MissingReason, why: str) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_id=analyzer_id,
        metric_name=metric,
        status=ResultStatus.SKIPPED,
        missing_reason=reason,
        diagnostics=[why],
    )


def _errored(analyzer_id: str, metric: str, exc: Exception) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_id=analyzer_id,
        metric_name=metric,
        status=ResultStatus.ERROR,
        missing_reason=MissingReason.ANALYZER_ERROR,
        diagnostics=[f"analyzer raised {exc.__class__.__name__}: {exc}"],
    )


def _gcc_version() -> str:
    try:
        out = subprocess.run(
            ["gcc", "--version"], capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.splitlines()[0].strip() if out.stdout else "unknown"
    except Exception:
        return "unknown"


def evaluate_submission(
    source_path: str | Path,
    *,
    assignment_dir: str | Path,
    loaded_rules: LoadedRules,
    models: ModelsConfig,
    cache_dir: str | Path,
    corpus_dir: str | Path | None = None,
    use_llm: bool = False,
    llm_client: LLMClient | None = None,
) -> EvaluationReport:
    import time

    source_path = Path(source_path)
    rules = loaded_rules.rules
    timings: dict = {"phases": {}, "analyzers": {}}
    _t0 = time.perf_counter()
    prep = prepare_assignment(
        assignment_dir, loaded_rules, models, cache_dir,
        use_llm=use_llm, llm_client=llm_client,
    )
    timings["phases"]["setup"] = round(time.perf_counter() - _t0, 4)
    flags: list[str] = []
    limitations: list[str] = [
        (
            "Sandbox isolation is process-level (limits, timeout, namespaces "
            "where probed), not a chroot; see README."
        ),
        (
            "Static complexity and structure use heuristic source analysis; "
            "their evidence records the method used."
        ),
    ]
    provenance: dict[str, str] = {
        "rules_hash": loaded_rules.rules_hash,
        "assignment_spec_hash": prep.spec.specification_hash,
        "cache_key": prep.cache_key,
        "cache_status": prep.status,
        "gcc": _gcc_version(),
        "scoring_policy": "d3-v1",
        "oracle_policy": "oracle-v1",
    }

    def finish(results: list[AnalyzerResult], submission_hash: str,
               evidence: list[dict]) -> EvaluationReport:
        import time

        _ts = time.perf_counter()
        outcome = score_results(rules, results)
        timings["phases"]["scoring"] = round(time.perf_counter() - _ts, 4)
        evidence = [*evidence, {"type": "timings", **timings}]
        eval_id = "eval-" + hashlib.sha256(
            f"{submission_hash}|{loaded_rules.rules_hash}|"
            f"{prep.spec.specification_hash}".encode()
        ).hexdigest()[:12]
        return EvaluationReport(
            evaluation_id=eval_id,
            submission_name=source_path.name,
            submission_hash=submission_hash,
            assignment_hash=prep.spec.specification_hash,
            rules_hash=loaded_rules.rules_hash,
            overall_status=outcome.overall_status,
            overall_grade=outcome.overall_grade,
            metric_results=results,
            score_breakdown=outcome.breakdown,
            metric_coverage=outcome.metric_coverage,
            execution_evidence=evidence,
            flags=flags + [f"d3_case_{c}" for c in outcome.cases_applied],
            provenance=provenance,
            limitations=limitations + outcome.notes,
        )

    # --- stage 1: setup gate ---------------------------------------------
    if prep.status == "insufficient_evidence" or prep.suite is None:
        results = []
        for m in rules.metrics:
            if m.name == "correctness":
                results.append(
                    AnalyzerResult(
                        analyzer_id=m.analyzer,
                        metric_name=m.name,
                        status=ResultStatus.INSUFFICIENT_EVIDENCE,
                        missing_reason=MissingReason.INSUFFICIENT_EVIDENCE,
                        diagnostics=prep.diagnostics,
                        evidence={"sufficiency": prep.sufficiency},
                    )
                )
            else:
                results.append(
                    _skipped(m.analyzer, m.name,
                             MissingReason.INSUFFICIENT_EVIDENCE,
                             "assignment setup produced insufficient trusted "
                             "evidence; dependent metrics were not run")
                )
        from autograder.sandbox.compiler import source_hash_of

        return finish(results, source_hash_of(source_path.read_bytes()), [])

    suite = prep.suite
    limits = ExecutionLimits(
        wall_time_s=rules.time_limit_s, memory_mb=rules.memory_limit_mb
    )
    corpus_files = (
        sorted(Path(corpus_dir).glob("*.c")) if corpus_dir else []
    )
    client = llm_client
    if use_llm and client is None:
        client = LLMClient(models.llm)

    def run_analyzer(metric) -> AnalyzerResult:
        """Dispatch one rules metric to its analyzer, exactly once."""
        import time

        _ta = time.perf_counter()
        result = _dispatch(metric)
        timings["analyzers"][metric.name] = round(time.perf_counter() - _ta, 4)
        return result

    def _dispatch(metric) -> AnalyzerResult:
        params = metric.params
        try:
            if metric.analyzer == "io_tests":
                return analyze_correctness(
                    binary, suite, submission_hash=comp.source_hash,
                    sandbox=sandbox, limits=limits,
                )
            if metric.analyzer == "edge_case_runner":
                return analyze_logical(
                    binary, suite, submission_hash=comp.source_hash,
                    sandbox=sandbox, limits=limits,
                )
            if metric.analyzer == "compiler_warnings":
                return analyze_syntax(
                    source_path, work_dir=sandbox.workspace / "syntax",
                    flags=str(params.get("flags", "-Wall -Wextra -Werror -std=c11")),
                )
            if metric.analyzer == "static_analysis":
                return analyze_structure(
                    source_path,
                    max_cyclomatic=int(params.get("max_cyclomatic", 8)),
                    max_function_length=int(params.get("max_function_length", 40)),
                )
            if metric.analyzer == "function_split":
                return analyze_modularity(
                    source_path,
                    min_functions=int(params.get("min_functions", 2)),
                    expect_helpers=bool(params.get("expect_helpers", True)),
                )
            if metric.analyzer == "complexity_estimator":
                return analyze_complexity(
                    source_path, required=str(params.get("required", "O(1)"))
                )
            if metric.analyzer == "sanitizer_run":
                return analyze_memory_safety(
                    source_path, suite, sandbox=sandbox,
                    flags=str(params.get("flags", "-fsanitize=address,undefined")),
                )
            if metric.analyzer == "llm_review":
                advisory = bool(params.get("llm_advisory", False)) and use_llm
                return analyze_readability(
                    source_path,
                    llm_client=client if advisory else None,
                    llm_advisory=advisory,
                )
            if metric.analyzer == "similarity_flag":
                return analyze_originality(
                    source_path, corpus_files,
                    flag_threshold=float(params.get("flag_threshold", 0.85)),
                )
        except Exception as exc:  # an analyzer must never crash the evaluation
            return _errored(metric.analyzer, metric.name, exc)
        return _errored(
            metric.analyzer, metric.name,
            ValueError(f"unknown analyzer '{metric.analyzer}'"),
        )

    evidence: list[dict] = []
    with Sandbox() as sandbox:
        import time

        _tc = time.perf_counter()
        comp = sandbox.compile(source_path, flags=FIRST_PASS_FLAGS)
        timings["phases"]["compile"] = round(time.perf_counter() - _tc, 4)
        if not comp.success:
            flags.append("compile_error")
            results = []
            for m in rules.metrics:
                if m.name in _EXEC_METRICS:
                    results.append(
                        _skipped(m.analyzer, m.name,
                                 MissingReason.STUDENT_COMPILE_FAILURE,
                                 "submission did not compile; execution-dependent "
                                 "metric skipped (D-5)")
                    )
                else:
                    results.append(run_analyzer(m))
            evidence.append(
                {"type": "compilation", "success": False,
                 "diagnostics": comp.diagnostics[:2000]}
            )
            return finish(results, comp.source_hash, evidence)

        binary = comp.binary_path
        assert binary is not None
        # --- stage 3: smoke run -------------------------------------------
        first_trusted = next(t for t in suite if t.counts_as_trusted)
        _tsm = time.perf_counter()
        smoke = sandbox.run(
            binary, test_id="smoke", submission_hash=comp.source_hash,
            input_data=first_trusted.input_data,
            limits=ExecutionLimits(wall_time_s=rules.time_limit_s, memory_mb=rules.memory_limit_mb),
        )
        timings["phases"]["smoke"] = round(time.perf_counter() - _tsm, 4)
        evidence.append(
            {"type": "smoke_run", "status": smoke.status.value,
             "input": first_trusted.input_data, "duration_ms": smoke.duration_ms}
        )
        if smoke.status is ExecutionStatus.TIMEOUT:
            flags.append("suspected_infinite_loop")
            results = []
            for m in rules.metrics:
                if m.name in _EXEC_METRICS:
                    results.append(
                        _skipped(m.analyzer, m.name,
                                 MissingReason.STUDENT_TIMEOUT,
                                 "smoke run timed out (suspected infinite loop); "
                                 "execution-dependent metric skipped")
                    )
                else:
                    results.append(run_analyzer(m))
            return finish(results, comp.source_hash, evidence)

        # --- stage 4: all analyzers ---------------------------------------
        results = [run_analyzer(m) for m in rules.metrics]
        try:
            profile = measure_profile(
                binary, workspace=sandbox.workspace,
                input_data=first_trusted.input_data, runs=3,
                submission_hash=comp.source_hash,
            )
            evidence.append({"type": "profile", **profile.as_dict()})
        except Exception as exc:  # profiling evidence must never fail grading
            evidence.append({"type": "profile", "error": f"{exc.__class__.__name__}: {exc}"})
        return finish(results, comp.source_hash, evidence)
