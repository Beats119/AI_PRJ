"""Config validation tests (RTM P-04, P-11, E-01; D-1/D-2 bounds)."""

from pathlib import Path

import pytest

from autograder.config.loader import ConfigError, load_models_config, load_rules

ROOT = Path(__file__).resolve().parents[2]


def _rules(tmp_path, text: str) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(text)
    return p


BASE = """
problem: demo
metrics:
  - {name: correctness, analyzer: io_tests, weight: 0.6}
  - {name: syntax, analyzer: compiler_warnings, weight: 0.4}
"""


def test_example_rules_file_is_valid():
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    assert loaded.rules.problem == "add_two_integers"
    assert len(loaded.rules.metrics) == 9
    assert loaded.rules_hash.startswith("sha256:")
    assert loaded.rules.sufficiency.min_trusted_total == 8
    assert loaded.rules.generation.max_candidates == 40


def test_models_config_is_valid():
    cfg = load_models_config(ROOT / "configs" / "models.yaml")
    assert cfg.llm.backend == "ollama"
    assert cfg.llm.model == "llama3.1"
    assert cfg.llm.max_setup_calls == 2
    assert cfg.llm.temperature == 0


def test_weights_must_sum_to_one(tmp_path):
    bad = BASE.replace("weight: 0.4", "weight: 0.3")
    with pytest.raises(ConfigError) as ei:
        load_rules(_rules(tmp_path, bad))
    assert any("sum to 1.00" in p for p in ei.value.problems)


def test_unknown_analyzer_rejected(tmp_path):
    bad = BASE.replace("io_tests", "magic_guess")
    with pytest.raises(ConfigError) as ei:
        load_rules(_rules(tmp_path, bad))
    assert any("unknown analyzer" in p for p in ei.value.problems)


def test_duplicate_metric_rejected(tmp_path):
    bad = BASE.replace("name: syntax", "name: correctness")
    with pytest.raises(ConfigError):
        load_rules(_rules(tmp_path, bad))


def test_correctness_cannot_be_optional(tmp_path):
    bad = BASE.replace(
        "{name: correctness, analyzer: io_tests, weight: 0.6}",
        "{name: correctness, analyzer: io_tests, weight: 0.6, required: false}",
    )
    with pytest.raises(ConfigError) as ei:
        load_rules(_rules(tmp_path, bad))
    assert any("CORE" in p for p in ei.value.problems)


def test_generation_rounds_bounded_by_d2(tmp_path):
    bad = BASE + "\ngeneration:\n  rounds: 3\n"
    with pytest.raises(ConfigError):
        load_rules(_rules(tmp_path, bad))


def test_generation_candidates_bounded_by_d2(tmp_path):
    bad = BASE + "\ngeneration:\n  max_candidates: 41\n"
    with pytest.raises(ConfigError):
        load_rules(_rules(tmp_path, bad))


def test_missing_file_is_actionable(tmp_path):
    with pytest.raises(ConfigError) as ei:
        load_rules(tmp_path / "nope.yaml")
    assert any("not found" in p for p in ei.value.problems)


def test_hash_is_stable(tmp_path):
    p = _rules(tmp_path, BASE)
    assert load_rules(p).rules_hash == load_rules(p).rules_hash
