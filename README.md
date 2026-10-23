# AutoGrader: A Rule-Driven Evaluator for C Programs

An agent that grades student C programs automatically: it takes a student's C
submission and a set of grading rules the instructor has written, runs the
submission safely, checks it against every rule, and returns one overall grade
together with feedback. Contract: **same submission + same rules → same grade.**

## Install (development)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Commands

```bash
# Check this machine: compiler, optional tools, Ollama, sandbox capabilities
autograder doctor [--json]

# Validate an instructor rules file (actionable errors, no silent defaults)
autograder validate-rules --rules configs/example_rules.yaml
```

Coming in later approved stages (the CLI reports this honestly until then):
`prepare-assignment` (Stage 6), `evaluate` (Stage 9), `cache list/invalidate`
(Stage 6), `benchmark` (Stage 12). A polished web UI is staged after the core
engine (Stages 9–11) and is part of the final acceptance criteria.

## Configuration

- `configs/example_rules.yaml` — the assignment PDF's worked example
  (add_two_integers, 9 metrics, weights sum to 1.00). Rules live **outside**
  the code; changing a weight or threshold never requires editing the agent.
- `configs/models.yaml` — LLM configuration. Default backend is a local
  Ollama server with Llama 3.1; bounded calls only (at most 2 during
  assignment setup); no core grade depends on an unverified LLM judgement.

## Build status

- Stage 1–2: requirements traceability + architecture plan (approved).
- Stage 3–4: project environment, CLI (`doctor`, `validate-rules`), typed
  data contracts, strict config validation, and the deterministic scoring
  engine implementing the approved D-3 missing-evidence policy
  (no universal weight redistribution; insufficient trusted correctness
  evidence yields an incomplete result, never an ordinary grade).
- Stage 5: sandbox — controlled compilation (argv only, source copied under
  a fixed safe name) and safe execution (prlimit resource limits, wall-clock
  timeout with process-group kill, bounded output, scrubbed environment,
  per-submission temp workspace, network namespace only where a live probe
  proves it works; the isolation actually applied is reported in every
  result). This is process-level isolation for a classroom/lab setting, not
  a chroot — see the executor module docstring for the honest limits.
- Stage 6–7: assignment setup and correctness — spec builder from explicit
  package inputs (ambiguities recorded, never invented), bounded candidate
  generation (D-2: 1 round, ≤40 candidates, ≤2 setup LLM calls, Ollama-only
  client with hard budgets and usage accounting), oracle verification with
  the trust model in `docs/TRUST_MODEL.md` (instructor / validated reference
  / independent derivation can create trust; LLM claims never can), the D-1
  sufficiency bar, a persistent versioned cache (atomic stores, integrity
  re-verified on load, corrupt entries quarantined, valid entries never
  overwritten), and the correctness + logical analyzers over trusted tests
  only. CLI: `prepare-assignment`, `cache list|invalidate`, and `evaluate`
  (correctness scope — it writes `correctness_report.json` and deliberately
  produces NO overall grade until the Stage 9 workflow runs every analyzer
  under the D-3 policy).
- Stage 8: the remaining analyzers — syntax (gcc warning evidence, strict
  -Werror compile + warning counts), structure/modularity (deterministic
  heuristic C parser; per-function cyclomatic/length findings WITH fix
  suggestions), complexity (static loop-nesting estimate + empirical growth
  classification that refuses noisy/tiny timings and reports disagreement as
  inconclusive), memory safety (ASan+UBSan over trusted tests; toolchain
  probed first — a broken toolchain is an environment error, never a student
  score; leaks included), readability (deterministic rubric; optional LLM
  prose is advisory-only per D-4 and cannot move the score), originality
  (identifier-canonicalized token-shingle similarity; a flag means "human
  review", never "proven copying"). Profiling (`analyzers/profiling.py`)
  measures real wall-times through the sandbox and reports hardware
  cache counters only when `perf` genuinely reads them — otherwise it says
  why they are unreadable (on this VM: perf is not installed).
- Stage 9–11: the full workflow (`workflow.py`: setup gate → sandboxed
  compile → smoke run with the PDF's `suspected_infinite_loop` path → every
  configured analyzer exactly once → D-3 scoring), canonical reports
  rendered as JSON + HTML + TXT from the single EvaluationReport
  (`reports/`), the remaining sample submissions (`timeout.c`,
  `compile_error.c`) with retained real outputs in `examples/outputs/`, and
  the web UI (`autograder serve`): evaluate form, report pages with
  JSON/TXT downloads, assignments/cache page with invalidation, and a
  doctor page. The UI calls the same workflow as the CLI — a parity test
  proves identical grades for identical inputs. Sample grades on this
  machine (corpus = examples/submissions): correct 100.0 complete,
  incorrect 85.2 complete, timeout 53.0 partial, compile_error 43.0 partial.
- Worked example included: `examples/assignments/add_two_integers/`
  (package + reference implementing the U-07 wider-type contract) and
  `examples/submissions/correct.c` / `incorrect.c` (the PDF's submission,
  which fails on large operands).
- Tests: `python -m pytest` (unit tests for config, contracts, scoring —
  one test per D-3 case — LLM budgets, spec/oracle/cache; security tests run
  real adversarial programs through the sandbox).

See `docs/` (added as stages complete) for architecture, flow, requirements
traceability, installation, benchmarks, and limitations.
