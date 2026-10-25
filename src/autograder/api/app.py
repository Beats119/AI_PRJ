"""AutoGrader v2 API (prompt §10).

Thin HTTP layer over services/: all state transitions, grading and
similarity live in the services + engine; routes validate input, call a
service, and serialize. Errors are actionable JSON ({detail: {code,
message, problems?}}), never stack traces.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from autograder.config.loader import ConfigError, load_rules
from autograder.db.models import (
    Assignment,
    AssignmentVersion,
    EvaluationRun,
    SimilarityFinding,
    Submission,
    SubmissionBatch,
)
from autograder.db.session import default_data_dir, make_engine, make_session_factory
from autograder.models.report import EvaluationReport
from autograder.reports.render import render_html, render_json
from autograder.reports.render import render_txt as render_text
from autograder.sandbox.docker_runner import backend_status
from autograder.services import assignments as asvc
from autograder.services import evaluations as esvc
from autograder.services.assignments import ServiceError
from autograder.services.state_machine import transition


def _err(status: int, code: str, message: str, problems=None):
    detail: dict = {"code": code, "message": message}
    if problems:
        detail["problems"] = problems
    raise HTTPException(status_code=status, detail=detail)


class AssignmentIn(BaseModel):
    name: str


class VersionIn(BaseModel):
    problem: str
    input: str
    output: str
    constraints: list[str] | str | None = None
    boundary: str | None = None
    title: str | None = None
    assignment_slug: str | None = None
    generator: str = "int_pair_v1"
    comparison: str = "whitespace_normalized"
    input_min: int | None = None
    input_max: int | None = None
    invalid_input_behavior: str | None = None
    examples: list[dict] = Field(default_factory=list)
    rules: dict


class RulesIn(BaseModel):
    rules: dict


class EvaluateIn(BaseModel):
    sandbox_backend: str | None = None


class DispositionIn(BaseModel):
    status: str  # confirmed_concern | dismissed | pending
    note: str = ""


def _version_dict(v: AssignmentVersion) -> dict:
    return {
        "id": v.id,
        "assignment_id": v.assignment_id,
        "version_no": v.version_no,
        "status": v.status,
        "rules_hash": v.rules_hash,
        "rules": json.loads(v.rules_json),
        "spec": json.loads(v.spec_json),
        "suite": json.loads(v.suite_json),
        "sufficiency": json.loads(v.sufficiency_json),
        "unresolved": json.loads(v.unresolved_json),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def create_api_app(
    data_dir: Path | None = None,
    db_url: str | None = None,
    models_path: Path | None = None,
) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(db_url, data_dir)
    factory = make_session_factory(engine)

    app = FastAPI(title="AutoGrader API", version="2.0")
    app.state.data_dir = data_dir
    app.state.models_path = models_path

    def get_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    # -- health ------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/health/dependencies")
    def dependencies():
        gcc = shutil.which("gcc")
        gcc_version = None
        if gcc:
            out = subprocess.run(
                ["gcc", "--version"], capture_output=True, text=True,
                timeout=10, check=False,
            )
            gcc_version = out.stdout.splitlines()[0] if out.stdout else None
        return {
            "app": "ok",
            "database": "ok (sqlite)",
            "gcc": gcc_version or "not found",
            "sandbox": backend_status(),
            "ollama": _ollama_status(),
            "data_dir": str(data_dir),
        }

    @app.get("/api/settings/model-status")
    def model_status():
        return _ollama_status()

    # -- assignments ---------------------------------------------------------
    @app.post("/api/assignments", status_code=201)
    def create_assignment(body: AssignmentIn, session=Depends(get_session)):
        try:
            row = asvc.create_assignment(session, body.name)
        except ServiceError as exc:
            _err(400, "invalid_assignment", str(exc), exc.problems)
        return {"id": row.id, "name": row.name}

    @app.get("/api/assignments")
    def list_assignments(session=Depends(get_session)):
        out = []
        for a in session.query(Assignment).order_by(Assignment.id).all():
            versions = (
                session.query(AssignmentVersion)
                .filter_by(assignment_id=a.id)
                .order_by(AssignmentVersion.version_no)
                .all()
            )
            out.append(
                {
                    "id": a.id,
                    "name": a.name,
                    "versions": [
                        {
                            "id": v.id, "version_no": v.version_no,
                            "status": v.status,
                            "trusted_tests": len(json.loads(v.suite_json)),
                        }
                        for v in versions
                    ],
                }
            )
        return out

    @app.get("/api/assignments/{assignment_id}")
    def get_assignment(assignment_id: int, session=Depends(get_session)):
        a = session.get(Assignment, assignment_id)
        if a is None:
            _err(404, "not_found", f"assignment {assignment_id} not found")
        versions = (
            session.query(AssignmentVersion)
            .filter_by(assignment_id=a.id)
            .order_by(AssignmentVersion.version_no)
            .all()
        )
        return {
            "id": a.id, "name": a.name,
            "versions": [_version_dict(v) for v in versions],
        }

    @app.post("/api/assignments/{assignment_id}/versions", status_code=201)
    def create_version(
        assignment_id: int, body: VersionIn, session=Depends(get_session)
    ):
        a = session.get(Assignment, assignment_id)
        if a is None:
            _err(404, "not_found", f"assignment {assignment_id} not found")
        try:
            v = asvc.create_version(
                session, data_dir, a, body.model_dump(),
                models_path=models_path,
            )
        except ServiceError as exc:
            _err(400, "invalid_version", str(exc), exc.problems)
        return _version_dict(v)

    @app.post("/api/assignments/{assignment_id}/versions/{version_id}/activate")
    def activate(
        assignment_id: int, version_id: int, session=Depends(get_session)
    ):
        v = session.get(AssignmentVersion, version_id)
        if v is None or v.assignment_id != assignment_id:
            _err(404, "not_found", "version not found")
        try:
            asvc.activate_version(session, v)
        except ServiceError as exc:
            _err(409, "cannot_activate", str(exc), exc.problems)
        return _version_dict(v)

    @app.post("/api/assignments/validate-rules")
    def validate_rules(body: RulesIn):
        tmp = data_dir / f"validate-{uuid.uuid4().hex[:8]}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            path = tmp / "rules.json"
            path.write_text(json.dumps(body.rules))
            try:
                loaded = load_rules(path)
            except ConfigError as exc:
                return {"valid": False, "problems": exc.problems}
            return {"valid": True, "problems": [], "rules_hash": loaded.rules_hash}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @app.get("/api/examples/add-two-integers")
    def example_payload():
        """The shipped worked example, as a create-version payload."""
        import yaml as _yaml

        root = Path(__file__).resolve().parents[3]
        pkg = root / "examples" / "assignments" / "add_two_integers"
        rules = _yaml.safe_load(
            (root / "configs" / "example_rules.yaml").read_text()
        )
        tests = _yaml.safe_load((pkg / "tests.yaml").read_text())
        return {
            "problem": "Read two integers and print their sum.",
            "input": "Two integers on one line separated by whitespace.",
            "output": "The mathematically correct sum followed by a newline.",
            "constraints": [
                "Operands are signed 32-bit integers.",
                "The sum may exceed 32 bits and must still be correct.",
            ],
            "examples": tests["tests"],
            "rules": rules,
        }

    # -- batches / submissions ----------------------------------------------
    @app.post("/api/batches", status_code=201)
    async def create_batch(
        version_id: int = Form(...),
        labels: str | None = Form(None),
        files: list[UploadFile] = File(...),
        session=Depends(get_session),
    ):
        version = session.get(AssignmentVersion, version_id)
        if version is None:
            _err(404, "not_found", f"version {version_id} not found")
        if version.status not in ("active", "validated"):
            _err(
                409, "version_not_ready",
                f"version is '{version.status}'; only validated/active "
                "versions can receive submissions",
            )
        label_list = json.loads(labels) if labels else []
        payload = []
        for i, f in enumerate(files):
            content = await f.read()
            payload.append(
                (f.filename or f"file-{i}.c", content,
                 label_list[i] if i < len(label_list) else None)
            )
        try:
            batch = esvc.create_batch(session, data_dir, version, payload)
        except ServiceError as exc:
            _err(400, "invalid_batch", str(exc), exc.problems)
        return _batch_dict(session, batch)

    @app.get("/api/batches/{batch_id}")
    def get_batch(batch_id: int, session=Depends(get_session)):
        batch = session.get(SubmissionBatch, batch_id)
        if batch is None:
            _err(404, "not_found", f"batch {batch_id} not found")
        return _batch_dict(session, batch)

    @app.get("/api/batches")
    def list_batches(session=Depends(get_session)):
        return [
            {
                "id": b.id, "version_id": b.version_id, "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "submissions": session.query(Submission)
                .filter_by(batch_id=b.id).count(),
            }
            for b in session.query(SubmissionBatch)
            .order_by(SubmissionBatch.id.desc()).all()
        ]

    @app.post("/api/batches/{batch_id}/evaluate")
    def evaluate(batch_id: int, body: EvaluateIn, session=Depends(get_session)):
        batch = session.get(SubmissionBatch, batch_id)
        if batch is None:
            _err(404, "not_found", f"batch {batch_id} not found")
        esvc.evaluate_batch(
            session, data_dir, batch, models_path=models_path,
            backend=body.sandbox_backend,
        )
        return _batch_dict(session, batch)

    # -- evaluations ---------------------------------------------------------
    @app.get("/api/evaluations/{run_id}")
    def get_run(run_id: int, session=Depends(get_session)):
        run = session.get(EvaluationRun, run_id)
        if run is None:
            _err(404, "not_found", f"run {run_id} not found")
        return _run_dict(session, run)

    @app.get("/api/evaluations")
    def list_runs(session=Depends(get_session)):
        return [
            {
                "id": r.id, "submission_id": r.submission_id,
                "version_id": r.version_id, "state": r.state,
                "overall_status": r.overall_status, "grade": r.grade,
                "retry_of_run_id": r.retry_of_run_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            }
            for r in session.query(EvaluationRun)
            .order_by(EvaluationRun.id.desc()).limit(200)
        ]

    @app.post("/api/evaluations/{run_id}/cancel")
    def cancel_run(run_id: int, session=Depends(get_session)):
        run = session.get(EvaluationRun, run_id)
        if run is None:
            _err(404, "not_found", f"run {run_id} not found")
        run.cancel_requested = True
        session.commit()
        if run.state in ("queued", "preparing"):
            transition(session, run, "cancelled")
        return {"id": run.id, "state": run.state, "cancel_requested": True}

    @app.post("/api/evaluations/{run_id}/retry", status_code=201)
    def retry_run(run_id: int, body: EvaluateIn, session=Depends(get_session)):
        old = session.get(EvaluationRun, run_id)
        if old is None:
            _err(404, "not_found", f"run {run_id} not found")
        sub = session.get(Submission, old.submission_id)
        version = session.get(AssignmentVersion, old.version_id)
        run = esvc.run_one(
            session, data_dir, sub, version,
            backend=body.sandbox_backend, retry_of=old.id,
        )
        return _run_dict(session, run)

    # -- submission detail / report ------------------------------------------
    @app.get("/api/submissions/{submission_id}")
    def get_submission(submission_id: int, session=Depends(get_session)):
        sub = session.get(Submission, submission_id)
        if sub is None:
            _err(404, "not_found", f"submission {submission_id} not found")
        source = Path(sub.source_path).read_text(errors="replace")
        return {
            "id": sub.id, "batch_id": sub.batch_id, "label": sub.label,
            "filename": sub.filename, "source_hash": sub.source_hash,
            "status": sub.status, "source": source,
            "result": esvc.result_row(session, sub),
        }

    @app.get("/api/submissions/{submission_id}/report")
    def get_report(
        submission_id: int, format: str = "json", session=Depends(get_session)
    ):
        sub = session.get(Submission, submission_id)
        if sub is None:
            _err(404, "not_found", f"submission {submission_id} not found")
        run = (
            session.query(EvaluationRun)
            .filter_by(submission_id=sub.id)
            .order_by(EvaluationRun.id.desc())
            .first()
        )
        if run is None or not run.report_json:
            _err(404, "no_report", "no completed report for this submission")
        report = EvaluationReport.model_validate_json(run.report_json)
        if format == "html":
            return PlainTextResponse(render_html(report), media_type="text/html")
        if format == "txt":
            return PlainTextResponse(render_text(report), media_type="text/plain")
        return PlainTextResponse(render_json(report), media_type="application/json")

    # -- similarity ------------------------------------------------------------
    @app.get("/api/similarity")
    def list_similarity(batch_id: int | None = None, session=Depends(get_session)):
        q = session.query(SimilarityFinding)
        if batch_id is not None:
            q = q.filter_by(batch_id=batch_id)
        out = []
        for f in q.order_by(SimilarityFinding.score.desc()).all():
            a = session.get(Submission, f.submission_a)
            b = session.get(Submission, f.submission_b)
            out.append(
                {
                    "id": f.id, "batch_id": f.batch_id,
                    "a": {"id": a.id, "label": a.label, "filename": a.filename},
                    "b": {"id": b.id, "label": b.label, "filename": b.filename},
                    "score": f.score, "method": f.method,
                    "review_status": f.review_status,
                    "disposition_note": f.disposition_note,
                }
            )
        return out

    @app.post("/api/similarity/{finding_id}/disposition")
    def disposition(
        finding_id: int, body: DispositionIn, session=Depends(get_session)
    ):
        f = session.get(SimilarityFinding, finding_id)
        if f is None:
            _err(404, "not_found", f"finding {finding_id} not found")
        if body.status not in ("confirmed_concern", "dismissed", "pending"):
            _err(400, "invalid_status", f"unknown disposition '{body.status}'")
        # A disposition NEVER changes a grade: it only records the review.
        f.review_status = body.status
        f.disposition_note = body.note
        session.commit()
        return {"id": f.id, "review_status": f.review_status}

    return app


def _ollama_status() -> dict:
    import os
    import urllib.request

    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        return {
            "base_url": base, "model": model, "reachable": True,
            "model_available": any(n.startswith(model) for n in names),
            "note": "LLM use is bounded + advisory surfaces only; the "
                    "deterministic pipeline works without it",
        }
    except Exception as exc:
        return {
            "base_url": base, "model": model, "reachable": False,
            "model_available": False,
            "note": f"unreachable ({exc.__class__.__name__}); deterministic "
                    "mode continues normally",
        }


def _batch_dict(session, batch: SubmissionBatch) -> dict:
    subs = (
        session.query(Submission)
        .filter_by(batch_id=batch.id)
        .order_by(Submission.id)
        .all()
    )
    return {
        "id": batch.id, "version_id": batch.version_id, "status": batch.status,
        "submissions": [esvc.result_row(session, s) for s in subs],
    }


def _run_dict(session, run: EvaluationRun) -> dict:
    from autograder.db.models import EvidenceRecord, ScoreBreakdownRecord

    evidence = (
        session.query(EvidenceRecord).filter_by(run_id=run.id).all()
    )
    breakdown = (
        session.query(ScoreBreakdownRecord).filter_by(run_id=run.id).first()
    )
    return {
        "id": run.id, "submission_id": run.submission_id,
        "version_id": run.version_id, "state": run.state,
        "overall_status": run.overall_status, "grade": run.grade,
        "error": run.error, "retry_of_run_id": run.retry_of_run_id,
        "report": json.loads(run.report_json) if run.report_json else None,
        "evidence": [
            {"kind": e.kind, "payload": json.loads(e.payload_json)}
            for e in evidence
        ],
        "breakdown": json.loads(breakdown.breakdown_json) if breakdown else [],
    }
