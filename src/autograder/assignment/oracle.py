"""Oracle verification + the D-1 sufficiency bar.

Trust categories (see docs/TRUST_MODEL.md):
  instructor_provided       trusted — the instructor stated this expected
                            output; the strongest source we have.
  reference_run             trusted — produced by a reference implementation
                            that itself passed every instructor case.
  independent_derivation    trusted — computed by a method independent of
                            both the student code and the LLM from a contract
                            that fully determines the output (e.g. integer
                            addition in arbitrary precision).
  llm_unverified            NEVER trusted — the LLM proposed it and nothing
                            independent confirmed it. Excluded from scoring.
  rejected                  invalid input, contradiction between independent
                            sources, or a broken oracle run. Not in the suite.

A candidate becomes trusted only through a source above that is independent
of the candidate's origin. An LLM that proposes both an input and its
expected output can therefore never make a test trusted by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autograder.assignment.specification import AssignmentPackage
from autograder.assignment.test_generation import INT32_MAX, INT32_MIN, parse_int_pair
from autograder.comparison import compare_outputs
from autograder.config.schema import SufficiencyConfig
from autograder.models.assignment import AssignmentSpec
from autograder.models.execution import ExecutionStatus
from autograder.models.tests import TestCase, TrustStatus
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits

ORACLE_POLICY_VERSION = "oracle-v1"


@dataclass
class SufficiencyReport:
    sufficient: bool
    applicable_categories: dict[str, str]  # category -> why applicable
    trusted_by_category: dict[str, int]
    conditions: list[dict]  # {name, passed, detail}
    total_trusted: int


@dataclass
class VerificationResult:
    suite: list[TestCase]  # trusted + untrusted (rejected are separate)
    rejected: list[TestCase]
    sufficiency: SufficiencyReport
    reference_trusted: bool | None  # None = no reference present
    validation_executions: int
    diagnostics: list[str] = field(default_factory=list)


def derive_int_pair(input_data: str) -> str | None:
    parsed = parse_int_pair(input_data, INT32_MIN, INT32_MAX)
    if parsed is None:
        return None
    a, b = parsed
    return str(a + b)  # Python ints: arbitrary precision, no overflow


DERIVERS = {"int_pair_v1": derive_int_pair}


def applicable_categories(
    spec: AssignmentSpec, package: AssignmentPackage, pool_categories: set[str]
) -> dict[str, str]:
    cfg = package.config
    applicable: dict[str, str] = {}
    for cat in ("ordinary_valid", "minimum_boundary", "maximum_boundary", "edge_values"):
        applicable[cat] = "core category: always applicable to a bounded-input contract"
    input_contract = (spec.input_contract or "").lower()
    if "whitespace" in input_contract or cfg.generator == "int_pair_v1":
        applicable["parsing_whitespace"] = (
            "text input format where whitespace separates tokens"
        )
    if spec.invalid_input_behavior is not None:
        applicable["invalid_input"] = (
            "the specification explicitly defines invalid-input behaviour"
        )
    for cat in sorted(pool_categories):
        if cat not in applicable:
            applicable[cat] = "assignment-specific category present in the candidate pool"
    return applicable


def check_sufficiency(
    suite: list[TestCase],
    spec: AssignmentSpec,
    package: AssignmentPackage,
    cfg: SufficiencyConfig,
    reference_trusted: bool | None,
    reference_used: bool,
) -> SufficiencyReport:
    pool_categories = {t.category for t in suite}
    applicable = applicable_categories(spec, package, pool_categories)
    trusted = [t for t in suite if t.counts_as_trusted]
    by_cat: dict[str, int] = {}
    for t in trusted:
        by_cat[t.category] = by_cat.get(t.category, 0) + 1

    conditions: list[dict] = []
    # (1) every authoritative instructor example is present + trusted
    instructor_inputs = {" ".join(e.input_data.split()) for e in spec.examples}
    trusted_inputs = {" ".join(t.input_data.split()) for t in trusted}
    missing_examples = instructor_inputs - trusted_inputs
    conditions.append(
        {
            "name": "all_authoritative_examples_trusted",
            "passed": not missing_examples,
            "detail": f"{len(instructor_inputs) - len(missing_examples)}/"
            f"{len(instructor_inputs)} instructor cases trusted"
            + (f"; missing: {sorted(missing_examples)}" if missing_examples else ""),
        }
    )
    # (2) per-category minima
    for cat in sorted(applicable):
        need = (
            cfg.min_per_core_category
            if cat in cfg.core_categories
            else cfg.min_per_applicable_category
        )
        got = by_cat.get(cat, 0)
        conditions.append(
            {
                "name": f"category_minimum:{cat}",
                "passed": got >= need,
                "detail": f"{got} trusted, need >={need}",
            }
        )
    # (3) total
    conditions.append(
        {
            "name": "min_trusted_total",
            "passed": len(trusted) >= cfg.min_trusted_total,
            "detail": f"{len(trusted)} trusted, need >={cfg.min_trusted_total}",
        }
    )
    # (4) every counted case carries provenance + method + comparison policy
    well_formed = all(
        t.provenance and t.validation_method != "none" and t.comparison_policy
        for t in trusted
    )
    conditions.append(
        {
            "name": "trusted_cases_well_formed",
            "passed": well_formed,
            "detail": "provenance, verification method and comparison policy recorded",
        }
    )
    # (5) a reference used as a trust source passed the authoritative examples
    conditions.append(
        {
            "name": "reference_validated_before_use",
            "passed": (not reference_used) or (reference_trusted is True),
            "detail": "reference not used"
            if not reference_used
            else f"reference_trusted={reference_trusted}",
        }
    )
    return SufficiencyReport(
        sufficient=all(c["passed"] for c in conditions),
        applicable_categories=applicable,
        trusted_by_category=by_cat,
        conditions=conditions,
        total_trusted=len(trusted),
    )


def verify_candidates(
    candidates: list[TestCase],
    package: AssignmentPackage,
    spec: AssignmentSpec,
    sufficiency_cfg: SufficiencyConfig,
) -> VerificationResult:
    policy = package.config.comparison_policy
    diagnostics: list[str] = []
    executions = 0

    # Instructor cases enter as trusted directly.
    suite: list[TestCase] = []
    for i, c in enumerate(package.instructor_cases):
        suite.append(
            TestCase(
                test_id=f"inst-{i + 1:03d}",
                input_data=c.input,
                expected_output=c.expected,
                category=c.category,
                trust_status=TrustStatus.TRUSTED,
                provenance="instructor:tests.yaml",
                validation_method="instructor_provided",
                comparison_policy=policy,
                requirement_coverage=c.category,
            )
        )

    # Validate the reference (if any) against ALL instructor cases first.
    reference_trusted: bool | None = None
    reference_used = False
    ref_binary: Path | None = None
    sandbox: Sandbox | None = None
    if package.reference_path is not None:
        sandbox = Sandbox()
        comp = sandbox.compile(package.reference_path)
        if not comp.success:
            diagnostics.append(
                f"reference implementation does not compile; rejected as a trust "
                f"source: {comp.diagnostics[:200]}"
            )
            reference_trusted = False
        else:
            ref_binary = comp.binary_path
            ok = True
            for case in package.instructor_cases:
                res = sandbox.run(
                    ref_binary,
                    test_id="refcheck",
                    submission_hash=comp.source_hash,
                    input_data=case.input,
                    limits=ExecutionLimits(wall_time_s=2.0),
                )
                executions += 1
                if res.status is not ExecutionStatus.OK or not compare_outputs(
                    case.expected, res.stdout, policy
                ):
                    ok = False
                    diagnostics.append(
                        f"reference disagrees with instructor case input={case.input!r} "
                        f"expected={case.expected!r} got={res.stdout!r} "
                        f"status={res.status.value}; reference rejected as a trust source"
                    )
            reference_trusted = ok

    deriver = DERIVERS.get(package.config.generator)
    rejected: list[TestCase] = []

    def reject(case: TestCase, why: str) -> None:
        rejected.append(
            case.model_copy(
                update={
                    "trust_status": TrustStatus.REJECTED,
                    "provenance": f"{case.provenance}; rejected: {why}",
                }
            )
        )

    for cand in candidates:
        lo = package.config.input_min if package.config.input_min is not None else INT32_MIN
        hi = package.config.input_max if package.config.input_max is not None else INT32_MAX
        if (
            package.config.generator == "int_pair_v1"
            and parse_int_pair(cand.input_data, lo, hi) is None
        ):
            reject(cand, "input violates the assignment's input constraints")
            continue
        derived = deriver(cand.input_data) if deriver else None
        ref_out: str | None = None
        if ref_binary is not None and reference_trusted:
            assert sandbox is not None
            res = sandbox.run(
                ref_binary,
                test_id=cand.test_id,
                submission_hash="reference",
                input_data=cand.input_data,
                limits=ExecutionLimits(wall_time_s=2.0),
            )
            executions += 1
            if res.status is ExecutionStatus.OK:
                ref_out = res.stdout.strip()
                reference_used = True
            else:
                reject(cand, f"reference run failed ({res.status.value})")
                continue
        if derived is not None and ref_out is not None:
            if compare_outputs(derived, ref_out, policy):
                suite.append(
                    cand.model_copy(
                        update={
                            "expected_output": derived,
                            "trust_status": TrustStatus.TRUSTED,
                            "validation_method": "reference_run+independent_derivation",
                            "provenance": f"{cand.provenance}; verified by reference run "
                            "and independent derivation",
                        }
                    )
                )
            else:
                reject(
                    cand,
                    f"independent sources contradict (derivation={derived!r}, "
                    f"reference={ref_out!r})",
                )
        elif derived is not None:
            suite.append(
                cand.model_copy(
                    update={
                        "expected_output": derived,
                        "trust_status": TrustStatus.TRUSTED,
                        "validation_method": "independent_derivation",
                        "provenance": f"{cand.provenance}; verified by independent "
                        "derivation from the contract",
                    }
                )
            )
        elif ref_out is not None:
            suite.append(
                cand.model_copy(
                    update={
                        "expected_output": ref_out,
                        "trust_status": TrustStatus.TRUSTED,
                        "validation_method": "reference_run",
                        "provenance": f"{cand.provenance}; verified by trusted "
                        "reference run",
                    }
                )
            )
        else:
            # Nothing independent can verify this candidate. An LLM-proposed
            # expected output stays an unverified claim, never trust.
            suite.append(
                cand.model_copy(
                    update={
                        "trust_status": TrustStatus.UNTRUSTED,
                        "validation_method": "llm_unverified"
                        if cand.provenance.startswith("llm")
                        else "none",
                    }
                )
            )
    if sandbox is not None:
        sandbox.__exit__()  # close the reference workspace

    sufficiency = check_sufficiency(
        suite, spec, package, sufficiency_cfg, reference_trusted, reference_used
    )
    if not sufficiency.sufficient:
        failed = [c["name"] for c in sufficiency.conditions if not c["passed"]]
        diagnostics.append(f"suite below the D-1 sufficiency bar: {failed}")
    return VerificationResult(
        suite=suite,
        rejected=rejected,
        sufficiency=sufficiency,
        reference_trusted=reference_trusted,
        validation_executions=executions,
        diagnostics=diagnostics,
    )
