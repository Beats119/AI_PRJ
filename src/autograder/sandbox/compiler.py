"""Controlled compilation of a C submission (argv arrays only, never a shell)."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FLAGS = "-O2 -Wall -Wextra -std=c11"
MAX_DIAGNOSTICS_CHARS = 65_536


@dataclass
class CompileResult:
    success: bool
    binary_path: Path | None
    diagnostics: str
    exit_code: int | None
    duration_ms: float
    source_hash: str
    source_name: str
    flags_used: list[str] = field(default_factory=list)


def source_hash_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compile_source(
    source_path: str | Path,
    dest_dir: str | Path,
    flags: str | list[str] = DEFAULT_FLAGS,
    timeout_s: float = 30.0,
    binary_name: str = "program",
) -> CompileResult:
    """Compile `source_path` into `dest_dir/binary_name`.

    The source is copied into the destination under a fixed safe name, so a
    hostile or merely odd original filename can never influence the command
    line. Compilation is a plain argv invocation with a timeout and a
    scrubbed environment; diagnostics are captured and bounded.
    """
    source_path = Path(source_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    data = source_path.read_bytes()
    digest = source_hash_of(data)
    local_source = dest_dir / "submission.c"
    local_source.write_bytes(data)
    binary = dest_dir / binary_name
    flag_list = shlex.split(flags) if isinstance(flags, str) else list(flags)
    argv = ["gcc", *flag_list, "-o", str(binary), str(local_source)]
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(dest_dir)}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, env=env,
            check=False,
        )
        duration = (time.monotonic() - started) * 1000
        diagnostics = (proc.stdout + proc.stderr)[:MAX_DIAGNOSTICS_CHARS]
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
        duration = (time.monotonic() - started) * 1000
        return CompileResult(
            success=False,
            binary_path=None,
            diagnostics=f"compilation exceeded {timeout_s}s and was stopped",
            exit_code=None,
            duration_ms=duration,
            source_hash=digest,
            source_name=source_path.name,
            flags_used=flag_list,
        )


def gcc_available() -> bool:
    return shutil.which("gcc") is not None and os.access(shutil.which("gcc") or "", os.X_OK)
