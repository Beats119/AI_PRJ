"""All three formats render from the same canonical EvaluationReport, so a
grade can never differ between the JSON, the HTML page and the text file.
No timestamps are emitted: identical evaluations render identically.
"""

from __future__ import annotations

import html
import json

from autograder.models.report import EvaluationReport


def render_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=1) + "\n"


def _grade_line(report: EvaluationReport) -> str:
    if report.overall_grade is None:
        return f"overall: {report.overall_status.value} — no grade (see breakdown)"
    return f"overall: {report.overall_status.value} — grade {report.overall_grade}/100"


def _failing(report: EvaluationReport) -> list[dict]:
    for r in report.metric_results:
        if r.metric_name == "correctness":
            return r.evidence.get("failing", [])
    return []


def render_txt(report: EvaluationReport) -> str:
    lines: list[str] = []
    lines.append("AutoGrader evaluation report")
    lines.append("============================")
    lines.append(f"submission : {report.submission_name} ({report.submission_hash})")
    lines.append(f"evaluation : {report.evaluation_id}")
    lines.append(_grade_line(report))
    lines.append(f"coverage   : {report.metric_coverage} of configured weight graded")
    if report.flags:
        lines.append(f"flags      : {', '.join(report.flags)}")
    lines.append("")
    lines.append("Per-metric breakdown (configured weight / score / contribution / "
                 "effective weight):")
    by_name = {r.metric_name: r for r in report.metric_results}
    for row in report.score_breakdown:
        score = "n/a" if row.score is None else f"{row.score}"
        contrib = "n/a" if row.contribution is None else f"{row.contribution}"
        eff = "n/a" if row.effective_weight is None else f"{row.effective_weight}"
        lines.append(
            f"  {row.name:<14} weight {row.configured_weight}  status {row.status:<10} "
            f"score {score:<6} contribution {contrib:<6} effective {eff}"
            + (f"  ({row.note})" if row.note else "")
        )
        result = by_name.get(row.name)
        if result and result.feedback:
            lines.append(f"      feedback: {result.feedback}")
    failing = _failing(report)
    if failing:
        lines.append("")
        lines.append("Counterexamples (trusted tests the submission fails):")
        for f in failing[:5]:
            lines.append(
                f"  test {f['test_id']} input {f['input']!r} expected "
                f"{f['expected']!r} got {f['actual']!r} [{f['outcome']}]"
            )
    if report.limitations:
        lines.append("")
        lines.append("Limitations and scoring notes:")
        for lim in report.limitations:
            lines.append(f"  - {lim}")
    lines.append("")
    lines.append("Provenance:")
    for k, v in sorted(report.provenance.items()):
        lines.append(f"  {k}: {v}")
    return "\n".join(lines) + "\n"


_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem auto;
max-width:960px;padding:0 1rem;color:#1a1a2e;background:#f7f7fb}
.card{background:#fff;border:1px solid #e2e2ea;border-radius:12px;padding:1.25rem 1.5rem;
margin-bottom:1rem;box-shadow:0 1px 3px rgba(20,20,60,.06)}
h1{font-size:1.5rem;margin:.2rem 0} h2{font-size:1.1rem;margin:.4rem 0 .8rem}
.grade{font-size:2.2rem;font-weight:700}
.chip{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.78rem;
font-weight:600;background:#e8e8f2}
.chip.complete{background:#d9f2e2}.chip.partial{background:#fdeec9}
.chip.incomplete{background:#f9d7d7}.chip.provisional{background:#e3dcf9}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:.45rem .5rem;border-bottom:1px solid #eee}
.bar{height:8px;background:#eee;border-radius:4px;min-width:90px}
.bar>div{height:8px;background:#4a6cf7;border-radius:4px}
pre{background:#10101c;color:#d8f3dc;padding:.8rem;border-radius:8px;overflow-x:auto;
font-size:.82rem}
.muted{color:#666;font-size:.85rem}
"""


def render_html(report: EvaluationReport) -> str:
    e = html.escape
    by_name = {r.metric_name: r for r in report.metric_results}
    rows = []
    for row in report.score_breakdown:
        pct = 0 if row.score is None else float(row.score) * 100
        result = by_name.get(row.name)
        feedback = e(result.feedback) if result and result.feedback else ""
        rows.append(
            f"<tr><td><b>{e(row.name)}</b><div class='muted'>{feedback}</div></td>"
            f"<td>{e(str(row.configured_weight))}</td><td>{e(row.status)}</td>"
            f"<td><div class='bar'><div style='width:{pct:.0f}%'></div></div></td>"
            f"<td>{'n/a' if row.score is None else e(str(row.score))}</td>"
            f"<td>{'n/a' if row.contribution is None else e(str(row.contribution))}</td>"
            f"<td>{'n/a' if row.effective_weight is None else e(str(row.effective_weight))}</td></tr>"
        )
    failing = _failing(report)
    counter = ""
    if failing:
        items = "\n".join(
            f"test {f['test_id']}  input {f['input']!r}  expected {f['expected']!r}  "
            f"got {f['actual']!r}  [{f['outcome']}]"
            for f in failing[:5]
        )
        counter = (
            "<div class='card'><h2>Counterexamples</h2>"
            f"<pre>{e(items)}</pre></div>"
        )
    grade = (
        "no grade" if report.overall_grade is None else f"{report.overall_grade}/100"
    )
    limitations = "".join(f"<li>{e(x)}</li>" for x in report.limitations)
    provenance = "".join(
        f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>"
        for k, v in sorted(report.provenance.items())
    )
    flags = "".join(f" <span class='chip'>{e(f)}</span>" for f in report.flags)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>AutoGrader report — {e(report.submission_name)}</title>
<style>{_CSS}</style></head><body>
<div class="card"><h1>AutoGrader evaluation report</h1>
<div class="muted">submission {e(report.submission_name)} · {e(report.submission_hash)}
 · evaluation {e(report.evaluation_id)}</div>
<div class="grade">{e(grade)}</div>
<span class="chip {e(report.overall_status.value)}">{e(report.overall_status.value)}</span>{flags}
<div class="muted">metric coverage {e(str(report.metric_coverage))} of configured weight</div></div>
<div class="card"><h2>Per-metric breakdown</h2><table>
<tr><th>Metric</th><th>Weight</th><th>Status</th><th></th><th>Score</th>
<th>Contribution</th><th>Effective weight</th></tr>
{''.join(rows)}</table></div>
{counter}
<div class="card"><h2>Limitations and scoring notes</h2><ul>{limitations}</ul></div>
<div class="card"><h2>Provenance</h2><table>{provenance}</table></div>
</body></html>
"""
