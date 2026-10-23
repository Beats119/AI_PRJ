"""Expert analyzers. Each returns a structured AnalyzerResult and never
crashes the evaluation: a failed analyzer reports its status honestly."""

from autograder.analyzers.complexity import analyze_complexity
from autograder.analyzers.correctness import (
    analyze_correctness,
    analyze_logical,
    run_trusted_tests,
)
from autograder.analyzers.memory_safety import analyze_memory_safety
from autograder.analyzers.profiling import ProfileReport, measure_profile
from autograder.analyzers.readability import analyze_readability
from autograder.analyzers.similarity import analyze_originality, pairwise_similarities
from autograder.analyzers.structure import analyze_modularity, analyze_structure
from autograder.analyzers.syntax import analyze_syntax

__all__ = [
    "ProfileReport",
    "analyze_complexity",
    "analyze_correctness",
    "analyze_logical",
    "analyze_memory_safety",
    "analyze_modularity",
    "analyze_originality",
    "analyze_readability",
    "analyze_structure",
    "analyze_syntax",
    "measure_profile",
    "pairwise_similarities",
    "run_trusted_tests",
]
