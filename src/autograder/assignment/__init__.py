"""Assignment setup: specification, generation, oracle, cache (Stages 6-7)."""

from autograder.assignment.cache import AssignmentCache, CacheEntry
from autograder.assignment.setup import PrepareResult, prepare_assignment
from autograder.assignment.specification import (
    AssignmentPackage,
    AssignmentPackageConfig,
    load_assignment_package,
)

__all__ = [
    "AssignmentCache",
    "AssignmentPackage",
    "AssignmentPackageConfig",
    "CacheEntry",
    "PrepareResult",
    "load_assignment_package",
    "prepare_assignment",
]
