"""Helper: professores vinculados a uma turma (para exibição em PDFs).

Regra de negócio (Jun/2026): exclusivamente para Educação Infantil e Ensino
Fundamental - Anos Iniciais, quando uma turma possui MAIS DE UM professor
vinculado, os nomes desses professores devem ser exibidos nos PDFs (notas,
frequência e objetos de conhecimento), e uma linha extra de assinatura é
adicionada. Turmas com um único professor mantêm o comportamento atual.
"""
from __future__ import annotations

MULTI_TEACHER_LEVELS = {"educacao_infantil", "fundamental_anos_iniciais"}


async def get_class_teacher_names(db, class_id, academic_year=None):
    """Nomes distintos (ordenados) dos professores ATIVOS vinculados à turma."""
    if not class_id:
        return []
    q = {"class_id": class_id, "status": "ativo"}
    if academic_year:
        q["academic_year"] = academic_year
    assigns = await db.teacher_assignments.find(q, {"_id": 0, "staff_id": 1}).to_list(1000)
    if not assigns and academic_year:
        # Fallback p/ dados legados sem academic_year coerente.
        assigns = await db.teacher_assignments.find(
            {"class_id": class_id, "status": "ativo"}, {"_id": 0, "staff_id": 1}
        ).to_list(1000)
    staff_ids = sorted({a["staff_id"] for a in assigns if a.get("staff_id")})
    if not staff_ids:
        return []
    staff_docs = await db.staff.find(
        {"id": {"$in": staff_ids}}, {"_id": 0, "nome": 1, "full_name": 1}
    ).to_list(1000)
    names = []
    for s in staff_docs:
        nm = (s.get("nome") or s.get("full_name") or "").strip()
        if nm:
            names.append(nm)
    return sorted(set(names), key=lambda x: x.lower())


async def get_multi_teacher_names_for_pdf(db, class_info, academic_year=None):
    """Lista de nomes APENAS quando o nível é Infantil/Anos Iniciais E há mais
    de um professor vinculado. Caso contrário, retorna [] (PDF inalterado)."""
    if not class_info:
        return []
    level = class_info.get("education_level") or class_info.get("nivel_ensino") or ""
    if level not in MULTI_TEACHER_LEVELS:
        return []
    names = await get_class_teacher_names(db, class_info.get("id"), academic_year)
    return names if len(names) > 1 else []
