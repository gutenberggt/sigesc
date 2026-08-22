"""Escopo do Registro de Conteúdos por vínculo docente — DVD Fase 2."""

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessContext,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)
from services.diary_assignment_snapshot_access import (
    DiaryAssignmentSnapshotAccessError,
    authorize_assignment_snapshot_access,
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
    historical_backfill: bool = False


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
    if component_id is None:
        # Não permitir que omitir o componente transforme contexto DVD em legado.
        # Assignments class-wide continuam compatíveis; assignments específicos
        # permanecem visíveis ao resolvedor para produzir erro em vez de fallback.
        class_wide = [a for a in items if a.get("component_id") is None]
        return class_wide or items
    return [a for a in items if _component_matches(a.get("component_id"), component_id)]


async def _historical_dvd_assignments(
    db,
    class_id: str,
    component_id: Optional[str],
    on_date: str,
) -> list[dict]:
    """Vínculos DVD posteriores à data pedagógica, usados apenas para backfill.

    O cutover de 18/08/2026 não pode impedir que o professor complete conteúdos
    de datas anteriores. A propriedade pedagógica é provada por um vínculo DVD
    posterior da mesma turma/componente, sem fingir que ele já estava vigente na
    data do conteúdo.
    """
    items = await db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
        },
        {"_id": 0},
    ).to_list(500)

    historical = [
        item
        for item in items
        if item.get("valid_from")
        and str(on_date) < str(item.get("valid_from"))
        and _component_matches(item.get("component_id"), component_id)
    ]

    if component_id is None:
        class_wide = [a for a in historical if a.get("component_id") is None]
        return class_wide or historical

    # Vínculo específico tem precedência sobre class-wide, espelhando a intenção
    # do resolver de frontend e evitando ambiguidade artificial.
    exact = [a for a in historical if a.get("component_id") == component_id]
    return exact or [a for a in historical if a.get("component_id") is None]


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


async def _validate_existing_assignment_provenance(
    db,
    context: DiaryAssignmentAccessContext,
    *,
    class_id: str,
    component_id: Optional[str],
    on_date: str,
) -> None:
    """Falha fechado se já houver conteúdo DVD com autoria incompatível."""
    collection = getattr(db, "content_entries", None)
    if collection is None:
        return
    query = {
        "assignment_id": context.assignment.get("id"),
        "class_id": class_id,
        "component_id": component_id,
        "date": on_date,
        "deleted": False,
    }
    cursor = collection.find(query, {"_id": 0, "teacher_id": 1})
    existing = await cursor.to_list(100)
    owner_teacher_id = context.assignment.get("teacher_id")
    if any(item.get("teacher_id") != owner_teacher_id for item in existing):
        raise ContentAssignmentScopeError(
            "CONTENT_PROVENANCE_MISMATCH",
            "Existe conteúdo com autoria incompatível com o vínculo docente; reconciliação é necessária.",
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
    """Autoriza CRIAÇÃO/upsert usando o vínculo vivo e vigente."""
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
    await _validate_existing_assignment_provenance(
        db,
        context,
        class_id=class_id,
        component_id=component_id,
        on_date=on_date,
    )
    return context


async def _authorize_historical_content_assignment(
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
    """Autoriza backfill anterior ao início do DVD sem alterar sua vigência.

    A autorização de propriedade/capability é verificada na própria data inicial
    do vínculo. A data pedagógica continua sendo a data histórica informada.
    Datas posteriores ao fim do vínculo NÃO entram neste fallback.
    """
    assignment = await db.teacher_class_assignments.find_one(
        {"id": assignment_id, "deleted": False}, {"_id": 0}
    )
    if not assignment:
        raise ContentAssignmentScopeError(
            "ASSIGNMENT_NOT_FOUND", "Vínculo docente não encontrado ou inativo por exclusão."
        )

    valid_from = assignment.get("valid_from")
    if not valid_from or str(on_date) >= str(valid_from):
        raise ContentAssignmentScopeError(
            "ASSIGNMENT_NOT_ACTIVE", "O vínculo não está vigente na data solicitada."
        )

    try:
        context = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=DiaryAction.CONTENT,
            on_date=str(valid_from),
            expected_class_id=class_id,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise ContentAssignmentScopeError(exc.code, exc.message) from exc

    _validate_snapshot(context, component_id, provided_teacher_id)
    await _validate_existing_assignment_provenance(
        db,
        context,
        class_id=class_id,
        component_id=component_id,
        on_date=on_date,
    )
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
    """Resolve o vínculo para uma nova escrita.

    Regra P0 pós-cutover: se a data pedagógica é anterior ao ``valid_from`` do
    vínculo DVD atual, o mesmo vínculo pode provar a propriedade para um backfill
    histórico. O vínculo não é retrodatado; a autorização ocorre em ``valid_from``
    e o registro conserva sua data pedagógica original.
    """
    if assignment_id:
        try:
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
            historical_backfill = False
        except ContentAssignmentScopeError as exc:
            if exc.code != "ASSIGNMENT_NOT_ACTIVE":
                raise
            context = await _authorize_historical_content_assignment(
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
            historical_backfill = True

        assignment = context.assignment
        return ContentAssignmentResolution(
            True,
            assignment.get("id"),
            assignment.get("teacher_id"),
            assignment.get("teacher_name"),
            context,
            historical_backfill=historical_backfill,
        )

    candidates = await _active_dvd_assignments(db, class_id, component_id, on_date)
    if candidates:
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
            historical_backfill=False,
        )

    # Nenhum vínculo era vigente na data. Antes de cair no modo sem assignment,
    # procura vínculo DVD posterior da mesma turma/componente. Isso cobre o
    # preenchimento retroativo anterior ao cutover e mantém o endpoint fail-closed.
    historical_candidates = await _historical_dvd_assignments(
        db, class_id, component_id, on_date
    )
    if historical_candidates:
        own_candidates = [
            a for a in historical_candidates
            if a.get("teacher_id") == current_user.get("id")
        ]
        if len(own_candidates) != 1:
            code = (
                "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS"
                if len(own_candidates) > 1
                else "DVD_CONTENT_ASSIGNMENT_REQUIRED"
            )
            message = (
                "Há mais de um vínculo docente posterior compatível; informe assignment_id explicitamente."
                if len(own_candidates) > 1
                else "A turma/componente possui vínculo DVD posterior; informe um assignment_id autorizado."
            )
            raise ContentAssignmentScopeError(code, message)

        context = await _authorize_historical_content_assignment(
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
            historical_backfill=True,
        )

    return ContentAssignmentResolution(
        False, None, provided_teacher_id or current_user.get("id"), None, None,
        historical_backfill=False,
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
    """Autoriza registro já persistido por snapshot histórico imutável."""
    if not entry.get("assignment_id"):
        return None
    try:
        return await authorize_assignment_snapshot_access(
            db,
            current_user,
            entry,
            action=action,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentSnapshotAccessError as exc:
        raise ContentAssignmentScopeError(exc.code, exc.message) from exc


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
