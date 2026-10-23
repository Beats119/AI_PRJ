"""Originality metric (similarity_flag): token-shingle similarity vs a corpus.

Method (deterministic): strip comments/literals, canonicalize identifiers
(user identifiers become ID in first-appearance order, so a renamed copy
still matches its original), keep keywords/operators, then Jaccard
similarity over 5-token shingles (fallback: token-sequence ratio for tiny
files). All N(N-1)/2 pairs can be compared for a whole class.

A high score FLAGS a pair for human review. It is never presented as proof
of copying: independent solutions to a tiny specified problem can look
alike, and the report says so wherever a flag is raised.
"""

from __future__ import annotations

import difflib
import itertools
import re
from decimal import Decimal
from pathlib import Path

from autograder.analyzers.c_source import KEYWORDS, strip_comments_and_literals
from autograder.models.analysis import (
    AnalyzerResult,
    MissingReason,
    ResultStatus,
)

_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||\+\+|--|->|.")
_SHINGLE = 5


def normalized_tokens(text: str) -> list[str]:
    stripped = strip_comments_and_literals(text)
    raw = _TOKEN_RE.findall(stripped)
    mapping: dict[str, str] = {}
    out: list[str] = []
    for tok in raw:
        if re.fullmatch(r"[A-Za-z_]\w*", tok):
            if tok in KEYWORDS:
                out.append(tok)
            else:
                if tok not in mapping:
                    mapping[tok] = f"ID{len(mapping)}"
                out.append(mapping[tok])
        elif re.fullmatch(r"\d+(?:\.\d+)?", tok):
            out.append("NUM")
        elif tok.strip() == "":
            continue
        else:
            out.append(tok)
    return out


def _shingles(tokens: list[str]) -> set[tuple[str, ...]]:
    if len(tokens) < _SHINGLE:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + _SHINGLE]) for i in range(len(tokens) - _SHINGLE + 1)}


def similarity_score(text_a: str, text_b: str) -> float:
    ta, tb = normalized_tokens(text_a), normalized_tokens(text_b)
    sa, sb = _shingles(ta), _shingles(tb)
    if sa and sb:
        return len(sa & sb) / len(sa | sb)
    return difflib.SequenceMatcher(a=ta, b=tb).ratio()


def pairwise_similarities(
    sources: dict[str, str], threshold: float = 0.85
) -> list[dict]:
    pairs: list[dict] = []
    for (name_a, a), (name_b, b) in itertools.combinations(sorted(sources.items()), 2):
        score = similarity_score(a, b)
        pairs.append(
            {
                "a": name_a,
                "b": name_b,
                "similarity": round(score, 4),
                "flagged": score >= threshold,
            }
        )
    return pairs


def analyze_originality(
    source_path: str | Path,
    corpus_paths: list[str | Path],
    *,
    flag_threshold: float = 0.85,
) -> AnalyzerResult:
    mine = Path(source_path).read_text(encoding="utf-8", errors="replace")
    corpus = [
        p for p in corpus_paths if Path(p).resolve() != Path(source_path).resolve()
    ]
    if not corpus:
        return AnalyzerResult(
            analyzer_id="similarity_flag",
            metric_name="originality",
            status=ResultStatus.INCONCLUSIVE,
            missing_reason=MissingReason.INCONCLUSIVE_EVIDENCE,
            diagnostics=[
                (
                    "no other submissions in the corpus: similarity cannot be "
                    "assessed for a single submission"
                )
            ],
            evidence={"corpus_size": 0},
        )
    comparisons: list[dict] = []
    for other in corpus:
        other_text = Path(other).read_text(encoding="utf-8", errors="replace")
        score = similarity_score(mine, other_text)
        comparisons.append(
            {
                "against": Path(other).name,
                "similarity": round(score, 4),
                "flagged": score >= flag_threshold,
            }
        )
    worst = max(comparisons, key=lambda c: c["similarity"])
    if worst["flagged"]:
        return AnalyzerResult(
            analyzer_id="similarity_flag",
            metric_name="originality",
            status=ResultStatus.FAILED,
            score=Decimal(0),
            feedback=(
                f"similarity {worst['similarity']} with {worst['against']} meets "
                f"the flag threshold {flag_threshold}: FLAGGED FOR HUMAN REVIEW. "
                "Similarity is not proof of copying — short solutions to a "
                "tightly specified problem can converge."
            ),
            evidence={"comparisons": comparisons, "threshold": flag_threshold},
        )
    return AnalyzerResult(
        analyzer_id="similarity_flag",
        metric_name="originality",
        status=ResultStatus.PASSED,
        score=Decimal(1),
        feedback=(
            f"highest similarity {worst['similarity']} (vs {worst['against']}), "
            f"below the flag threshold {flag_threshold}"
        ),
        evidence={"comparisons": comparisons, "threshold": flag_threshold},
    )
