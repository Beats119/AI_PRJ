"""Small deterministic C source helpers shared by the Stage 8 analyzers.

This is a heuristic lexer, not a full C parser: comments and literals are
blanked (preserving newlines), functions are found by brace matching at
top level. Its findings are labelled as heuristic wherever they surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Bool", "_Complex",
}


def strip_comments_and_literals(text: str) -> str:
    """Blank comments and string/char literal contents, preserving layout."""
    out: list[str] = []
    i, n = 0, len(text)
    state = "code"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line_comment"
                out.append("  ")
                i += 2
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                out.append("  ")
                i += 2
            elif ch == '"':
                state = "string"
                out.append('"')
                i += 1
            elif ch == "'":
                state = "char"
                out.append("'")
                i += 1
            else:
                out.append(ch)
                i += 1
        elif state == "line_comment":
            out.append("\n" if ch == "\n" else " ")
            if ch == "\n":
                state = "code"
            i += 1
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                out.append("  ")
                i += 2
                state = "code"
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
        elif state in ("string", "char"):
            quote = '"' if state == "string" else "'"
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
            elif ch == quote:
                out.append(quote)
                state = "code"
                i += 1
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
    return "".join(out)


@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    body: str  # stripped-code body (between the outer braces)
    header: str

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def cyclomatic(self) -> int:
        tokens = re.findall(r"\b(?:if|for|while|case)\b|&&|\|\||\?", self.body)
        return 1 + len(tokens)


@dataclass
class SourceInfo:
    text: str
    stripped: str
    functions: list[FunctionInfo] = field(default_factory=list)

    @property
    def code_lines(self) -> int:
        return sum(1 for line in self.stripped.splitlines() if line.strip())

    @property
    def comment_lines(self) -> int:
        original = self.text.splitlines()
        stripped = self.stripped.splitlines()
        count = 0
        for orig, strip in zip(original, stripped, strict=False):
            if orig.strip() and not strip.strip():
                count += 1
        return count


_FUNC_HEAD = re.compile(r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*$", re.DOTALL)


def parse_source(text: str) -> SourceInfo:
    stripped = strip_comments_and_literals(text)
    functions: list[FunctionInfo] = []
    depth = 0
    segment_start = 0
    i, n = 0, len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "{":
            if depth == 0:
                header = stripped[segment_start:i]
                m = None
                for cand in _FUNC_HEAD.finditer(header):
                    m = cand
                if m and m.group(1) not in KEYWORDS and not header.lstrip().startswith(
                    ("typedef", "struct", "enum", "union")
                ):
                    # find the matching closing brace
                    d = 1
                    j = i + 1
                    while j < n and d:
                        if stripped[j] == "{":
                            d += 1
                        elif stripped[j] == "}":
                            d -= 1
                        j += 1
                    functions.append(
                        FunctionInfo(
                            name=m.group(1),
                            start_line=stripped.count("\n", 0, i) + 1,
                            end_line=stripped.count("\n", 0, j) + 1,
                            body=stripped[i + 1 : j - 1],
                            header=header.strip(),
                        )
                    )
                    i = j
                    segment_start = j
                    continue
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                segment_start = i + 1
        elif ch == ";" and depth == 0:
            segment_start = i + 1
        i += 1
    return SourceInfo(text=text, stripped=stripped, functions=functions)


def identifiers(stripped: str) -> list[str]:
    return [
        tok
        for tok in re.findall(r"[A-Za-z_]\w*", stripped)
        if tok not in KEYWORDS
    ]


def numeric_literals(stripped: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", stripped)
