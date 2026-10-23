"""`autograder doctor`: honest environment/tool capability report.

Reports what is actually present and reachable on THIS machine. A missing
tool is reported as missing; nothing is inferred from another machine.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from autograder.config.loader import ConfigError, load_models_config

TOOL_NAMES = ["gcc", "cppcheck", "valgrind", "perf", "lizard"]


def _version_of(name: str) -> str | None:
    try:
        out = subprocess.run(
            [name, "--version"], capture_output=True, text=True, timeout=5, check=False
        )
        first = (out.stdout or out.stderr).strip().splitlines()
        return first[0].strip() if first else None
    except Exception:
        return None


def _ollama(models_path: Path) -> dict:
    info: dict = {"reachable": False, "models": [], "configured_model": None,
                  "configured_model_available": None}
    try:
        cfg = load_models_config(models_path)
        info["configured_model"] = cfg.llm.model
        base = cfg.llm.base_url.rstrip("/")
        timeout = min(cfg.llm.request_timeout_s, 3.0)
    except (ConfigError, Exception) as exc:  # config problem: report, don't crash
        info["error"] = f"models config unusable: {exc}"
        return info
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        info["reachable"] = True
        names = [m.get("name", "") for m in data.get("models", [])]
        info["models"] = names
        want = info["configured_model"]
        info["configured_model_available"] = any(
            n == want or n.startswith(want + ":") for n in names
        )
    except Exception as exc:
        info["error"] = f"not reachable: {exc.__class__.__name__}"
    return info


def _perf_status() -> dict:
    p = Path("/proc/sys/kernel/perf_event_paranoid")
    try:
        level = int(p.read_text().strip())
    except Exception:
        return {"paranoid_level": None, "note": "level unreadable on this platform"}
    usable = level <= 2 and shutil.which("perf") is not None
    return {
        "paranoid_level": level,
        "perf_binary": shutil.which("perf") is not None,
        "counters_likely_usable": usable,
        "note": "hardware counters need perf installed and paranoid level <= 2 for unprivileged use",
    }


def _namespace_probe() -> dict:
    if shutil.which("unshare") is None:
        return {"available": False, "note": "unshare binary not found"}
    try:
        out = subprocess.run(
            ["unshare", "--user", "--net", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return {"available": out.returncode == 0,
                "note": "user+network namespace probe ran" if out.returncode == 0
                        else f"probe failed with exit code {out.returncode}"}
    except Exception as exc:
        return {"available": False, "note": f"probe error: {exc.__class__.__name__}"}


def run_doctor(models_path: Path) -> dict:
    tools = {}
    for name in TOOL_NAMES + ["gcc"]:
        path = shutil.which(name)
        tools[name] = {"found": path is not None, "path": path,
                       "version": _version_of(name) if path else None}
    tools.pop("gcc", None)
    gcc_path = shutil.which("gcc")
    report = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "gcc": {"found": gcc_path is not None, "path": gcc_path,
                "version": _version_of("gcc") if gcc_path else None},
        "optional_tools": tools,
        "ollama": _ollama(models_path),
        "perf": _perf_status(),
        "sandbox_capabilities": {
            "rlimit_module": _rlimit_available(),
            "user_network_namespace": _namespace_probe(),
        },
    }
    return report


def _rlimit_available() -> bool:
    try:
        import resource  # noqa: F401

        return True
    except Exception:
        return False


def format_doctor_text(report: dict) -> str:
    lines = ["AutoGrader doctor — environment report", "=" * 42]
    lines.append(f"Platform : {report['platform']}")
    lines.append(f"Python   : {report['python']}")
    gcc = report["gcc"]
    lines.append(f"gcc      : {'FOUND ' + (gcc['version'] or '') if gcc['found'] else 'NOT FOUND'}")
    for name, t in report["optional_tools"].items():
        lines.append(
            f"{name:<9}: {'FOUND ' + (t['version'] or '') if t['found'] else 'not found (optional)'}"
        )
    o = report["ollama"]
    if o["reachable"]:
        avail = o["configured_model_available"]
        lines.append(
            f"Ollama   : reachable, models={o['models']}, "
            f"configured '{o['configured_model']}' available={avail}"
        )
    else:
        lines.append(f"Ollama   : NOT reachable ({o.get('error', 'unknown')}) — LLM features off")
    perf = report["perf"]
    lines.append(
        f"perf     : paranoid={perf['paranoid_level']}, binary={perf['perf_binary']}, "
        f"counters likely usable={perf['counters_likely_usable']}"
    )
    sb = report["sandbox_capabilities"]
    lines.append(f"rlimits  : {sb['rlimit_module']}")
    lines.append(
        f"netns    : available={sb['user_network_namespace']['available']} "
        f"({sb['user_network_namespace']['note']})"
    )
    return "\n".join(lines)
