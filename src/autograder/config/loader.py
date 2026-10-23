"""Load + validate rules / model config files; compute canonical hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from autograder.config.schema import ModelsConfig, Rules


class ConfigError(Exception):
    """An actionable configuration problem (never a silent default)."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class LoadedRules:
    def __init__(self, rules: Rules, source_path: Path, rules_hash: str):
        self.rules = rules
        self.source_path = source_path
        self.rules_hash = rules_hash


def _read_structured(path: Path) -> object:
    if not path.exists():
        raise ConfigError([f"file not found: {path}"])
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except Exception as exc:  # parse error: report it, don't guess
        raise ConfigError([f"could not parse {path}: {exc}"]) from exc


def _validate(model_cls, data: object, label: str):
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        problems = [
            f"{label}: {'/'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        ]
        raise ConfigError(problems) from exc


def canonical_hash(data: object) -> str:
    """Stable SHA-256 over a canonical JSON rendering (sorted keys)."""
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_rules(path: str | Path) -> LoadedRules:
    path = Path(path)
    data = _read_structured(path)
    if not isinstance(data, dict):
        raise ConfigError([f"{path}: top level must be a mapping"])
    rules = _validate(Rules, data, str(path))
    digest = canonical_hash(rules.model_dump(mode="json"))
    return LoadedRules(rules=rules, source_path=path, rules_hash=digest)


def load_models_config(path: str | Path) -> ModelsConfig:
    data = _read_structured(Path(path))
    if not isinstance(data, dict):
        raise ConfigError([f"{path}: top level must be a mapping"])
    return _validate(ModelsConfig, data, str(path))
