# AutoGrader — Architecture

One grading engine with two front doors (CLI and web UI). Everything the
user sees — grades, reports, web pages — is derived from a single canonical
`EvaluationReport` produced by `autograder.workflow.evaluate_submission`.

## Components

| Area | Modules | Responsibility |
|---|---|---|
| Front doors | `cli.py`, `web/` (FastAPI, server-rendered) | Commands and pages. Neither grades anything itself; both call the workflow. |
| Workflow | `workflow.py` | The pipeline: setup gate → compile → smoke run → analyzers → scoring → canonical report. Owns the D-5 branches and per-phase timing evidence. |
| Config | `config/schema.py`, `config/loader.py` | Strict rules/models validation (weights sum to 1.00, known analyzers only, D-2 caps enforced in schema). Canonical sorted-JSON SHA-256 hashing for all identities. |
| Contracts | `models/` | Typed pydantic contracts: `AssignmentSpec`, `TestCase`, `ExecutionResult`, `AnalyzerResult`, `EvaluationReport`. Validators enforce honesty (an unscored result must say why; a scored one must carry a score). |
| Assignment setup | `assignment/specification.py` | Builds the spec from explicit package inputs; missing contract pieces become `unresolved_questions`, never invented rules. |
| Generation | `assignment/test_generation.py` | Bounded candidate generation (D-2): one round, ≤40 candidates, ≤2 setup LLM calls; deterministic generators per assignment kind; candidates leave untrusted. |
| Oracle | `assignment/oracle.py`, `docs/TRUST_MODEL.md` | Establishes trust (instructor / validated reference / independent derivation), rejects contradictions, applies the D-1 sufficiency bar (policy `oracle-v1`). |
| Cache | `assignment/cache.py` | Persistent versioned store for the spec + trusted suite. Atomic writes, SHA-256 integrity + schema re-verified per load, corrupt entries quarantined, valid entries never overwritten, flock-serialized. Assignment artifacts only — never student results. |
| Sandbox | `sandbox/` | argv-only compilation (source copied under a fixed safe name), `prlimit` resource limits, wall-clock timeout with process-group kill, bounded output, scrubbed environment, network namespace only where a live probe proves it works. Process-level isolation, honestly labelled — not a chroot. |
| Analyzers | `analyzers/` | One module per metric: correctness, logical, syntax, structure, modularity, complexity, memory safety, readability, similarity; plus profiling (measurements, not a score). A failing analyzer becomes an ERROR result; it cannot crash an evaluation. |
| Scoring | `scoring/engine.py`, `scoring/policy.py` | Deterministic Decimal engine implementing the approved D-3 missing-evidence matrix (`d3-v1`). Pure function of (rules, results). |
| LLM | `llm/client.py` | The only place LLM calls happen: bounded Ollama client, per-purpose + total caps checked before each call, full usage accounting, injectable transport for tests. |
| Reports | `reports/render.py` | JSON / HTML / TXT renderers over the one canonical report. No timestamps: identical evaluations render identically. |
| Benchmarks | `benchmark.py`, CLI `benchmark` | Cold setup vs warm setup vs per-submission evaluation with phase splits, against the real cache. |

## Key invariants

1. **Trust before grading.** No test influences a grade unless the oracle
   established its expected output independently of the candidate's origin.
   LLM output alone never creates trust (`docs/TRUST_MODEL.md`).
2. **Determinism.** Same submission bytes + same rules + same trusted
   suite + same analyzer versions → same grade, exactly (Decimal math,
   round-half-up, hashes recorded in every report). There is no ±tolerance.
3. **Missing evidence is explicit.** The D-3 matrix decides incomplete /
   partial / provisional / excluded outcomes; the report always discloses
   configured weights, contributions, effective weights and coverage.
4. **Setup is paid once.** The trusted suite is built per assignment
   version and reused for every student; a cache hit performs zero
   generation and zero validation executions.
5. **Fail safely, report honestly.** Missing tools, unreadable counters,
   ambiguous complexity — all surface as labelled outcomes, never as
   fabricated numbers or silent passes.

## Data flow

```
C source + rules ──► workflow ──► prepare (cache hit? ──► load+verify suite)
                                   │ miss ──► spec ──► bounded generation
                                   │          ──► oracle verify ──► D-1 bar
                                   │          ──► atomic cache store
                                   ▼
                     sandbox compile ──► smoke run ──► 9 analyzers
                                   │                        │
                                   └────► profiling evidence ┘
                                                    ▼
                                        D-3 scoring ──► EvaluationReport
                                                    ▼
                                        JSON / HTML / TXT + web UI
```

See `docs/FLOW.md` for the branch-by-branch runtime behaviour,
`docs/TRUST_MODEL.md` for the trust categories, and
`docs/REQUIREMENTS_TRACEABILITY.md` for requirement-by-requirement mapping.
