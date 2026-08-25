"""Compatibilidade de leitura entre conteúdos legados e o Diário por Vínculo.

Este serviço é estritamente READ-ONLY. Ele nunca migra, copia, atualiza ou exclui
``learning_objects``. ``content_entries`` continua sendo a fonte canônica para
novas escritas, inclusive para backfill de datas anteriores ao ``valid_from`` do
assignment quando a propriedade pedagógica foi autorizada pelo motor canônico.
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
    item["historical_backfill"] = False
    return item


def _canonical_public(record: Mapping[str, Any], *, valid_from: Optional[str] = None) -> dict:
    item = dict(record)
    item.pop("_id", None)
    item["course_id"] = item.get("course_id") or item.get("component_id")
    item["component_id"] = item.get("component_id") or item.get("course_id")
    item.setdefault("source", "content_entries")
    item.setdefault("legacy", False)
    item.setdefault("read_only", False)
    item["historical_backfill"] = bool(
        valid_from
        and item.get("date")
        and str(item.get("date")) < str(valid_from)
    )
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


def _semantic_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Chave defensiva para não duplicar legado quando já existe backfill canônico."""
    return (
        str(item.get("class_id") or ""),
        str(item.get("component_id") or item.get("course_id") or ""),
        str(item.get("teacher_id") or item.get("recorded_by") or ""),
        str(item.get("date") or ""),
    )


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
    - ``content_entries`` do próprio assignment são visíveis em qualquer data;
    - entry anterior a ``valid_from`` é classificada como ``historical_backfill``;
    - ``learning_objects`` anterior ao cutover continua visível e read-only pelo
      escopo autorizado de turma/componente, preservando ``recorded_by`` apenas
      como proveniência histórica e não como filtro adicional de visibilidade;
    - se houver backfill canônico para a mesma turma/componente/professor/data,
      ele prevalece sobre o registro legado equivalente;
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

    # O assignment_id + snapshot persistido é a prova de propriedade histórica.
    # Por isso um content_entry canônico criado como backfill antes de valid_from
    # continua visível sem retroagir a validade do vínculo vivo.
    canonical_query: dict[str, Any] = {"assignment_id": assignment_id}
    if not include_deleted:
        canonical_query["deleted"] = False
    if resolved_class_id:
        canonical_query["class_id"] = resolved_class_id
    if resolved_component_id:
        canonical_query["component_id"] = resolved_component_id
    if date:
        canonical_query["date"] = date

    canonical_candidates = await db.content_entries.find(
        canonical_query, {"_id": 0}
    ).to_list(2000)
    canonical_visible = await filter_visible_content_entries(
        db,
        current_user,
        canonical_candidates,
        active_mantenedora_id=active_mantenedora_id,
    )
    canonical_items = [
        _canonical_public(item, valid_from=valid_from)
        for item in canonical_visible
    ]

    legacy_items: list[dict] = []
    legacy_date_allowed = not date or str(date) < str(valid_from)
    if legacy_date_allowed:
        # No contrato legado, a linha do tempo pedagógica era da turma/componente;
        # ``recorded_by`` identificava quem efetuou a gravação, mas não restringia
        # a leitura. O DVD já prova o acesso à turma/componente pelo assignment.
        # Reaplicar recorded_by aqui escondia registros legítimos feitos por
        # coordenação, administração, conta anterior ou outro responsável histórico.
        legacy_query: dict[str, Any] = {
            "class_id": resolved_class_id,
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

    # Backfill canônico prevalece sobre o legado equivalente. Isso evita duas
    # linhas para a mesma data quando um lançamento histórico foi reconstruído
    # pelo motor novo.
    canonical_historical_keys = {
        _semantic_key(item)
        for item in canonical_items
        if item.get("historical_backfill") is True
    }
    legacy_items = [
        item for item in legacy_items
        if _semantic_key(item) not in canonical_historical_keys
    ]

    # Deduplicação por origem+id continua como proteção adicional.
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
            "historical_backfill_enabled": True,
        },
    }
