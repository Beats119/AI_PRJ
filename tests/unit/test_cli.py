"""CLI tests: validate-rules + doctor behave honestly on this machine."""

import json
from pathlib import Path

from autograder.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_validate_rules_example(capsys):
    code = main(["validate-rules", "--rules", str(ROOT / "configs" / "example_rules.yaml")])
    out = capsys.readouterr().out
    assert code == 0
    assert "Rules OK" in out
    assert "correctness" in out


def test_validate_rules_missing_file(capsys):
    code = main(["validate-rules", "--rules", str(ROOT / "configs" / "missing.yaml")])
    err = capsys.readouterr().err
    assert code == 2
    assert "ERROR" in err


def test_doctor_json(capsys):
    code = main(["doctor", "--json", "--models", str(ROOT / "configs" / "models.yaml")])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["gcc"]["found"] is True  # gcc exists on the dev/CI machines we target
    assert "configured_model" in out["ollama"]
    assert set(out["optional_tools"]) == {"gcc", "cppcheck", "valgrind", "perf", "lizard"} - {"gcc"}


def test_all_commands_are_implemented():
    # Stage 12 completed the command set: every subcommand now exists and
    # parses (benchmark with a real assignment is covered by its own
    # integration test; here we assert the parser knows all commands).
    from autograder.cli import build_parser

    parser = build_parser()
    actions = {a.dest: a for a in parser._subparsers._group_actions}
    choices = actions["command"].choices
    assert set(choices) == {
        "doctor", "validate-rules", "prepare-assignment", "evaluate",
        "cache", "benchmark", "serve",
    }
