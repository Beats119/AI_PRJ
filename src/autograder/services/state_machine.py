"""Evaluation-run lifecycle (prompt §3, Agent 5).

Explicit states and legal transitions; anything else raises
IllegalTransition. Every transition is audit-logged and committed
immediately, so a page refresh (or a process restart) always shows a
trustworthy state — an interrupted run is left in its last persisted
state, never silently marked completed.
"""

from __future__ import annotations

import json

from autograder.db.models import AuditEvent, EvaluationRun

STATES = (
    "queued", "preparing", "compiling", "testing", "analyzing",
    "validating_evidence", "scoring", "reporting",
    "completed", "needs_review", "failed", "cancelled",
)

LEGAL: dict[str, set[str]] = {
    "queued": {"preparing", "cancelled", "failed"},
    "preparing": {"compiling", "failed", "cancelled", "needs_review"},
    "compiling": {"testing", "analyzing", "failed", "cancelled"},
    "testing": {"analyzing", "failed", "cancelled"},
    "analyzing": {"validating_evidence", "failed", "cancelled"},
    "validating_evidence": {"scoring", "failed"},
    "scoring": {"reporting", "failed"},
    "reporting": {"completed", "needs_review", "failed"},
    "completed": set(),
    "needs_review": set(),
    "failed": set(),
    "cancelled": set(),
}

TERMINAL = {"completed", "needs_review", "failed", "cancelled"}


class IllegalTransition(RuntimeError):
    pass


def transition(session, run: EvaluationRun, to_state: str) -> EvaluationRun:
    if to_state == run.state:
        return run
    if to_state not in LEGAL.get(run.state, set()):
        raise IllegalTransition(f"{run.state} -> {to_state} is not a legal transition")
    from_state = run.state
    run.state = to_state
    session.add(
        AuditEvent(
            entity="evaluation_run",
            entity_id=run.id,
            action="state_transition",
            detail_json=json.dumps({"from": from_state, "to": to_state}),
        )
    )
    session.commit()
    return run
