"""Projeção read-only de Conteúdo para professor em cutover parcial DVD.

A SSoT desta camada é o conjunto de componentes ativos em ``teacher_assignments``
(o mesmo entitlement usado por ``GET /professor/turmas``). Para cada componente
alocado, a leitura escolhe uma única origem efetiva:

- componente coberto por Diário por Vínculo (DVD): histórico canônico via
  ``list_assignment_content_history``;
- componente ainda sem Diário por Vínculo: ``learning_objects`` legado,
  estritamente filtrado pelo conjunto de componentes alocados ao professor.

O serviço nunca escreve, migra, remapeia ou cria vínculos. Em especial, ele não
abre a leitura class-wide do legado: o fallback é sempre limitado ao conjunto
explícito de ``course_id`` autorizados para professor + turma + ano + tenant.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from services.content_history_bridge import (
    ContentHistoryBridgeError,
    list_assignment_content_history,
)
from services.teacher_diaries import list_teacher_diaries


class ProfessorContentProjectionError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _normalize_legacy(record: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(record)
    item.pop("_id", None)
    component_id = item.get("course_id") or item.get("component_id")
    item["course_id"] = component_id
    item["component_id"] = component_id
    item["teacher_id"] = item.get("recorded_by")
    item["assignment_id"] = None
    item["source"] = "learning_objects"
    item["legacy"] = True
    item["read_only"] = True
    item["historical_backfill"] = False
    return item


def _in_requested_period(
    item: Mapping[str, Any],
    *,
    academic_year: int,
    month: Optional[int],
    date: Optional[str],
) -> bool:
    item_date = _norm(item.get("date"))[:10]
    if date and item_date != _norm(date)[:10]:
        return False

    item_year = item.get("academic_year")
    if item_year not in (None, ""):
        try:
            if int(item_year) != int(academic_year):
                return False
        except (TypeError, ValueError):
            return False
    elif item_date and not item_date.startswith(f"{academic_year:04d}-"):
        return False

    if month:
        return len(item_date) >= 7 and item_date[5:7] == f"{int(month):02d}"
    return True


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items.sort(
        key=lambda item: (
            item.get("aula_numero") is None,
            item.get("aula_numero") if item.get("aula_numero") is not None else 0,
        )
    )
    items.sort(key=lambda item: _norm(item.get("date")), reverse=True)
    return items


async def _resolve_staff(
    db,
    current_user: Mapping[str, Any],
    *,
    mantenedora_id: str,
) -> Optional[dict[str, Any]]:
    projection = {"_id": 0, "id": 1, "mantenedora_id": 1}
    user_id = _norm(current_user.get("id"))
    if user_id:
        staff = await db.staff.find_one(
            {"user_id": user_id, "mantenedora_id": mantenedora_id},
            projection,
        )
        if staff:
            return staff

    email = _norm(current_user.get("email"))
    if email:
        return await db.staff.find_one(
            {"email": email, "mantenedora_id": mantenedora_id},
            projection,
        )
    return None


async def _active_entitled_course_ids(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    academic_year: int,
    mantenedora_id: str,
) -> set[str]:
    staff = await _resolve_staff(db, current_user, mantenedora_id=mantenedora_id)
    if not staff or not staff.get("id"):
        return set()

    assignments = await db.teacher_assignments.find(
        {
            "staff_id": staff["id"],
            "class_id": class_id,
            "academic_year": academic_year,
            "status": "ativo",
            "mantenedora_id": mantenedora_id,
        },
        {"_id": 0, "course_id": 1},
    ).to_list(1000)
    return {_norm(row.get("course_id")) for row in assignments if _norm(row.get("course_id"))}


async def list_professor_content_projection(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    academic_year: Optional[int] = None,
    month: Optional[int] = None,
    date: Optional[str] = None,
    active_mantenedora_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Compõe a visão class-wide do professor sem ampliar entitlement.

    O retorno preserva o contrato histórico de ``GET /learning-objects`` (lista
    plana), mas cada componente é projetado da fonte efetiva correta. O caso
    crítico F2.7 é 7 componentes DVD + 2 legados: os nove permanecem visíveis
    numa única leitura, sem tornar o reader legado class-wide irrestrito.
    """
    if current_user.get("role") != "professor":
        raise ProfessorContentProjectionError(
            "PROFESSOR_ROLE_REQUIRED",
            "A projeção mista de conteúdo é exclusiva do perfil professor.",
        )

    mantenedora_id = _norm(active_mantenedora_id or current_user.get("mantenedora_id"))
    if not mantenedora_id:
        raise ProfessorContentProjectionError(
            "TENANT_SCOPE_REQUIRED",
            "Não foi possível determinar a mantenedora ativa do professor.",
        )

    year = int(academic_year or datetime.now().year)
    class_doc = await db.classes.find_one(
        {"id": class_id, "mantenedora_id": mantenedora_id},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    )
    if not class_doc:
        raise ProfessorContentProjectionError(
            "CLASS_NOT_FOUND_IN_TENANT",
            "Turma não encontrada no escopo da mantenedora ativa.",
        )

    entitled_course_ids = await _active_entitled_course_ids(
        db,
        current_user,
        class_id=class_id,
        academic_year=year,
        mantenedora_id=mantenedora_id,
    )
    if not entitled_course_ids:
        return []

    diaries_payload = await list_teacher_diaries(
        db,
        current_user,
        academic_year=year,
        active_mantenedora_id=mantenedora_id,
    )
    content_diaries = [
        item
        for item in (diaries_payload.get("items") or [])
        if item.get("class_id") == class_id
        and item.get("capabilities", {}).get("content_enabled") is True
        and item.get("assignment_id")
        and (
            not item.get("component_id")
            or _norm(item.get("component_id")) in entitled_course_ids
        )
    ]

    # Um vínculo class-wide canônico cobre todos os componentes já autorizados
    # no teacher_assignments. Vínculos específicos cobrem somente seu component_id.
    has_classwide_diary = any(not item.get("component_id") for item in content_diaries)
    if has_classwide_diary:
        canonical_course_ids = set(entitled_course_ids)
    else:
        canonical_course_ids = {
            _norm(item.get("component_id"))
            for item in content_diaries
            if _norm(item.get("component_id")) in entitled_course_ids
        }

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for diary in content_diaries:
        try:
            history = await list_assignment_content_history(
                db,
                current_user,
                assignment_id=diary["assignment_id"],
                class_id=class_id,
                component_id=diary.get("component_id") or None,
                active_mantenedora_id=mantenedora_id,
            )
        except ContentHistoryBridgeError as exc:
            # Nunca fazer fallback silencioso para legado quando um componente
            # já está sob governança canônica: falha fechada evita exibir uma
            # origem incorreta ou conteúdo pós-cutover indevido.
            raise ProfessorContentProjectionError(
                "CANONICAL_CONTENT_HISTORY_UNAVAILABLE",
                f"Não foi possível compor o histórico canônico ({exc.code}).",
            ) from exc

        for raw in history.get("items") or []:
            item = dict(raw)
            component_id = _norm(item.get("component_id") or item.get("course_id"))
            if component_id not in entitled_course_ids:
                continue
            if not _in_requested_period(item, academic_year=year, month=month, date=date):
                continue
            key = (
                _norm(item.get("source")),
                _norm(item.get("id")),
                component_id,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    legacy_only_course_ids = entitled_course_ids - canonical_course_ids
    if legacy_only_course_ids:
        legacy_query: dict[str, Any] = {
            "class_id": class_id,
            "course_id": {"$in": sorted(legacy_only_course_ids)},
            "academic_year": year,
            "mantenedora_id": mantenedora_id,
        }
        if date:
            legacy_query["date"] = _norm(date)[:10]
        elif month:
            start_date = f"{year}-{int(month):02d}-01"
            if int(month) == 12:
                end_date = f"{year + 1}-01-01"
            else:
                end_date = f"{year}-{int(month) + 1:02d}-01"
            legacy_query["date"] = {"$gte": start_date, "$lt": end_date}

        legacy_rows = await db.learning_objects.find(
            legacy_query,
            {"_id": 0},
        ).to_list(5000)
        for raw in legacy_rows:
            item = _normalize_legacy(raw)
            component_id = _norm(item.get("course_id"))
            if component_id not in legacy_only_course_ids:
                continue
            if not _in_requested_period(item, academic_year=year, month=month, date=date):
                continue
            key = ("learning_objects", _norm(item.get("id")), component_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    course_ids = sorted({
        _norm(item.get("course_id") or item.get("component_id"))
        for item in merged
        if _norm(item.get("course_id") or item.get("component_id"))
    })
    course_names: dict[str, str] = {}
    if course_ids:
        courses = await db.courses.find(
            {"id": {"$in": course_ids}, "mantenedora_id": mantenedora_id},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(course_ids))
        course_names = {
            _norm(course.get("id")): str(course.get("name") or "")
            for course in courses
        }

    class_name = str(class_doc.get("name") or "")
    for item in merged:
        component_id = _norm(item.get("course_id") or item.get("component_id"))
        item["class_name"] = item.get("class_name") or class_name
        item["course_name"] = item.get("course_name") or course_names.get(component_id, "")

    return _sort_items(merged)
