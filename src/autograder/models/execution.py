"""ExecutionResult: the structured outcome of running a submission on one test."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    OK = "ok"
    COMPILE_ERROR = "compile_error"
    CRASH = "crash"
    TIMEOUT = "timeout"
    EXCESSIVE_OUTPUT = "excessive_output"
    RESOURCE_EXCEEDED = "resource_exceeded"
    TOOL_ERROR = "tool_error"


class ExecutionResult(BaseModel):
    submission_hash: str
    test_id: str
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: float = 0.0
    resource_usage: dict[str, float] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
