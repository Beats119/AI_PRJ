"""Stage 6 tests: spec builder, bounded generation, oracle trust, sufficiency.

The LLM here is a FAKE transport returning canned JSON — a labelled test
fixture, never a real model result. No test needs a live Ollama server.
"""

from pathlib import Path

import pytest

from autograder.assignment.oracle import verify_candidates
from autograder.assignment.specification import build_spec, load_assignment_package
from autograder.assignment.test_generation import generate_candidates
from autograder.config.loader import ConfigError, load_models_config, load_rules
from autograder.config.schema import GenerationConfig
from autograder.llm.client import LLMClient
from autograder.models.tests import TrustStatus

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"


def _rules():
    return load_rules(ROOT / "configs" / "example_rules.yaml")


def _models():
    return load_models_config(ROOT / "configs" / "models.yaml")


def _fake_client(response_text: str) -> LLMClient:
    def fake_transport(url, payload):
        return {"response": response_text, "prompt_eval_count": 10, "eval_count": 5}

    return LLMClient(_models().llm, transport=fake_transport, transport_name="fake")


def test_example_package_builds_spec():
    pkg = load_assignment_package(EXAMPLE)
    spec = build_spec(pkg)
    assert spec.assignment_id == "add_two_integers"
    assert len(spec.examples) == 3
    assert spec.examples[0].expected_output == "12"  # PDF worked example
    assert spec.unresolved_questions == []
    assert spec.specification_hash.startswith("sha256:")
    assert spec.invalid_input_behavior is None  # NOT applicable, not invented


def test_missing_contract_sections_become_unresolved(tmp_path):
    (tmp_path / "assignment.md").write_text("# X\n\n## Problem\n\nDo something.\n")
    (tmp_path / "spec.yaml").write_text("assignment_id: x\ngenerator: none\n")
    pkg = load_assignment_package(tmp_path)
    spec = build_spec(pkg)
    joined = " ".join(spec.unresolved_questions)
    assert "no ## Input section" in joined
    assert "no ## Output section" in joined
    assert "no instructor cases and no reference" in joined


def test_missing_files_are_actionable_errors(tmp_path):
    with pytest.raises(ConfigError):
        load_assignment_package(tmp_path / "does-not-exist")
    (tmp_path / "assignment.md").write_text("# X\n")
    with pytest.raises(ConfigError) as exc:
        load_assignment_package(tmp_path)
    assert "spec.yaml" in str(exc.value)


def test_generation_is_bounded_and_deduped():
    pkg = load_assignment_package(EXAMPLE)
    existing = {" ".join(c.input.split()) for c in pkg.instructor_cases}
    candidates, report = generate_candidates(
        pkg, _rules().rules.generation, existing_inputs=existing
    )
    assert report.rounds == 1
    assert report.kept == len(candidates) == 21
    assert report.discarded_duplicates >= 2  # '7 5' and '0 0' already instructor cases
    assert all(c.trust_status is TrustStatus.UNTRUSTED for c in candidates)
    assert all(c.expected_output is None for c in candidates)  # nothing pre-trusted


def test_generation_respects_candidate_cap():
    pkg = load_assignment_package(EXAMPLE)
    cfg = GenerationConfig(max_candidates=10)
    candidates, report = generate_candidates(pkg, cfg)
    assert len(candidates) == 10
    assert report.discarded_over_cap > 0


def test_oracle_trusts_via_reference_and_derivation():
    pkg = load_assignment_package(EXAMPLE)
    spec = build_spec(pkg)
    candidates, _ = generate_candidates(
        pkg, _rules().rules.generation,
        existing_inputs={" ".join(c.input.split()) for c in pkg.instructor_cases},
    )
    result = verify_candidates(candidates, pkg, spec, _rules().rules.sufficiency)
    assert result.reference_trusted is True
    assert result.sufficiency.sufficient is True
    assert result.sufficiency.total_trusted == 24
    generated = [t for t in result.suite if t.test_id.startswith("gen-")]
    assert all(
        t.validation_method == "reference_run+independent_derivation" for t in generated
    )
    instructor = [t for t in result.suite if t.test_id.startswith("inst-")]
    assert all(t.validation_method == "instructor_provided" for t in instructor)


def test_u07_boundary_expected_output_is_mathematically_correct():
    pkg = load_assignment_package(EXAMPLE)
    spec = build_spec(pkg)
    candidates, _ = generate_candidates(pkg, _rules().rules.generation)
    result = verify_candidates(candidates, pkg, spec, _rules().rules.sufficiency)
    by_input = {" ".join(t.input_data.split()): t for t in result.suite}
    case = by_input["2147483647 1"]
    assert case.expected_output == "2147483648"  # NOT the wrapped -2147483648
    assert case.counts_as_trusted
    big = by_input["2000000000 2000000000"]
    assert big.expected_output == "4000000000"


def test_bad_reference_is_rejected_as_trust_source(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "assignment.md").write_text((EXAMPLE / "assignment.md").read_text())
    (pkg_dir / "spec.yaml").write_text((EXAMPLE / "spec.yaml").read_text())
    (pkg_dir / "tests.yaml").write_text((EXAMPLE / "tests.yaml").read_text())
    (pkg_dir / "reference.c").write_text(
        "#include <stdio.h>\nint main(void){ long long a,b;"
        " if(scanf(\"%lld %lld\",&a,&b)!=2) return 1;"
        " printf(\"%lld\\n\", a+b+1); return 0; }\n"  # wrong on purpose
    )
    pkg = load_assignment_package(pkg_dir)
    spec = build_spec(pkg)
    candidates, _ = generate_candidates(pkg, _rules().rules.generation)
    result = verify_candidates(candidates, pkg, spec, _rules().rules.sufficiency)
    assert result.reference_trusted is False
    assert any("rejected as a trust source" in d for d in result.diagnostics)
    # Derivation still independently establishes trust:
    generated = [t for t in result.suite if t.test_id.startswith("gen-")]
    assert generated and all(
        t.validation_method == "independent_derivation" for t in generated
    )
    assert result.sufficiency.sufficient is True


def test_contradicting_reference_rejects_the_candidate(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "assignment.md").write_text((EXAMPLE / "assignment.md").read_text())
    (pkg_dir / "spec.yaml").write_text((EXAMPLE / "spec.yaml").read_text())
    (pkg_dir / "tests.yaml").write_text((EXAMPLE / "tests.yaml").read_text())
    (pkg_dir / "reference.c").write_text(
        "#include <stdio.h>\nint main(void){ long long a,b;"
        " if(scanf(\"%lld %lld\",&a,&b)!=2) return 1;"
        " if(a==2 && b==3){ printf(\"999\\n\"); return 0; }"
        " printf(\"%lld\\n\", a+b); return 0; }\n"  # contradicts only '2 3'
    )
    pkg = load_assignment_package(pkg_dir)
    spec = build_spec(pkg)
    candidates, _ = generate_candidates(pkg, _rules().rules.generation)
    result = verify_candidates(candidates, pkg, spec, _rules().rules.sufficiency)
    assert result.reference_trusted is True  # passed all instructor cases
    rejected_inputs = {" ".join(t.input_data.split()) for t in result.rejected}
    assert "2 3" in rejected_inputs  # contradiction => rejected, never voted on


def test_llm_expected_output_never_becomes_trust_by_itself(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "assignment.md").write_text(
        "# Mystery\n\n## Problem\n\nAdd numbers somehow.\n\n## Input\n\n"
        "Two integers.\n\n## Output\n\nTheir sum.\n"
    )
    (pkg_dir / "spec.yaml").write_text("assignment_id: mystery\ngenerator: none\n")
    pkg = load_assignment_package(pkg_dir)
    spec = build_spec(pkg)
    client = _fake_client(
        '[{"input": "3 4\\n", "expected": "999", "category": "edge_values"}]'
    )
    candidates, report = generate_candidates(
        pkg, _rules().rules.generation, llm_client=client, use_llm=True
    )
    assert report.llm_candidates_proposed == 1
    result = verify_candidates(candidates, pkg, spec, _rules().rules.sufficiency)
    case = result.suite[0]
    assert case.validation_method == "llm_unverified"
    assert not case.counts_as_trusted
    assert result.sufficiency.sufficient is False  # D-1 bar cannot be met


def test_llm_proposed_input_becomes_trusted_only_via_independent_check():
    pkg = load_assignment_package(EXAMPLE)
    client = _fake_client(
        '[{"input": "3 4\\n", "expected": "999", "category": "edge_values"}]'
    )
    candidates, _ = generate_candidates(
        pkg, _rules().rules.generation, llm_client=client, use_llm=True,
        existing_inputs={" ".join(c.input.split()) for c in pkg.instructor_cases},
    )
    llm_case = [c for c in candidates if c.provenance == "llm_proposal"]
    assert llm_case and llm_case[0].expected_output == "999"  # unverified claim kept
    result = verify_candidates(
        candidates, pkg, build_spec(pkg), _rules().rules.sufficiency
    )
    verified = [t for t in result.suite if t.input_data == "3 4\n"]
    assert verified[0].expected_output == "7"  # corrected by independent sources
    assert verified[0].validation_method == "reference_run+independent_derivation"
    assert verified[0].counts_as_trusted
    assert client.usage.total_calls == 1
    assert client.usage.calls[0].transport == "fake"  # labelled honestly
