"""AutoGrader web UI (Stage 11): a second front door to the same engine.

The UI never grades anything itself: every evaluation goes through
autograder.workflow.evaluate_submission and every page renders the same
canonical EvaluationReport the CLI writes, so a UI grade and a CLI grade
for the same inputs are identical by construction (and by test).
"""
