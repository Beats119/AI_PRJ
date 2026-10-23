"""FastAPI application factory for the AutoGrader UI.

Configuration is explicit (paths chosen by the `serve` CLI command).
Assignment selection is restricted to packages found in the configured
assignments directory — the browser can never point the grader at arbitrary
filesystem paths. Uploaded files are stored under the reports directory
with sanitized names.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from autograder.assignment.cache import AssignmentCache
from autograder.config.loader import load_models_config, load_rules
from autograder.doctor import run_doctor
from autograder.models.report import EvaluationReport
from autograder.reports import render_html, render_json, render_txt
from autograder.web import pages
from autograder.workflow import evaluate_submission

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(filename: str) -> str:
    name = _SAFE_NAME.sub("_", Path(filename).name)
    return name if name.endswith(".c") else name + ".c"


def create_app(
    *,
    rules_path: Path,
    models_path: Path,
    cache_dir: Path,
    assignments_dir: Path,
    reports_dir: Path,
    corpus_dir: Path | None = None,
) -> FastAPI:
    reports_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir = reports_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    assignment_dirs = {
        d.name: d for d in sorted(assignments_dir.iterdir()) if d.is_dir()
    } if assignments_dir.is_dir() else {}

    app = FastAPI(title="AutoGrader")

    def _report_summaries() -> list[dict]:
        out = []
        for f in sorted(reports_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            grade = data.get("overall_grade")
            out.append(
                {
                    "stem": f.stem,
                    "status": data.get("overall_status", "?"),
                    "grade": "no grade" if grade is None else f"{grade}/100",
                }
            )
        return out

    def _load_report(stem: str) -> EvaluationReport | None:
        path = reports_dir / f"{stem}.json"
        if not path.exists():
            return None
        return EvaluationReport.model_validate_json(path.read_text())

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return pages.home_page(sorted(assignment_dirs), _report_summaries())

    @app.post("/evaluate")
    def evaluate(assignment: str = Form(...), file: UploadFile = File(...)):
        target_dir = assignment_dirs.get(assignment)
        if target_dir is None:
            return PlainTextResponse(f"unknown assignment '{assignment}'", status_code=400)
        safe = _sanitize(file.filename or "submission.c")
        saved = uploads_dir / safe
        saved.write_bytes(file.file.read())
        loaded = load_rules(rules_path)
        models = load_models_config(models_path)
        report = evaluate_submission(
            saved,
            assignment_dir=target_dir,
            loaded_rules=loaded,
            models=models,
            cache_dir=cache_dir,
            corpus_dir=corpus_dir,
        )
        stem = saved.stem
        (reports_dir / f"{stem}.json").write_text(render_json(report))
        (reports_dir / f"{stem}.html").write_text(render_html(report))
        (reports_dir / f"{stem}.txt").write_text(render_txt(report))
        return RedirectResponse(url=f"/reports/{stem}", status_code=303)

    # NOTE: the .json/.txt routes are registered BEFORE /reports/{stem} so
    # "name.json" is never swallowed by the page route as a stem.
    @app.get("/reports/{stem}.json")
    def report_json(stem: str):
        report = _load_report(stem)
        if report is None:
            return PlainTextResponse("report not found", status_code=404)
        return JSONResponse(content=json.loads(render_json(report)))

    @app.get("/reports/{stem}.txt", response_class=PlainTextResponse)
    def report_txt(stem: str):
        report = _load_report(stem)
        if report is None:
            return PlainTextResponse("report not found", status_code=404)
        return render_txt(report)

    @app.get("/reports/{stem}", response_class=HTMLResponse)
    def report_page(stem: str):
        report = _load_report(stem)
        if report is None:
            return PlainTextResponse("report not found", status_code=404)
        return render_html(report)

    @app.get("/assignments", response_class=HTMLResponse)
    def assignments():
        entries = AssignmentCache(cache_dir).list_entries()
        return pages.assignments_page(entries, sorted(assignment_dirs))

    @app.post("/assignments/{assignment_id}/invalidate")
    def invalidate(assignment_id: str):
        AssignmentCache(cache_dir).invalidate(assignment_id)
        return RedirectResponse(url="/assignments", status_code=303)

    @app.get("/doctor", response_class=HTMLResponse)
    def doctor():
        report = run_doctor(models_path)
        return pages.doctor_page(json.dumps(report, indent=1, default=str))

    return app
