"""Build an AssignmentSpec from explicit, validated assignment inputs.

Assignment package layout (a directory):
  assignment.md   problem statement with ## Problem / ## Input / ## Output /
                  ## Constraints sections (deterministic heading extraction)
  spec.yaml       machine fields: assignment_id, generator, comparison,
                  optional input range, optional invalid-input behaviour
  tests.yaml      optional instructor-provided cases {input, expected, category}
  reference.c     optional reference implementation

Nothing is inferred silently: missing contract pieces are recorded as
unresolved questions on the spec, and they weaken what the oracle may claim.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from autograder.config.loader import canonical_hash
from autograder.models.assignment import AssignmentExample, AssignmentSpec

GENERATORS = ("none", "int_pair_v1")
COMPARISONS = ("exact", "whitespace_normalized", "numeric_tolerance")


class AssignmentPackageConfig(BaseModel):
    assignment_id: str
    generator: str = "none"
    comparison: str = "whitespace_normalized"
    input_min: int | None = None
    input_max: int | None = None
    invalid_input_behavior: str | None = None

    @property
    def comparison_policy(self):
        from autograder.models.tests import ComparisonPolicy

        return ComparisonPolicy(self.comparison)


class InstructorCase(BaseModel):
    input: str
    expected: str
    category: str = "ordinary_valid"


class AssignmentPackage(BaseModel):
    config: AssignmentPackageConfig
    statement_sections: dict[str, str] = Field(default_factory=dict)
    instructor_cases: list[InstructorCase] = Field(default_factory=list)
    reference_path: Path | None = None
    source_dir: Path

    model_config = {"arbitrary_types_allowed": True}


def _split_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def load_assignment_package(assignment_dir: str | Path) -> AssignmentPackage:
    """Load + validate an assignment package. Errors are actionable."""
    from autograder.config.loader import ConfigError

    root = Path(assignment_dir)
    problems: list[str] = []
    if not root.is_dir():
        raise ConfigError([f"assignment directory not found: {root}"])
    md_path = root / "assignment.md"
    spec_path = root / "spec.yaml"
    if not md_path.exists():
        problems.append(f"missing required file: {md_path}")
    if not spec_path.exists():
        problems.append(f"missing required file: {spec_path}")
    if problems:
        raise ConfigError(problems)

    try:
        raw_cfg = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        config = AssignmentPackageConfig.model_validate(raw_cfg)
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigError([f"{spec_path}: {exc}"]) from exc
    if config.generator not in GENERATORS:
        raise ConfigError(
            [f"{spec_path}: unknown generator '{config.generator}' (known: {GENERATORS})"]
        )
    if config.comparison not in COMPARISONS:
        raise ConfigError(
            [f"{spec_path}: unknown comparison '{config.comparison}' (known: {COMPARISONS})"]
        )

    cases: list[InstructorCase] = []
    tests_path = root / "tests.yaml"
    if tests_path.exists():
        try:
            raw = yaml.safe_load(tests_path.read_text(encoding="utf-8")) or {}
            cases = [InstructorCase.model_validate(c) for c in raw.get("tests", [])]
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigError([f"{tests_path}: {exc}"]) from exc

    reference = root / "reference.c"
    return AssignmentPackage(
        config=config,
        statement_sections=_split_sections(md_path.read_text(encoding="utf-8")),
        instructor_cases=cases,
        reference_path=reference if reference.exists() else None,
        source_dir=root,
    )


def build_spec(package: AssignmentPackage) -> AssignmentSpec:
    s = package.statement_sections
    unresolved: list[str] = []
    if "input" not in s:
        unresolved.append("assignment.md has no ## Input section: input contract unknown")
    if "output" not in s:
        unresolved.append("assignment.md has no ## Output section: output contract unknown")
    if not package.instructor_cases and package.reference_path is None:
        unresolved.append(
            "no instructor cases and no reference implementation: "
            "no authoritative trust source is available"
        )
    constraints = [
        line.strip("- ").strip()
        for line in s.get("constraints", "").splitlines()
        if line.strip()
    ]
    examples = [
        AssignmentExample(
            input_data=c.input,
            expected_output=c.expected,
            provenance=f"instructor tests.yaml case #{i + 1} (category {c.category})",
        )
        for i, c in enumerate(package.instructor_cases)
    ]
    spec = AssignmentSpec(
        assignment_id=package.config.assignment_id,
        purpose=s.get("problem", ""),
        input_contract=s.get("input", ""),
        output_contract=s.get("output", ""),
        constraints=constraints,
        boundary_conditions=[
            line.strip("- ").strip()
            for line in s.get("boundary", "").splitlines()
            if line.strip()
        ],
        invalid_input_behavior=package.config.invalid_input_behavior,
        examples=examples,
        unresolved_questions=unresolved,
        provenance=[
            f"assignment package: {package.source_dir}",
            f"generator: {package.config.generator}",
            f"comparison: {package.config.comparison}",
            f"instructor cases: {len(package.instructor_cases)}",
            f"reference: {'present' if package.reference_path else 'absent'}",
        ],
    )
    digest = canonical_hash(spec.model_dump(mode="json", exclude={"specification_hash"}))
    spec.specification_hash = digest
    return spec
