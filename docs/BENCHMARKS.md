# Benchmarks (Stage 12)

Measured with `autograder benchmark` (3 repetitions, medians reported)
against the **real** pipeline and a real on-disk cache. Raw results:
`benchmarks/benchmark_results.json` (regenerate any time; on the target
machine — e.g. Khushi's WSL — numbers will differ but the method is the
deliverable).

**Environment:** Linux 7.0.0-39-generic x86_64, Ubuntu 24.04 (glibc 2.39),
Python 3.12.3, gcc 13.3.0. LLM disabled (deterministic path; no model
loading is involved in ordinary grading).

## Results

| Measurement | Median | Notes |
|---|---|---|
| Assignment setup, cache **miss** | **0.158 s** | spec build + 24 candidate generations + **24 oracle validation executions** (reference checks) + atomic store |
| Assignment setup, cache **hit** | **0.003 s** | integrity/schema re-verified, **0 validation executions** — the validated suite is genuinely reused |
| Evaluate `correct.c` (complete) | **0.91 s** | grade 100.0, identical across repetitions |
| Evaluate `incorrect.c` (complete) | **0.96 s** | grade 85.2 |
| Evaluate `timeout.c` (partial) | **1.15 s** | includes the 1 s smoke-run timeout being enforced |
| Evaluate `compile_error.c` (partial) | **0.05 s** | stops at the first pass; source-only analyzers only |

## Where an evaluation's second goes (correct.c, medians)

| Phase / analyzer | Seconds |
|---|---|
| setup (cache hit) | 0.004 |
| compile | 0.051 |
| smoke run | 0.004 |
| correctness (24 trusted runs) | 0.114 |
| logical (13 boundary/edge runs) | 0.067 |
| syntax (2 compiles) | 0.105 |
| memory safety (ASan compile + 24 instrumented runs) | 0.639 |
| structure / modularity / complexity / readability | < 0.001 each |
| originality | 0.003 |
| scoring | 0.0002 |

## Interpretation

- The spec target is **< 2–3 minutes per evaluation after setup**. The
  measured figure is **~1 second** — roughly two orders of magnitude
  inside the target, with all safety checks (sandboxing, sanitizers,
  process-group kills) enabled. Nothing was removed to buy speed.
- The dominant cost is memory safety (ASan/UBSan compile + instrumented
  runs), which is also the highest-value evidence per rupee of time.
- Setup is paid **once per assignment version**: the second and every
  later student cost ~3 ms of setup and zero validation executions —
  this is the structural fix for the previous implementation's ~49-minute
  single run (which regenerated and re-validated everything per student,
  multiplied by unbounded LLM retries).
