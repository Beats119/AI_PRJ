# Test trust model (Stages 6–7, policy `oracle-v1`)

A generated or proposed test is a **candidate**, not a trusted test. Trust is
established only by a source independent of whoever proposed the test.

| Category (`validation_method`) | Can it make a test trusted? | Why |
|---|---|---|
| `instructor_provided` — expected output stated by the instructor (tests.yaml) | Yes | Strongest available source: the assignment's own authority. |
| `reference_run` — output of the reference implementation | Yes, conditionally | Only after the reference has passed **every** instructor case. A reference that disagrees with an instructor case is rejected as a trust source (its outputs are then unusable). |
| `independent_derivation` — computed from the contract by a method independent of the student code and the LLM (e.g. arbitrary-precision integer addition) | Yes | The contract fully determines the output; the derivation is reproducible by anyone. |
| `reference_run+independent_derivation` | Yes (strongest generated form) | Two independent sources agree. If they ever **contradict**, the candidate is rejected rather than resolved by vote. |
| `llm_unverified` — the LLM proposed the expected output and nothing independent confirmed it | **Never** | A test must not become trusted merely because the LLM generated both its input and its expected output. Unverified cases stay in the suite marked untrusted: visible, excluded from scoring. |
| Rejected (`trust_status: rejected`) | No — not even in the suite | Invalid input (violates the contract's constraints), contradiction between independent sources, or a broken oracle/reference run. Rejections are recorded with reasons in the cache entry metadata. |

## Sufficiency (D-1)

An ordinary grade requires **all** of: every authoritative instructor case
trusted; each applicable *core* category (`ordinary_valid`,
`minimum_boundary`, `maximum_boundary`, `edge_values`) has ≥ the configured
minimum of trusted cases (default 2); each other applicable category has ≥ 1;
the total trusted count meets `min_trusted_total` (default 8); every counted
case carries provenance, a verification method, and a comparison policy; and
any reference used as a trust source passed validation first. A category is
*applicable* only when the contract says so — e.g. `invalid_input` counts
only when the assignment explicitly defines invalid-input behaviour, so the
grader never invents requirements the assignment does not state.

If the bar is not met, the outcome is **insufficient evidence** (D-3 case 1):
setup caches nothing and evaluation produces no ordinary grade.

## U-07 (addition example)

The supported contract is mathematically correct addition of two signed
32-bit operands; the sum is computed in 64-bit / arbitrary precision. No
expected output ever asserts a "wrapped" result for INT_MAX + 1: signed
overflow in C is undefined behaviour, not a specification.
