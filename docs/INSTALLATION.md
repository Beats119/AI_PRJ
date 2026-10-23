# Installation

## Requirements

- Linux (developed and verified on Ubuntu 24.04; WSL2 works the same way)
- Python 3.11+
- gcc (the submissions are C; `gcc --version` should succeed)
- Optional: Ollama with a Llama 3.1 model for the bounded LLM features
  (setup proposals / readability advisory). **The grader is fully usable
  without it** — deterministic paths cover grading; `doctor` reports its
  absence honestly.
- Optional: `perf` for hardware cache counters in profiling evidence.
  Without it, profiling still reports real wall-times and states that
  counters are unreadable.

## Install

```bash
git clone https://github.com/Beats119/AI_PRJ.git
cd AI_PRJ
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"        # core + test tooling
.venv/bin/pip install -e ".[web]"        # add this for the web UI
```

## Verify the environment

```bash
.venv/bin/autograder doctor              # real probes: gcc, tools, Ollama, limits
.venv/bin/autograder validate-rules --rules configs/example_rules.yaml
```

`doctor` never guesses: a tool it cannot find or run is reported as such,
and analyzers that need a missing tool return an *environment* outcome
instead of scoring the student for it.

## Run

```bash
# 1) Build (or reuse) the trusted test suite for an assignment — once
.venv/bin/autograder prepare-assignment \
  --assignment examples/assignments/add_two_integers

# 2) Evaluate one submission (writes <name>.json/.html/.txt)
.venv/bin/autograder evaluate \
  --source examples/submissions/correct.c \
  --assignment examples/assignments/add_two_integers \
  --corpus-dir examples/submissions

# 3) Inspect or invalidate the suite cache
.venv/bin/autograder cache list
.venv/bin/autograder cache invalidate --assignment-id add_two_integers

# 4) Benchmarks (cold vs warm setup, per-submission timings)
.venv/bin/autograder benchmark --assignment examples/assignments/add_two_integers

# 5) Web UI (http://127.0.0.1:8000)
.venv/bin/autograder serve --assignments-dir examples/assignments \
  --corpus-dir examples/submissions
```

Exit codes for `evaluate`: `0` = evaluation completed (any grade, including
failing ones — the grade carries the news), `4` = completed but
*incomplete* (insufficient trusted evidence or a host-blocked required
metric), `2` = configuration/input error.

## Configuration

- Grading policy: an instructor rules file (YAML or JSON) — see
  `configs/example_rules.yaml`. Weights must sum to 1.00; thresholds,
  generation bounds (D-2) and the sufficiency bar (D-1) all live there.
  Changing them never requires editing code.
- LLM: `configs/models.yaml` (backend, model, temperature 0, seed, and the
  hard call caps). Point `base_url` at your Ollama if it is not on
  `127.0.0.1:11434`.

## Tests

```bash
.venv/bin/python -m pytest        # full suite (unit + integration + security)
.venv/bin/ruff check src tests
```

See `docs/TESTING.md` for what is covered and the honesty rules
(mocked LLM transports are labelled `fake`; nothing requires a live Ollama).

## Troubleshooting

- *Ollama unreachable in `doctor`* — expected without a local install; only
  the optional LLM features are affected.
- *`perf` counters unreadable* — perf not installed or
  `kernel.perf_event_paranoid` too restrictive; profiling evidence says
  which. Install `linux-tools` / adjust the sysctl on a machine you own if
  you need counters.
- *Memory-safety environment error* — the ASan/UBSan probe failed (missing
  runtime libraries). Install your distro's compiler runtime packages.
- Run the grader as a **dedicated user or in a VM**: the sandbox is
  process-level isolation, not a chroot (see `docs/LIMITATIONS.md`).
