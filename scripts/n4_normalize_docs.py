#!/usr/bin/env python3
"""Normalização temporária da documentação viva para a N4.

Escopo deliberadamente restrito a README.md e docs/*.md.
Blocos de código cercados por ```/~~~ e spans inline entre crases são preservados,
pois podem conter valores técnicos legados (role="aluno", /aluno, student_id etc.).

Este arquivo é temporário e deve ser removido antes do PR final.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bAlunos\(as\)\b"), "Estudantes"),
    (re.compile(r"\bAluno\(a\)\b"), "Estudante"),
    (re.compile(r"\balunos\(as\)\b"), "estudantes"),
    (re.compile(r"\baluno\(a\)\b"), "estudante"),
    (re.compile(r"\bAlunas\b"), "Estudantes"),
    (re.compile(r"\bAluna\b"), "Estudante"),
    (re.compile(r"\balunas\b"), "estudantes"),
    (re.compile(r"\baluna\b"), "estudante"),
    (re.compile(r"\bAlunos\b"), "Estudantes"),
    (re.compile(r"\bAluno\b"), "Estudante"),
    (re.compile(r"\balunos\b"), "estudantes"),
    (re.compile(r"\baluno\b"), "estudante"),
]

INLINE_CODE = re.compile(r"(`+[^`]*?`+)")


def replace_prose(text: str) -> str:
    parts = INLINE_CODE.split(text)
    for idx in range(0, len(parts), 2):
        value = parts[idx]
        for pattern, replacement in REPLACEMENTS:
            value = pattern.sub(replacement, value)
        parts[idx] = value
    return "".join(parts)


def normalize(path: Path) -> tuple[int, list[str]]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    in_fence = False
    fence_marker: str | None = None
    changed_lines: list[str] = []
    output: list[str] = []

    for line_no, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"

        if marker:
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            output.append(line)
            continue

        new_line = line if in_fence else replace_prose(line)
        if new_line != line:
            changed_lines.append(f"{path.relative_to(ROOT)}:{line_no}: {line.rstrip()} -> {new_line.rstrip()}")
        output.append(new_line)

    normalized = "".join(output)
    if normalized != original:
        path.write_text(normalized, encoding="utf-8")
    return len(changed_lines), changed_lines


def main() -> int:
    total = 0
    report: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        count, lines = normalize(path)
        total += count
        report.extend(lines)

    print(f"N4 docs normalization: {total} linha(s) alterada(s).")
    for item in report:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
