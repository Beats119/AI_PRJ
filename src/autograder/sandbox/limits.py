"""Execution limits and capability probes for the sandbox.

Limits are enforced with `prlimit` (util-linux) wrapped around the child
process — never by in-process preexec tricks. The wall-clock timeout is
enforced by the parent (executor), which kills the child's process group.
"""

from __future__ import annotations

import functools
import math
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionLimits:
    wall_time_s: float = 1.0
    memory_mb: int | None = 64  # None disables the address-space limit
    max_output_bytes: int = 65_536
    cpu_time_s: int | None = None  # defaults to ceil(wall_time_s)
    # ASan-instrumented binaries reserve a very large virtual address space;
    # callers running them must disable the address-space limit explicitly.
    apply_memory_limit: bool = True

    @property
    def cpu_seconds(self) -> int:
        if self.cpu_time_s is not None:
            return self.cpu_time_s
        return max(1, math.ceil(self.wall_time_s))

    @property
    def memory_bytes(self) -> int | None:
        if self.memory_mb is None or not self.apply_memory_limit:
            return None
        return self.memory_mb * 1024 * 1024


@functools.lru_cache(maxsize=1)
def probe_network_namespace() -> bool:
    """True only if a user+network namespace was actually created here."""
    if shutil.which("unshare") is None:
        return False
    try:
        out = subprocess.run(
            ["unshare", "--user", "--map-root-user", "--net", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return out.returncode == 0
    except Exception:
        return False


def prlimit_prefix(limits: ExecutionLimits) -> list[str]:
    """argv prefix applying resource limits, or [] if prlimit is missing."""
    if shutil.which("prlimit") is None:
        return []
    args = ["prlimit", f"--cpu={limits.cpu_seconds}", "--core=0",
            f"--fsize={limits.max_output_bytes}"]
    mem = limits.memory_bytes
    if mem is not None:
        args.append(f"--as={mem}")
    return args


def namespace_prefix() -> list[str]:
    return ["unshare", "--user", "--map-root-user", "--net", "--"]
