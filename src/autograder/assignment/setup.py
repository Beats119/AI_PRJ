"""prepare-assignment orchestration: spec -> cache -> generation -> oracle.

Cache key material (EVERY input that can change the suite):
  normalized specification hash (includes instructor cases), full rules hash,
  generation + sufficiency configuration, generator id + version, oracle
  policy version, comparison policy, reference implementation hash, and the
  model identity when LLM proposals are enabled ("llm:disabled" otherwise).

Only a suite that passes the D-1 sufficiency bar is ever stored. A failed
setup stores nothing and can therefore never overwrite a valid entry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from autograder.assignment.cache import AssignmentCache
from autograder.assignment.oracle import ORACLE_POLICY_VERSION, verify_candidates
from autograder.assignment.specification import build_spec, load_assignment_package
from autograder.assignment.test_generation import generate_candidates
from autograder.config.loader import LoadedRules, canonical_hash
from autograder.config.schema import ModelsConfig
from autograder.llm.client import LLMClient
from autograder.models.assignment import AssignmentSpec
from autograder.models.tests import TestCase

GENERATOR_VERSION = "gen-v1"


@dataclass
class PrepareResult:
    status: str  # prepared_new | prepared_cache_hit | insufficient_evidence
    cache_key: str
    spec: AssignmentSpec
    suite: list[TestCase] | None
    generation_report: dict | None
    llm_usage: dict | None
    sufficiency: dict | None
    diagnostics: list[str] = field(default_factory=list)
    validation_executions: int = 0


def _file_hash(path: Path | None) -> str:
    if path is None:
        return "none"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def compute_cache_key(
    *,
    spec: AssignmentSpec,
    loaded_rules: LoadedRules,
    package_generator: str,
    comparison: str,
    reference_path: Path | None,
    models: ModelsConfig,
    use_llm: bool,
) -> str:
    material = {
        "spec_hash": spec.specification_hash,
        "rules_hash": loaded_rules.rules_hash,
        "generation": loaded_rules.rules.generation.model_dump(mode="json"),
        "sufficiency": loaded_rules.rules.sufficiency.model_dump(mode="json"),
        "generator_id": package_generator,
        "generator_version": GENERATOR_VERSION,
        "oracle_policy_version": ORACLE_POLICY_VERSION,
        "comparison": comparison,
        "reference_hash": _file_hash(reference_path),
        "model_identity": (
            f"{models.llm.backend}:{models.llm.model}:t{models.llm.temperature}"
            f":s{models.llm.seed}"
            if use_llm
            else "llm:disabled"
        ),
    }
    return canonical_hash(material).removeprefix("sha256:")


def prepare_assignment(
    assignment_dir: str | Path,
    loaded_rules: LoadedRules,
    models: ModelsConfig,
    cache_root: str | Path,
    use_llm: bool = False,
    llm_client: LLMClient | None = None,
) -> PrepareResult:
    package = load_assignment_package(assignment_dir)
    spec = build_spec(package)
    rules = loaded_rules.rules
    key = compute_cache_key(
        spec=spec,
        loaded_rules=loaded_rules,
        package_generator=package.config.generator,
        comparison=package.config.comparison,
        reference_path=package.reference_path,
        models=models,
        use_llm=use_llm,
    )
    cache = AssignmentCache(cache_root)
    look = cache.lookup(key)
    if look.kind == "hit" and look.entry is not None:
        md = look.entry.metadata
        return PrepareResult(
            status="prepared_cache_hit",
            cache_key=key,
            spec=look.entry.spec,
            suite=look.entry.suite,
            generation_report=md.get("generation_report"),
            llm_usage=md.get("llm_usage"),
            sufficiency=md.get("sufficiency"),
            diagnostics=["cache hit: suite revalidated (schema, integrity, provenance)"],
        )
    diagnostics: list[str] = []
    if look.kind == "corrupt":
        diagnostics.append(f"existing cache entry rejected: {look.detail}; regenerating")

    client = llm_client
    if use_llm and client is None:
        client = LLMClient(models.llm)
    existing_inputs = {" ".join(c.input.split()) for c in package.instructor_cases}
    candidates, gen_report = generate_candidates(
        package, rules.generation, llm_client=client, use_llm=use_llm,
        existing_inputs=existing_inputs,
    )
    verification = verify_candidates(candidates, package, spec, rules.sufficiency)
    diagnostics += verification.diagnostics
    sufficiency_dict = {
        "sufficient": verification.sufficiency.sufficient,
        "applicable_categories": verification.sufficiency.applicable_categories,
        "trusted_by_category": verification.sufficiency.trusted_by_category,
        "conditions": verification.sufficiency.conditions,
        "total_trusted": verification.sufficiency.total_trusted,
    }
    gen_dict = vars(gen_report)
    usage_dict = client.usage.as_dict() if client is not None else {"total_calls": 0}

    if not verification.sufficiency.sufficient:
        return PrepareResult(
            status="insufficient_evidence",
            cache_key=key,
            spec=spec,
            suite=None,
            generation_report=gen_dict,
            llm_usage=usage_dict,
            sufficiency=sufficiency_dict,
            diagnostics=diagnostics
            + [
                (
                    "insufficient trusted correctness evidence: no suite was cached "
                    "and no ordinary grade may be produced from this setup"
                )
            ],
            validation_executions=verification.validation_executions,
        )

    stored = cache.store(
        key,
        spec,
        verification.suite,
        {
            "provenance": {
                "rules_hash": loaded_rules.rules_hash,
                "generator_version": GENERATOR_VERSION,
                "oracle_policy_version": ORACLE_POLICY_VERSION,
                "reference_hash": _file_hash(package.reference_path),
                "reference_trusted": verification.reference_trusted,
            },
            "generation_report": gen_dict,
            "llm_usage": usage_dict,
            "sufficiency": sufficiency_dict,
            "rejected_tests": [t.model_dump(mode="json") for t in verification.rejected],
            "validation_executions": verification.validation_executions,
        },
    )
    if stored.entry is None:  # pragma: no cover - store just wrote it
        raise RuntimeError("cache store did not return an entry")
    return PrepareResult(
        status="prepared_new",
        cache_key=key,
        spec=stored.entry.spec,
        suite=stored.entry.suite,
        generation_report=gen_dict,
        llm_usage=usage_dict,
        sufficiency=sufficiency_dict,
        diagnostics=diagnostics + ["cache miss: suite generated, verified and stored"],
        validation_executions=verification.validation_executions,
    )
