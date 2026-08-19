"""Compatibilidade de leitura entre conteúdos legados e o Diário por Vínculo.

Este serviço é estritamente READ-ONLY. Ele nunca migra, copia, atualiza ou exclui
``learning_objects``. ``content_entries`` continua sendo a fonte canônica para
escritas DVD e para o período iniciado em ``assignment.valid_from``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from services.content_assignment_scope import filter_visible_content_entries
from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)


class ContentHistoryBridgeError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _legacy_public(record: Mapping[str, Any]) -> dict:
    item = dict(record)
    item.pop("_id", None)
    component_id = item.get("course_id") or item.get("component_id")
    recorded_by = item.get("recorded_by")
    item["course_id"] = component_id
    item["component_id"] = component_id
    item["teacher_id"] = recorded_by
    item["assignment_id"] = None
    item["source"] = "learning_objects"
    item["legacy"] = True
    item["read_only"] = True
    return item


def _canonical_public(record: Mapping[str, Any]) -> dict:
    item = dict(record)
    item.pop("_id", None)
    item["course_id"] = item.get("course_id") or item.get("component_id")
    item["component_id"] = item.get("component_id") or item.get("course_id")
    item.setdefault("source", "content_entries")
    item.setdefault("legacy", False)
    item.setdefault("read_only", False)
    return item


def _sort_items(items: list[dict]) -> list[dict]:
    # Mesmo contrato predominante do endpoint canônico: data desc; dentro da
    # mesma data, aula_numero asc (None por último). Dois sorts estáveis evitam
    # inverter aula_numero quando a data é ordenada em reverse.
    items.sort(
        key=lambda item: (
            item.get("aula_numero") is None,
            item.get("aula_numero") if item.get("aula_numero") is not None else 0,
        )
    )
    items.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return items


async def list_assignment_content_history(
    db,
    current_user: Mapping[str, Any],
    *,
    assignment_id: str,
    class_id: Optional[str] = None,
    date: Optional[str] = None,
    teacher_id: Optional[str] = None,
    component_id: Optional[str] = None,
    include_deleted: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> dict:
    """Retorna a linha do tempo consolidada de um vínculo DVD.

    Regras:
    - autoriza o vínculo vivo para VIEW usando a política central DVD;
    - ``date < valid_from`` pode vir somente de ``learning_objects``;
    - ``date >= valid_from`` pode vir somente de ``content_entries``;
    - legado é filtrado pelo ``recorded_by`` histórico do proprietário;
    - nenhuma operação de escrita é executada.
    """
    try:
        context = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=DiaryAction.VIEW,
            expected_class_id=class_id,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise ContentHistoryBridgeError(exc.code, exc.message) from exc

    assignment = context.assignment
    resolved_class_id = assignment.get("class_id")
    assignment_component_id = assignment.get("component_id")
    owner_teacher_id = assignment.get("teacher_id")
    valid_from = assignment.get("valid_from")

    if not valid_from:
        raise ContentHistoryBridgeError(
            "ASSIGNMENT_VALID_FROM_REQUIRED",
            "O vínculo DVD não possui data inicial válida para compor o histórico.",
        )

    if component_id and assignment_component_id and component_id != assignment_component_id:
        raise ContentHistoryBridgeError(
            "COMPONENT_MISMATCH",
            "O vínculo não pertence ao componente informado.",
        )

    if teacher_id and owner_teacher_id and teacher_id != owner_teacher_id:
        raise ContentHistoryBridgeError(
            "CONTENT_TEACHER_MISMATCH",
            "O professor informado diverge do proprietário pedagógico do vínculo.",
        )

    resolved_component_id = component_id or assignment_component_id

    # Fechamento temporal explícito: conteúdo canônico nunca é projetado para o
    # período anterior ao início do vínculo, mesmo que exista dado inconsistente.
    canonical_date_allowed = not date or str(date) >= str(valid_from)
    canonical_items: list[dict] = []
    if canonical_date_allowed:
        canonical_query: dict[str, Any] = {"assignment_id": assignment_id}
        if not include_deleted:
            canonical_query["deleted"] = False
        if resolved_class_id:
            canonical_query["class_id"] = resolved_class_id
        if resolved_component_id:
            canonical_query["component_id"] = resolved_component_id
        if date:
            canonical_query["date"] = date
        else:
            canonical_query["date"] = {"$gte": valid_from}

        canonical_candidates = await db.content_entries.find(
            canonical_query, {"_id": 0}
        ).to_list(2000)
        canonical_visible = await filter_visible_content_entries(
            db,
            current_user,
            canonical_candidates,
            active_mantenedora_id=active_mantenedora_id,
        )
        canonical_items = [_canonical_public(item) for item in canonical_visible]

    legacy_items: list[dict] = []
    legacy_date_allowed = not date or str(date) < str(valid_from)
    if legacy_date_allowed and owner_teacher_id:
        legacy_query: dict[str, Any] = {
            "class_id": resolved_class_id,
            "recorded_by": owner_teacher_id,
        }
        if resolved_component_id:
            legacy_query["course_id"] = resolved_component_id
        if date:
            legacy_query["date"] = date
        else:
            legacy_query["date"] = {"$lt": valid_from}

        legacy_candidates = await db.learning_objects.find(
            legacy_query, {"_id": 0}
        ).to_list(5000)
        legacy_items = [_legacy_public(item) for item in legacy_candidates]

    # Deduplicação somente defensiva por origem+id. Não cruza IDs nem tenta
    # considerar um legado como versão de um content_entry.
    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for item in [*canonical_items, *legacy_items]:
        key = (str(item.get("source") or ""), str(item.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    return {
        "items": _sort_items(merged),
        "total": len(merged),
        "history_bridge": {
            "assignment_id": assignment_id,
            "valid_from": valid_from,
            "legacy_read_only": True,
        },
    }
