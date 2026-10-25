"""SQLite persistence for AutoGrader v2 (master prompt §9).

The grading engine (assignment/, analyzers/, scoring/, workflow.py) is
unchanged and file-based; this layer stores the product state around it:
assignments and their immutable versions, batches, submissions, durable
evaluation runs with an explicit state machine, evidence, score
breakdowns, similarity findings, reports and audit events.
"""
