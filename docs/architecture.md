# Architecture (v2)

AutoGrader is a local-first, single-instance grading workbench:

```
React + TypeScript dashboard (frontend/, Vite + Tailwind)
        │  JSON over HTTP (/api, same origin in production via `autograder api`)
FastAPI API layer (src/autograder/api)         — validation + serialization only
        │
Services (src/autograder/services)            — Agent 5 coordinator:
        │  assignments (version lifecycle, activation gating),
        │  evaluations (batch upload, run state machine, similarity findings)
SQLite (src/autograder/db, SQLAlchemy 2.x)    — durable product state
        │
Grading engine (unchanged, fully tested core)
  assignment/  spec build, bounded test generation, oracle-v2, versioned cache
  sandbox/     process adapter + Docker adapter behind one interface
  analyzers/   9 deterministic analyzers (+ bounded LLM advisory surface)
  scoring/     D-3 deterministic Decimal scoring (pure function of evidence)
  reports/     one canonical EvaluationReport → JSON / HTML / TXT
  llm/         bounded Ollama client (advisory only; system runs without it)
```

## Roles (prompt §3) mapped to real modules

| Role | Where | Notes |
|---|---|---|
| 1 Assignment Understanding & Test Design | `assignment/` + `services/assignments.py` | Deterministic spec extraction; bounded candidate generation; oracle-v2 verification; ambiguity surfaces as unresolved questions + `requires_review` tests, never as deductions |
| 2 Solution/Compliance & Complexity | `analyzers/` | GCC/sanitizer/static evidence; scores come only from the deterministic analyzers + scoring engine |
| 3 Similarity & Originality Evidence | `analyzers/similarity.py` + findings in `services/evaluations.py` | Produces evidence + review queue; never edits grades |
| 4 Feedback & Report | `reports/` + investigation API | Read-only on scores; renders the canonical report |
| 5 Coordinator | `services/` + `services/state_machine.py` | Deterministic Python state machine, bounded sequential execution per batch, durable transitions, audit trail |

## Persistence & immutability

Assignment versions are immutable once created (edits create a new
version); each version records its rules hash, spec, verified suite and
sufficiency evidence. A grade is always reconstructible from
(version, submission hash, rules hash, scoring policy `d3-v1`, oracle
policy `oracle-v2`) — all stored on the run.

## Frontend serving

Development: Vite dev server proxies `/api` to the backend. Production:
`npm run build` then `autograder api` serves the API and mounts the built
dashboard at `/app`.
