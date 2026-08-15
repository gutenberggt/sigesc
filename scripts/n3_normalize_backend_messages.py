#!/usr/bin/env python3
"""N3 temporário — normaliza Aluno/Alunos somente em mensagens humanas do backend.

Fronteiras:
- NÃO altera identificadores, chaves/campos com underscore, rotas/URLs, nomes de arquivo;
- NÃO altera o valor técnico isolado ``aluno``/``alunos``/``aluna``/``alunas``;
- NÃO altera docstrings, comentários, print/logging;
- backend/pdf fica fora (tratado na N2);
- backend/scripts fica fora (ferramentas operacionais, não API pública);
- testes entram apenas para manter asserções de mensagens públicas coerentes.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
REPORT = ROOT / "n3_scan_report.txt"

TERM_RE = re.compile(r"(?i)(?<![\w_])(?:aluno|aluna|alunos|alunas)(?:\(a?s?\))?(?![\w_])")
EXACT_TECH = {"aluno", "aluna", "alunos", "alunas"}
SKIP_DIR_PARTS = {"pdf", "scripts", "__pycache__"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

PRE_REPLACEMENTS = [
    (re.compile(r"(?i)\bdo\(a\)\s+aluno\(a\)\b"), "do estudante"),
    (re.compile(r"(?i)\bdo\(a\)\s+aluno\b"), "do estudante"),
    (re.compile(r"(?i)\bo\(a\)\s+aluno\(a\)\b"), "o estudante"),
    (re.compile(r"(?i)\bo\(a\)\s+aluno\b"), "o estudante"),
    (re.compile(r"(?i)\bao\(à\)\s+aluno\(a\)\b"), "ao estudante"),
    (re.compile(r"(?i)\bpelo\(a\)\s+aluno\(a\)\b"), "pelo estudante"),
]


def replacement(match: re.Match[str]) -> str:
    word = match.group(0)
    low = word.lower()
    plural = "alunos" in low or "alunas" in low or "(as)" in low
    out = "Estudantes" if plural else "Estudante"
    if word[:1].islower():
        out = out.lower()
    if word.isupper():
        out = out.upper()
    return out


def iter_files():
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if any(part in SKIP_DIR_PARTS for part in rel.parts[:-1]):
            continue
        yield path


def node_range(node: ast.AST) -> tuple[int, int, int, int] | None:
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        return None
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def contains_pos(rng: tuple[int, int, int, int], line: int, col: int) -> bool:
    sl, sc, el, ec = rng
    if line < sl or line > el:
        return False
    if line == sl and col < sc:
        return False
    if line == el and col >= ec:
        return False
    return True


def skip_ranges(tree: ast.AST) -> list[tuple[int, int, int, int]]:
    ranges: list[tuple[int, int, int, int]] = []

    # Docstrings.
    candidates = [tree]
    candidates.extend(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    for node in candidates:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            rng = node_range(body[0].value)
            if rng:
                ranges.append(rng)

    # Logs e prints não são contrato de resposta ao usuário.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        skip = isinstance(func, ast.Name) and func.id == "print"
        if isinstance(func, ast.Attribute) and func.attr in LOG_METHODS:
            base = func.value
            if isinstance(base, ast.Name) and base.id in {"logger", "logging", "log"}:
                skip = True
        if skip:
            rng = node_range(node)
            if rng:
                ranges.append(rng)
    return ranges


def is_technical_literal(raw: str) -> bool:
    # Conservador: remove prefixos de string e aspas externas apenas para classificação.
    m = re.match(r"(?is)^[rubf]*(['\"]{1,3})(.*)\1$", raw)
    inner = m.group(2) if m else raw
    stripped = inner.strip()
    if stripped in EXACT_TECH:
        return True
    if stripped.startswith(("/", "http://", "https://")):
        return True
    if re.search(r"\b(?:aluno|aluna|alunos|alunas)_[A-Za-z0-9_]", stripped, re.I):
        return True
    if re.search(r"[A-Za-z0-9_]_(?:aluno|aluna|alunos|alunas)\b", stripped, re.I):
        return True
    # nomes de arquivos/caminhos/identificadores compostos
    if ("/" in stripped or "\\" in stripped) and " " not in stripped:
        return True
    if re.search(r"\.(?:pdf|json|csv|xlsx?|docx?|html?)\b", stripped, re.I):
        return True
    return False


def normalize_raw_string(raw: str) -> tuple[str, int]:
    if is_technical_literal(raw):
        return raw, 0
    updated = raw
    for pattern, repl in PRE_REPLACEMENTS:
        updated = pattern.sub(repl, updated)
    before = updated
    updated, count = TERM_RE.subn(replacement, updated)
    # contabiliza também pré-normalizações
    if updated != raw and count == 0:
        count = 1
    return updated, count


def process(path: Path, apply: bool) -> tuple[int, list[tuple[int, str]]]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0, []
    ranges = skip_ranges(tree)
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    replacements = 0
    residuals: list[tuple[int, str]] = []
    out_tokens = []

    for tok in tokens:
        new_tok = tok
        if tok.type == tokenize.STRING:
            line, col = tok.start
            if not any(contains_pos(r, line, col) for r in ranges):
                updated, count = normalize_raw_string(tok.string)
                if count:
                    replacements += count
                    new_tok = tokenize.TokenInfo(tok.type, updated, tok.start, tok.end, tok.line)
                # verifica resíduo apenas em literal que não é técnico
                candidate = updated
                if not is_technical_literal(candidate) and TERM_RE.search(candidate):
                    residuals.append((line, candidate[:240]))
        out_tokens.append(new_tok)

    if apply and replacements:
        path.write_text(tokenize.untokenize(out_tokens), encoding="utf-8")
    return replacements, residuals


def main() -> int:
    apply = "--apply" in sys.argv
    total_files = 0
    total_repl = 0
    all_residuals: list[tuple[str, int, str]] = []
    changed: list[tuple[str, int]] = []

    for path in iter_files():
        repl, residuals = process(path, apply=apply)
        rel = path.relative_to(ROOT).as_posix()
        if repl:
            total_files += 1
            total_repl += repl
            changed.append((rel, repl))
        for line, text in residuals:
            all_residuals.append((rel, line, text))

    lines = [
        "N3_BACKEND_MESSAGE_NORMALIZATION",
        f"mode={'apply' if apply else 'check'}",
        f"files_changed_or_candidate={total_files}",
        f"replacements={total_repl}",
        f"visible_residuals={len(all_residuals)}",
        "",
        "CHANGED:",
    ]
    lines.extend(f"{rel} | replacements={n}" for rel, n in changed)
    lines.append("")
    lines.append("RESIDUALS:")
    lines.extend(f"{rel}:{line}: {text}" for rel, line, text in all_residuals)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    if all_residuals:
        for item in lines[-min(50, len(all_residuals)):]:
            print(item)
    return 1 if all_residuals else 0


if __name__ == "__main__":
    raise SystemExit(main())
