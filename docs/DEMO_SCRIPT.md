# Demo script — 15–20 minute walkthrough

A narration + command script for the required demonstration video. Run
everything from the repository root in a prepared virtualenv
(`docs/INSTALLATION.md`). Timings assume the reference machine; on a
slower laptop each segment still fits — the evaluations take ~1 s.

| Time | Segment | Show / say |
|---|---|---|
| 0:00–1:30 | Problem & promise | "AutoGrader grades C submissions against instructor rules. Three promises: grades are reproducible exactly, expected outputs are never invented by an LLM, and a hostile submission can't hang or hurt the grader." Show the assignment PDF's contract page briefly. |
| 1:30–3:00 | Environment honesty | `autograder doctor` — walk the probes: gcc present; Ollama absent on this machine and reported as absent; perf counters unavailable. "Every tool claim in this system is probed, not assumed." |
| 3:00–4:00 | Rules are data | Open `configs/example_rules.yaml`: 9 metrics, weights sum to 1.00, thresholds editable. `autograder validate-rules --rules configs/example_rules.yaml`. "Change grading policy by editing YAML — never code." |
| 4:00–6:30 | Trusted tests + cache | `autograder prepare-assignment --assignment examples/assignments/add_two_integers` (miss: 24 trusted tests, 24 validation executions). Run it again (hit: ~0.003 s, **0** executions). Explain the trust model (`docs/TRUST_MODEL.md`): instructor cases, a reference that must first pass them, independent derivation; contradictions are rejected; LLM proposals can't self-trust. Show `autograder cache list`. |
| 6:30–9:00 | A correct submission | `autograder evaluate --source examples/submissions/correct.c --assignment examples/assignments/add_two_integers --corpus-dir examples/submissions` → 100.0 complete. Open the HTML report: per-metric disclosure (weights, contributions, effective weights, coverage), provenance hashes. |
| 9:00–11:30 | A wrong submission with a story | Evaluate `incorrect.c` → 85.2. In the report: the counterexample (`-2147483648 -2147483648` → expected `-4294967296`, got `0`), modularity 0.5 (everything in `main`), and the UBSan finding naming the signed overflow. "The PDF's own example bug, caught three different ways." |
| 11:30–13:00 | Hostile submissions | Evaluate `timeout.c` → partial 53.0, `suspected_infinite_loop` flag, execution metrics skipped, source metrics still graded. Evaluate `compile_error.c` → partial 43.0. "The grader never hangs and never pretends a partial grade is a complete one." |
| 13:00–15:00 | Web UI | `autograder serve --assignments-dir examples/assignments --corpus-dir examples/submissions`; upload `incorrect.c`, show the same report in the browser (same grade — it's the same engine), the assignments/cache page and invalidation, the doctor page. |
| 15:00–17:00 | Reproducibility & speed | `autograder benchmark --assignment examples/assignments/add_two_integers` — setup miss vs hit, ~1 s evaluations vs the 2–3 min target; mention the previous design's 49-minute run and the structural fix (pay setup once, bound everything). Re-run one evaluation: same grade, digit for digit. |
| 17:00–19:00 | Tests & limitations | `python -m pytest -q` (109 tests incl. adversarial sandbox suite). Close with `docs/USEFULNESS_AND_LIMITATIONS.md`: tests sample behaviour, a wrong-but-validated reference is the deepest risk, heuristic analysis can misjudge macro-heavy code, and machine-dependent evidence is reported honestly rather than faked. |
| 19:00–20:00 | Wrap | Repo tour: `docs/ARCHITECTURE.md`, traceability matrix, sample outputs in `examples/outputs/`. "Working, verifiable software — every claim in this video can be re-run." |

## Fallbacks

- If Ollama is installed on the demo machine, `doctor` shows it and you
  may add: prepare with `--use-llm` to show the bounded setup call and its
  usage accounting (≤2 calls, logged). Never present fake-transport output
  as a real model result.
- If the demo machine lacks sanitizer runtimes, memory safety will show
  an environment error — use it as a live example of honest degradation,
  and show the retained reports in `examples/outputs/` for the full path.
