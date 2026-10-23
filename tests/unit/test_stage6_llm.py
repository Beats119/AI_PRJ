"""Bounded LLM client tests — fake transport fixtures only, labelled 'fake'."""

from pathlib import Path

import pytest

from autograder.config.loader import load_models_config
from autograder.llm.client import BudgetExceeded, LLMClient, LLMUnavailable

ROOT = Path(__file__).resolve().parents[2]


def _client(responder=None):
    cfg = load_models_config(ROOT / "configs" / "models.yaml").llm

    def transport(url, payload):
        if responder:
            return responder(url, payload)
        return {"response": "[]", "prompt_eval_count": 3, "eval_count": 2}

    return LLMClient(cfg, transport=transport, transport_name="fake")


def test_purpose_cap_enforced_before_call():
    client = _client()
    client.generate("spec_assist", "p")
    with pytest.raises(BudgetExceeded):
        client.generate("spec_assist", "p")  # cap is 1


def test_total_setup_cap_enforced_across_purposes():
    client = _client()
    client.generate("spec_assist", "p")
    client.generate("test_proposal", "p")
    with pytest.raises(BudgetExceeded):
        client.generate("test_proposal", "p")  # per-purpose cap also hit
    assert client.usage.total_calls == 2  # D-2: at most two setup calls


def test_readability_budget_is_separate_from_setup():
    client = _client()
    client.generate("readability", "p")
    client.generate("spec_assist", "p")
    client.generate("test_proposal", "p")  # setup total still exactly 2
    assert client.usage.total_calls == 3


def test_unavailable_backend_raises_typed_error():
    def boom(url, payload):
        raise ConnectionError("connection refused")

    client = _client(responder=boom)
    with pytest.raises(LLMUnavailable):
        client.generate("test_proposal", "p")
    assert client.usage.total_calls == 0  # failed calls are not billed as usage


def test_usage_accounting_records_tokens_and_transport():
    client = _client()
    client.generate("test_proposal", "hello")
    record = client.usage.calls[0]
    assert record.transport == "fake"
    assert record.prompt_tokens == 3 and record.response_tokens == 2
    assert client.usage.as_dict()["total_calls"] == 1
