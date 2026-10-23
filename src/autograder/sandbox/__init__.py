"""Safe compilation and execution of untrusted C submissions (Stage 5)."""

from autograder.sandbox.compiler import CompileResult, compile_source
from autograder.sandbox.executor import Sandbox, run_program
from autograder.sandbox.limits import ExecutionLimits, probe_network_namespace

__all__ = [
    "CompileResult",
    "ExecutionLimits",
    "Sandbox",
    "compile_source",
    "probe_network_namespace",
    "run_program",
]
