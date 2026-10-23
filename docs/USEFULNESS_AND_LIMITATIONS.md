# Usefulness and Limitations

*(The assignment's required section: 3–4 concrete examples of each. Every
limitation names a specific scenario in which a verdict can be wrong or
unreliable.)*

## Usefulness

1. **A class set graded in minutes, with receipts.** Once an assignment's
   trusted suite is built (≈0.16 s for the worked example), each
   submission grades in ≈1 s, and every grade decomposes into per-metric
   contributions a student or teacher can audit. In a hiring/interview
   screen (the PDF's scenario), 500 candidates could be ranked with an
   explainable per-metric reason for every rejection instead of a bare
   score.
2. **Counterexamples students can act on.** A wrong submission doesn't get
   "correctness: failed" — it gets the exact failing input, the trusted
   expected output, and its own actual output (e.g. input
   `-2147483648 -2147483648`, expected `-4294967296`, got `0`), plus
   per-function findings with concrete fixes. That is feedback a student
   can debug from immediately.
3. **It catches real bugs that output-checking alone misses.** The PDF's
   own example submission produces the "expected" wrapped answer for
   several overflow inputs on common platforms — plain diffing can pass
   or fail it inconsistently. AutoGrader's UBSan run names the actual
   defect: `signed integer overflow: -2147483648 + -2147483648 cannot be
   represented in type 'int'`. Memory errors and leaks are likewise
   reported from sanitizer evidence, not guessed.
4. **Copying triage that respects the accused.** Pairwise similarity over
   the whole class (N(N−1)/2 pairs) flags only pairs at/above the
   instructor's threshold (e.g. 0.93 ≥ 0.85) for human review, resists
   variable renaming, and every flag states that similarity is not proof
   of copying — a shortlist for a human, not a verdict.

## Limitations

1. **Tests sample behaviour; they cannot prove correctness.** A
   submission can pass all 24 trusted tests and still be wrong on an
   input shape no test covers — e.g. an addition program that reads with
   `%d` and prints with extra trailing spaces may pass a
   whitespace-normalized comparison while violating a stricter output
   contract the instructor intended but never specified. Mitigation:
   generated categories include parsing/whitespace variants, and the
   comparison policy is explicit — but an unstated requirement cannot be
   graded.
2. **The trusted suite is only as good as its trust sources.** If an
   instructor's reference implementation is subtly wrong *and* agrees
   with the instructor's examples (so it passes validation), the oracle
   will trust its outputs and mark correct students wrong on those
   inputs — systematically, for the whole class, until someone notices
   and runs `cache invalidate`. Provenance and the reference-must-pass-
   examples gate reduce this risk; they cannot eliminate it.
3. **Heuristic source analysis can misjudge unusual code.** Structure
   and complexity read a brace-matched, comment-stripped view of the
   source. A correct program that generates its logic through macros, or
   a recursive algorithm whose loop depth is data-dependent, can be
   scored as more (or less) complex than it truly is; timing-based
   classification on a noisy shared machine can likewise land on
   "inconclusive" for a genuinely O(n) program — in which case the D-3
   policy makes the outcome provisional rather than pretending certainty.
4. **Machine-dependent evidence is honestly variable.** On a host
   without `perf` (like the reference VM), cache-miss counters are
   unreadable and profiling reports wall-times only; on a host without
   sanitizer runtimes, memory safety becomes an environment error rather
   than a student verdict. The same submission can therefore receive a
   *complete* grade on one lab machine and an *incomplete (environment)*
   outcome on another — by design, because grading a student for our
   missing tools would be worse, but it is a real operational limitation.
