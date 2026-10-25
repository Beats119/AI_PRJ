"""Assignment + version service (prompt §8.3, Agent 1 behind it).

A version is materialized as an engine assignment package on disk
(assignment.md / spec.yaml / tests.yaml / rules.json) under the app data
dir, then prepared with the REAL engine (spec build, bounded generation,
oracle-v2 verification, D-1 sufficiency). Activation is gated: a version
whose suite is below the sufficiency bar stays a draft and can never be
activated, so unverified tests can never become score-affecting through
the UI.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from autograder.assignment import prepare_assignment
from autograder.config.loader import ConfigError, load_models_config, load_rules
from autograder.db.models import Assignment, AssignmentVersion, AuditEvent

DEFAULT_MODELS = Path("configs/models.yaml")


class ServiceError(RuntimeError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _audit(session, entity, entity_id, action, detail=None):
    session.add(
        AuditEvent(
            entity=entity, entity_id=entity_id, action=action,
            detail_json=json.dumps(detail or {}),
        )
    )


def create_assignment(session, name: str) -> Assignment:
    row = Assignment(name=name.strip())
    if not row.name:
        raise ServiceError(["assignment name must not be empty"])
    session.add(row)
    session.commit()
    _audit(session, "assignment", row.id, "created", {"name": row.name})
    session.commit()
    return row


def _render_markdown(payload: dict) -> str:
    def section(title: str, body: str) -> str:
        return f"## {title}\n\n{body.strip()}\n"

    parts = [f"# {payload.get('title', 'Assignment')}\n"]
    parts.append(section("Problem", payload["problem"]))
    parts.append(section("Input", payload["input"]))
    parts.append(section("Output", payload["output"]))
    constraints = payload.get("constraints") or []
    if isinstance(constraints, str):
        constraints = [c for c in constraints.splitlines() if c.strip()]
    if constraints:
        parts.append(
            section("Constraints", "\n".join(f"- {c}" for c in constraints))
        )
    if payload.get("boundary"):
        parts.append(section("Boundary", payload["boundary"]))
    return "\n".join(parts)


def create_version(
    session,
    data_dir: Path,
    assignment: Assignment,
    payload: dict,
    models_path: Path | None = None,
) -> AssignmentVersion:
    """payload: problem/input/output (+constraints, boundary, generator,
    comparison, input_min/max, invalid_input_behavior), examples[], rules{}"""
    for field_name in ("problem", "input", "output", "rules"):
        if not payload.get(field_name):
            raise ServiceError([f"missing required field: {field_name}"])
    existing = (
        session.query(AssignmentVersion)
        .filter_by(assignment_id=assignment.id)
        .count()
    )
    version_no = existing + 1
    pkg_dir = data_dir / "packages" / f"assignment-{assignment.id}" / f"v{version_no}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "assignment.md").write_text(_render_markdown(payload))
    spec = {
        "assignment_id": payload.get("assignment_slug")
        or f"assignment-{assignment.id}-v{version_no}",
        "generator": payload.get("generator", "int_pair_v1"),
        "comparison": payload.get("comparison", "whitespace_normalized"),
        "input_min": payload.get("input_min"),
        "input_max": payload.get("input_max"),
        "invalid_input_behavior": payload.get("invalid_input_behavior"),
    }
    (pkg_dir / "spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    examples = payload.get("examples") or []
    if examples:
        (pkg_dir / "tests.yaml").write_text(
            yaml.safe_dump({"tests": examples}, sort_keys=False)
        )
    rules_path = pkg_dir / "rules.json"
    rules_path.write_text(json.dumps(payload["rules"], indent=1))
    try:
        loaded = load_rules(rules_path)
    except ConfigError as exc:
        raise ServiceError([f"rules: {p}" for p in exc.problems]) from exc

    models = load_models_config(models_path or DEFAULT_MODELS)
    prep = prepare_assignment(
        pkg_dir, loaded, models, data_dir / "cache"
    )
    version = AssignmentVersion(
        assignment_id=assignment.id,
        version_no=version_no,
        status="validated" if prep.status != "insufficient_evidence" else "draft",
        problem_statement=(pkg_dir / "assignment.md").read_text(),
        rules_json=json.dumps(payload["rules"], indent=1),
        rules_hash=loaded.rules_hash,
        spec_json=prep.spec.model_dump_json(),
        suite_json=json.dumps(
            [t.model_dump(mode="json") for t in (prep.suite or [])]
        ),
        sufficiency_json=json.dumps(prep.sufficiency or {}),
        unresolved_json=json.dumps(
            list(prep.spec.unresolved_questions)
            + [
                d for d in prep.diagnostics
                if "insufficient" in d or "below the D-1" in d
            ]
        ),
        package_dir=str(pkg_dir),
    )
    session.add(version)
    session.commit()
    _audit(
        session, "assignment_version", version.id, "created",
        {"version_no": version_no, "status": version.status,
         "prepare_status": prep.status},
    )
    session.commit()
    return version


def activate_version(session, version: AssignmentVersion) -> AssignmentVersion:
    if version.status == "draft":
        raise ServiceError(
            [
                (
                    "this version is a draft: its trusted suite is below the "
                    "sufficiency bar, so it cannot be activated (unverified "
                    "tests must never become score-affecting)"
                )
            ]
        )
    for other in (
        session.query(AssignmentVersion)
        .filter_by(assignment_id=version.assignment_id, status="active")
        .all()
    ):
        other.status = "superseded"
    version.status = "active"
    session.commit()
    _audit(session, "assignment_version", version.id, "activated", {})
    session.commit()
    return version
