# Evaluation flow (v2)

The dashboard flow Khushi specified, end to end:

```
1. CREATE / SELECT ASSIGNMENT
   problem statement + input/output contracts
   → JSON rules & rubric (validated in the editor, problems located)
   → preparation (Agent 1): spec → bounded candidates → oracle-v2
     verification → D-1 sufficiency bar
       ├─ bar not met → version stays DRAFT: ambiguity/unresolved items
       │   listed, activation impossible, nothing can be graded
       └─ bar met → VALIDATED → instructor ACTIVATES the version
2. UPLOAD BATCH (many .c files at once)
   → per-file validation, exact-duplicate detection (duplicates stored
     outside the peer corpus, visibly marked, never evaluated)
   → EVALUATE: for each submission a durable run walks
     queued → preparing → compiling → testing → analyzing →
     validating_evidence → scoring → reporting → completed |
     needs_review (incomplete outcome) | failed (infrastructure,
     e.g. sandbox fail-closed) | cancelled
     (tests + static analysis | complexity | similarity vs batch peers)
   → deterministic rubric scoring from validated evidence only
3. ONE CONSOLIDATED DASHBOARD
   grades · tests passed · compile status · failures with
   input/expected/actual · feedback · similarity flags for review
   → per-submission investigation (rubric trace, source, evidence)
   → similarity review queue (dispositions never change grades)
```

Scoring invariants (engine, unchanged): only `validated` tests affect
points; unverifiable expected outputs never deduct; tool-unavailable is
distinguishable from student failure (D-3 matrix); similarity is
evidence, not a verdict.
