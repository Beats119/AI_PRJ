"""Server-rendered pages for the UI (no JavaScript build, works offline)."""

from __future__ import annotations

import html

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;
color:#1a1a2e;background:#f7f7fb}
header{background:#1a1a2e;color:#fff;padding:.9rem 1.5rem;display:flex;gap:1.5rem;
align-items:baseline}
header b{font-size:1.15rem} header a{color:#bcd;text-decoration:none;font-size:.95rem}
main{max-width:980px;margin:1.5rem auto;padding:0 1rem}
.card{background:#fff;border:1px solid #e2e2ea;border-radius:12px;
padding:1.25rem 1.5rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(20,20,60,.06)}
h1{font-size:1.4rem;margin:.2rem 0 1rem} h2{font-size:1.05rem;margin:.3rem 0 .7rem}
label{display:block;font-weight:600;margin:.7rem 0 .3rem;font-size:.92rem}
select,input[type=file]{width:100%;padding:.5rem;border:1px solid #ccd;border-radius:8px}
button{background:#4a6cf7;color:#fff;border:0;border-radius:8px;padding:.6rem 1.2rem;
font-weight:600;cursor:pointer;margin-top:1rem}
button.secondary{background:#e8e8f2;color:#1a1a2e}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:.45rem .5rem;border-bottom:1px solid #eee}
.chip{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.78rem;
font-weight:600;background:#e8e8f2}
.chip.complete{background:#d9f2e2}.chip.partial{background:#fdeec9}
.chip.incomplete{background:#f9d7d7}.chip.provisional{background:#e3dcf9}
.muted{color:#666;font-size:.86rem} .grade{font-weight:700}
pre{background:#10101c;color:#d8f3dc;padding:.8rem;border-radius:8px;overflow-x:auto;
font-size:.8rem}
"""


def layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)} — AutoGrader</title>
<style>{CSS}</style></head><body>
<header><b>AutoGrader</b><a href="/">Evaluate</a><a href="/assignments">Assignments &amp; cache</a><a href="/doctor">Environment</a></header>
<main>{body}</main></body></html>"""


def home_page(assignments: list[str], reports: list[dict]) -> str:
    options = "".join(
        f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in assignments
    )
    rows = "".join(
        f"<tr><td><a href='/reports/{html.escape(r['stem'])}'>{html.escape(r['stem'])}</a></td>"
        f"<td><span class='chip {html.escape(r['status'])}'>{html.escape(r['status'])}</span></td>"
        f"<td class='grade'>{html.escape(r['grade'])}</td>"
        f"<td><a href='/reports/{html.escape(r['stem'])}.json'>JSON</a> · "
        f"<a href='/reports/{html.escape(r['stem'])}.txt'>TXT</a></td></tr>"
        for r in reports
    ) or "<tr><td colspan='4' class='muted'>No evaluations yet.</td></tr>"
    body = f"""
<div class="card"><h1>Evaluate a submission</h1>
<form method="post" action="/evaluate" enctype="multipart/form-data">
<label for="assignment">Assignment</label>
<select id="assignment" name="assignment">{options}</select>
<label for="file">Student C submission (.c)</label>
<input id="file" type="file" name="file" accept=".c" required>
<button type="submit">Run evaluation</button>
</form>
<p class="muted">The evaluation runs the same workflow as the CLI: sandboxed
compile, smoke run, all configured analyzers, deterministic scoring.
Reports are stored and listed below.</p></div>
<div class="card"><h2>Recent reports</h2><table>
<tr><th>Submission</th><th>Status</th><th>Grade</th><th>Downloads</th></tr>
{rows}</table></div>"""
    return layout("Evaluate", body)


def assignments_page(entries: list[dict], known: list[str]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(e.get('assignment_id', '?')))}</td>"
        f"<td class='muted'>{html.escape(str(e.get('key', ''))[:16])}…</td>"
        f"<td>{html.escape(str(e.get('trusted_tests', '—')))}</td>"
        f"<td><form method='post' action='/assignments/{html.escape(str(e.get('assignment_id', '')))}/invalidate'>"
        "<button class='secondary' type='submit'>Invalidate</button></form></td></tr>"
        for e in entries
    ) or "<tr><td colspan='4' class='muted'>Cache is empty — suites are built on first use.</td></tr>"
    known_txt = ", ".join(html.escape(k) for k in known) or "none configured"
    body = f"""
<div class="card"><h1>Assignments &amp; trusted-suite cache</h1>
<p class="muted">Known assignment packages: {known_txt}. A suite is generated
once, verified against the D-1 bar, then reused for every student; a cache
entry is revalidated (schema + integrity) on every read.</p>
<table><tr><th>Assignment</th><th>Cache key</th><th>Trusted tests</th><th></th></tr>
{rows}</table></div>"""
    return layout("Assignments", body)


def doctor_page(report_json: str) -> str:
    body = f"""
<div class="card"><h1>Environment (doctor)</h1>
<p class="muted">What this machine actually provides. Analyzers that need a
missing tool report an environment outcome instead of scoring the student.</p>
<pre>{html.escape(report_json)}</pre></div>"""
    return layout("Environment", body)
