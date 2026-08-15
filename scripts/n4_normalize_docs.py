#!/usr/bin/env python3
"""Normalização temporária da documentação viva para a N4.

Escopo deliberadamente restrito a README.md e docs/*.md.
Blocos de código cercados por ```/~~~ e spans inline entre crases são preservados
na passada genérica, pois podem conter valores técnicos legados
(role="aluno", /aluno, student_id etc.). Casos editoriais específicos são
tratados depois por substituições exatas e auditáveis.

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

EDITORIAL_NOTE_LEGACY = (
    "> **Nota editorial (Ago/2026):** normalização da nomenclatura institucional "
    "**Aluno → Estudante**. Esta alteração é exclusivamente textual e **não** "
    "modifica schema, shape, invariantes, regras de negócio nem versão do contrato.\n"
)
EDITORIAL_NOTE = (
    "> **Nota editorial (Ago/2026):** normalização da nomenclatura institucional "
    "**Aluno → Estudante**. Esta alteração é exclusivamente textual e **não** "
    "modifica schema, shape, invariantes, regras de negócio nem versão do contrato. "
    "<!-- nomenclature-allow: registro editorial da migração terminológica -->\n"
)


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

        # Waivers e a nota editorial documentam intencionalmente o termo legado.
        if "nomenclature-allow" in line or "Nota editorial (Ago/2026)" in line:
            new_line = line
        else:
            new_line = line if in_fence else replace_prose(line)

        if new_line != line:
            changed_lines.append(f"{path.relative_to(ROOT)}:{line_no}: {line.rstrip()} -> {new_line.rstrip()}")
        output.append(new_line)

    normalized = "".join(output)
    if normalized != original:
        path.write_text(normalized, encoding="utf-8")
    return len(changed_lines), changed_lines


def apply_exact(path: Path, replacements: list[tuple[str, str]]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    changes: list[str] = []
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changes.append(f"{path.relative_to(ROOT)}: {old!r} -> {new!r}")
    path.write_text(text, encoding="utf-8")
    return changes


def ensure_editorial_note(path: Path, anchor: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if EDITORIAL_NOTE in text:
        return []
    if EDITORIAL_NOTE_LEGACY in text:
        path.write_text(text.replace(EDITORIAL_NOTE_LEGACY, EDITORIAL_NOTE, 1), encoding="utf-8")
        return [f"{path.relative_to(ROOT)}: waiver editorial adicionado"]
    if anchor not in text:
        raise RuntimeError(f"Âncora editorial não encontrada em {path}: {anchor!r}")
    path.write_text(text.replace(anchor, anchor + EDITORIAL_NOTE, 1), encoding="utf-8")
    return [f"{path.relative_to(ROOT)}: nota editorial inserida"]


def targeted_fixes() -> list[str]:
    report: list[str] = []

    academic = ROOT / "docs/ACADEMIC_EVENT_CONTRACT.md"
    diary = ROOT / "docs/DIARY_API_CONTRACT.md"
    history = ROOT / "docs/HISTORICO_ESCOLAR_CONTRACT.md"
    dependency = ROOT / "docs/STUDENT_DEPENDENCY.md"

    report += ensure_editorial_note(
        academic,
        "> Este contrato precede qualquer implementação de movimentação acadêmica.\n",
    )
    report += ensure_editorial_note(
        diary,
        "> **Pré-requisito**: Fase 1 da Dependência de Estudos validada (ver `STUDENT_DEPENDENCY.md`).\n",
    )
    report += ensure_editorial_note(
        history,
        "> Rotas de implementação: Fase 4 (depois do Boletim — Fase 3).\n",
    )

    report += apply_exact(
        academic,
        [
            ("Para o estudante tem evento ativo, queries de listagem/diário consultam ambas", "Quando o estudante tem evento ativo, queries de listagem/diário consultam ambas"),
            ('"message": "Aluno foi movimentado em 15/08/2026. Edição bloqueada."', '"message": "Estudante foi movimentado em 15/08/2026. Edição bloqueada."'),
            ("# 2. Eventos ATIVOS do aluno onde target_date está no intervalo herdado", "# 2. Eventos ATIVOS do estudante onde target_date está no intervalo herdado"),
            ("# 3. Aplica lente: marca _inherited, _locked, etc. por aluno", "# 3. Aplica lente: marca _inherited, _locked, etc. por estudante"),
        ],
    )

    report += apply_exact(
        diary,
        [
            ("// null se aluno regular", "// null se estudante regular"),
            ('"message": "Volume anômalo de alunos em dependência neste componente."', '"message": "Volume anômalo de estudantes em dependência neste componente."'),
            ("\nAlunos:\n", "\nEstudantes:\n"),
        ],
    )

    report += apply_exact(
        history,
        [
            ("// sem nome do aluno", "// sem nome do estudante"),
        ],
    )

    report += apply_exact(
        dependency,
        [
            ("# Duplicidade: 1 dep ativa por aluno×componente×ano de origem", "# Duplicidade: 1 dep ativa por estudante×componente×ano de origem"),
            ("1. alunos regulares (sort alfabético do nome)", "1. estudantes regulares (sort alfabético do nome)"),
        ],
    )

    # Registra que STUDENT_DEPENDENCY recebeu apenas atualização terminológica,
    # sem reescrever status/cronologia de implementação.
    text = dependency.read_text(encoding="utf-8")
    note = "> **Nota editorial (Ago/2026):** nomenclatura institucional padronizada para **Estudante**, sem alteração de modelo, endpoints ou regras.\n"
    anchor = "> Dependência **NÃO** é matrícula simplificada — é entidade acadêmica própria.\n"
    if note.strip() not in text:
        if anchor not in text:
            raise RuntimeError("Âncora não encontrada em STUDENT_DEPENDENCY.md")
        dependency.write_text(text.replace(anchor, anchor + note, 1), encoding="utf-8")
        report.append("docs/STUDENT_DEPENDENCY.md: nota editorial inserida")

    return report


def main() -> int:
    total = 0
    report: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        count, lines = normalize(path)
        total += count
        report.extend(lines)

    targeted = targeted_fixes()
    report.extend(targeted)

    print(f"N4 docs normalization: {total} linha(s) genérica(s) alterada(s); {len(targeted)} ajuste(s) dirigido(s).")
    for item in report:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
