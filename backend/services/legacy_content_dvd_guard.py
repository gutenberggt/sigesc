"""Guard de cutover do conteúdo legado para Diário por Vínculo Docente.

A decisão é deliberadamente simples e fail-closed para professor comum:
se existe teacher_class_assignment habilitado para a turma/componente, o endpoint
legado /learning-objects não pode ser usado como caminho alternativo de leitura
ou escrita. O frontend DVD deve usar content_entries, cuja autorização é canônica.

Gestão não é reclassificada aqui; suas visões consolidadas continuam nos fluxos
existentes até contrato específico de gestão.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


def build_professor_dvd_query(
    current_user: Mapping[str, Any], *, class_id: str, course_id: Optional[str] = None
) -> Optional[dict]:
    if current_user.get("role") != "professor" or not current_user.get("id") or not class_id:
        return None

    query: dict = {
        "teacher_id": current_user["id"],
        "class_id": class_id,
        "deleted": False,
        "diary_settings.enabled": True,
    }
    if course_id:
        query["$or"] = [
            {"component_id": course_id},
            {"component_id": None},
            {"component_id": {"$exists": False}},
        ]
    return query


async def professor_has_active_dvd_content(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    course_id: Optional[str] = None,
) -> bool:
    query = build_professor_dvd_query(
        current_user, class_id=class_id, course_id=course_id
    )
    if query is None:
        return False

    doc = await db.teacher_class_assignments.find_one(query, {"_id": 0, "id": 1})
    return bool(doc)


def legacy_content_block_detail() -> dict:
    return {
        "code": "DVD_CONTENT_LEGACY_BLOCKED",
        "message": (
            "Este vínculo já utiliza o Diário por Vínculo Docente. "
            "Conteúdos devem ser acessados pelo motor canônico content_entries."
        ),
    }
