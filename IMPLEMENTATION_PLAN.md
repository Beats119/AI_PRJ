# Implementation Plan — AutoGrader v2 (Master Prompt, 2026-10-24)

**STATUS 2026-10-24: M1–M7 implemented and verified** — see
`docs/V2_COMPLETION_REPORT.md` for the §17 report (implemented items,
deviations, exact test evidence, benchmark, limitations). Owner
authorized full implementation "exactly as asked" at 02:30 IST; DV-1
and DV-2 were applied as proposed below.

Written per the master prompt's Milestone 0. The prompt's own instruction
governs adaptation: *"Adapt to an existing repository rather than forcing a
rewrite"* and *"unless the existing repository has a compatible
implementation already in place."* Deviations are recorded in
`docs/decisions.md`.

## Audit (2026-10-24, this machine)

**Environment**
- Python 3.12.3 ✓ · Node v24.22.1 + npm 10.9.4 ✓ (React/Vite feasible)
- gcc 13.3.0 ✓ · **Docker: ABSENT (no CLI, no daemon)** · Ollama: absent
  (deterministic mode is therefore the default run mode, as before)
- 8 GB RAM, ~98 GB free disk

**Existing repository (all verified working, 109 tests passing, ruff clean)**
- Grading engine: strict rules config (YAML+JSON), typed contracts,
  assignment spec builder, bounded test generation, oracle + D-1
  sufficiency, versioned cache, process sandbox (limits/timeout/kill,
  adversarially tested), 9 analyzers, deterministic D-3 Decimal scoring,
  canonical JSON/HTML/TXT reports, bounded Ollama client, benchmarks.
- What the master prompt needs that does **not** exist yet: React
  frontend, `/api` layer, SQLite persistence, assignment creation from the
  UI, batches + evaluation-run lifecycle, consolidated results dashboard,
  similarity review UI, Docker sandbox adapter.
- Role mapping (prompt §3): Agent 1 = `assignment/` (spec/generation/
  oracle), Agent 2 = `analyzers/` (deterministic tools; LLM advisory
  only), Agent 3 = `analyzers/similarity.py`, Agent 4 = `reports/`,
  Agent 5 = `workflow.py` + the new evaluation service. The engine is
  preserved; v2 builds the product shell around it.

## Vertical slices (each: tests first, targeted tests, regression, commit)

| Slice | Contents | Test gate |
|---|---|---|
| M1 Foundation | FastAPI `/api` app + health/dependencies endpoints; SQLite (SQLAlchemy) models for Assignment/Version/Batch/Submission/Run/Evidence/Score/Similarity/Report/Audit per prompt §9; React+TS+Vite+Tailwind shell with the six-section navigation, Overview + Settings & Health pages live | API tests (TestClient, temp DB); frontend unit tests; backend suite still green |
| M2 Assignments | Create/list/detail/version APIs; JSON rules editor (syntax + schema errors with locations); prepare via Agent 1; validation & ambiguity summary; test preview (validated / requires-review states); activation gating — unverified tests never activate | Rules validation tests; prepare-flow integration test; activation-gate test |
| M3 Sandbox | Sandbox interface; Docker adapter implementing prompt §6 controls (non-root, `--network=none`, caps dropped, limits, host-side kill); existing process adapter behind the same interface; fake runner for fast tests | Compile/run/timeout/cleanup tests per adapter (Docker ones run only where a daemon exists, blocker documented otherwise); fail-closed-when-configured test |
| M4 Batches & lifecycle | Multi-file upload (validation, duplicate detection, labels); durable runs with the prompt's state machine (legal transitions tested); bounded concurrency; progress polling; consolidated results table (search/filter/sort, CSV export with formula neutralization) | Lifecycle transition tests; duplicate/idempotency tests; restart-recovery test; results-table component tests |
| M5 Evidence & scoring | Engine wired into runs; evidence records per prompt §5.3; batch-scoped similarity (peers as corpus); scoring strictly from validated evidence | End-to-end batch test (correct/incorrect/timeout fixtures → expected statuses/grades); similarity-pair test; unavailable-tool ≠ zero test |
| M6 Reports & review | Investigation view (breakdown + calculation trace, source viewer, test-by-test evidence, diagnostics separated); downloadable reports; similarity review with disposition (never edits grades) | Report-vs-evidence consistency test; score-immutability test; disposition test |
| M7 Hardening | Security test batch (traversal, oversized, injection-in-content, XSS escaping, CSV formulas); coverage ≥80% on business logic; batch benchmark on this machine; README/docs refresh; final report per prompt §17 | Full suites + lint/type checks + production build; benchmark recorded with environment |

## Commands

- Backend tests: `.venv/bin/python -m pytest` · lint: `.venv/bin/ruff check src tests`
- Frontend: `cd frontend && npm run test / npm run build / npm run lint`
- Run (dev): `.venv/bin/autograder api` (new) + `cd frontend && npm run dev`
- Existing CLI remains fully functional throughout.

## Decisions needing the owner's sign-off (see docs/decisions.md)

1. **DV-1 (grading rule):** the master prompt (§5.2) forbids a reference
   implementation as a runtime oracle; the current D-1 trust model allows
   `reference_run`. Proposed: adopt the prompt — trust = instructor
   examples + independent derivation (+ properties); `reference.c` leaves
   the runtime path.
2. **DV-2 (security posture):** Docker is absent here; the prompt (§6)
   demands Docker-only, fail-closed execution. Proposed: sandbox
   interface with the Docker adapter preferred where a daemon exists and
   the existing tested process adapter as an explicitly-reported
   alternative backend; `SANDBOX_REQUIRE_DOCKER=true` restores strict
   fail-closed behaviour where required.
