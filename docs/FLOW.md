# AutoGrader — Runtime flow

This is the control flow implemented by `autograder/workflow.py`
(`evaluate_submission`), matching the assignment's intended flow.

```mermaid
flowchart TD
    A["Student C source + instructor rules"] --> B["Validate rules + models config"]
    B --> C["Compute assignment cache key"]
    C --> D{"Trusted suite cached and valid?"}
    D -->|Yes| E["Load suite (schema + integrity + provenance re-verified)"]
    D -->|No| F["Build assignment specification"]
    F --> G["Generate bounded candidates (1 round, ≤40, ≤2 LLM calls)"]
    G --> H["Oracle: establish expected outputs independently"]
    H --> I{"D-1 sufficiency bar met?"}
    I -->|No| J["INCOMPLETE: no grade, diagnostics kept, nothing cached"]
    I -->|Yes| K["Persist suite atomically"] --> E
    E --> L["Compile in sandbox (-O2 first pass)"]
    L -->|fails| M["D-5 branch: source-only analyzers run; execution metrics
                    SKIPPED (student_compile_failure); PARTIAL report"]
    L -->|ok| N["Smoke run on first trusted input (rules time limit)"]
    N -->|timeout| O["Flag suspected_infinite_loop; execution metrics
                      SKIPPED (student_timeout); PARTIAL report"]
    N -->|ok| P["Run each configured analyzer exactly once"]
    P --> Q["Profiling evidence (wall time; perf counters if readable)"]
    Q --> R["Deterministic D-3 scoring"]
    J --> R
    M --> R
    O --> R
    R --> S["Canonical EvaluationReport → JSON + HTML + TXT (+ web UI)"]
```

## Branches and their scoring outcomes (D-3 policy `d3-v1`)

| Situation | Execution metrics | Overall status | Grade |
|---|---|---|---|
| Trusted evidence insufficient at setup | not run | `incomplete` | none |
| Required metric blocked by host/tool failure | — | `incomplete` (environment) | none |
| Optional metric unavailable | excluded, weights renormalized + disclosed | `complete` | yes |
| Compilation failure (student's fault) | skipped | `partial` | yes, from earned contributions; achievable maximum + coverage disclosed |
| Smoke-run timeout (student's fault) | skipped | `partial` | same as above |
| Required metric inconclusive (e.g. originality with an empty corpus) | scored where possible | `provisional` | per engine policy; disclosed |
| Normal run | all scored | `complete` | yes |

## Timing evidence

Every report carries an `execution_evidence` entry of type `timings` with
per-phase seconds (setup, compile, smoke, scoring) and per-analyzer
seconds, measured with a monotonic clock. The `benchmark` command aggregates
these across repetitions (see `docs/BENCHMARKS.md`).

## Per-student independence

Each evaluation compiles and executes in its own fresh sandbox workspace
with its own evidence; the only shared artifact between students is the
assignment-level trusted suite (never another student's results).
