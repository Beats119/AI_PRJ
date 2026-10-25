"""V2 sandbox backends: docker argv policy, fail-closed, honest status.

No Docker daemon exists on this machine, so the Docker adapter is tested
through an injected command runner that records argv (policy proof), and
the fail-closed behaviour is tested for real. Live docker execution is
NOT claimed anywhere.
"""

import subprocess
from pathlib import Path

import pytest

from autograder.models.execution import ExecutionStatus
from autograder.sandbox.docker_runner import (
    DockerSandbox,
    SandboxUnavailable,
    backend_status,
    make_sandbox,
)
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits


class FakeRunner:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "gcc" in argv:
            # simulate a successful compile: create the -o artifact
            out = argv[argv.index("-o") + 1]
            ws = next(
                a.split("src=")[1].split(",")[0]
                for a in argv if a.startswith("type=bind")
            )
            Path(ws, out).write_bytes(b"\x7fELF-fake")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, "42\n", "")


def test_docker_argv_enforces_prompt_controls(tmp_path):
    runner = FakeRunner()
    src = tmp_path / "s.c"
    src.write_text("int main(void){return 0;}\n")
    with DockerSandbox(runner=runner, check_available=False) as sb:
        comp = sb.compile(src)
        assert comp.success
        res = sb.run(
            comp.binary_path, test_id="t1", submission_hash="sha256:x",
            input_data="20 22\n", limits=ExecutionLimits(wall_time_s=1, memory_mb=64),
        )
    assert res.status is ExecutionStatus.OK and res.stdout == "42\n"
    run_argv = runner.calls[-1]
    joined = " ".join(run_argv)
    for token in (
        "--network=none", "--cap-drop", "ALL", "no-new-privileges",
        "--read-only", "--memory", "64m", "--pids-limit", "--user",
    ):
        assert token in joined, token
    assert "readonly" in joined  # workspace mounted read-only for runs


def test_docker_backend_fails_closed_without_daemon():
    # Real environment: no docker. Selecting it must raise, never fall back.
    with pytest.raises(SandboxUnavailable):
        make_sandbox("docker")
    status = backend_status()
    assert status["docker_available"] is False
    assert status["selected_backend"] == "process"  # auto mode is honest


def test_process_backend_still_default_and_working():
    with make_sandbox("process") as sb:
        assert isinstance(sb, Sandbox)
