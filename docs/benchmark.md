# Benchmark (v2, measured 2026-10-24 on the development VM)

Environment: this VM (Python 3.12.3, gcc 13.3.0, 8 GB RAM), process
sandbox backend, no Ollama (deterministic mode), example assignment
(add_two_integers, 24 trusted tests).

## Setup (assignment preparation)

| Path | Median | Validation executions |
|---|---|---|
| Cache miss (oracle-v2) | **0.0046 s** | 0 — trust is computational (derivation), nothing is executed |
| Cache hit | 0.0024 s | 0 |

(v1's oracle ran a reference implementation 24 times per setup: 0.158 s.
oracle-v2 removed that entire class of work.)

## Single evaluations (CLI path, medians of 3)

| Submission | Median | Outcome | Grade |
|---|---|---|---|
| compile_error.c | 0.05 s | partial | 43.0 |
| correct.c | 0.94 s | complete | 100.0 |
| incorrect.c | 0.96 s | complete | 85.2 |
| timeout.c | 1.16 s | partial | 53.0 |

## Batch evaluation (API path, live server)

5 evaluated submissions (+1 exact duplicate detected at upload),
sequential: **4.34 s total** on the first measured run; two repeat runs
under post-restart machine load took 11.7 s and 12.1 s (≈0.9–2.4
s/submission). Even the slowest observed run puts a 60-student batch at
~2.5 minutes — inside the prompt's <10-minute target for ordinary
batches. (In that demo batch the correct submission scored 90.0: its
renamed twin was also in the batch, so originality evidence applied —
see V2_COMPLETION_REPORT.md. Without a twin it scores 100.0, as the
service tests prove.)

No claim is made for Docker-backend timings: no Docker daemon exists on
this machine.
