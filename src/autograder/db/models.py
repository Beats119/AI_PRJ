"""SQLAlchemy models (prompt §9). SQLite for the single-instance app.

JSON columns hold versioned payloads (spec, suite, report, breakdown);
large artifacts (stored sources, rendered reports) live under the app
data directory, never at user-supplied paths.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AssignmentVersion(Base):
    __tablename__ = "assignment_versions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "version_no", name="uq_assignment_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    # draft | validated | active | superseded  (validated = D-1 bar met)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    problem_statement: Mapped[str] = mapped_column(Text)
    rules_json: Mapped[str] = mapped_column(Text)
    rules_hash: Mapped[str] = mapped_column(String(80), default="")
    spec_json: Mapped[str] = mapped_column(Text, default="{}")
    suite_json: Mapped[str] = mapped_column(Text, default="[]")
    sufficiency_json: Mapped[str] = mapped_column(Text, default="{}")
    unresolved_json: Mapped[str] = mapped_column(Text, default="[]")
    package_dir: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SubmissionBatch(Base):
    __tablename__ = "submission_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_versions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("submission_batches.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(300))
    source_hash: Mapped[str] = mapped_column(String(80), index=True)
    source_path: Mapped[str] = mapped_column(Text)
    # stored | duplicate
    status: Mapped[str] = mapped_column(String(20), default="stored")
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id"), index=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("assignment_versions.id"))
    state: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_of_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    overall_status: Mapped[str] = mapped_column(String(24), default="")
    grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[str] = mapped_column(Text, default="")


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60))  # metric name / profile / timings
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ScoreBreakdownRecord(Base):
    __tablename__ = "score_breakdowns"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id"), unique=True, index=True
    )
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakdown_json: Mapped[str] = mapped_column(Text, default="[]")
    scoring_policy: Mapped[str] = mapped_column(String(40), default="d3-v1")


class SimilarityFinding(Base):
    __tablename__ = "similarity_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("submission_batches.id"), index=True
    )
    submission_a: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    submission_b: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(80), default="shingle-jaccard-v1")
    # pending | confirmed_concern | dismissed
    review_status: Mapped[str] = mapped_column(String(24), default="pending")
    disposition_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(60))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
