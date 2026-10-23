# Limitations (engineering, stated plainly)

For the *academic* Usefulness & Limitations deliverable (with concrete
wrong-verdict scenarios), see `docs/USEFULNESS_AND_LIMITATIONS.md`. This
file is the engineering list.

## Security

- The sandbox is **process-level isolation**: resource limits, wall-clock
  timeout with process-group kill, bounded output, scrubbed environment,
  per-run temp workspace, and a network namespace only where a live probe
  proves user namespaces work. It is **not a chroot/jail**: a submission
  can read any file the grading user can read. Run the grader as a
  dedicated user or inside a VM, and never next to secrets.
- Compilation of hostile source is bounded by a timeout, but a compiler is
  a large attack surface; the dedicated-user guidance above applies.

## Analysis

- Structure, modularity, readability, and the static half of complexity
  use a **heuristic C lexer** (comments/literals blanked, brace-matched
  functions), not a full C parser. Preprocessor-heavy or macro-generated
  code can be misread; findings record the method used.
- Empirical complexity classification needs runtimes above ~0.1 ms and a
  workload generator for scaled inputs; for assignments whose input size
  doesn't scale (like adding two integers), only the static leg applies,
  and static/empirical disagreement is reported as inconclusive.
- Memory safety is dynamic: ASan/UBSan only see the paths the trusted
  tests execute. A clean run is evidence, not proof.
- Profiling hardware counters require `perf` and kernel permission; where
  unavailable the report says so and gives wall-times only. Per-function
  counter attribution is not available.
- Similarity detects textual/structural resemblance after identifier
  canonicalization. It cannot detect heavily restructured copying, and a
  flag is a prompt for human review — never proof.
- The deterministic test generator currently covers the `int_pair_v1`
  problem shape. Other shapes rely on instructor cases + a validated
  reference (+ optional bounded LLM proposals for *inputs*); when those
  can't meet the D-1 bar, the outcome is insufficient evidence rather
  than invented tests.

## Scope

- Single-file C submissions only (the assignment's model). Multi-file
  projects are out of scope (open question U-08 from planning).
- The web UI is a local/lab tool: single-user, no authentication, binds
  to localhost by default. It is not a hosted service.
- LLM features are bounded and optional by design; with no Ollama the
  advisory readability prose and LLM setup proposals are simply absent.
- The cache trusts its key material completely: any input that can change
  the suite is hashed into the key, but a *wrong-but-trusted* instructor
  case or reference will systematically affect every student until the
  assignment is invalidated — which is why provenance is recorded and
  `cache invalidate` exists.

## Open items outside the code (owner: Khushi)

- Course deadline and weekly dates (U-01), group members and workload
  split (U-02), `agentic01.pdf` status (U-03) — never invented here.
- The professor's handwritten-requirements image was not re-supplied in
  this redo (U-10): the H-rows of the traceability matrix rest on the
  2026-10-19 transcription and remain PROVISIONAL until checked against
  the image.
- Real-machine verification on Khushi's WSL (Ollama model identifier,
  perf availability, tool set) is still to be done there; `doctor` and
  `benchmark` are the tools for it.
