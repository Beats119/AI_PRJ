# Requirements Traceability Matrix — FINAL (Stages 1–2 draft v2, updated at Stage 13)

Sources: (P) the 9-page assignment PDF, read literally 2026-10-22;
(H) the professor's handwritten "Extras to do!" — **PROVISIONAL**: the image
itself was never re-supplied in this redo (open item U-10); rows rest on the
2026-10-19 transcription confirmed by Khushi 2026-10-22;
(E) Khushi's master implementation spec §§0–10 + her D-1…D-8/U-07 decisions.

Status key: **Done** = implemented and covered by the cited test/evidence.
**Partial** = implemented with a stated limitation. **Open** = not a code
item (Khushi's deliverable / unresolved input).

## PDF — core contract

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| P-01 | Submission + rules → safe run, all rules checked, one grade + feedback | `workflow.evaluate_submission`, CLI `evaluate`, web UI | `test_stage9_workflow` (all four samples end-to-end) | Done |
| P-02 | Reproducibility: same submission + rules → same grade | Decimal scoring engine + versioned cache + recorded hashes | repeat-run tests in stages 7/8/9 (identical grades, breakdowns, evaluation IDs) | Done |
| P-03/P-10 | Safe run under fixed time/memory; survive crash & infinite loops | `sandbox/` (prlimit, wall timeout + process-group kill, bounded output) | `tests/security/test_sandbox.py` — 12 adversarial tests | Done |
| P-04/P-11 | Rules live outside code; editable metrics/thresholds/weights; invalid rules rejected actionably | `config/` strict schema (weights sum 1.00, known analyzers, D-2 caps) | `test_config.py` (10 tests) | Done |
| P-05 | One analyzer per metric; weights combine into the grade | `analyzers/` (9 metrics) + `scoring/engine.py` | full-pipeline test: grade equals hand-computed weighted sum exactly | Done |
| P-06/P-14 | Incorrect submission → specific failing input + expected + explanation; corner cases covered | correctness analyzer counterexamples; generation categories incl. boundaries/whitespace | incorrect.c report contains the INT_MIN counterexample with expected/actual | Done |
| P-07 | Flag suspected copying | `analyzers/similarity.py` (canonicalized shingle Jaccard) | renamed-copy flags ≥0.85; every flag states "not proof of copying" | Done |
| P-08/P-15/P-19 | Usefulness & Limitations, 3–4 concrete each, in the final report | `docs/USEFULNESS_AND_LIMITATIONS.md` | this doc set; each limitation names a concrete wrong-verdict scenario | Done |
| P-09 | Methods are the team's choice; contract (P-02) fixed | `docs/ARCHITECTURE.md`, `docs/FLOW.md` | — | Done |
| P-12 | Metric set is open (rules choose the subset) | dispatch is driven by the rules file | CLI test: parser/commands; engine rejects unknown metrics | Done |
| P-13 | End-to-end unattended; exit codes distinguish outcomes | CLI (0 complete/partial, 4 incomplete, 2 config error, 3 unimplemented — none remain) | `test_cli.py`, workflow tests | Done |
| P-16 | Complete working agent + install docs | whole repo + README + `docs/INSTALLATION.md` | Stage 14 clean-environment review (`docs/FINAL_REVIEW.md`) | Done |
| P-17 | Editable rules + ≥1 example set | `configs/example_rules.yaml` (PDF's 9 metrics/params) | `validate-rules` exits 0 | Done |
| P-18 | Agent output on sample submissions | `examples/submissions/{correct,incorrect,timeout,compile_error}.c` + retained real outputs in `examples/outputs/` | NOTE (U-04): no samples were actually provided with the assignment; these four were authored to the PDF's descriptions and their outputs are genuine runs | Done (with note) |
| P-20 | Ollama local LLM (may use) | `llm/client.py`, `configs/models.yaml` (Ollama + llama3.1 default) | `doctor` reports absence honestly; full pipeline passes with Ollama absent | Done |
| P-21 | Codacy (may use) | D-8 decision: not integrated in v1 | recorded decision | Done (excluded by decision) |

## PDF — worked example as oracle

| ID | Requirement | Verification | Status |
|---|---|---|---|
| P-22 | add_two_integers, sample `7 5` → `12` as trusted case | example package; sample is instructor case #1 | Done |
| P-23 | PDF's add.c weaknesses surface in its report | incorrect.c: modularity 0.5, readability findings, overflow counterexamples | Done |
| P-24 | Example rules mirror the PDF's 9 metrics/weights/params | `configs/example_rules.yaml`; each analyzer consumes its params | Done |
| P-25 | First pass: `-O2` compile + 1s/64MB smoke + static sanity | workflow stages 2–3 (smoke uses rules limits) | Done |
| P-26 | Smoke timeout → flag, skip execution analyzers, run source-only, partial report | timeout.c: partial, flag present, correctness/logical/memory_safety skipped. **Deviation, deliberate:** our complexity analyzer is static (it never executes the binary), so it also runs on this branch; only execution-dependent metrics skip | Done (deviation noted) |
| P-27 | Dispatch each expert once with its params slice | workflow dispatch; analyzer exceptions become ERROR results. **Note:** dispatch is sequential — determinism and simplicity were chosen over parallelism ("where possible"); at ~1 s per evaluation this costs nothing measurable | Done (note) |
| P-28 | PDF's example totals (89/100) | NOT a reproduction target (the PDF's numbers are illustrative); our arithmetic is verified against hand-computed sums on our own evidence | Done (as specified in draft v2) |
| P-29 | Reports: JSON + student-readable from one source | renderers produce JSON+HTML+TXT from the canonical report; agreement test | Done |
| P-30 | JSON fields incl. hashes, per-metric evidence, flags, tool versions | EvaluationReport schema test + retained outputs; provenance records the real gcc version; cppcheck/lizard are not separate tools in this design (built-in parser), so no versions are claimed for them | Done |
| P-31 | Failing-test presentation input/expected/got/WHY + suggestions | reports show counterexamples; structure/readability findings carry concrete fixes | Done |
| P-32 | PDF's INT_MAX+1 expected value is signed-overflow UB — do not assert wrapped results (U-07) | wider-type contract in the shipped assignment; trusted expected = `2147483648`; UBSan flags the student's overflow as UB evidence | Done |
| P-33/P-34 | Usefulness/limitation examples from the PDF | included in `docs/USEFULNESS_AND_LIMITATIONS.md` | Done |
| P-35 | Group ≤4 | members unknown (U-02) — Khushi's input | Open |
| P-36 | ~4 weeks, weekly evals | dates unknown (U-01) — Khushi's input | Open |
| P-37 | Final: report + GitHub + install guide + 15–20 min video | docs complete; `docs/DEMO_SCRIPT.md` scripts the video; recording + submission are Khushi's | Partial (video = owner) |
| P-38 | agentic01.pdf before next lab | status unknown (U-03); this RTM + Architecture Plan are its reusable content core; **not** claimed generated or submitted | Open |
| P-39 | Own the code; don't use AI output blindly | process: every stage was test-verified and reviewed at Khushi's gates | Done (process) |

## Handwritten "Extras" (PROVISIONAL source — see header)

| ID | Requirement | Verification | Status |
|---|---|---|---|
| H-01 | Identical marks across runs | = P-02 | Done |
| H-02 | Big-O check (O(n), O(n log n), …) | complexity analyzer: static + empirical classifier with inconclusive path; fixture tests for O(1)/O(n)/O(n log n)/O(n²) | Done |
| H-03 | Professional report | HTML renderer + retained outputs | Done |
| H-04 | Code + assignment in → report to student | reports generated + downloadable in UI; **no email/messaging sending** (assumption A-05, unchanged) | Done (as scoped) |
| H-05 | Generates "perfect" test cases | interpreted defensibly: bounded generation + oracle verification; "perfect" is never claimed — coverage + provenance are | Done (interpretation recorded since Stage 1) |
| H-06 | Tool checker | `doctor` (real probes, honest absences) | Done |
| H-07 | Profiling for time consumption | profiling: real median wall-times via executor | Done |
| H-08 | Cache-miss check (per function, per Khushi's note) | perf counters attempted when perf exists; **on the reference VM perf is not installed → counters reported unreadable with reason; per-function attribution is not available** (whole-process only, when perf exists at all) | Partial (host-limited, honestly reported) |
| H-09 | Per-function check with fixes & suggestions | structure analyzer findings include per-function fixes; no fabricated line numbers | Done |

## Master spec (E)

| ID | Requirement | Status |
|---|---|---|
| E-01 | Input validation, normalized config, stable hashes, actionable errors | Done (`test_config.py`) |
| E-02 | Cache: full key material, persistence, atomicity, integrity, schema, concurrency, invalidation, failed-regen protection, inspect/invalidate commands | Done (`test_stage7_cache.py`, 8 tests incl. crash-mid-store and 24 concurrent ops) |
| E-03 | Spec building with provenance + unresolved ambiguities | Done (`test_stage6_setup.py`) |
| E-04 | Bounded generation (D-2) with per-test records + logged usage | Done (generation report + LLM usage accounting; budgets enforced pre-call) |
| E-05 | Trust rule + D-1 sufficiency bar | Done (`docs/TRUST_MODEL.md`; per-condition diagnostics tested) |
| E-06 | Per-student independence | Done (fresh sandbox per evaluation; only the suite is shared) |
| E-07 | Execution safety + honest guarantees | Done (security suite; limits documented in README + `docs/LIMITATIONS.md`) |
| E-08 | Analyzer failure never crashes/masquerades | Done (workflow converts exceptions to ERROR results; test via broken toolchain) |
| E-09 | Complexity honesty (multi-size empirical, inconclusive allowed) | Done (classifier refuses noise/sub-resolution/disagreement) |
| E-10 | Code quality with concrete fixes; LLM advisory only | Done (D-4 test: advisory never changes the score) |
| E-11 | Memory safety: ASan/UBSan, explicit leak handling, honest unavailable path | Done (probe-first; broken toolchain → environment ERROR, unscored) |
| E-12 | Profiling/cache honesty; no penalty for missing host profiler | Done (profiling is unscored evidence, never a metric) |
| E-13 | Similarity: explainable, N(N−1)/2 pairs, ≠ proof | Done, **except** pair-result caching is not implemented — pairs are recomputed per evaluation (negligible at classroom scale; recorded here rather than silently absent) |
| E-14 | D-3 scoring matrix + full disclosure | Done (one test per matrix case; disclosure asserted in report tests) |
| E-15 | One canonical report → JSON + HTML (+TXT) | Done |
| E-16 | Typed contracts used by the real workflow | Done |
| E-17 | CLI command set incl. benchmark; meaningful exit codes | Done (all 7 commands live) |
| E-18 | Example assignment + 4 submissions + boundary demo | Done (`examples/`) |
| E-19 | Reproducibility + performance with split timings | Done (`docs/BENCHMARKS.md`, `benchmarks/benchmark_results.json`) |
| E-20 | Test plan honesty (mocked LLM labelled; real-tool integration) | Done (`docs/TESTING.md`; fake transports record `"transport": "fake"`) |
| E-21 | Academic docs incl. demo script; agentic01 never falsely claimed | Done (this docs set) |
| E-22 | 14-stage discipline, no placeholders/fake results | Done (per-stage gates + verification in git history) |
| E-23 | Final acceptance: 13 questions with evidence | Done (`docs/FINAL_REVIEW.md`) |
| E-24 | Web UI mandatory, staged after engine, same engine as CLI | Done (UI↔workflow grade-parity test; live serve smoke test) |
