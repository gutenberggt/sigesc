"""Extração conservadora de PDFs de Versão Curricular Estruturada do SIGESC.

Este extrator NÃO tenta transformar qualquer PDF curricular em dados canônicos.
Ele reconhece o contrato editorial "VERSÃO CURRICULAR ESTRUTURADA" e extrai
somente elementos que podem ser rastreados no próprio documento.

O documento original continua sendo a evidência; a extração é um rascunho para
revisão/publicação humana.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Any

import pdfplumber


BNCC_CODE_RE = re.compile(r"\bEF\d{2}[A-Z]{2}\d{2}\b", re.IGNORECASE)


class StructuredCurriculumPdfError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _clean(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _codes(value: Any) -> list[str]:
    return list(dict.fromkeys(code.upper() for code in BNCC_CODE_RE.findall(_clean(value))))


def _split_objects(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [part.strip(" .") for part in re.split(r"\s*;\s*", text) if part.strip(" .")]


def _cell(row: list[Any], index: int) -> str:
    return _clean(row[index]) if index < len(row) else ""


def _header_index(row: list[Any], needle: str) -> int | None:
    target = needle.lower()
    for idx, raw in enumerate(row):
        if target in _clean(raw).lower():
            return idx
    return None


def parse_skill_table(table: list[list[Any]], *, source_page: int) -> list[dict[str, Any]]:
    """Lê a tabela Código/status · Habilidade · Objeto · Evidência · Origem."""
    if not table:
        return []
    header = table[0]
    code_i = _header_index(header, "código")
    focus_i = _header_index(header, "habilidade")
    objects_i = _header_index(header, "objeto")
    evidence_i = _header_index(header, "evidência")
    origin_i = _header_index(header, "origem")
    if code_i is None or focus_i is None or objects_i is None:
        return []

    result: list[dict[str, Any]] = []
    for row in table[1:]:
        code_cell = _cell(row, code_i)
        codes = _codes(code_cell)
        if not codes:
            continue
        status_text = code_cell.lower()
        status = "mandatory" if "obrigat" in status_text else "documented"
        for code in codes:
            result.append({
                "code": code,
                "status": status,
                "focus": _cell(row, focus_i),
                "knowledge_objects": _split_objects(_cell(row, objects_i)),
                "evidence": _cell(row, evidence_i) if evidence_i is not None else "",
                "origin": _cell(row, origin_i) if origin_i is not None else "",
                "source_page": source_page,
            })
    return result


def parse_object_table(table: list[list[Any]], *, source_page: int) -> list[dict[str, Any]]:
    """Lê Prática/eixo · Objetos de conhecimento · Habilidades relacionadas."""
    if not table:
        return []
    header = table[0]
    practice_i = _header_index(header, "prática")
    objects_i = _header_index(header, "objetos de conhecimento")
    skills_i = _header_index(header, "habilidades relacionadas")
    if practice_i is None or objects_i is None:
        return []
    result: list[dict[str, Any]] = []
    for row in table[1:]:
        practice = _cell(row, practice_i)
        objects = _split_objects(_cell(row, objects_i))
        if not practice and not objects:
            continue
        result.append({
            "practice_or_axis": practice,
            "knowledge_objects": objects,
            "skill_codes": _codes(_cell(row, skills_i)) if skills_i is not None else [],
            "source_page": source_page,
        })
    return result


def parse_complementary_table(table: list[list[Any]], *, source_page: int) -> list[dict[str, Any]]:
    if not table:
        return []
    header = table[0]
    code_i = _header_index(header, "código")
    purpose_i = _header_index(header, "finalidade")
    usage_i = _header_index(header, "uso no")
    if code_i is None or purpose_i is None:
        return []
    result = []
    for row in table[1:]:
        codes = _codes(_cell(row, code_i))
        for code in codes:
            result.append({
                "code": code,
                "status": "complementary",
                "purpose": _cell(row, purpose_i),
                "usage": _cell(row, usage_i) if usage_i is not None else "",
                "source_page": source_page,
            })
    return result


def _extract_between(text: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r"\s*(.*?)\s*" + re.escape(end), re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    return _clean(match.group(1)) if match else ""


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return _clean(match.group(1))
    return ""


def _grade_number(value: str) -> int | None:
    match = re.search(r"\b([1-9])\s*[ºo°]?\s*(?:ano)?\b", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _bimestre_number(value: str) -> int | None:
    match = re.search(r"\b([1-4])\s*[ºo°]?\s*bimestre\b", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_structured_curriculum_pdf(content: bytes) -> dict[str, Any]:
    if not content.startswith(b"%PDF"):
        raise StructuredCurriculumPdfError("CURRICULUM_PDF_INVALID", "O arquivo não possui assinatura PDF válida.")

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            pages_text: list[str] = []
            all_tables: list[tuple[int, list[list[Any]]]] = []
            for page_number, page in enumerate(pdf.pages, start=1):
                pages_text.append(page.extract_text() or "")
                for table in page.extract_tables() or []:
                    if table:
                        all_tables.append((page_number, table))
    except Exception as exc:
        raise StructuredCurriculumPdfError("CURRICULUM_PDF_READ_FAILED", f"Não foi possível ler o PDF: {exc}") from exc

    full_text = "\n".join(pages_text)
    normalized = _clean(full_text)
    if "versão curricular estruturada" not in normalized.lower():
        raise StructuredCurriculumPdfError(
            "CURRICULUM_PDF_CONTRACT_UNRECOGNIZED",
            "O PDF não se identifica como 'Versão Curricular Estruturada'.",
        )

    component_name = _first_match([
        r"Componente curricular\s+([^\n]+)",
        r"Componente\s+([^\n]+)",
    ], full_text)
    grade_text = _first_match([r"Ano\s+([^\n]+ano)", r"(\d+\s*[ºo°]?\s*ano)"], full_text)
    bimestre_text = _first_match([r"Período\s+([^\n]+bimestre)", r"Bimestre\s+([^\n]+)"], full_text)
    education_stage = _first_match([r"Etapa\s+([^\n]+)"], full_text)
    grade = _grade_number(grade_text)
    bimestre = _bimestre_number(bimestre_text or normalized)

    skill_rows: list[dict[str, Any]] = []
    object_groups: list[dict[str, Any]] = []
    complementary: list[dict[str, Any]] = []
    for page_number, table in all_tables:
        skill_rows.extend(parse_skill_table(table, source_page=page_number))
        object_groups.extend(parse_object_table(table, source_page=page_number))
        complementary.extend(parse_complementary_table(table, source_page=page_number))

    # Fallback conservador: códigos do bloco DCM obrigatório, sem inventar descrições.
    mandatory = [row for row in skill_rows if row.get("status") == "mandatory"]
    if not mandatory:
        mandatory_block = _extract_between(full_text, "Habilidades DCM obrigatórias", "Habilidades BNCC complementares")
        mandatory = [
            {"code": code, "status": "mandatory", "focus": "", "knowledge_objects": [], "evidence": "", "origin": "", "source_page": None}
            for code in _codes(mandatory_block)
        ]

    if not complementary:
        comp_block = _extract_between(full_text, "Habilidades BNCC complementares", "Integração transversal")
        complementary = [
            {"code": code, "status": "complementary", "purpose": "", "usage": "", "source_page": None}
            for code in _codes(comp_block)
        ]

    trans_block = _extract_between(full_text, "Integração transversal", "Campo predominante")
    transversal = [
        {"code": code, "status": "transversal", "source_page": None}
        for code in _codes(trans_block)
    ]
    if not transversal:
        for page_number, page_text in enumerate(pages_text, start=1):
            if "Integração com Computação" in page_text:
                transversal = [
                    {"code": code, "status": "transversal", "source_page": page_number}
                    for code in _codes(page_text)
                    if "CO" in code
                ]
                break

    if grade is None or bimestre is None or not component_name:
        raise StructuredCurriculumPdfError(
            "CURRICULUM_PDF_SCOPE_INCOMPLETE",
            "Não foi possível identificar componente, ano/série e bimestre no documento.",
        )
    if not mandatory:
        raise StructuredCurriculumPdfError(
            "CURRICULUM_PDF_MANDATORY_SKILLS_MISSING",
            "Nenhuma habilidade obrigatória foi identificada no documento.",
        )

    canonical_text = pages_text[7] if len(pages_text) >= 8 else full_text
    eixos = _extract_between(canonical_text, "Eixos DCM", "Gêneros")
    genres = _extract_between(canonical_text, "Gêneros", "Objetos DCM")
    objects_canonical = _extract_between(canonical_text, "Objetos DCM", "Habilidades DCM obrigatórias")
    field = _extract_between(canonical_text, "Campo predominante BNCC", "Status de origem")

    return {
        "contract": "SIGESC_CURRICULUM_STRUCTURED_V1",
        "component_name": component_name,
        "grade_scope": [str(grade)],
        "grade": grade,
        "bimestre": bimestre,
        "education_stage": education_stage,
        "mandatory_skills": list({row["code"]: row for row in mandatory}.values()),
        "complementary_skills": list({row["code"]: row for row in complementary}.values()),
        "transversal_skills": list({row["code"]: row for row in transversal}.values()),
        "knowledge_object_groups": object_groups,
        "canonical_knowledge_objects": _split_objects(objects_canonical),
        "eixos": _split_objects(eixos),
        "genres": _split_objects(genres),
        "predominant_field": field,
        "page_count": len(pages_text),
    }
