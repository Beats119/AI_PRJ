# Final acceptance review (Stage 14)

Performed 2026-10-24 in a **clean environment**: `git archive HEAD`
extracted to a fresh directory, a brand-new virtualenv, installation
strictly per `docs/INSTALLATION.md`, then the documented commands.
This review caught two real defects (below) that the in-place development
venv had masked — both fixed and re-verified before this document was
written.

## The 13 questions

1. **Can a user install and run the project from the documented
   instructions?** Yes — clean-room install (`pip install -e ".[dev,web]"`)
   succeeded and every documented command ran. *Defects found & fixed
   during this review:* (a) `.gitignore`'s bare `reports/` pattern had
   silently excluded the whole `src/autograder/reports/` package from
   every commit — a fresh clone would not have run; the pattern is now
   scoped to the root runtime directory and the package is committed.
   (b) `httpx` (FastAPI TestClient dependency) was missing from the dev
   extra; now declared.
2. **Does the complete workflow work on the example assignment?** Yes —
   in the clean room: prepare (miss → 24 trusted tests) → prepare (hit)
   → evaluate correct.c = **complete, 100.0**, timeout.c = **partial,
   53.0** with the infinite-loop flag; cache list shows the suite.
3. **Safely handle incorrect, crashing, non-terminating submissions?**
   Yes — incorrect.c grades with counterexamples; the security suite runs
   real segfault/fork-bomb/output-flood/infinite-loop programs through
   the sandbox and the grader survives all of them (12 adversarial
   tests); timeout.c is killed at the rules limit, every time.
4. **Are expected outputs trusted and traceable?** Yes — every trusted
   test records provenance + verification method (`docs/TRUST_MODEL.md`);
   a reference must pass all instructor cases before it may vouch for
   outputs; reference/derivation contradictions are rejected; LLM
   outputs can never self-trust. U-07 holds: no trusted test asserts a
   wrapped signed-overflow result.
5. **Does the second student reuse the validated suite?** Yes — proven
   by benchmark: cache hit performs **0** validation executions and
   costs ~0.003 s vs ~0.158 s for setup; evaluation reports record
   `cache_status: prepared_cache_hit`.
6. **Do relevant changes invalidate stale entries?** Yes — the cache key
   hashes spec content, the full rules file, generation + sufficiency
   config, generator/oracle versions, comparison policy, reference hash
   and model identity; changing any of them produces a different key
   (tested). `cache invalidate` removes an assignment's entries.
7. **Identical source + rules → same grade?** Yes — Decimal scoring,
   deterministic suite, no timestamps in reports. Repeat-run tests assert
   identical grades, per-metric scores, contributions and evaluation IDs;
   benchmark repetitions return identical grades.
8. **Complexity, memory safety, profiling, cache misses, similarity —
   implemented honestly?** Yes, with stated bounds: complexity is
   static + an empirical classifier that refuses noise (inconclusive,
   never fabricated); memory safety is real ASan/UBSan with a probe-first
   environment outcome; profiling reports real wall-times and labels
   unreadable counters (perf absent on the reference VM — stated, not
   faked); similarity is canonicalized shingle Jaccard with the
   "not proof" caveat on every flag.
9. **Unavailable tools reported accurately?** Yes — `doctor` probes
   reality (on the reference VM: gcc 13.3 present; ollama, cppcheck,
   valgrind, perf, lizard absent — and reported absent); analyzers
   degrade to labelled environment outcomes, never silent passes.
10. **Reports evidence-backed and internally consistent?** Yes — one
    canonical `EvaluationReport`; JSON/HTML/TXT are renderings of it
    (agreement tested); each discloses weights, contributions, effective
    weights, coverage, counterexamples, limitations and provenance
    hashes. Nothing is invented to fill a field: unavailable data is
    `null` plus a reason.
11. **Every academic requirement mapped to implementation and
    verification?** Yes — `docs/REQUIREMENTS_TRACEABILITY.md`. Known
    partials/deviations are recorded there, not hidden: H-08 per-function
    cache attribution (host-limited), E-13 pair-result caching (not
    implemented — recomputed, negligible at classroom scale), P-26/P-27
    notes (static complexity also runs on the smoke-timeout branch;
    dispatch is sequential by design).
12. **Real tests and benchmarks run and recorded?** Yes — full suite
    **109 passed** in the clean room (and in-place), ruff clean;
    benchmarks in `docs/BENCHMARKS.md` + `benchmarks/benchmark_results.json`
    (medians of 3): setup miss 0.158 s, hit 0.003 s, evaluations
    0.05–1.15 s vs the 2–3 minute target.
13. **All known incomplete items clearly disclosed?** Yes —
    `docs/LIMITATIONS.md` and the RTM's Open rows: course deadline (U-01),
    group members/workload (U-02) and `agentic01.pdf` status (U-03) are
    Khushi's inputs, never invented; the professor's handwritten image
    (U-10) was never re-supplied, so H-rows remain PROVISIONAL against
    the 2026-10-19 transcription; WSL verification of the Ollama model
    identifier and tool set (U-05/U-06) remains to be done on Khushi's
    machine with `doctor`/`benchmark`. Nothing has been pushed to GitHub;
    all commits are local, per Khushi's standing instruction.

## Verdict

The application is complete against the specification as approved
through Khushi's stage gates: a working, verifiable grader whose claims
are all backed by the tests and measurements cited above. Remaining work
is course logistics (group data, agentic01, video recording, the push
decision) — all owned by, and awaiting, Khushi.
