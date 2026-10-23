"""Safe execution of a compiled submission against one test input.

Isolation actually applied (and reported in the result's diagnostics):
  * per-run temporary workspace containing only this submission's files
  * argv-array invocation (never a shell), scrubbed environment, cwd = workspace
  * resource limits via prlimit (CPU time, address space, file size, no cores)
  * output bounded by the file-size limit; captured output truncated to the cap
  * wall-clock timeout enforced by the parent; on timeout the WHOLE process
    group is killed, so forked children cannot outlive the run
  * a user+network namespace is added only when a live probe proved it works
    on this machine (limits.probe_network_namespace)

Honest limit: this is process-level isolation for a classroom/lab setting.
It does not provide a chroot; a submission can read host files that the
grading user can read. Run the grader as a dedicated user on a dedicated
machine/VM. See docs/LIMITATIONS.md (Stage 13).
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Self

from autograder.models.execution import ExecutionResult, ExecutionStatus
from autograder.sandbox.compiler import CompileResult, compile_source
from autograder.sandbox.limits import (
    ExecutionLimits,
    namespace_prefix,
    prlimit_prefix,
    probe_network_namespace,
)

_SIGXCPU = int(signal.SIGXCPU)
_SIGXFSZ = int(signal.SIGXFSZ)


def _read_capped(path: Path, cap: int) -> tuple[str, int]:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return "", 0
    with path.open("rb") as fh:
        data = fh.read(cap)
    return data.decode("utf-8", errors="replace"), size


def run_program(
    binary_path: str | Path,
    *,
    workspace: str | Path,
    test_id: str,
    submission_hash: str,
    input_data: str = "",
    limits: ExecutionLimits | None = None,
    use_namespace: bool = True,
) -> ExecutionResult:
    limits = limits or ExecutionLimits()
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    if not Path(binary_path).is_file():
        # Our infrastructure problem, never the student's: the compiled
        # binary should exist. (Detected here, before wrapper prefixes
        # could disguise it as a program exit code.)
        return ExecutionResult(
            submission_hash=submission_hash,
            test_id=test_id,
            status=ExecutionStatus.TOOL_ERROR,
            exit_code=None,
            duration_ms=0.0,
            diagnostics=[f"binary not found: {binary_path}"],
        )
    stdout_file = workspace / f"out_{test_id}.txt"
    stderr_file = workspace / f"err_{test_id}.txt"
    input_file = workspace / f"in_{test_id}.txt"
    input_file.write_text(input_data, encoding="utf-8")

    netns = bool(use_namespace and probe_network_namespace())
    argv: list[str] = []
    if netns:
        argv += namespace_prefix()
    argv += prlimit_prefix(limits)
    argv.append(str(binary_path))

    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(workspace)}
    diagnostics = [
        (
            f"isolation: process_limits={'prlimit' if prlimit_prefix(limits) else 'none'}"
            f", network_namespace={'on' if netns else 'off'}"
        )
    ]

    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    fin = input_file.open("rb")
    fout = stdout_file.open("wb")
    ferr = stderr_file.open("wb")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=fin,
            stdout=fout,
            stderr=ferr,
            cwd=str(workspace),
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        fin.close(), fout.close(), ferr.close()
        return ExecutionResult(
            submission_hash=submission_hash,
            test_id=test_id,
            status=ExecutionStatus.TOOL_ERROR,
            exit_code=None,
            duration_ms=(time.monotonic() - started) * 1000,
            diagnostics=diagnostics + [f"could not start the program: {exc}"],
        )
    try:
        try:
            returncode = proc.wait(timeout=limits.wall_time_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = proc.wait(timeout=5)
    finally:
        fin.close(), fout.close(), ferr.close()
    duration_ms = (time.monotonic() - started) * 1000

    cap = limits.max_output_bytes
    stdout, stdout_size = _read_capped(stdout_file, cap)
    stderr, stderr_size = _read_capped(stderr_file, cap)
    flooded = stdout_size >= cap or stderr_size >= cap

    if flooded or (returncode is not None and returncode == -_SIGXFSZ):
        status = ExecutionStatus.EXCESSIVE_OUTPUT
        diagnostics.append("output reached the configured cap and was truncated")
    elif timed_out:
        status = ExecutionStatus.TIMEOUT
        diagnostics.append(f"exceeded wall-clock limit of {limits.wall_time_s}s; "
                             "process group killed")
    elif returncode is not None and returncode == -_SIGXCPU:
        status = ExecutionStatus.RESOURCE_EXCEEDED
        diagnostics.append("exceeded CPU time limit")
    elif returncode is not None and returncode < 0:
        status = ExecutionStatus.CRASH
        diagnostics.append(f"terminated by signal {-returncode}")
    elif returncode is None:
        status = ExecutionStatus.TOOL_ERROR
        diagnostics.append("execution outcome unknown")
    else:
        status = ExecutionStatus.OK

    return ExecutionResult(
        submission_hash=submission_hash,
        test_id=test_id,
        status=status,
        stdout=stdout,
        stderr=stderr,
        exit_code=returncode,
        duration_ms=duration_ms,
        resource_usage={
            "stdout_bytes": float(stdout_size),
            "stderr_bytes": float(stderr_size),
            "wall_time_s": limits.wall_time_s,
        },
        diagnostics=diagnostics,
    )


class Sandbox:
    """A per-submission workspace: compile here, run here, cleaned on exit."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="autograder-")
        self.workspace = Path(self._tmp.name)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()

    def compile(self, source_path: str | Path, **kwargs) -> CompileResult:
        return compile_source(source_path, self.workspace, **kwargs)

    def run(self, binary_path: str | Path, **kwargs) -> ExecutionResult:
        kwargs.setdefault("workspace", self.workspace)
        return run_program(binary_path, **kwargs)
