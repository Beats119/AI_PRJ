"""Stage 12 benchmark smoke test: real pipeline, real cache, real reuse."""

from pathlib import Path

from autograder.benchmark import run_benchmarks
from autograder.config.loader import load_models_config, load_rules

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"
SUB = ROOT / "examples" / "submissions"


def test_benchmark_proves_cache_reuse(tmp_path):
    results = run_benchmarks(
        assignment_dir=EXAMPLE,
        submissions=[SUB / "correct.c", SUB / "incorrect.c"],
        loaded_rules=load_rules(ROOT / "configs" / "example_rules.yaml"),
        models=load_models_config(ROOT / "configs" / "models.yaml"),
        scratch_dir=tmp_path / "scratch",
        repetitions=1,
    )
    miss, hit = results["setup_cache_miss"], results["setup_cache_hit"]
    assert miss["validation_executions"] == [0]  # oracle-v2: derivation only
    assert hit["validation_executions"] == 0  # the hit did NO setup work
    assert hit["seconds_median"] < miss["seconds_median"]
    by_name = {e["submission"]: e for e in results["evaluations"]}
    assert by_name["correct.c"]["grade"] == "100.0"
    assert by_name["correct.c"]["grades_all_repetitions"] == ["100.0"]
    assert by_name["incorrect.c"]["status"] == "complete"
    # phase split is present and sane
    phases = by_name["correct.c"]["phases_s"]
    assert phases["compile"] > 0 and phases["scoring"] >= 0
    assert "memory_safety" in by_name["correct.c"]["analyzers_s"]
    # far under the 2-3 minute per-evaluation target on this machine
    assert by_name["correct.c"]["evaluation_s_median"] < 60
