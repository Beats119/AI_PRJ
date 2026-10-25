"""Batch + evaluation service (prompt §8.4/§8.5, Agent 5 coordinator).

Runs are durable: every state transition commits immediately. Evaluation
executes the real engine workflow per submission with the batch itself as
the similarity corpus (peers), then computes pairwise similarity
findings for the batch. A sandbox that cannot run (e.g. docker required
but absent) fails the run closed with the reason recorded — it never
falls back silently and never fabricates a result.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from autograder.analyzers.similarity import pairwise_similarities
from autograder.config.loader import load_models_config, load_rules
from autograder.db.models import (
    AssignmentVersion,
    EvaluationRun,
    EvidenceRecord,
    ScoreBreakdownRecord,
    SimilarityFinding,
    Submission,
    SubmissionBatch,
)
from autograder.sandbox.docker_runner import SandboxUnavailable
from autograder.services.assignments import DEFAULT_MODELS, ServiceError
from autograder.services.state_machine import IllegalTransition, transition
from autograder.workflow import evaluate_submission

MAX_FILE_BYTES = 1_000_000
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_batch(
    session,
    data_dir: Path,
    version: AssignmentVersion,
    files: list[tuple[str, bytes, str | None]],
) -> SubmissionBatch:
    if not files:
        raise ServiceError(["no files uploaded"])
    batch = SubmissionBatch(version_id=version.id, status="created")
    session.add(batch)
    session.commit()
    batch_dir = data_dir / "batches" / f"batch-{batch.id}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    seen_hashes: dict[str, int] = {}
    used_names: set[str] = set()
    for filename, content, label in files:
        if not filename.lower().endswith(".c"):
            raise ServiceError([f"{filename}: only .c files are submissions"])
        if len(content) > MAX_FILE_BYTES:
            raise ServiceError(
                [f"{filename}: exceeds the {MAX_FILE_BYTES} byte upload limit"]
            )
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        safe = _SAFE.sub("_", Path(filename).name) or "submission.c"
        stored_name = safe
        counter = 2
        while stored_name in used_names:
            stored_name = f"{Path(safe).stem}-{counter}{Path(safe).suffix}"
            counter += 1
        used_names.add(stored_name)
        is_duplicate = digest in seen_hashes
        # Exact duplicates are upload artifacts, not peer submissions:
        # they are stored OUTSIDE the batch corpus directory so they can
        # never trigger originality flags against their own original.
        stored = (batch_dir / "_duplicates" / stored_name) if is_duplicate else (
            batch_dir / stored_name
        )
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(content)
        sub = Submission(
            batch_id=batch.id,
            label=(label or Path(filename).stem),
            filename=filename,
            source_hash=digest,
            source_path=str(stored),
            status="duplicate" if is_duplicate else "stored",
            duplicate_of=seen_hashes.get(digest),
        )
        session.add(sub)
        session.commit()
        if digest not in seen_hashes:
            seen_hashes[digest] = sub.id
    return batch


def _flag_threshold(version: AssignmentVersion) -> float:
    try:
        rules = json.loads(version.rules_json)
        for m in rules.get("metrics", []):
            if m.get("name") == "originality":
                return float(m.get("params", {}).get("flag_threshold", 0.85))
    except Exception:
        pass
    return 0.85


def evaluate_batch(
    session,
    data_dir: Path,
    batch: SubmissionBatch,
    *,
    models_path: Path | None = None,
    backend: str | None = None,
) -> SubmissionBatch:
    version = session.get(AssignmentVersion, batch.version_id)
    pkg_dir = Path(version.package_dir)
    loaded = load_rules(pkg_dir / "rules.json")
    models = load_models_config(models_path or DEFAULT_MODELS)
    batch_dir = data_dir / "batches" / f"batch-{batch.id}"
    submissions = (
        session.query(Submission)
        .filter_by(batch_id=batch.id, status="stored")
        .order_by(Submission.id)
        .all()
    )
    batch.status = "evaluating"
    session.commit()
    for sub in submissions:
        run_one(
            session, data_dir, sub, version, backend=backend,
            _ctx=(pkg_dir, loaded, models, batch_dir),
        )
    # Pairwise similarity across the batch (peers), N(N-1)/2 pairs.
    sources = {
        sub.filename: Path(sub.source_path).read_text(errors="replace")
        for sub in submissions
    }
    by_name = {sub.filename: sub for sub in submissions}
    for pair in pairwise_similarities(sources, _flag_threshold(version)):
        if not pair["flagged"]:
            continue
        session.add(
            SimilarityFinding(
                batch_id=batch.id,
                submission_a=by_name[pair["a"]].id,
                submission_b=by_name[pair["b"]].id,
                score=pair["similarity"],
            )
        )
    batch.status = "completed"
    session.commit()
    return batch


def run_one(
    session,
    data_dir: Path,
    sub: Submission,
    version: AssignmentVersion,
    *,
    backend: str | None = None,
    retry_of: int | None = None,
    _ctx=None,
) -> EvaluationRun:
    """Create a queued run for one submission and execute it to a terminal
    state. Used by batch evaluation and by single-run retry."""
    if _ctx is None:
        pkg_dir = Path(version.package_dir)
        loaded = load_rules(pkg_dir / "rules.json")
        models = load_models_config(DEFAULT_MODELS)
        batch = session.get(SubmissionBatch, sub.batch_id)
        batch_dir = data_dir / "batches" / f"batch-{batch.id}"
        _ctx = (pkg_dir, loaded, models, batch_dir)
    pkg_dir, loaded, models, batch_dir = _ctx
    run = EvaluationRun(
        submission_id=sub.id, version_id=version.id, state="queued",
        retry_of_run_id=retry_of,
        config_json=json.dumps({"sandbox_backend": backend or "auto"}),
    )
    session.add(run)
    session.commit()
    _execute_run(
        session, data_dir, run, sub, version, pkg_dir, loaded, models,
        batch_dir, backend,
    )
    return run


def _execute_run(
    session, data_dir, run, sub, version, pkg_dir, loaded, models,
    batch_dir, backend,
) -> None:
    transition(session, run, "preparing")
    run.started_at = _now()
    session.commit()
    session.refresh(run)
    if run.cancel_requested:
        transition(session, run, "cancelled")
        run.ended_at = _now()
        session.commit()
        return

    def _progress(stage: str) -> None:
        try:
            session.refresh(run)
            if run.state != stage:
                transition(session, run, stage)
        except IllegalTransition:
            pass  # stage hints never break a real evaluation

    try:
        report = evaluate_submission(
            sub.source_path,
            assignment_dir=pkg_dir,
            loaded_rules=loaded,
            models=models,
            cache_dir=data_dir / "cache",
            corpus_dir=batch_dir,
            sandbox_backend=backend,
            progress=_progress,
        )
    except SandboxUnavailable as exc:
        run.error = f"sandbox unavailable (fail-closed): {exc}"
        transition(session, run, "failed")
        run.ended_at = _now()
        session.commit()
        return
    except Exception as exc:  # a run failure must not kill the batch
        run.error = f"{exc.__class__.__name__}: {exc}"
        transition(session, run, "failed")
        run.ended_at = _now()
        session.commit()
        return

    run.report_json = report.model_dump_json()
    run.grade = float(report.overall_grade) if report.overall_grade is not None else None
    run.overall_status = report.overall_status.value
    for result in report.metric_results:
        session.add(
            EvidenceRecord(
                run_id=run.id, kind=result.metric_name,
                payload_json=result.model_dump_json(),
            )
        )
    for item in report.execution_evidence:
        session.add(
            EvidenceRecord(
                run_id=run.id, kind=f"execution:{item.get('type', 'misc')}",
                payload_json=json.dumps(item, default=str),
            )
        )
    session.add(
        ScoreBreakdownRecord(
            run_id=run.id, total=run.grade,
            breakdown_json=json.dumps(
                [b.model_dump(mode="json") for b in report.score_breakdown]
            ),
        )
    )
    session.commit()
    final = "needs_review" if report.overall_status.value == "incomplete" else "completed"
    transition(session, run, final)
    run.ended_at = _now()
    session.commit()


_PASSED_RE = re.compile(r"(\d+)/(\d+) trusted tests pass")


def result_row(session, sub: Submission) -> dict:
    """One consolidated-results row for a submission (latest run)."""
    run = (
        session.query(EvaluationRun)
        .filter_by(submission_id=sub.id)
        .order_by(EvaluationRun.id.desc())
        .first()
    )
    row = {
        "submission_id": sub.id,
        "label": sub.label,
        "filename": sub.filename,
        "status": sub.status,
        "run_id": run.id if run else None,
        "run_state": run.state if run else None,
        "overall_status": run.overall_status if run else "",
        "grade": run.grade if run else None,
        "tests_passed": None,
        "tests_total": None,
        "compile_ok": None,
        "flags": [],
    }
    if run and run.report_json:
        report = json.loads(run.report_json)
        row["flags"] = report.get("flags", [])
        for result in report.get("metric_results", []):
            if result["metric_name"] == "correctness":
                m = _PASSED_RE.search(result.get("feedback", ""))
                if m:
                    row["tests_passed"] = int(m.group(1))
                    row["tests_total"] = int(m.group(2))
            if result["metric_name"] == "syntax":
                row["compile_ok"] = result["status"] != "error"
        if "compile_error" in row["flags"]:
            row["compile_ok"] = False
    return row
