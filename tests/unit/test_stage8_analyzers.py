"""Stage 8 analyzer tests: syntax, structure, modularity, complexity,
profiling honesty, readability (deterministic + advisory), similarity."""

from decimal import Decimal
from pathlib import Path

from autograder.analyzers.complexity import analyze_complexity, classify_growth
from autograder.analyzers.profiling import measure_profile
from autograder.analyzers.readability import analyze_readability
from autograder.analyzers.similarity import (
    analyze_originality,
    pairwise_similarities,
    similarity_score,
)
from autograder.analyzers.structure import analyze_modularity, analyze_structure
from autograder.analyzers.syntax import analyze_syntax
from autograder.config.loader import load_models_config
from autograder.llm.client import LLMClient
from autograder.models.analysis import ResultStatus
from autograder.sandbox.executor import Sandbox

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "examples" / "submissions"

WARN_C = """
#include <stdio.h>
int main(void){ int unused = 5; printf("hi\\n"); return 0; }
"""

BRANCHY_C = """
#include <stdio.h>
int classify(int x) {
    int r = 0;
    if (x > 0) { r += 1; }
    if (x > 10) { r += 2; }
    if (x > 20) { r += 3; }
    if (x > 30) { r += 4; }
    if (x > 40) { r += 5; }
    if (x > 50) { r += 6; }
    if (x > 60) { r += 7; }
    if (x > 70) { r += 8; }
    if (x > 80) { r += 9; }
    if (x > 90) { r += 10; }
    return r;
}
int main(void){ printf("%d\\n", classify(42)); return 0; }
"""

LONG_C = "int compute(void) {\n" + "".join(
    f"    int v{i} = {i};\n" for i in range(45)
) + "    return v0;\n}\nint main(void){ return compute(); }\n"

LINEAR_C = """
#include <stdio.h>
int main(void){ long n, s = 0; if (scanf("%ld", &n) != 1) return 1;
  for (long i = 0; i < n; i++) { s += i; } printf("%ld\\n", s); return 0; }
"""

NESTED_C = """
#include <stdio.h>
int main(void){ long n, s = 0; if (scanf("%ld", &n) != 1) return 1;
  for (long i = 0; i < n; i++) { for (long j = 0; j < n; j++) { s += 1; } }
  printf("%ld\\n", s); return 0; }
"""

BADSTYLE_C = """
#include <stdio.h>
int main(void){int a,b,c,d,e,f;scanf("%d %d",&a,&b);c=a*b+12345;d=c-987;e=d/34;f=e%77;printf("%d %d %d %d\\n",c,d,e,f);int g=a+555;int h=b+444;int i=g*h;int j=i-333;int k=j+222;int l=k*11;int m=l/13;int n=m+17;int o=n-19;int p=o*23;printf("%d %d %d %d %d %d %d %d %d\\n",g,h,i,j,k,l,m,n,o);return 0;}
"""

RENAMED_COPY = """
#include <stdio.h>
static long long combine(long long first, long long second) {
    return first + second;
}
int main(void) {
    long long first, second;
    if (scanf("%lld %lld", &first, &second) != 2) {
        return 1;
    }
    printf("%lld\\n", combine(first, second));
    return 0;
}
"""

DIFFERENT_C = """
#include <stdio.h>
#include <string.h>
int main(void) {
    char buf[256];
    if (!fgets(buf, sizeof buf, stdin)) return 1;
    int vowels = 0;
    for (size_t i = 0; i < strlen(buf); i++) {
        if (buf[i]=='a'||buf[i]=='e'||buf[i]=='i'||buf[i]=='o'||buf[i]=='u') vowels++;
    }
    printf("%d\\n", vowels);
    return 0;
}
"""


def _write(tmp_path, name, code):
    p = tmp_path / name
    p.write_text(code)
    return p


# -- syntax ---------------------------------------------------------------
def test_syntax_clean_and_warned(tmp_path):
    clean = analyze_syntax(SUB / "correct.c", work_dir=tmp_path)
    assert clean.status is ResultStatus.PASSED and clean.score == Decimal(1)
    warned_src = _write(tmp_path, "w.c", WARN_C)
    warned = analyze_syntax(warned_src, work_dir=tmp_path)
    assert warned.status is ResultStatus.FAILED
    assert warned.evidence["warnings"] >= 1
    assert warned.evidence["strict_werror_compile_passed"] is False
    broken = _write(tmp_path, "b.c", "int main(void){ nope; }\n")
    failed = analyze_syntax(broken, work_dir=tmp_path)
    assert failed.score == Decimal(0) and failed.evidence["errors"] >= 1


# -- structure / modularity ------------------------------------------------
def test_structure_findings_and_fixes(tmp_path):
    ok = analyze_structure(SUB / "correct.c")
    assert ok.status is ResultStatus.PASSED and ok.score == Decimal(1)
    branchy = analyze_structure(_write(tmp_path, "br.c", BRANCHY_C))
    assert branchy.status is ResultStatus.FAILED
    finding = next(f for f in branchy.evidence["functions"] if f["function"] == "classify")
    assert finding["cyclomatic"] > 8
    assert finding["problems"] and finding["suggested_fixes"]
    long_res = analyze_structure(
        _write(tmp_path, "long.c", LONG_C), max_function_length=40
    )
    long_finding = next(f for f in long_res.evidence["functions"]
                        if f["function"] == "compute")
    assert any("length" in p for p in long_finding["problems"])


def test_modularity_rewards_helpers(tmp_path):
    good = analyze_modularity(SUB / "correct.c")
    assert good.score == Decimal(1) and good.status is ResultStatus.PASSED
    solo = analyze_modularity(SUB / "incorrect.c")
    assert solo.score == Decimal("0.5") and solo.status is ResultStatus.FAILED


# -- complexity -------------------------------------------------------------
def test_complexity_static_estimates(tmp_path):
    ok = analyze_complexity(SUB / "correct.c", required="O(1)")
    assert ok.status is ResultStatus.PASSED and ok.evidence["estimated"] == "O(1)"
    lin = analyze_complexity(_write(tmp_path, "lin.c", LINEAR_C), required="O(1)")
    assert lin.evidence["estimated"] == "O(n)" and lin.score == Decimal("0.5")
    nested = analyze_complexity(_write(tmp_path, "nest.c", NESTED_C), required="O(1)")
    assert nested.evidence["estimated"] == "O(n^2)" and nested.score == Decimal(0)


def test_classify_growth_exact_models():
    sizes = [100, 200, 400, 800]
    const, _ = classify_growth(sizes, [0.01, 0.01, 0.01, 0.01])
    assert const == "O(1)"
    linear, _ = classify_growth(sizes, [0.01, 0.02, 0.04, 0.08])
    assert linear == "O(n)"
    quad, _ = classify_growth(sizes, [1e-3, 4e-3, 1.6e-2, 6.4e-2])
    assert quad == "O(n^2)"
    nlogn, _ = classify_growth(
        [64, 128, 256, 512], [0.000384, 0.000896, 0.002048, 0.004608]
    )
    assert nlogn == "O(n log n)"


def test_classify_growth_refuses_noise():
    tiny, ev = classify_growth([1, 10, 100], [1e-9, 2e-9, 3e-9])
    assert tiny is None and "resolution" in ev["reason"]
    noisy, _ev = classify_growth([100, 200, 400, 800], [0.01, 0.5, 0.02, 0.9])
    assert noisy is None


def test_complexity_disagreement_is_inconclusive(tmp_path):
    src = _write(tmp_path, "lin.c", LINEAR_C)  # static says O(n)
    result = analyze_complexity(
        src, required="O(1)", timings=([100, 200, 400, 800], [0.01, 0.01, 0.01, 0.01])
    )
    assert result.status is ResultStatus.INCONCLUSIVE  # empirical says O(1)
    assert result.score is None


# -- profiling ---------------------------------------------------------------
def test_profiling_measures_time_and_is_honest_about_perf(tmp_path):
    with Sandbox() as sb:
        comp = sb.compile(SUB / "correct.c")
        assert comp.success
        report = measure_profile(
            comp.binary_path, workspace=sb.workspace,
            input_data="7 5\n", runs=3,
        )
    assert report.wall_time_ms_median is not None
    assert report.run_statuses == ["ok"] * 3
    # on this machine perf is absent; where present, counters must be real
    assert report.perf_note
    if report.cache_counters is None:
        assert "perf" in report.perf_note
    else:
        assert "cache-misses" in report.cache_counters


# -- readability ---------------------------------------------------------------
def test_readability_clean_vs_bad_style(tmp_path):
    good = analyze_readability(SUB / "correct.c")
    assert good.status is ResultStatus.PASSED and good.score == Decimal(1)
    bad = analyze_readability(_write(tmp_path, "bad.c", BADSTYLE_C))
    assert bad.score < Decimal("0.7")
    checks = {f["check"] for f in bad.evidence["findings"]}
    assert "naming" in checks and "magic_numbers" in checks
    assert all(f["fix"] for f in bad.evidence["findings"])


def test_readability_llm_advisory_never_changes_score(tmp_path):
    src = _write(tmp_path, "bad.c", BADSTYLE_C)
    plain = analyze_readability(src)
    cfg = load_models_config(ROOT / "configs" / "models.yaml").llm

    def fake(url, payload):
        return {"response": "Consider naming things better.",
                "prompt_eval_count": 1, "eval_count": 1}

    client = LLMClient(cfg, transport=fake, transport_name="fake")
    advised = analyze_readability(src, llm_client=client, llm_advisory=True)
    assert advised.score == plain.score  # D-4: advisory only
    assert advised.evidence["llm_advisory"]["transport"] == "fake"
    assert "ADVISORY ONLY" in advised.evidence["llm_advisory"]["note"]


# -- similarity ---------------------------------------------------------------
def test_similarity_detects_renamed_copies(tmp_path):
    correct_text = (SUB / "correct.c").read_text()
    assert similarity_score(correct_text, correct_text) == 1.0
    renamed = similarity_score(correct_text, RENAMED_COPY)
    assert renamed >= 0.85  # identifier renaming must not defeat it
    different = similarity_score(correct_text, DIFFERENT_C)
    assert different < 0.5


def test_originality_flags_and_inconclusive_paths(tmp_path):
    copy_path = _write(tmp_path, "copy.c", RENAMED_COPY)
    flagged = analyze_originality(SUB / "correct.c", [copy_path])
    assert flagged.status is ResultStatus.FAILED and flagged.score == Decimal(0)
    assert "not proof of copying" in flagged.feedback
    alone = analyze_originality(SUB / "correct.c", [])
    assert alone.status is ResultStatus.INCONCLUSIVE
    pairs = pairwise_similarities(
        {"a": (SUB / "correct.c").read_text(), "b": RENAMED_COPY, "c": DIFFERENT_C}
    )
    assert len(pairs) == 3  # N(N-1)/2
    ab = next(p for p in pairs if {p["a"], p["b"]} == {"a", "b"})
    assert ab["flagged"] is True
