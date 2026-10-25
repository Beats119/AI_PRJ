# V2 Completion Report (master prompt §17) — 2026-10-24

Built overnight per Khushi's instruction: "complete it exactly as asked
in the prompt; no more questions; tests and screenshots ready by
morning." **Nothing was pushed** — the commits are local, ready for her
morning push.

## 1. Implemented

**Backend / agents / evaluation**
- oracle-v2: reference implementations removed from the trust path
  entirely (prompt §5.2). Trust = instructor examples + independent
  derivation; the `no_reference_oracle` sufficiency condition asserts it;
  a test proves a deliberately wrong `reference.c` in the package
  changes nothing.
- Sandbox interface with three adapters: process (default here),
  Docker (full §6 argv controls, fail-closed when selected without a
  daemon), and policy tests via an injected runner. Workflow accepts
  `sandbox_backend=`; run provenance records the choice.
- SQLite persistence (SQLAlchemy 2.x): assignments, immutable versions
  (hashed rules/spec/suite/sufficiency), batches, submissions,
  evaluation runs, evidence records, score breakdowns, similarity
  findings, audit events.
- Services: assignment lifecycle (create → prepare with the REAL engine
  → D-1-gated activation; drafts can never activate), batch upload
  (validation, exact-duplicate detection with duplicates stored outside
  the peer corpus), evaluation coordinator with the prompt's lifecycle
  state machine (legal transitions enforced + audit-logged, driven by
  real workflow progress hooks), pairwise batch similarity findings,
  consolidated result rows, single-run retry linked to its predecessor.
- FastAPI `/api` per §10 incl. dependency health with honest sandbox /
  ollama state, rules validation with located problems, report
  downloads (JSON/HTML/TXT from the one canonical report), similarity
  disposition that provably never changes a grade.
- CLI: `autograder api` serves the API + the built dashboard at `/app`.
  The v1 server-rendered UI was retired (DV-5) once the dashboard
  covered its flows.

**UI (React + TypeScript + Vite + Tailwind)**
- Six sections exactly per the requested flow: Overview, Assignments
  (guided wizard: contracts, examples JSON, rules JSON editor with API
  validation, worked-example loader, sufficiency evidence, suite
  preview in validated / requires-review / rejected states, activation
  gating), Submissions & Results (multi-file batch upload with client
  validation, consolidated table with search/filter/sort, formula-safe
  CSV export, investigation view: rubric breakdown with clean number
  formatting, failing-test input/expected/actual, source viewer, report
  downloads), Similarity Review (dispositions), Evaluation Runs
  (lifecycle + retry), Settings & Health (live backend/ollama/gcc
  truth). Status is always icon + text, never colour alone.

## 2. Architecture deviations

Recorded in `docs/decisions.md` (DV-1…DV-5). In short: DV-1 adopted the
prompt over the old D-1 reference design (owner-authorized). DV-2
sandbox: Docker adapter implemented, but the process adapter remains
the default *on machines without Docker* — with the backend always
labelled and a fail-closed switch — because Docker is entirely absent
here; strict prompt posture is one env var away. DV-3 layout adapted to
the existing package. DV-4 rules editor is JSON (YAML still loads).
DV-5 v1 UI removed after replacement.

## 3. How to run

```bash
.venv/bin/pip install -e ".[dev,api]"
cd frontend && npm install && npm run build && cd ..
.venv/bin/autograder api        # dashboard at http://127.0.0.1:8000/app/
```

## 4. Tests executed (exact)

- Backend: `.venv/bin/python -m pytest` → **117 passed** (incl. 13 new
  v2 tests: sandbox backends 3, services 6, API 4) · `ruff check` clean.
- Frontend: `npm run test` → **11 passed** · `npm run build` (tsc
  strict + vite) succeeds · `npm run lint` (oxlint) clean.
- Coverage: **87%** overall (pytest-cov); oracle 94%, workflow 94%,
  state machine 94%, services 88–91%, scoring 86%, API 79%.
- Live end-to-end: real server + seeded batch (6 files): duplicate
  detected at upload; grades 90.0 / 85.2 / 53.0 partial / 43.0 partial /
  90.0; similarity finding (asha_k ↔ esha_t, 1.0) queued for review.
- NOT executed: live Docker runs (no daemon exists here — fail-closed
  behaviour tested instead); Ollama paths (fake transport, labelled);
  scripted Playwright journeys (the sandbox's Playwright CDN is
  blocked; screenshots were captured with Chrome-for-Testing driven by
  puppeteer-core instead — real browser, real clicks).

## 5. Security status

See `docs/security.md`. Implemented: argv-only execution, upload
validation + server-side storage names, strict rules schema, XSS-safe
report rendering, CSV formula neutralization, bounded LLM, no
reference-oracle attack surface. Known limits: process backend is not
a chroot; Docker path untested live (no daemon); single-process API
(evaluation is synchronous per request — batch of 5 ≈ 4–12 s observed).

## 6. Performance

`docs/benchmark.md`: setup miss 0.0046 s (oracle-v2 executes nothing),
hit 0.0024 s; single evaluations 0.05–1.16 s; API batch of 5 in
4.34 s (first run; 11.7–12.1 s under load). No Docker timings claimed.

## 7. Known limitations

- Evaluation runs synchronously inside the request (durable states, but
  no background worker yet); very large batches will want the queued
  worker the state machine already models.
- Alembic migrations are not wired; schema is created via SQLAlchemy
  metadata (single-instance SQLite scope). `SCHEMA_VERSION` is recorded
  in `db/session.py` for the future migration path.
- The originality score inside a batch still follows the approved
  rules' semantics (a flagged twin affects the originality metric's
  score — visible in the breakdown and paired with the review queue);
  making flags purely advisory would be a rules change for the owner.
- One demo observation: in the seeded batch, the correct submission
  scores 90.0 (not 100.0) *because its renamed twin is in the same
  batch* — the same behaviour the v1 UI showed, now with the finding
  explicitly queued in Similarity Review. Without a twin it is 100.0
  (service tests prove both).

## 8. Next steps (concrete)

1. Khushi: review + push (snapshot flow as before).
2. On a Docker host: run the suite with
   `AUTOGRADER_SANDBOX_BACKEND=docker` to exercise the adapter live.
3. Optional: background worker for batch evaluation; Alembic wiring;
   Playwright journeys once a browser-download path exists in CI.
