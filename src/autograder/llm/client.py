"""A bounded Ollama client with hard call budgets and full usage accounting.

Design rules (approved plan):
  * Deterministic configuration only: temperature 0, fixed seed (enforced
    by the models-config schema).
  * Every call is counted BEFORE it is made, per purpose and in total,
    against the caps in configs/models.yaml (D-2). Exceeding a cap raises
    BudgetExceeded — the call is never made.
  * No retries that multiply calls silently: exactly one transport attempt
    per logical call.
  * The transport is injectable so tests can substitute a FAKE transport.
    Fake-transport results are test fixtures, never real model results, and
    are labelled as such wherever they are recorded.
  * If Ollama is unreachable, LLMUnavailable is raised; callers must fall
    back to deterministic paths or report insufficiency — never fabricate.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from autograder.config.schema import LLMConfig

PURPOSES = ("spec_assist", "test_proposal", "readability")


class BudgetExceeded(Exception):
    pass


class LLMUnavailable(Exception):
    pass


@dataclass
class LLMCallRecord:
    purpose: str
    model: str
    prompt_chars: int
    response_chars: int
    prompt_tokens: int | None
    response_tokens: int | None
    duration_ms: float
    transport: str  # "ollama-http" for real calls, "fake" in tests


@dataclass
class LLMUsage:
    calls: list[LLMCallRecord] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    def calls_for(self, purpose: str) -> int:
        return sum(1 for c in self.calls if c.purpose == purpose)

    def as_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "by_purpose": {p: self.calls_for(p) for p in PURPOSES},
            "calls": [vars(c) for c in self.calls],
        }


Transport = Callable[[str, dict], dict]  # (url, payload) -> parsed JSON response


def _http_transport(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = 120.0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LLMClient:
    def __init__(
        self,
        config: LLMConfig,
        transport: Transport | None = None,
        transport_name: str = "ollama-http",
    ):
        self.config = config
        self._transport = transport or _http_transport
        self._transport_name = transport_name if transport else "ollama-http"
        self.usage = LLMUsage()

    def _cap_for(self, purpose: str) -> int:
        if purpose == "spec_assist":
            return self.config.max_spec_assist_calls
        if purpose == "test_proposal":
            return self.config.max_test_proposal_calls
        if purpose == "readability":
            return self.config.max_readability_calls_per_evaluation
        raise ValueError(f"unknown LLM purpose '{purpose}'")

    def _check_budget(self, purpose: str) -> None:
        if self.usage.calls_for(purpose) >= self._cap_for(purpose):
            raise BudgetExceeded(
                f"LLM purpose '{purpose}' cap ({self._cap_for(purpose)}) reached"
            )
        if purpose in ("spec_assist", "test_proposal"):
            # Setup purposes share the D-2 total setup cap; readability calls
            # are budgeted per evaluation and do not consume it.
            setup_used = sum(
                1 for c in self.usage.calls if c.purpose != "readability"
            )
            if setup_used >= self.config.max_setup_calls:
                raise BudgetExceeded(
                    f"setup LLM call cap ({self.config.max_setup_calls}) reached"
                )

    def generate(self, purpose: str, prompt: str) -> str:
        """One bounded call. Returns the model's response text."""
        if purpose not in PURPOSES:
            raise ValueError(f"unknown LLM purpose '{purpose}'")
        self._check_budget(purpose)
        url = self.config.base_url.rstrip("/") + "/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.config.temperature, "seed": self.config.seed},
        }
        started = time.monotonic()
        try:
            data = self._transport(url, payload)
        except Exception as exc:
            raise LLMUnavailable(
                f"Ollama call for '{purpose}' failed: {exc.__class__.__name__}: {exc}"
            ) from exc
        duration = (time.monotonic() - started) * 1000
        text = data.get("response", "")
        self.usage.calls.append(
            LLMCallRecord(
                purpose=purpose,
                model=self.config.model,
                prompt_chars=len(prompt),
                response_chars=len(text),
                prompt_tokens=data.get("prompt_eval_count"),
                response_tokens=data.get("eval_count"),
                duration_ms=duration,
                transport=self._transport_name,
            )
        )
        return text
