"""Guard de cutover do conteúdo legado para Diário por Vínculo Docente.

O bloqueio do reader legado precisa usar a mesma projeção canônica que o
frontend recebe em ``/professor/diarios``. Um ``teacher_class_assignment`` bruto
com ``diary_settings.enabled=true`` não é suficiente: o vínculo ainda pode ser
rejeitado pelo autorizador canônico (escopo DVD, tenant, escola, vigência,
proprietário) ou não possuir capability de conteúdo.

Invariante F2.5: o endpoint legado ``/learning-objects`` só é bloqueado quando a
mesma turma/componente aparece em ``list_teacher_diaries`` com
``capabilities.content_enabled=true``. Assim, se o ``contentDvdBridge`` não tem
candidato canônico e cai no reader legado, o backend também permite esse
fallback. Gestão não é reclassificada aqui.

``build_professor_dvd_query`` é preservado como helper estrutural/forense para
auditorias do conjunto bruto de candidatos; ele não é a autoridade de cutover.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from services.teacher_diaries import list_teacher_diaries


def build_professor_dvd_query(
    current_user: Mapping[str, Any],
    *,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    on_date: Optional[str] = None,
) -> Optional[dict]:
    """Monta o conjunto bruto de candidatos DVD para auditoria/diagnóstico.

    O retorno desta função não deve ser usado isoladamente para decidir o
    cutover. A decisão funcional passa por ``list_teacher_diaries`` abaixo.
    """
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


def _diary_matches_content_context(
    item: Mapping[str, Any],
    *,
    class_id: Optional[str],
    course_id: Optional[str],
) -> bool:
    """Espelha o matching do ``contentDvdBridge`` para candidatos de conteúdo."""
    if class_id and item.get("class_id") != class_id:
        return False

    item_component_id = item.get("component_id")
    if course_id and item_component_id and item_component_id != course_id:
        return False

    return (item.get("capabilities") or {}).get("content_enabled") is True


async def professor_has_active_dvd_content(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    on_date: Optional[str] = None,
) -> bool:
    """Retorna True somente quando existe rota DVD canônica de conteúdo.

    Esta função é chamada pelo guard do endpoint legado. Reutilizar
    ``list_teacher_diaries`` evita que frontend e backend tomem decisões de
    cutover com critérios diferentes.
    """
    if current_user.get("role") != "professor" or not current_user.get("id"):
        return False

    target_date = on_date or date.today().isoformat()
    diaries_payload = await list_teacher_diaries(
        db,
        current_user,
        reference_date=target_date,
        active_mantenedora_id=current_user.get("mantenedora_id"),
    )

    return any(
        _diary_matches_content_context(
            item,
            class_id=class_id,
            course_id=course_id,
        )
        for item in (diaries_payload.get("items") or [])
    )


def legacy_content_block_detail() -> dict:
    return {
        "code": "DVD_CONTENT_LEGACY_BLOCKED",
        "message": (
            "Este vínculo já utiliza o Diário por Vínculo Docente. "
            "Conteúdos devem ser acessados pelo motor canônico content_entries."
        ),
    }
