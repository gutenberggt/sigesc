#!/usr/bin/env python3
"""N1 — normalização segura de nomenclatura na UI.

Escopo: apenas literais de texto em frontend/src/**/*.{js,jsx,ts,tsx}.
Preserva deliberadamente identificadores técnicos como:
- role = 'aluno'
- /aluno
- cadastro-aluno
- student / students / student_id
- nomes de componentes/imports como AlunoDashboard e BoletimAluno

O script é temporário e será removido antes do diff final do PR N1.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

# Formas que são inequivocamente de apresentação quando aparecem como palavras
# independentes dentro de um literal de texto.
CAPITALIZED_REPLACEMENTS = [
    (re.compile(r"\bAlunos\(as\)\b"), "Estudantes"),
    (re.compile(r"\bAluno\(a\)\b"), "Estudante"),
    (re.compile(r"\bAlunos\b"), "Estudantes"),
    (re.compile(r"\bAlunas\b"), "Estudantes"),
    (re.compile(r"\bAluno\b"), "Estudante"),
    (re.compile(r"\bAluna\b"), "Estudante"),
]

LOWER_REPLACEMENTS = [
    (re.compile(r"\balunos\(as\)\b"), "estudantes"),
    (re.compile(r"\baluno\(a\)\b"), "estudante"),
    (re.compile(r"\balunos\b"), "estudantes"),
    (re.compile(r"\balunas\b"), "estudantes"),
    (re.compile(r"\baluno\b"), "estudante"),
    (re.compile(r"\baluna\b"), "estudante"),
]

# Valores técnicos inteiros que não devem ser tratados como linguagem humana.
TECHNICAL_EXACT = {
    "aluno",
    "alunos",
    "AlunoDashboard",
    "BoletimAluno",
    "AlunoTab",
}


def looks_human_text(value: str) -> bool:
    """Distingue frase/label de identificador, rota, import, classe CSS ou chave técnica."""
    stripped = value.strip()
    if not stripped or stripped in TECHNICAL_EXACT:
        return False
    if stripped.startswith(("/", "@/", "http://", "https://", "data:", "#")):
        return False
    if re.fullmatch(r"[A-Za-z0-9_./:@-]+", stripped) and not re.search(r"\s", stripped):
        return False
    # Frases, labels com espaços ou pontuação textual são linguagem humana.
    return bool(re.search(r"\s", stripped) or re.search(r"[,:;!?()]", stripped))


def normalize_literal(value: str, *, allow_lower: bool) -> str:
    original = value
    for pattern, replacement in CAPITALIZED_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    if allow_lower and looks_human_text(original):
        for pattern, replacement in LOWER_REPLACEMENTS:
            value = pattern.sub(replacement, value)
    return value


def transform_source(source: str) -> tuple[str, int]:
    """Transforma apenas conteúdo de strings; ignora comentários e código."""
    out: list[str] = []
    i = 0
    n = len(source)
    changed_literals = 0

    while i < n:
        ch = source[i]

        # Comentário de linha.
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            j = source.find("\n", i + 2)
            if j == -1:
                out.append(source[i:])
                break
            out.append(source[i:j])
            i = j
            continue

        # Comentário de bloco.
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
        # Em template literals, não fazemos substituição lowercase para não tocar
        # acidentalmente em identificadores dentro de ${...}.
        normalized = normalize_literal(literal, allow_lower=(quote != "`"))
        if normalized != literal:
            changed_literals += 1
        out.append(normalized)

        if i < n and source[i] == quote:
            out.append(quote)
            i += 1

    return "".join(out), changed_literals


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
