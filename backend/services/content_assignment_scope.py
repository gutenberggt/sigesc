"""Escopo do Registro de Conteúdos por vínculo docente — DVD Fase 2."""

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessContext,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)


class ContentAssignmentScopeError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ContentAssignmentResolution:
    dvd_enabled: bool
    assignment_id: Optional[str]
    teacher_id: Optional[str]
    teacher_name: Optional[str]
    access_context: Optional[DiaryAssignmentAccessContext]


def _component_matches(assignment_component_id: Optional[str], component_id: Optional[str]) -> bool:
    return assignment_component_id is None or assignment_component_id == component_id


async def _active_dvd_assignments(db, class_id: str, component_id: Optional[str], on_date: str) -> list[dict]:
    query = {
        "class_id": class_id,
        "deleted": False,
        "diary_settings.enabled": True,
        "valid_from": {"$lte": on_date},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": on_date}}],
    }
    items = await db.teacher_class_assignments.find(query, {"_id": 0}).to_list(500)
    return [a for a in items if _component_matches(a.get("component_id"), component_id)]


def _validate_snapshot(context, component_id: Optional[str], provided_teacher_id: Optional[str] = None):
    assignment = context.assignment
    if not _component_matches(assignment.get("component_id"), component_id):
        raise ContentAssignmentScopeError(
            "CONTENT_COMPONENT_MISMATCH",
            "O vínculo docente não autoriza o componente informado para o conteúdo.",
        )
    if provided_teacher_id and provided_teacher_id != assignment.get("teacher_id"):
        raise ContentAssignmentScopeError(
            "CONTENT_TEACHER_MISMATCH",
            "teacher_id informado diverge do professor proprietário do vínculo docente.",
        )


async def _authorize_content_assignment(
    db,
    current_user: Mapping[str, Any],
    assignment_id: str,
    *,
    class_id: str,
    component_id: Optional[str],
    on_date: str,
    provided_teacher_id: Optional[str] = None,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
):
    try:
        context = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=DiaryAction.CONTENT,
            on_date=on_date,
            expected_class_id=class_id,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise ContentAssignmentScopeError(exc.code, exc.message) from exc
    _validate_snapshot(context, component_id, provided_teacher_id)
    return context


async def resolve_content_assignment_for_create(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    component_id: Optional[str],
    on_date: str,
    assignment_id: Optional[str] = None,
    provided_teacher_id: Optional[str] = None,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> ContentAssignmentResolution:
    if assignment_id:
        context = await _authorize_content_assignment(
            db,
            current_user,
            assignment_id,
            class_id=class_id,
            component_id=component_id,
            on_date=on_date,
            provided_teacher_id=provided_teacher_id,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
        assignment = context.assignment
        return ContentAssignmentResolution(
            True,
            assignment.get("id"),
            assignment.get("teacher_id"),
            assignment.get("teacher_name"),
            context,
        )

    candidates = await _active_dvd_assignments(db, class_id, component_id, on_date)
    if not candidates:
        return ContentAssignmentResolution(
            False, None, provided_teacher_id or current_user.get("id"), None, None
        )

    own_candidates = [a for a in candidates if a.get("teacher_id") == current_user.get("id")]
    if len(own_candidates) != 1:
        code = (
            "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS"
            if len(own_candidates) > 1
            else "DVD_CONTENT_ASSIGNMENT_REQUIRED"
        )
        message = (
            "Há mais de um vínculo docente compatível; informe assignment_id explicitamente."
            if len(own_candidates) > 1
            else "A turma/componente está no Diário por Vínculo; informe um assignment_id autorizado."
        )
        raise ContentAssignmentScopeError(code, message)

    context = await _authorize_content_assignment(
        db,
        current_user,
        own_candidates[0]["id"],
        class_id=class_id,
        component_id=component_id,
        on_date=on_date,
        provided_teacher_id=provided_teacher_id,
        active_mantenedora_id=active_mantenedora_id,
    )
    assignment = context.assignment
    return ContentAssignmentResolution(
        True,
        assignment.get("id"),
        assignment.get("teacher_id"),
        assignment.get("teacher_name"),
        context,
    )


async def authorize_content_record(
    db,
    current_user: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    action: DiaryAction | str = DiaryAction.VIEW,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
):
    assignment_id = entry.get("assignment_id")
    if not assignment_id:
        return None
    try:
        context = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=action,
            on_date=entry.get("date"),
            expected_class_id=entry.get("class_id"),
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise ContentAssignmentScopeError(exc.code, exc.message) from exc
    _validate_snapshot(context, entry.get("component_id"))
    if entry.get("teacher_id") != context.assignment.get("teacher_id"):
        raise ContentAssignmentScopeError(
            "CONTENT_PROVENANCE_MISMATCH",
            "A autoria persistida do conteúdo diverge do vínculo docente informado.",
        )
    return context


async def filter_visible_content_entries(
    db,
    current_user: Mapping[str, Any],
    entries: list[dict],
    *,
    active_mantenedora_id: Optional[str] = None,
) -> list[dict]:
    visible = []
    for entry in entries:
        if not entry.get("assignment_id"):
            visible.append(entry)
            continue
        try:
            await authorize_content_record(
                db,
                current_user,
                entry,
                action=DiaryAction.VIEW,
                active_mantenedora_id=active_mantenedora_id,
            )
        except ContentAssignmentScopeError:
            continue
        visible.append(entry)
    return visible
