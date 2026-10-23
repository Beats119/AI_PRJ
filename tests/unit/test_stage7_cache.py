"""Stage 7 cache tests: hit/miss, invalidation, corruption, atomicity,
concurrency, and the failed-regeneration guarantee."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autograder.assignment.cache import AssignmentCache
from autograder.assignment.oracle import verify_candidates
from autograder.assignment.specification import build_spec, load_assignment_package
from autograder.assignment.test_generation import generate_candidates
from autograder.config.loader import load_rules

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignments" / "add_two_integers"


def _suite():
    pkg = load_assignment_package(EXAMPLE)
    spec = build_spec(pkg)
    rules = load_rules(ROOT / "configs" / "example_rules.yaml").rules
    candidates, _ = generate_candidates(pkg, rules.generation)
    result = verify_candidates(candidates, pkg, spec, rules.sufficiency)
    return spec, result.suite


@pytest.fixture(scope="module")
def built():
    return _suite()


def test_store_then_lookup_is_a_hit(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    stored = cache.store("k1", spec, suite, {})
    assert stored.entry is not None
    look = cache.lookup("k1")
    assert look.kind == "hit"
    assert look.entry.spec.specification_hash == spec.specification_hash
    assert len(look.entry.suite) == len(suite)
    assert cache.lookup("nope").kind == "miss"


def test_store_never_overwrites_a_valid_entry(tmp_path, built):
    """A failed/mistaken regeneration cannot destroy a valid cached suite."""
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("k1", spec, suite, {})
    truncated = suite[:2]
    again = cache.store("k1", spec, truncated, {})
    assert len(again.entry.suite) == len(suite)  # original intact


def test_corrupt_payload_is_rejected_then_quarantined(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("k1", spec, suite, {})
    suite_file = tmp_path / "k1" / "suite.json"
    data = bytearray(suite_file.read_bytes())
    data[10] ^= 0xFF
    suite_file.write_bytes(bytes(data))
    look = cache.lookup("k1")
    assert look.kind == "corrupt"
    assert "integrity" in look.detail
    # a fresh store quarantines the corrupt entry and installs a valid one
    restored = cache.store("k1", spec, suite, {})
    assert restored.entry is not None
    assert cache.lookup("k1").kind == "hit"
    assert (tmp_path / "quarantine").exists()


def test_schema_version_mismatch_is_rejected(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("k1", spec, suite, {})
    meta_path = tmp_path / "k1" / "metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["schema_version"] = 999
    meta_path.write_text(json.dumps(meta))
    look = cache.lookup("k1")
    assert look.kind == "corrupt" and "schema_version" in look.detail


def test_interrupted_write_never_destroys_valid_entry(tmp_path, built, monkeypatch):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("good", spec, suite, {})

    import autograder.assignment.cache as cache_mod

    real_rename = cache_mod.os.rename

    def dying_rename(src, dst):
        if "bad" in str(dst):
            raise OSError("simulated crash mid-store")
        return real_rename(src, dst)

    monkeypatch.setattr(cache_mod.os, "rename", dying_rename)
    with pytest.raises(OSError):
        cache.store("bad", spec, suite, {})
    assert cache.lookup("good").kind == "hit"  # prior entry untouched
    assert cache.lookup("bad").kind == "miss"  # no partial entry visible


def test_leftover_temp_dirs_do_not_confuse_listing(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("k1", spec, suite, {})
    (tmp_path / ".tmp-entry-abandoned").mkdir()
    entries = cache.list_entries()
    assert [e["key"] for e in entries] == ["k1"]


def test_invalidate_removes_only_matching_assignment(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)
    cache.store("k1", spec, suite, {})
    cache.store("k2", spec, suite, {})
    removed = cache.invalidate("add_two_integers")
    assert removed == 2
    assert cache.lookup("k1").kind == "miss"
    assert cache.invalidate("other_assignment") == 0


def test_concurrent_stores_and_lookups_are_safe(tmp_path, built):
    spec, suite = built
    cache = AssignmentCache(tmp_path)

    def work(i):
        key = f"key-{i % 3}"
        cache.store(key, spec, suite, {})
        return cache.lookup(key).kind

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(work, range(24)))
    assert all(r == "hit" for r in results)
    assert len(cache.list_entries()) == 3
