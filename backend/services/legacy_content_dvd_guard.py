"""Guard de cutover do conteúdo legado para Diário por Vínculo Docente.

A decisão é deliberadamente simples e fail-closed para professor comum:
se existe teacher_class_assignment habilitado e vigente para o contexto, o
endpoint legado /learning-objects não pode ser usado como caminho alternativo
de leitura ou escrita. O frontend DVD usa content_entries, cuja autorização é
canônica.

Uma requisição ampla do professor sem class_id também é bloqueada quando ele
possui qualquer DVD vigente, evitando contornar o isolamento omitindo filtros.
Gestão não é reclassificada aqui; suas visões consolidadas continuam nos fluxos
existentes até contrato específico de gestão.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional


def build_professor_dvd_query(
    current_user: Mapping[str, Any],
    *,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    on_date: Optional[str] = None,
) -> Optional[dict]:
    if current_user.get("role") != "professor" or not current_user.get("id"):
        return None

    target_date = on_date or date.today().isoformat()
    clauses: list[dict] = [
        {
            "$or": [
                {"valid_from": {"$lte": target_date}},
                {"valid_from": None},
                {"valid_from": {"$exists": False}},
            ]
        },
        {
            "$or": [
                {"valid_until": {"$gte": target_date}},
                {"valid_until": None},
                {"valid_until": {"$exists": False}},
            ]
        },
    ]

    query: dict = {
        "teacher_id": current_user["id"],
        "deleted": False,
        "diary_settings.enabled": True,
        "$and": clauses,
    }
    if class_id:
        query["class_id"] = class_id
    if course_id:
        clauses.append(
            {
                "$or": [
                    {"component_id": course_id},
                    {"component_id": None},
                    {"component_id": {"$exists": False}},
                ]
            }
        )
    return query


async def professor_has_active_dvd_content(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    on_date: Optional[str] = None,
) -> bool:
    query = build_professor_dvd_query(
        current_user,
        class_id=class_id,
        course_id=course_id,
        on_date=on_date,
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
