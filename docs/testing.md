# Testing (v2)

## Deterministic (always run, must pass)

- Backend: `.venv/bin/python -m pytest` — 117 tests: engine units
  (config, scoring D-3, oracle-v2 incl. the wrong-reference-is-ignored
  proof, cache integrity, sandbox adversarial set), services (state
  machine legality, activation gating, duplicate handling, end-to-end
  batch), API journey (health → assignment → version → activate → batch
  → evaluate → investigation → report downloads → retry → disposition
  grade-immutability), sandbox backend policy (docker argv via injected
  runner; fail-closed without a daemon).
- Frontend: `cd frontend && npm run test` — 11 Vitest tests (formatting,
  CSV formula neutralization, filtering/sorting, upload validation, test
  states, badge/scorebar accessibility) + `npm run build` (tsc strict)
  + `npm run lint` (oxlint).

## Environment-dependent (reported honestly, never faked)

- **Docker sandbox live runs**: no Docker daemon exists on the dev
  machine, so live container execution is NOT exercised; the adapter is
  covered at argv-policy level and its unavailability is itself tested
  (fail-closed). On a Docker host, run the same suite with
  `AUTOGRADER_SANDBOX_BACKEND=docker`.
- **Ollama**: absent here; LLM paths are tested with a labelled fake
  transport. Deterministic mode is the default and fully tested.
- **Playwright/browser E2E**: dashboard rendering is verified by
  screenshots from a real Chromium against the live seeded server
  (see the completion report); scripted Playwright journeys are not yet
  part of CI on this machine.

## Coverage (pytest-cov, 2026-10-24)

87% overall. Business logic: oracle 94%, workflow 94%, state machine
94%, assignment service 91%, evaluation service 88%, scoring engine 86%,
API app 79%.
