# Testing

Run everything:

```bash
.venv/bin/python -m pytest        # 109 tests, ~30 s on the reference VM
.venv/bin/ruff check src tests    # lint must be clean
```

## Layout and what each suite proves

| Suite | Contents |
|---|---|
| `tests/unit/test_config.py` | Rules/models validation: weights, unknown analyzers, D-2 caps enforced by schema, canonical hashing. |
| `tests/unit/test_models.py` | Contract validators (a scored result must carry a score; an unscored one must say why). |
| `tests/unit/test_scoring.py` | The D-3 engine: **one test per matrix case 1–5**, disclosure completeness, determinism, Decimal rounding. |
| `tests/unit/test_cli.py` | CLI surface: doctor JSON, validate-rules, honest command set. |
| `tests/unit/test_stage6_llm.py` | LLM budgets with a **fake** transport (labelled `"fake"` in usage records): per-purpose caps, total setup cap, separate readability budget, typed unavailability. |
| `tests/unit/test_stage6_setup.py` | Spec building (missing sections → unresolved questions), bounded generation (caps + dedupe), oracle trust categories, trojan-reference rejection, U-07 boundary expected outputs, LLM claims never self-trusting. |
| `tests/unit/test_stage7_cache.py` | Cache hit/miss, never-overwrite, corruption → quarantine, schema mismatch, crash-mid-store atomicity, invalidation, 24 concurrent operations. |
| `tests/unit/test_stage8_analyzers.py` | Syntax/structure/modularity/complexity (incl. growth classification of exact O(1)/O(n)/O(n log n)/O(n²) models and noise refusal), profiling honesty, readability rubric + advisory invariance, similarity (renamed copies flag). |
| `tests/unit/test_stage10_reports.py` | All three formats agree on the grade; disclosure present; HTML escapes untrusted content; JSON round-trips. |
| `tests/security/test_sandbox.py` | Real adversarial programs through the real sandbox: infinite loop, forked child (verified dead), segfault, output flood cap, 512 MB allocation under a 64 MB limit, environment-leak probe, hostile filename, cleanup. |
| `tests/integration/test_stage7_correctness.py` | Prepare miss→hit end-to-end, correctness + counterexamples, infra-error vs student-failure separation, repeatability, CLI flow. |
| `tests/integration/test_stage8_memory.py` | Real ASan/UBSan runs: buffer overflow, signed-overflow UB and leak fixtures caught; broken toolchain = environment error; full 9-metric scoring determinism. |
| `tests/integration/test_stage9_workflow.py` | Complete/partial/incomplete branches incl. D-5 compile branch and smoke-timeout branch; breakdown sums exactly to the grade. |
| `tests/integration/test_stage11_web.py` | UI pages, upload evaluation, **UI grade == workflow grade on identical inputs**, cache/doctor pages, 404/400 paths. |
| `tests/integration/test_stage12_benchmark.py` | Benchmark structure: miss performs 24 validation executions, hit performs 0 and is faster; phases/analyzers split present. |

## Honesty rules for tests

- Mocked LLM calls use injected fake transports and are labelled as such in
  every usage record; **no test requires a live Ollama server**, and no fake
  result is ever presented as a real model result.
- Tool-dependent tests probe reality first (e.g. sanitizers) — the suite
  was developed on a machine *without* cppcheck/valgrind/perf/lizard so the
  unavailable paths are exercised for real, not simulated.
- Tests are never weakened to get a green run; two genuine product bugs
  found by these suites (a loop-detection regex, a route-ordering bug) are
  recorded in the git history with their fixes.
- Verification commands in this project are run with `pipefail` so a piped
  test run can never mask pytest's exit code.
