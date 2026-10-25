# AutoGrader: Evidence-Based Grading for C Programs

AutoGrader takes an assignment (problem statement + instructor examples +
a JSON rubric) and a **batch** of student C submissions, and produces one
consolidated, evidence-backed result set: grades, per-test failures with
input/expected/actual, rubric traces, and similarity flags for human
review. Contract: **same submission + same assignment version + same
rules → same grade**, deterministically.

It deliberately does **not** use reference solutions: expected outputs
are trusted only when the instructor stated them or they are
independently derived from the contract (see `docs/TRUST_MODEL.md`).

## Quick start (v2 dashboard)

```bash
# backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,api]"
# frontend
cd frontend && npm install && npm run build && cd ..
# run (API + built dashboard at /app)
.venv/bin/autograder api            # http://127.0.0.1:8000/app/
```

Development mode: `autograder api` in one terminal,
`cd frontend && npm run dev` in another (Vite proxies `/api`).

Then: create an assignment → load the worked example → create the
version (the trusted suite is prepared and shown with its sufficiency
evidence) → activate it → upload a batch of `.c` files → Evaluate →
investigate any row → review similarity flags.

## CLI (engine, unchanged)

```bash
autograder doctor [--json]                 # environment + capability truth
autograder validate-rules --rules configs/example_rules.yaml
autograder prepare-assignment --assignment examples/assignments/add_two_integers --rules configs/example_rules.yaml
autograder evaluate examples/submissions/correct.c --assignment examples/assignments/add_two_integers --rules configs/example_rules.yaml --out reports
autograder cache list | invalidate <key>
autograder benchmark --assignment examples/assignments/add_two_integers --rules configs/example_rules.yaml --submissions-dir examples/submissions --out bench.json
```

## Configuration

- Rules live **outside** the code (YAML or JSON, strict schema):
  `configs/example_rules.yaml` is the assignment PDF's worked example
  (9 metrics, weights sum to 1.00). The dashboard editor is JSON.
- `.env.example` lists the environment knobs: Ollama base URL/model,
  sandbox backend (`auto|docker|process`), fail-closed switch, data dir.
- The LLM (Ollama, local) is bounded and advisory only; the deterministic
  pipeline is complete without it.

## Tests

```bash
.venv/bin/python -m pytest              # backend: 117 tests (engine, services, API, security)
.venv/bin/ruff check src tests
cd frontend && npm run test             # 11 Vitest tests
cd frontend && npm run build            # production build (tsc + vite)
```

Coverage (2026-10-24): 87% overall; scoring 86%, oracle 94%, services
88–91%, state machine 94%.

## Documentation

- `docs/architecture.md` — v2 system shape and role mapping
- `docs/evaluation-flow.md` — the dashboard flow, step by step
- `docs/api.md` — every route
- `docs/security.md` — sandbox backends, fail-closed behaviour, app controls
- `docs/benchmark.md` — measured timings on this machine
- `docs/TRUST_MODEL.md` — how a test earns trust (oracle-v2)
- `docs/LIMITATIONS.md`, `docs/USEFULNESS_AND_LIMITATIONS.md` — honest limits
- `docs/V2_COMPLETION_REPORT.md` — what was built, deviations, evidence
- `docs/decisions.md` — architectural decisions and deviations
- `IMPLEMENTATION_PLAN.md` — the v2 milestone plan and its audit

## Deliberate non-features

No student/instructor portals, accounts, roles, or LMS integration; no
reference solutions; similarity is evidence for review, never an
automatic verdict; no grade depends on an unverified LLM judgement.
