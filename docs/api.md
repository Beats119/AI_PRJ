# API reference (v2)

Base: same origin as the dashboard (`autograder api`, default
`http://127.0.0.1:8000`). Errors are JSON:
`{"detail": {"code": "...", "message": "...", "problems": [...]}}`.

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness |
| `GET /api/health/dependencies` | gcc, database, sandbox backend status (docker availability reported honestly), ollama, data dir |
| `GET /api/settings/model-status` | configured Ollama base URL/model + reachability |
| `GET /api/examples/add-two-integers` | the shipped worked example as a create-version payload |
| `POST /api/assignments` | create assignment `{name}` |
| `GET /api/assignments` / `GET /api/assignments/{id}` | list / detail with versions |
| `POST /api/assignments/{id}/versions` | create version (problem/input/output/examples/rules) → runs real preparation; returns spec, suite with validation states, sufficiency evidence, unresolved items |
| `POST /api/assignments/{id}/versions/{vid}/activate` | activate a validated version (409 for drafts) |
| `POST /api/assignments/validate-rules` | validate a rules document alone; returns located problems |
| `POST /api/batches` | multipart upload (`version_id`, `files[]`, optional `labels` JSON) → batch with per-file status incl. duplicates |
| `GET /api/batches` / `GET /api/batches/{id}` | list / batch + consolidated result rows |
| `POST /api/batches/{id}/evaluate` | evaluate all stored submissions (`{sandbox_backend}` optional) |
| `GET /api/evaluations` / `GET /api/evaluations/{id}` | runs list / run detail (report, evidence, breakdown) |
| `POST /api/evaluations/{id}/cancel` | request cancellation (queued/preparing → cancelled) |
| `POST /api/evaluations/{id}/retry` | new run linked via `retry_of_run_id`, executed immediately |
| `GET /api/submissions/{id}` | submission + source + latest result row |
| `GET /api/submissions/{id}/report?format=json\|html\|txt` | canonical report download |
| `GET /api/similarity?batch_id=` | flagged pairs for review |
| `POST /api/similarity/{id}/disposition` | record `confirmed_concern` / `dismissed` / `pending` + note (never changes grades) |
