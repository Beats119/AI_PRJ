# Test trust model (policy `oracle-v2`, master prompt §5.2)

A generated or proposed test is a **candidate**, not a trusted test. Trust is
established only by a source independent of whoever proposed the test.

**Reference implementations are never used.** AutoGrader does not require,
request, generate, or compare against a reference solution (v1's
`reference_run` category was removed in oracle-v2). A `reference.c` file
present in an assignment directory is ignored by design — a test proves a
deliberately wrong one changes nothing.

| Category (`validation_method`) | Can it make a test trusted? | Why |
|---|---|---|
| `instructor_provided` — expected output stated by the instructor (examples) | Yes | Strongest available source: the assignment's own authority. |
| `independent_derivation` — computed from the contract by a method independent of the student code and the LLM (e.g. arbitrary-precision integer addition) | Yes | The contract fully determines the output; the derivation is reproducible by anyone. |
| `llm_unverified` — the LLM proposed the expected output and nothing independent confirmed it | **Never** | A test must not become trusted merely because the LLM generated both its input and its expected output. Unverified cases stay visible in the suite as `requires_review`, excluded from scoring. |
| Rejected (`trust_status: rejected`) | No — not even in the suite | Invalid input (violates the contract's constraints) or no justifiable expected output exists. Rejections are recorded with reasons. |

## Sufficiency (D-1)

An ordinary grade requires **all** of: every authoritative instructor case
trusted; each applicable *core* category (`ordinary_valid`,
`minimum_boundary`, `maximum_boundary`, `edge_values`) has ≥ the configured
minimum of trusted cases (default 2); each other applicable category has ≥ 1;
the total trusted count meets `min_trusted_total` (default 8); every counted
case carries provenance, a verification method, and a comparison policy; and
no trusted case was produced by a reference implementation (asserted as the
`no_reference_oracle` condition). A category is *applicable* only when the
contract says so — e.g. `invalid_input` counts only when the assignment
explicitly defines invalid-input behaviour, so the grader never invents
requirements the assignment does not state.

If the bar is not met, the outcome is **insufficient evidence** (D-3 case 1):
setup caches nothing, the dashboard version stays a non-activatable draft,
and evaluation produces no ordinary grade.

## U-07 (addition example)

The supported contract is mathematically correct addition of two signed
32-bit operands; the sum is derived in arbitrary precision. No expected
output ever asserts a "wrapped" result for INT_MAX + 1: signed overflow in C
is undefined behaviour, not a specification.
