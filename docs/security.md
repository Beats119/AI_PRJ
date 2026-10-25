# Security (v2)

## Sandbox backends

One interface (`sandbox/`), two adapters, selected by
`AUTOGRADER_SANDBOX_BACKEND=auto|docker|process` (auto = docker when a
daemon is reachable, else process). The active backend and its limits
are shown in Settings & Health and recorded per run — never silently
substituted.

**Docker adapter** (`sandbox/docker_runner.py`) — when Docker exists:
one-off `--rm` containers, `--network=none`, `--cap-drop ALL`,
`--security-opt no-new-privileges`, unprivileged uid, read-only root
filesystem for execution with the per-run workspace bind-mounted
read-only, `--memory`/`--cpus`/`--pids-limit` from the run limits,
host-side timeout that removes the container. Selecting docker without
a daemon **fails closed** (`SandboxUnavailable` → the run is recorded
`failed` with the reason); student code is never executed on the host
as a silent fallback. `AUTOGRADER_REQUIRE_DOCKER=1` forces this posture
in auto mode. Live Docker execution is **not available on the
development machine** (no daemon): the adapter's argv policy is
unit-tested with an injected runner, and live behaviour is documented
as untested-here rather than claimed.

**Process adapter** (default here) — prlimit (CPU/AS/file size),
wall-clock timeout with process-group kill, scrubbed environment,
per-run temp workspace, namespace only when a live probe proves it
works. It is process-level isolation, **not a chroot**: run the grader
as a dedicated user on a dedicated machine/VM. Docker reduces risk; it
is not a formal proof of isolation either.

## Application-level controls

- Uploads: `.c` only, 1 MB cap, stored under server-generated names in
  the app data dir (user filenames never become paths — traversal-safe).
- Rules/JSON: strict schema validation with located, actionable errors;
  unknown fields rejected.
- Student content is data: source code/comments are never executed as
  shell, never interpreted as instructions; report HTML escapes all
  student-derived text (tested).
- CSV export neutralizes spreadsheet formula prefixes (`= + - @`).
- LLM (Ollama) is bounded (≤2 setup calls, advisory/readability only),
  its expected outputs are never trusted, and the system is fully
  functional without it.
- No reference solutions exist anywhere in the runtime path
  (oracle-v2), removing the poisoned-oracle failure class entirely.
