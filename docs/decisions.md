# Decisions and deviations (v2, master prompt 2026-10-24)

Format: decision, basis, impact. Items marked **OWNER SIGN-OFF** change a
grading rule or security posture Khushi previously approved; they are not
applied silently (master prompt §0.11: never silently decide a grading
rule on behalf of an instructor).

**RESOLVED 2026-10-24 02:30 IST:** Khushi instructed "complete it exactly
as asked in the prompt, if required you can remove whatever" — DV-1 and
DV-2 below were therefore applied as proposed, and DV-5 was executed.
The build proceeded without further questions, per her instruction.

## DV-1 — Reference implementation as oracle — OWNER SIGN-OFF REQUIRED

- **Master prompt:** §0 rule 8, §1.2, §5.2 — no reference implementation
  may be required, requested, generated as a hidden oracle, or compared
  against. Accepted evidence: explicit examples, specification semantics,
  independently justified outcomes, properties/metamorphic relations,
  tool observations.
- **Current state (approved by Khushi 2026-10-22 as D-1):** the oracle
  accepts `instructor_provided`, `reference_run` (a supplied `reference.c`
  that must first pass all instructor cases) and
  `independent_derivation`.
- **Proposed deviation from the *old* design (i.e. adopt the prompt):**
  remove `reference_run` from the trust model. The add-two-integers
  example is unaffected in outcome: its 24 trusted tests come from
  instructor examples + deterministic derivation (mathematically correct
  sums, U-07 intact). `reference.c` leaves the assignment package's
  runtime inputs; the cache key drops the reference hash.
- **Impact:** oracle tests rewritten (reference/trojan cases become
  "reference is never consulted"); TRUST_MODEL.md updated; a class of
  systemic risk (wrong-but-validated reference skewing a whole cohort)
  disappears — the exact scenario LIMITATIONS.md already flags.

## DV-2 — Sandbox backend — OWNER SIGN-OFF REQUIRED

- **Master prompt:** §6 — compile/run only inside Docker; fail closed
  when Docker is unavailable; never fall back to host execution.
- **Evidence:** Docker is entirely absent on the development machine
  (no CLI, no daemon — audited 2026-10-24) and untested on Khushi's WSL.
  A Docker-only build cannot evaluate a single submission in either
  environment today, contradicting the prompt's own success criteria
  (§1.3) and its adaptation clause (§2/§14).
- **Proposed:** a sandbox *interface* with two adapters — (a) Docker
  adapter implementing §6's controls, used when a daemon is reachable;
  (b) the existing process adapter (prlimit + timeout + process-group
  kill + scrubbed env, 12 adversarial tests) used otherwise. The active
  backend and its isolation limits are reported by the health endpoint
  and stored in every run's provenance — never silently. Setting
  `SANDBOX_REQUIRE_DOCKER=true` yields the prompt's strict fail-closed
  behaviour for deployments that require it.
- **Impact:** the app works everywhere the current one does, gains the
  Docker path where available, and never *claims* Docker-grade isolation
  for the process backend (LIMITATIONS.md already states its limits).

## DV-3 — Layout: adapt, don't rewrite (no owner decision needed)

The prompt's §14 tree puts code under `backend/app/...`; the existing
package `src/autograder/` already provides the same module boundaries
(config, models, assignment, sandbox, analyzers, scoring, reports, llm,
workflow). v2 adds `db/`, `api/`, `services/` inside the existing package
and a top-level `frontend/`. Rationale: prompt §14's own first line —
"Adapt to an existing repository rather than forcing a rewrite."

## DV-4 — Rules format in the UI: JSON first (no owner decision needed)

The prompt specifies JSON rules. The existing loader already accepts JSON
and YAML under one strict schema. The UI editor will be JSON (with the
example in JSON); YAML files remain loadable via CLI/API. No rule
semantics change.

## DV-5 — Server-rendered UI retired when React covers the flows

The Stage-11 FastAPI HTML UI remains until the React dashboard covers
evaluate/reports/cache/doctor equivalents (M4–M6), then `web/` is removed
and the snapshot history records the replacement. Until then nothing
working is deleted (prompt §0.1).
