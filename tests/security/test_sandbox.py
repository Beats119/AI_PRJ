"""Stage 5 sandbox tests (spec section 7: compilation and execution).

These run the REAL compiler and executor — no mocks. Adversarial programs
(timeout, crash, output flood, memory hog, forked child, environment probe)
must all be contained, and the grader must survive every one of them.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

from autograder.models.execution import ExecutionStatus
from autograder.sandbox import ExecutionLimits, Sandbox

ADD = r"""
#include <stdio.h>
int main(void){ long long a,b; if(scanf("%lld %lld",&a,&b)!=2) return 1;
  printf("%lld\n", a+b); return 0; }
"""

BROKEN = "int main(void){ this is not C; }"

LOOP = r"""
#include <stdio.h>
int main(void){ for(;;){ } return 0; }
"""

FORK_LOOP = r"""
#include <unistd.h>
int main(void){ if(fork()==0){ for(;;){} } for(;;){} return 0; }
"""

CRASH = r"""
int main(void){ int *p = 0; *p = 42; return 0; }
"""

FLOOD = r"""
#include <stdio.h>
int main(void){ for(;;){ printf("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"); } }
"""

ALLOC = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void){
  size_t n = 512UL*1024*1024; char *p = malloc(n);
  if(!p){ printf("alloc failed\n"); return 3; }
  memset(p, 1, n); printf("allocated\n"); return 0; }
"""

ENVPROBE = r"""
#include <stdio.h>
#include <stdlib.h>
int main(void){ const char *v = getenv("AUTOGRADER_SECRET");
  printf("%s\n", v ? "leaked" : "absent"); return 0; }
"""


def _src(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code)
    return p


def _compile_and_run(tmp_path, code, input_data="", limits=None, name="s.c"):
    src = _src(tmp_path, name, code)
    sb = Sandbox()
    comp = sb.compile(src)
    assert comp.success, comp.diagnostics
    res = sb.run(
        comp.binary_path,
        test_id="t1",
        submission_hash=comp.source_hash,
        input_data=input_data,
        limits=limits,
    )
    return sb, comp, res


def test_correct_program_compiles_and_runs(tmp_path):
    sb, comp, res = _compile_and_run(tmp_path, ADD, input_data="7 5\n")
    with sb:
        assert res.status is ExecutionStatus.OK
        assert res.stdout.strip() == "12"
        assert res.exit_code == 0
        assert comp.source_hash.startswith("sha256:")


def test_compile_error_is_structured(tmp_path):
    src = _src(tmp_path, "bad.c", BROKEN)
    with Sandbox() as sb:
        comp = sb.compile(src)
        assert not comp.success
        assert comp.binary_path is None
        assert "error" in comp.diagnostics.lower()


def test_infinite_loop_times_out_and_grader_survives(tmp_path):
    started = time.monotonic()
    sb, _c, res = _compile_and_run(
        tmp_path, LOOP, limits=ExecutionLimits(wall_time_s=1.0)
    )
    elapsed = time.monotonic() - started
    with sb:
        assert res.status is ExecutionStatus.TIMEOUT
        assert elapsed < 6  # the grader did NOT hang with the student program


def test_forked_child_is_killed_with_process_group(tmp_path):
    src = _src(tmp_path, "fork.c", FORK_LOOP)
    sb = Sandbox()
    with sb:
        comp = sb.compile(src)
        assert comp.success
        started = time.monotonic()
        res = sb.run(
            comp.binary_path,
            test_id="t1",
            submission_hash=comp.source_hash,
            limits=ExecutionLimits(wall_time_s=1.0),
        )
        assert res.status is ExecutionStatus.TIMEOUT
        assert time.monotonic() - started < 6
        time.sleep(0.3)
        alive = subprocess.run(
            ["pgrep", "-f", str(comp.binary_path)],
            capture_output=True, text=True, check=False,
        )
        assert alive.returncode != 0, "a forked child outlived the run"


def test_crash_is_reported_not_fatal(tmp_path):
    sb, _c, res = _compile_and_run(tmp_path, CRASH)
    with sb:
        assert res.status is ExecutionStatus.CRASH
        assert res.exit_code is not None and res.exit_code < 0


def test_output_flood_is_capped(tmp_path):
    limits = ExecutionLimits(wall_time_s=3.0, max_output_bytes=8192)
    sb, _c, res = _compile_and_run(tmp_path, FLOOD, limits=limits)
    with sb:
        assert res.status is ExecutionStatus.EXCESSIVE_OUTPUT
        assert len(res.stdout.encode()) <= 8192


def test_memory_limit_is_enforced(tmp_path):
    # With a 64 MB address-space limit a 512 MB allocation must fail inside
    # the student program (it prints 'alloc failed' and exits 3). Without
    # enforcement it would print 'allocated'.
    sb, _c, res = _compile_and_run(
        tmp_path, ALLOC, limits=ExecutionLimits(wall_time_s=5.0, memory_mb=64)
    )
    with sb:
        assert "alloc failed" in res.stdout
        assert res.exit_code == 3


def test_environment_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOGRADER_SECRET", "topsecret")
    sb, _c, res = _compile_and_run(tmp_path, ENVPROBE)
    with sb:
        assert res.stdout.strip() == "absent"
    assert os.environ["AUTOGRADER_SECRET"] == "topsecret"  # parent untouched


def test_hostile_filename_cannot_inject_commands(tmp_path):
    evil = _src(tmp_path, "a;touch PWNED;.c", ADD)
    with Sandbox() as sb:
        comp = sb.compile(evil)
        assert comp.success
        res = sb.run(
            comp.binary_path, test_id="t1",
            submission_hash=comp.source_hash, input_data="1 2\n",
        )
        assert res.stdout.strip() == "3"
    assert not (tmp_path / "PWNED").exists()
    assert not Path("PWNED").exists()


def test_workspace_is_cleaned_up(tmp_path):
    sb = Sandbox()
    workspace = sb.workspace
    with sb:
        assert workspace.exists()
    assert not workspace.exists()


@pytest.mark.parametrize("code", [ADD, LOOP])
def test_isolation_is_reported(tmp_path, code):
    sb, _c, res = _compile_and_run(
        tmp_path, code, limits=ExecutionLimits(wall_time_s=1.0)
    )
    with sb:
        assert any(d.startswith("isolation:") for d in res.diagnostics)
