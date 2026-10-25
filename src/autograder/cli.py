"""AutoGrader command line interface.

Implemented: `doctor`, `validate-rules`, `prepare-assignment`, `cache`,
`evaluate` (full Stage 9 workflow -> canonical report rendered as
JSON+HTML+TXT), and `serve` (the web UI).
Exit codes: 0 = success (an evaluation with failing metrics still exits 0;
its grade says so), 2 = configuration/input error, 3 = not yet
implemented in this stage, 4 = evaluation completed but INCOMPLETE
(insufficient trusted evidence or a blocked required metric, D-3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autograder.config.loader import ConfigError, load_models_config, load_rules
from autograder.doctor import format_doctor_text, run_doctor

DEFAULT_MODELS = Path("configs/models.yaml")
DEFAULT_CACHE = Path(".cache/autograder")

NOT_IMPLEMENTED: dict[str, str] = {}


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(Path(args.models))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_doctor_text(report))
    return 0


def _cmd_validate_rules(args: argparse.Namespace) -> int:
    try:
        loaded = load_rules(Path(args.rules))
    except ConfigError as exc:
        for p in exc.problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2
    r = loaded.rules
    print(f"Rules OK: {loaded.source_path}")
    print(f"  problem        : {r.problem}")
    print(f"  rules hash     : {loaded.rules_hash}")
    print(f"  time/memory    : {r.time_limit_s}s / {r.memory_limit_mb} MB")
    print(f"  metrics        : {len(r.metrics)} (weights sum to 1.00)")
    for m in r.metrics:
        kind = "required" if m.required else "optional"
        print(f"    - {m.name:<15} {m.analyzer:<20} w={m.weight} [{kind}]")
    print(
        f"  generation     : rounds={r.generation.rounds}, "
        f"max_candidates={r.generation.max_candidates}"
    )
    print(
        f"  sufficiency    : min_total={r.sufficiency.min_trusted_total}, "
        f"core>={r.sufficiency.min_per_core_category}, "
        f"applicable>={r.sufficiency.min_per_applicable_category}"
    )
    return 0


def _cmd_not_implemented(name: str) -> int:
    print(
        f"'{name}' is not implemented yet — it arrives in {NOT_IMPLEMENTED[name]} "
        "of the approved build plan. No result has been produced.",
        file=sys.stderr,
    )
    return 3


def _load_all(args):
    loaded = load_rules(Path(args.rules))
    models = load_models_config(Path(args.models))
    return loaded, models


def _cmd_prepare(args: argparse.Namespace) -> int:
    from autograder.assignment import prepare_assignment

    try:
        loaded, models = _load_all(args)
        result = prepare_assignment(
            Path(args.assignment), loaded, models, Path(args.cache_dir),
            use_llm=args.use_llm,
        )
    except ConfigError as exc:
        for p in exc.problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2
    trusted = (
        sum(1 for t in result.suite if t.counts_as_trusted) if result.suite else 0
    )
    print(f"prepare-assignment: {result.status}")
    print(f"  assignment : {result.spec.assignment_id}")
    print(f"  cache key  : {result.cache_key}")
    print(f"  trusted tests: {trusted}")
    if result.sufficiency:
        print(f"  sufficiency: sufficient={result.sufficiency['sufficient']} "
              f"(total trusted {result.sufficiency['total_trusted']})")
    if result.llm_usage is not None:
        print(f"  LLM calls  : {result.llm_usage.get('total_calls', 0)} "
              "(setup, bounded by D-2)")
    print(f"  validation executions: {result.validation_executions}")
    for d in result.diagnostics:
        print(f"  note: {d}")
    return 0 if result.status != "insufficient_evidence" else 4


def _cmd_cache(args: argparse.Namespace) -> int:
    from autograder.assignment.cache import AssignmentCache

    cache = AssignmentCache(Path(args.cache_dir))
    if args.cache_command == "list":
        entries = cache.list_entries()
        if not entries:
            print("cache is empty")
        for e in entries:
            print(json.dumps(e, default=str))
        return 0
    removed = cache.invalidate(args.assignment_id)
    print(f"invalidated {removed} cache entr{'y' if removed == 1 else 'ies'} "
          f"for assignment '{args.assignment_id}'")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    """Full evaluation via the Stage 9 workflow; writes JSON+HTML+TXT."""
    from autograder.reports import render_html, render_json, render_txt
    from autograder.workflow import evaluate_submission

    try:
        loaded, models = _load_all(args)
        report = evaluate_submission(
            Path(args.source),
            assignment_dir=Path(args.assignment),
            loaded_rules=loaded,
            models=models,
            cache_dir=Path(args.cache_dir),
            corpus_dir=Path(args.corpus_dir) if args.corpus_dir else None,
            use_llm=args.use_llm,
        )
    except ConfigError as exc:
        for p in exc.problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.source).stem
    (out_dir / f"{stem}.json").write_text(render_json(report))
    (out_dir / f"{stem}.html").write_text(render_html(report))
    (out_dir / f"{stem}.txt").write_text(render_txt(report))
    grade = "no grade" if report.overall_grade is None else f"{report.overall_grade}/100"
    print(f"evaluate: {report.overall_status.value} — {grade} "
          f"(reports: {out_dir / (stem + '.json')}, .html, .txt)")
    for row in report.score_breakdown:
        result = next(
            (r for r in report.metric_results if r.metric_name == row.name), None
        )
        score_txt = "n/a" if row.score is None else f"{float(row.score):.3f}"
        print(f"  {row.name:<14} {row.status:<10} score {score_txt}")
        if result and row.name == "correctness":
            failing = result.evidence.get("failing", [])
            if failing:
                f0 = failing[0]
                print(f"    counterexample: test {f0['test_id']} input {f0['input']!r} "
                      f"expected {f0['expected']!r} got {f0['actual']!r}")
    if report.flags:
        print(f"  flags: {', '.join(report.flags)}")
    return 4 if report.overall_status.value == "incomplete" else 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    import tempfile

    from autograder.benchmark import run_benchmarks

    try:
        loaded, models = _load_all(args)
    except ConfigError as exc:
        for p in exc.problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2
    submissions = sorted(Path(args.submissions_dir).glob("*.c"))
    if not submissions:
        print(f"ERROR: no .c submissions in {args.submissions_dir}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="autograder-bench-") as scratch:
        results = run_benchmarks(
            assignment_dir=Path(args.assignment),
            submissions=submissions,
            loaded_rules=loaded,
            models=models,
            scratch_dir=Path(scratch),
            repetitions=args.repetitions,
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    miss, hit = results["setup_cache_miss"], results["setup_cache_hit"]
    print(f"benchmark results written to {out}")
    print(f"  setup (cache miss): median {miss['seconds_median']}s, "
          f"validation executions {miss['validation_executions']}")
    print(f"  setup (cache hit) : median {hit['seconds_median']}s, "
          "validation executions 0 (suite reused)")
    for ev in results["evaluations"]:
        print(f"  evaluate {ev['submission']:<18} median {ev['evaluation_s_median']}s "
              f"-> {ev['status']} grade {ev['grade']}")
    return 0


def _cmd_api(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "the v2 API needs the 'api' extra: pip install -e \".[api]\"",
            file=sys.stderr,
        )
        return 2
    from autograder.api.app import create_api_app

    app = create_api_app(
        data_dir=Path(args.data_dir),
        models_path=Path(args.models),
    )
    frontend = Path("frontend/dist")
    if frontend.is_dir():  # serve the built dashboard alongside the API
        from fastapi.staticfiles import StaticFiles

        app.mount(
            "/app", StaticFiles(directory=frontend, html=True), name="frontend"
        )
    print(f"AutoGrader API on http://{args.host}:{args.port} "
          f"(dashboard at /app when the frontend is built)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autograder", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="check compiler, tools and environment")
    d.add_argument("--models", default=str(DEFAULT_MODELS))
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=_cmd_doctor)

    v = sub.add_parser("validate-rules", help="validate an instructor rules file")
    v.add_argument("--rules", required=True)
    v.set_defaults(func=_cmd_validate_rules)

    pa = sub.add_parser("prepare-assignment", help="build/reuse the trusted test suite")
    pa.add_argument("--assignment", required=True)
    pa.add_argument("--rules", default="configs/example_rules.yaml")
    pa.add_argument("--models", default=str(DEFAULT_MODELS))
    pa.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    pa.add_argument("--use-llm", action="store_true",
                    help="allow the bounded setup LLM calls (D-2); off by default")
    pa.set_defaults(func=_cmd_prepare)

    ev = sub.add_parser("evaluate", help="evaluate one submission (full workflow)")
    ev.add_argument("--source", required=True)
    ev.add_argument("--assignment", required=True)
    ev.add_argument("--rules", default="configs/example_rules.yaml")
    ev.add_argument("--models", default=str(DEFAULT_MODELS))
    ev.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ev.add_argument("--out", default="reports")
    ev.add_argument("--corpus-dir", default=None,
                    help="directory of peer .c submissions for the originality metric")
    ev.add_argument("--use-llm", action="store_true")
    ev.set_defaults(func=_cmd_evaluate)

    c = sub.add_parser("cache", help="inspect or invalidate the assignment cache")
    c.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    csub = c.add_subparsers(dest="cache_command", required=True)
    cl = csub.add_parser("list")
    cl.set_defaults(func=_cmd_cache)
    ci = csub.add_parser("invalidate")
    ci.add_argument("--assignment-id", required=True)
    ci.set_defaults(func=_cmd_cache)

    ap = sub.add_parser("api", help="run the v2 JSON API (+ built dashboard)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data-dir", default=".autograder-data")
    ap.add_argument("--models", default=str(DEFAULT_MODELS))
    ap.set_defaults(func=_cmd_api)

    b = sub.add_parser("benchmark", help="measure stage timings and cache reuse")
    b.add_argument("--assignment", required=True)
    b.add_argument("--submissions-dir", default="examples/submissions")
    b.add_argument("--rules", default="configs/example_rules.yaml")
    b.add_argument("--models", default=str(DEFAULT_MODELS))
    b.add_argument("--out", default="benchmarks/benchmark_results.json")
    b.add_argument("--repetitions", type=int, default=3)
    b.set_defaults(func=_cmd_benchmark)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
