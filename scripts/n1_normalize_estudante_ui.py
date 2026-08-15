#!/usr/bin/env python3
"""N1 — normalização segura de nomenclatura na UI.

Escopo: apresentação em frontend/src/**/*.{js,jsx,ts,tsx}.
Preserva deliberadamente identificadores técnicos como:
- role = 'aluno'
- /aluno
- cadastro-aluno
- student / students / student_id
- nomes de componentes/imports como AlunoDashboard e BoletimAluno

Regras canônicas de apresentação:
- Aluno / Aluna / Aluno(a) -> Estudante
- Alunos / Alunas / Alunos(as) -> Estudantes
- nunca usar Estudante(a) ou Estudantes(as)

O script é temporário e será removido antes do diff final do PR N1.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

# Formas de apresentação, incluindo a limpeza da primeira passada.
CAPITALIZED_REPLACEMENTS = [
    (re.compile(r"Estudantes\(as\)"), "Estudantes"),
    (re.compile(r"Estudante\(a\)"), "Estudante"),
    (re.compile(r"Alunos\(as\)"), "Estudantes"),
    (re.compile(r"Aluno\(a\)"), "Estudante"),
    (re.compile(r"\bAlunos\b"), "Estudantes"),
    (re.compile(r"\bAlunas\b"), "Estudantes"),
    (re.compile(r"\bAluno\b"), "Estudante"),
    (re.compile(r"\bAluna\b"), "Estudante"),
]

LOWER_REPLACEMENTS = [
    (re.compile(r"estudantes\(as\)"), "estudantes"),
    (re.compile(r"estudante\(a\)"), "estudante"),
    (re.compile(r"alunos\(as\)"), "estudantes"),
    (re.compile(r"aluno\(a\)"), "estudante"),
    (re.compile(r"\balunos\b"), "estudantes"),
    (re.compile(r"\balunas\b"), "estudantes"),
    (re.compile(r"\baluno\b"), "estudante"),
    (re.compile(r"\baluna\b"), "estudante"),
]

TECHNICAL_EXACT = {
    "aluno",
    "alunos",
    "AlunoDashboard",
    "BoletimAluno",
    "AlunoTab",
}


def looks_human_text(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped in TECHNICAL_EXACT:
        return False
    if stripped.startswith(("/", "@/", "http://", "https://", "data:", "#")):
        return False
    if re.fullmatch(r"[A-Za-z0-9_./:@-]+", stripped) and not re.search(r"\s", stripped):
        return False
    return bool(re.search(r"\s", stripped) or re.search(r"[,:;!?()]", stripped))


def polish_canonical_text(value: str) -> str:
    """Ajustes editoriais inequívocos após a troca terminológica."""
    value = value.replace("Novo(a) Estudante", "Novo Estudante")
    value = value.replace("Total Estudantes", "Total de Estudantes")
    value = value.replace("Capacidade Estudantes", "Capacidade de Estudantes")
    if value == "Alu.":
        value = "Est."
    return value


def normalize_literal(value: str, *, allow_lower: bool) -> str:
    original = value
    for pattern, replacement in CAPITALIZED_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    if allow_lower and looks_human_text(original):
        for pattern, replacement in LOWER_REPLACEMENTS:
            value = pattern.sub(replacement, value)
    return polish_canonical_text(value)


def find_template_expr_end(value: str, start: int) -> int:
    """Localiza o } que fecha ${...}, preservando strings dentro da expressão."""
    depth = 1
    i = start
    quote: str | None = None
    escaped = False
    while i < len(value):
        ch = value[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(value) - 1


def normalize_template(value: str) -> str:
    """Normaliza somente o texto de template literals, nunca o código de ${...}."""
    out: list[str] = []
    i = 0
    while i < len(value):
        marker = value.find("${", i)
        if marker == -1:
            out.append(normalize_literal(value[i:], allow_lower=True))
            break
        out.append(normalize_literal(value[i:marker], allow_lower=True))
        end = find_template_expr_end(value, marker + 2)
        out.append(value[marker:end + 1])
        i = end + 1
    return "".join(out)


def normalize_jsx_text_nodes(source: str) -> tuple[str, int]:
    """Normaliza texto puro entre tag de abertura e fechamento na mesma linha."""
    pattern = re.compile(
        r">([^<>{}\n]*(?:Aluno|Alunos|Aluna|Alunas|aluno|alunos|aluna|alunas|Estudante\(a\)|Estudantes\(as\))[^<>{}\n]*)</"
    )
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        text = match.group(1)
        normalized = normalize_literal(text, allow_lower=True)
        if normalized == text:
            return match.group(0)
        count += 1
        return ">" + normalized + "</"

    return pattern.sub(repl, source), count


def transform_source(source: str) -> tuple[str, int]:
    """Transforma literais de texto; ignora comentários e identificadores de código."""
    out: list[str] = []
    i = 0
    n = len(source)
    changed_literals = 0

    while i < n:
        ch = source[i]

        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            j = source.find("\n", i + 2)
            if j == -1:
                out.append(source[i:])
                break
            out.append(source[i:j])
            i = j
            continue

        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            j = source.find("*/", i + 2)
            if j == -1:
                out.append(source[i:])
                break
            j += 2
            out.append(source[i:j])
            i = j
            continue

        if ch not in {"'", '"', "`"}:
            out.append(ch)
            i += 1
            continue

        quote = ch
        out.append(quote)
        i += 1
        buf: list[str] = []
        escaped = False

        while i < n:
            cur = source[i]
            if escaped:
                buf.append(cur)
                escaped = False
                i += 1
                continue
            if cur == "\\":
                buf.append(cur)
                escaped = True
                i += 1
                continue
            if cur == quote:
                break
            buf.append(cur)
            i += 1

        literal = "".join(buf)
        normalized = normalize_template(literal) if quote == "`" else normalize_literal(literal, allow_lower=True)
        if normalized != literal:
            changed_literals += 1
        out.append(normalized)

        if i < n and source[i] == quote:
            out.append(quote)
            i += 1

    transformed = "".join(out)
    transformed, jsx_count = normalize_jsx_text_nodes(transformed)
    return transformed, changed_literals + jsx_count


def main() -> int:
    files_changed = 0
    literals_changed = 0

    for path in sorted(FRONTEND.rglob("*")):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        source = path.read_text(encoding="utf-8")
        transformed, count = transform_source(source)
        if transformed == source:
            continue
        path.write_text(transformed, encoding="utf-8")
        files_changed += 1
        literals_changed += count
        print(f"CHANGED {path.relative_to(ROOT)} | literals={count}")

    print(f"SUMMARY files_changed={files_changed} literals_changed={literals_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
