"""Persistent, versioned assignment cache (Stage 7).

Stores assignment-level artifacts ONLY: the specification and the validated
trusted test suite. Student grades and execution results are never cached.

Entry layout:  <root>/<key>/{spec.json, suite.json, metadata.json}
metadata.json carries SHA-256 integrity hashes of both payload files, the
schema version, and the full key material (rules/model/generator/oracle
versions) for provenance.

Safety properties (all covered by tests):
  * atomic persistence: an entry is built in a temp directory on the same
    filesystem and renamed into place; an interrupted write can never
    destroy a previously valid entry
  * a valid existing entry is NEVER overwritten by a regeneration
  * integrity + schema + compatibility are re-verified on every load;
    corrupt entries are rejected (and quarantined on the next store)
  * a file lock serializes store/lookup critical sections across processes
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from autograder.models.assignment import AssignmentSpec
from autograder.models.tests import TestCase

CACHE_SCHEMA_VERSION = 1


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class CacheEntry:
    key: str
    spec: AssignmentSpec
    suite: list[TestCase]
    metadata: dict


@dataclass
class CacheLookup:
    kind: str  # "hit" | "miss" | "corrupt"
    entry: CacheEntry | None = None
    detail: str = ""


class AssignmentCache:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.root / ".lock"

    # -- internal helpers -------------------------------------------------
    def _locked(self):
        class _Lock:
            def __init__(self, path: Path):
                self._fh = path.open("a+")

            def __enter__(self):
                fcntl.flock(self._fh, fcntl.LOCK_EX)
                return self

            def __exit__(self, *exc):
                fcntl.flock(self._fh, fcntl.LOCK_UN)
                self._fh.close()

        return _Lock(self._lock_path)

    def _read_entry(self, key: str) -> CacheLookup:
        entry_dir = self.root / key
        if not entry_dir.is_dir():
            return CacheLookup("miss", detail="no entry for this key")
        try:
            metadata = json.loads((entry_dir / "metadata.json").read_text())
            spec_bytes = (entry_dir / "spec.json").read_bytes()
            suite_bytes = (entry_dir / "suite.json").read_bytes()
        except Exception as exc:
            return CacheLookup("corrupt", detail=f"unreadable entry: {exc}")
        if metadata.get("schema_version") != CACHE_SCHEMA_VERSION:
            return CacheLookup(
                "corrupt",
                detail=f"schema_version {metadata.get('schema_version')} "
                f"!= {CACHE_SCHEMA_VERSION}",
            )
        if metadata.get("key") != key:
            return CacheLookup("corrupt", detail="metadata key does not match directory")
        integrity = metadata.get("integrity", {})
        if integrity.get("spec_sha256") != _sha(spec_bytes):
            return CacheLookup("corrupt", detail="spec.json integrity hash mismatch")
        if integrity.get("suite_sha256") != _sha(suite_bytes):
            return CacheLookup("corrupt", detail="suite.json integrity hash mismatch")
        try:
            spec = AssignmentSpec.model_validate_json(spec_bytes)
            suite = [TestCase.model_validate(t) for t in json.loads(suite_bytes)]
        except Exception as exc:
            return CacheLookup("corrupt", detail=f"payload failed validation: {exc}")
        return CacheLookup("hit", entry=CacheEntry(key, spec, suite, metadata))

    # -- public API --------------------------------------------------------
    def lookup(self, key: str) -> CacheLookup:
        with self._locked():
            return self._read_entry(key)

    def store(
        self,
        key: str,
        spec: AssignmentSpec,
        suite: list[TestCase],
        metadata_extra: dict,
    ) -> CacheLookup:
        """Persist an entry atomically. Never overwrites a valid entry."""
        with self._locked():
            existing = self._read_entry(key)
            if existing.kind == "hit":
                return existing  # valid entry wins; regeneration is discarded
            entry_dir = self.root / key
            if existing.kind == "corrupt" and entry_dir.exists():
                quarantine = self.root / "quarantine"
                quarantine.mkdir(exist_ok=True)
                target = quarantine / f"{key}-{len(list(quarantine.iterdir()))}"
                shutil.move(str(entry_dir), str(target))
            spec_bytes = spec.model_dump_json(indent=1).encode()
            suite_bytes = json.dumps(
                [t.model_dump(mode="json") for t in suite], indent=1
            ).encode()
            metadata = {
                "key": key,
                "assignment_id": spec.assignment_id,
                "schema_version": CACHE_SCHEMA_VERSION,
                "integrity": {
                    "spec_sha256": _sha(spec_bytes),
                    "suite_sha256": _sha(suite_bytes),
                },
                **metadata_extra,
            }
            tmp = Path(tempfile.mkdtemp(prefix=".tmp-entry-", dir=self.root))
            try:
                (tmp / "spec.json").write_bytes(spec_bytes)
                (tmp / "suite.json").write_bytes(suite_bytes)
                (tmp / "metadata.json").write_text(json.dumps(metadata, indent=1))
                os.rename(tmp, entry_dir)  # atomic on the same filesystem
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            return self._read_entry(key)

    def list_entries(self) -> list[dict]:
        out = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or child.name.startswith((".tmp", "quarantine")):
                continue
            look = self._read_entry(child.name)
            if look.kind == "hit" and look.entry:
                md = look.entry.metadata
                out.append(
                    {
                        "key": child.name,
                        "assignment_id": md.get("assignment_id"),
                        "trusted_tests": sum(
                            1 for t in look.entry.suite if t.counts_as_trusted
                        ),
                        "schema_version": md.get("schema_version"),
                    }
                )
            else:
                out.append({"key": child.name, "status": look.kind, "detail": look.detail})
        return out

    def invalidate(self, assignment_id: str) -> int:
        """Remove every entry for an assignment id. Returns how many."""
        removed = 0
        with self._locked():
            for child in list(self.root.iterdir()):
                if not child.is_dir() or child.name.startswith((".tmp", "quarantine")):
                    continue
                try:
                    md = json.loads((child / "metadata.json").read_text())
                except Exception:
                    continue
                if md.get("assignment_id") == assignment_id:
                    shutil.rmtree(child)
                    removed += 1
        return removed
