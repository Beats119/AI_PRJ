"""Stage 8 integration: real sanitizer runs over the trusted suite, and a
full 9-metric scoring run feeding the Stage 4 D-3 engine."""

from decimal import Decimal
from pathlib import Path

import pytest

from autograder.analyzers.complexity import analyze_complexity
from autograder.analyzers.correctness import analyze_correctness, analyze_logical
from autograder.analyzers.memory_safety import analyze_memory_safety
from autograder.analyzers.readability import analyze_readability
from autograder.analyzers.similarity import analyze_originality
from autograder.analyzers.structure import analyze_modularity, analyze_structure
from autograder.analyzers.syntax import analyze_syntax
from autograder.assignment import prepare_assignment
from autograder.config.loader import load_models_config, load_rules
from autograder.models.analysis import ResultStatus
from autograder.models.tests import TestCase, TrustStatus
from autograder.sandbox.executor import Sandbox
from autograder.sandbox.limits import ExecutionLimits
from autograder.scoring.engine import score_results

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"
SUB = ROOT / "examples" / "submissions"
LIMITS = ExecutionLimits(wall_time_s=2.0, memory_mb=64)


def _case(i, text, expected):
    return TestCase(
        test_id=f"t{i}", input_data=text, expected_output=expected,
        category="ordinary_valid", trust_status=TrustStatus.TRUSTED,
        provenance="test fixture", validation_method="instructor_provided",
    )


SMALL_SUITE = [_case(1, "7 5\n", "12"), _case(2, "0 0\n", "0"),
               _case(3, "-3 -4\n", "-7")]

BUFOVER_C = """
#include <stdio.h>
int main(void){ int a, b; if (scanf("%d %d", &a, &b) != 2) return 1;
  int buf[4]; for (int i = 0; i < 12; i++) { buf[i] = i; }
  printf("%d\\n", a + b + buf[0]); return 0; }
"""

UB_C = """
#include <stdio.h>
#include <limits.h>
int main(void){ int a, b; if (scanf("%d %d", &a, &b) != 2) return 1;
  printf("%d\\n", a + b); return 0; }
"""

LEAK_C = """
#include <stdio.h>
#include <stdlib.h>
int main(void){ int a, b; if (scanf("%d %d", &a, &b) != 2) return 1;
  int *p = malloc(sizeof(int) * 4); p[0] = a + b; printf("%d\\n", p[0]); return 0; }
"""


def _write(tmp_path, name, code):
    p = tmp_path / name
    p.write_text(code)
    return p


def test_memory_safety_clean_submission(tmp_path):
    with Sandbox() as sb:
        result = analyze_memory_safety(SUB / "correct.c", SMALL_SUITE, sandbox=sb)
    assert result.status is ResultStatus.PASSED and result.score == Decimal(1)
    assert all(r["outcome"] == "clean" for r in result.evidence["records"])


def test_memory_safety_catches_buffer_overflow(tmp_path):
    src = _write(tmp_path, "over.c", BUFOVER_C)
    with Sandbox() as sb:
        result = analyze_memory_safety(src, SMALL_SUITE, sandbox=sb)
    assert result.status is ResultStatus.FAILED and result.score == Decimal(0)
    findings = result.evidence["records"][0]["findings"]
    assert any("Sanitizer" in f or "sanitizer" in f for f in findings)


def test_memory_safety_catches_signed_overflow_ub(tmp_path):
    src = _write(tmp_path, "ub.c", UB_C)
    suite = [_case(9, "2147483647 1\n", "2147483648")]
    with Sandbox() as sb:
        result = analyze_memory_safety(src, suite, sandbox=sb)
    assert result.status is ResultStatus.FAILED
    findings = result.evidence["records"][0]["findings"]
    assert any("runtime error" in f for f in findings)


def test_memory_safety_catches_leak(tmp_path):
    src = _write(tmp_path, "leak.c", LEAK_C)
    with Sandbox() as sb:
        result = analyze_memory_safety(src, SMALL_SUITE[:1], sandbox=sb)
    assert result.status is ResultStatus.FAILED
    rec = result.evidence["records"][0]
    assert rec["outcome"] == "sanitizer_finding"


def test_memory_safety_broken_toolchain_is_environment_error(tmp_path):
    with Sandbox() as sb:
        result = analyze_memory_safety(
            SUB / "correct.c", SMALL_SUITE, sandbox=sb,
            flags="-fsanitize=doesnotexist",
        )
    assert result.status is ResultStatus.ERROR
    assert result.score is None  # our tools, not the student


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    models = load_models_config(ROOT / "configs" / "models.yaml")
    cache = tmp_path_factory.mktemp("cache8")
    return prepare_assignment(EXAMPLE, loaded, models, cache)


def _all_metrics(source: Path, corpus: list[Path], suite, work: Path):
    with Sandbox() as sb:
        comp = sb.compile(source)
        assert comp.success
        results = [
            analyze_correctness(comp.binary_path, suite,
                                submission_hash=comp.source_hash,
                                sandbox=sb, limits=LIMITS),
            analyze_logical(comp.binary_path, suite,
                            submission_hash=comp.source_hash,
                            sandbox=sb, limits=LIMITS),
            analyze_syntax(source, work_dir=work),
            analyze_structure(source),
            analyze_modularity(source),
            analyze_complexity(source, required="O(1)"),
            analyze_memory_safety(source, suite, sandbox=sb),
            analyze_readability(source),
            analyze_originality(source, corpus),
        ]
    return results


def test_full_nine_metric_scoring_is_deterministic(prepared, tmp_path):
    loaded = load_rules(ROOT / "configs" / "example_rules.yaml")
    suite = prepared.suite
    r1 = _all_metrics(SUB / "correct.c", [SUB / "incorrect.c"], suite, tmp_path / "a")
    outcome1 = score_results(loaded.rules, r1)
    assert outcome1.overall_status.value == "complete"
    expected = (
        sum(
            (m.weight * r.score for m, r in zip(loaded.rules.metrics, r1, strict=True)
             if r.score is not None),
            Decimal(0),
        ) * 100
    ).quantize(Decimal("0.1"))
    assert outcome1.overall_grade == expected
    r2 = _all_metrics(SUB / "correct.c", [SUB / "incorrect.c"], suite, tmp_path / "b")
    assert [r.score for r in r2] == [r.score for r in r1]  # repeatability


def test_incorrect_submission_full_run(prepared, tmp_path):
    suite = prepared.suite
    results = _all_metrics(SUB / "incorrect.c", [SUB / "correct.c"], suite,
                           tmp_path / "w")
    by_metric = {r.metric_name: r for r in results}
    assert by_metric["correctness"].score < Decimal(1)
    assert by_metric["modularity"].score == Decimal("0.5")
    # UBSan catches the PDF example's signed-overflow bug for real:
    ms = by_metric["memory_safety"]
    assert ms.score < Decimal(1)
    assert any(
        "runtime error" in f
        for rec in ms.evidence["records"] for f in rec["findings"]
    )
    assert by_metric["originality"].status is ResultStatus.PASSED
