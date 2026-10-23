"""Pydantic schema for instructor rules and LLM model configuration.

Validation is strict on purpose (master spec stage A): an invalid rules file
must produce actionable errors, never silently substituted defaults.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

# Analyzer names the engine knows how to dispatch (PDF example + registry).
KNOWN_ANALYZERS = {
    "io_tests",
    "compiler_warnings",
    "static_analysis",
    "function_split",
    "edge_case_runner",
    "complexity_estimator",
    "sanitizer_run",
    "llm_review",
    "similarity_flag",
}

CORE_CATEGORY_DEFAULTS = [
    "ordinary_valid",
    "minimum_boundary",
    "maximum_boundary",
    "edge_values",
]


class MetricRule(BaseModel):
    name: str
    analyzer: str
    weight: Decimal
    params: dict[str, Any] = Field(default_factory=dict)
    # A metric is REQUIRED unless the rules explicitly mark it optional.
    # `correctness` can never be optional (enforced in Rules).
    required: bool = True
    # Only meaningful for a required metric: declare how an inconclusive
    # result is treated. "provisional" (default, D-3 case 5) or
    # "advisory_exclude" (treated like an excluded optional metric).
    inconclusive_treatment: str = "provisional"

    @model_validator(mode="after")
    def _check(self) -> MetricRule:
        if self.analyzer not in KNOWN_ANALYZERS:
            raise ValueError(
                f"metric '{self.name}': unknown analyzer '{self.analyzer}' "
                f"(known: {sorted(KNOWN_ANALYZERS)})"
            )
        if not (Decimal(0) < self.weight <= Decimal(1)):
            raise ValueError(f"metric '{self.name}': weight {self.weight} outside (0, 1]")
        if self.inconclusive_treatment not in ("provisional", "advisory_exclude"):
            raise ValueError(
                f"metric '{self.name}': inconclusive_treatment must be "
                "'provisional' or 'advisory_exclude'"
            )
        return self


class GenerationConfig(BaseModel):
    # D-2 (approved): one generation round, at most 40 candidates.
    rounds: int = 1
    max_candidates: int = 40
    max_candidates_per_category: int = 10

    @model_validator(mode="after")
    def _bounds(self) -> GenerationConfig:
        if self.rounds != 1:
            raise ValueError("generation.rounds must be 1 (D-2: no repeated refinement)")
        if not (1 <= self.max_candidates <= 40):
            raise ValueError("generation.max_candidates must be between 1 and 40 (D-2)")
        if not (1 <= self.max_candidates_per_category <= self.max_candidates):
            raise ValueError(
                "generation.max_candidates_per_category must be between 1 and max_candidates"
            )
        return self


class SufficiencyConfig(BaseModel):
    # D-1 (approved as amended): the explicit trusted-test sufficiency bar.
    min_trusted_total: int = 8
    min_per_core_category: int = 2
    min_per_applicable_category: int = 1
    core_categories: list[str] = Field(default_factory=lambda: list(CORE_CATEGORY_DEFAULTS))

    @model_validator(mode="after")
    def _bounds(self) -> SufficiencyConfig:
        if self.min_trusted_total < 1:
            raise ValueError("sufficiency.min_trusted_total must be >= 1")
        if self.min_per_core_category < 1 or self.min_per_applicable_category < 1:
            raise ValueError("sufficiency per-category minima must be >= 1")
        return self


class Rules(BaseModel):
    problem: str
    time_limit_s: float = 1.0
    memory_limit_mb: int = 64
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    sufficiency: SufficiencyConfig = Field(default_factory=SufficiencyConfig)
    metrics: list[MetricRule]

    @model_validator(mode="after")
    def _check(self) -> Rules:
        if not self.metrics:
            raise ValueError("rules must define at least one metric")
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate metric names: {dupes}")
        total = sum((m.weight for m in self.metrics), Decimal(0))
        if abs(total - Decimal(1)) > Decimal("0.000001"):
            raise ValueError(f"metric weights must sum to 1.00, got {total}")
        for m in self.metrics:
            if m.name == "correctness" and not m.required:
                raise ValueError("the correctness metric is CORE and cannot be optional")
        if self.time_limit_s <= 0:
            raise ValueError("time_limit_s must be positive")
        if self.memory_limit_mb <= 0:
            raise ValueError("memory_limit_mb must be positive")
        return self

    def metric(self, name: str) -> MetricRule:
        for m in self.metrics:
            if m.name == name:
                return m
        raise KeyError(name)


class LLMConfig(BaseModel):
    backend: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1"
    temperature: float = 0
    seed: int = 42
    # D-2 (approved): at most two setup LLM calls, one per purpose.
    max_setup_calls: int = 2
    max_spec_assist_calls: int = 1
    max_test_proposal_calls: int = 1
    max_readability_calls_per_evaluation: int = 1
    request_timeout_s: float = 120

    @model_validator(mode="after")
    def _bounds(self) -> LLMConfig:
        if self.backend != "ollama":
            raise ValueError("llm.backend: only 'ollama' is supported in this version")
        if not (0 <= self.max_setup_calls <= 2):
            raise ValueError("llm.max_setup_calls must be between 0 and 2 (D-2)")
        if self.max_spec_assist_calls > 1 or self.max_test_proposal_calls > 1:
            raise ValueError("per-purpose setup LLM calls are capped at 1 each (D-2)")
        if self.max_spec_assist_calls + self.max_test_proposal_calls > self.max_setup_calls:
            raise ValueError("per-purpose setup call caps exceed llm.max_setup_calls")
        if self.max_readability_calls_per_evaluation > 1:
            raise ValueError("readability LLM calls are capped at 1 per evaluation")
        if self.temperature != 0:
            raise ValueError("llm.temperature must be 0 (reproducibility contract)")
        return self


class ModelsConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
