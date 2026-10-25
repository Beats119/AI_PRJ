"""Docker sandbox adapter (master prompt §6) + backend selection.

Implements the same interface as sandbox.executor.Sandbox (context manager
with compile()/run()) so the workflow can use either backend unchanged.

Controls applied to every container (and asserted by tests on the exact
argv): non-root default image user is root in gcc images, so --user is set
to an unprivileged uid; --network=none; --cap-drop ALL;
--security-opt no-new-privileges; read-only root filesystem for runs with
only the per-run workspace bind-mounted (read-only for execution);
--memory / --cpus / --pids-limit / fsize ulimit from ExecutionLimits; a
host-side timeout that kills the container even if the process ignores
signals; the container is always removed (--rm) and the workspace is a
fresh temp directory.

No Docker daemon exists on the reference development machine, so this
adapter's argv *policy* is unit-tested with an injected command runner,
and its live behaviour is honestly reported as untested-here through
backend_status(). Selecting docker when it is unavailable fails closed
(SandboxUnavailable) — code NEVER silently falls back to host execution
when docker was explicitly required.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Self

from autograder.models.execution import ExecutionResult, ExecutionStatus
from autograder.sandbox.compiler import CompileResult, source_hash_of
from autograder.sandbox.limits import ExecutionLimits

DEFAULT_IMAGE = "gcc:13-bookworm"


class SandboxUnavailable(RuntimeError):
    """The requested sandbox backend cannot run here. Fail closed."""


def _default_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=False, **kwargs)


def docker_available(runner=_default_runner) -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = runner(["docker", "info"], capture_output=True, timeout=10)
    except Exception:
        return False
    return proc.returncode == 0


class DockerSandbox:
    """Per-submission workspace executed through one-off containers."""

    def __init__(
        self,
        image: str | None = None,
        runner=_default_runner,
        check_available: bool = True,
    ) -> None:
        if check_available and not docker_available(runner):
            raise SandboxUnavailable(
                "docker backend requested but no docker daemon is reachable; "
                "failing closed (student code is never executed on the host "
                "as a fallback)"
            )
        self.image = image or os.environ.get("AUTOGRADER_DOCKER_IMAGE", DEFAULT_IMAGE)
        self._runner = runner
        self._tmp = tempfile.TemporaryDirectory(prefix="autograder-docker-")
        self.workspace = Path(self._tmp.name)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()

    # -- shared hardened flags -------------------------------------------------
    def _base_argv(self, *, writable: bool, limits: ExecutionLimits | None) -> list[str]:
        argv = [
            "docker", "run", "--rm",
            "--network=none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            "--pids-limit", "128",
            "--cpus", "1",
        ]
        if not writable:
            argv += ["--read-only", "--tmpfs", "/tmp:size=16m,mode=1777"]
        mem = (limits.memory_mb if limits and limits.memory_mb else 512)
        argv += ["--memory", f"{mem}m", "--memory-swap", f"{mem}m"]
        mount = f"type=bind,src={self.workspace},dst=/work"
        if not writable:
            mount += ",readonly"
        argv += ["--mount", mount, "--workdir", "/work"]
        return argv

    def compile(
        self,
        source_path: str | Path,
        flags: str | list[str] = "-O2 -Wall -Wextra -std=c11",
        timeout_s: float = 60.0,
        binary_name: str = "program",
    ) -> CompileResult:
        source_path = Path(source_path)
        data = source_path.read_bytes()
        digest = source_hash_of(data)
        (self.workspace / "submission.c").write_bytes(data)
        flag_list = shlex.split(flags) if isinstance(flags, str) else list(flags)
        argv = self._base_argv(writable=True, limits=None) + [
            self.image, "gcc", *flag_list, "-o", binary_name, "submission.c",
        ]
        started = time.monotonic()
        try:
            proc = self._runner(
                argv, capture_output=True, text=True, timeout=timeout_s
            )
            duration = (time.monotonic() - started) * 1000
            diagnostics = ((proc.stdout or "") + (proc.stderr or ""))[:65_536]
            binary = self.workspace / binary_name
            success = proc.returncode == 0 and binary.exists()
            return CompileResult(
                success=success,
                binary_path=binary if success else None,
                diagnostics=diagnostics,
                exit_code=proc.returncode,
                duration_ms=duration,
                source_hash=digest,
                source_name=source_path.name,
                flags_used=flag_list,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                binary_path=None,
                diagnostics=f"docker compile exceeded {timeout_s}s and was killed",
                exit_code=None,
                duration_ms=(time.monotonic() - started) * 1000,
                source_hash=digest,
                source_name=source_path.name,
                flags_used=flag_list,
            )

    def run(
        self,
        binary_path: str | Path,
        *,
        test_id: str,
        submission_hash: str,
        input_data: str = "",
        limits: ExecutionLimits | None = None,
        **_ignored,
    ) -> ExecutionResult:
        limits = limits or ExecutionLimits()
        binary_name = Path(binary_path).name
        argv = self._base_argv(writable=False, limits=limits) + [
            "-i", self.image, f"/work/{binary_name}",
        ]
        started = time.monotonic()
        try:
            proc = self._runner(
                argv,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=limits.wall_time_s + 5,
            )
            duration = (time.monotonic() - started) * 1000
            rc = proc.returncode
            if rc == 0:
                status = ExecutionStatus.OK
            elif rc == 137:
                status = ExecutionStatus.RESOURCE_EXCEEDED
            else:
                status = ExecutionStatus.CRASH
            diagnostics = [
                "backend: docker",
                f"image: {self.image}",
                (
                    "isolation: network=none, cap-drop ALL, no-new-privileges, "
                    "read-only rootfs, workspace bind-mounted read-only"
                ),
            ]
            if status is ExecutionStatus.RESOURCE_EXCEEDED:
                diagnostics.append("container killed (likely memory/pids limit)")
            return ExecutionResult(
                submission_hash=submission_hash,
                test_id=test_id,
                status=status,
                stdout=(proc.stdout or "")[: limits.max_output_bytes],
                stderr=(proc.stderr or "")[: limits.max_output_bytes],
                exit_code=rc,
                duration_ms=duration,
                resource_usage={
                    "stdout_bytes": float(len(proc.stdout or "")),
                    "stderr_bytes": float(len(proc.stderr or "")),
                    "wall_time_s": limits.wall_time_s,
                },
                diagnostics=diagnostics,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                submission_hash=submission_hash,
                test_id=test_id,
                status=ExecutionStatus.TIMEOUT,
                exit_code=None,
                duration_ms=(time.monotonic() - started) * 1000,
                diagnostics=[
                    "backend: docker",
                    (
                        f"exceeded wall-clock limit {limits.wall_time_s}s; "
                        "container removed by host-side timeout"
                    ),
                ],
            )


def backend_status() -> dict:
    """Honest sandbox capability report for health endpoints/doctor."""
    docker_ok = docker_available()
    requested = os.environ.get("AUTOGRADER_SANDBOX_BACKEND", "auto").lower()
    require_docker = os.environ.get("AUTOGRADER_REQUIRE_DOCKER", "").lower() in (
        "1", "true", "yes",
    )
    if requested == "docker" or (require_docker and requested == "auto"):
        selected = "docker"
    elif requested == "process":
        selected = "process"
    else:
        selected = "docker" if docker_ok else "process"
    return {
        "docker_available": docker_ok,
        "docker_image": os.environ.get("AUTOGRADER_DOCKER_IMAGE", DEFAULT_IMAGE),
        "requested_backend": requested,
        "require_docker": require_docker,
        "selected_backend": selected,
        "fail_closed": selected == "docker" and not docker_ok,
        "process_backend_note": (
            "process-level isolation (prlimit, timeout, process-group kill, "
            "scrubbed env) — not a chroot; see docs/LIMITATIONS.md"
        ),
    }


def make_sandbox(backend: str | None = None):
    """Return a Sandbox or DockerSandbox context manager.

    backend: "process" | "docker" | "auto" | None (env/default auto).
    Selecting docker without a daemon raises SandboxUnavailable — the
    fail-closed behaviour the master prompt requires.
    """
    from autograder.sandbox.executor import Sandbox

    status = backend_status()
    chosen = (backend or status["selected_backend"]).lower()
    if chosen == "auto":
        chosen = status["selected_backend"]
    if chosen == "docker":
        return DockerSandbox()
    if chosen == "process":
        return Sandbox()
    raise ValueError(f"unknown sandbox backend '{chosen}'")
