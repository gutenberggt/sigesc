"""Domínio de Notas/Conceitos por Vínculo Docente — DVD Fase 5.

A coleção ``grades`` continua sendo a fonte canônica e mantém um documento por
estudante/turma/componente/ano. Como esse documento contém vários períodos, a
autoria pedagógica NÃO pode ser representada por um ``assignment_id`` único no
documento inteiro. A proveniência é persistida por dado em ``grade_ownership``.

Exemplo::

    grade_ownership = {
        "b1": {<snapshot do assignment A>},
        "b2": {<snapshot do assignment B>},
    }

Valores, escalas conceituais e regras de cálculo existentes não são alterados.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    DiaryAssignmentAccessContext,
    authorize_assignment_access,
)
from services.diary_assignment_contract import DiaryProfile, StudentScope
from services.diary_assignment_snapshot_access import (
    DiaryAssignmentSnapshotAccessError,
    authorize_assignment_snapshot_access,
)

GRADE_VALUE_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery")
GRADE_OWNERSHIP_FIELDS = GRADE_VALUE_FIELDS + ("observations",)
GRADE_PERIOD = {
    "b1": 1,
    "b2": 2,
    "b3": 3,
    "b4": 4,
    "rec_s1": 2,
    "rec_s2": 4,
    "recovery": 4,
}


class GradeAssignmentScopeError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GradeAssignmentContext:
    access: DiaryAssignmentAccessContext
    assignment_id: str
    class_id: str
    course_id: str
    profile: DiaryProfile
    student_scope: StudentScope
    snapshot: Mapping[str, Any]

    @property
    def assignment(self) -> Mapping[str, Any]:
        return self.access.assignment

    @property
    def class_info(self) -> Mapping[str, Any]:
        return self.access.class_info


def _scope_error(exc: Exception) -> GradeAssignmentScopeError:
    code = getattr(exc, "code", "GRADE_ASSIGNMENT_ACCESS_DENIED")
    message = getattr(exc, "message", str(exc))
    return GradeAssignmentScopeError(code, message)


def _snapshot_from_access(access: DiaryAssignmentAccessContext, course_id: str) -> dict[str, Any]:
    assignment = access.assignment
    klass = access.class_info
    return {
        "assignment_id": assignment.get("id"),
        "assignment_profile_at_record": access.settings.profile.value,
        "assignment_schema_version_at_record": access.settings.schema_version,
        "teacher_id": assignment.get("teacher_id"),
        "teacher_name": assignment.get("teacher_name"),
        "class_id": assignment.get("class_id"),
        # O dado avaliativo pertence ao componente efetivamente avaliado. Em
        # vínculos de regência, assignment.component_id pode ser None.
        "component_id": course_id,
        "assignment_component_id": assignment.get("component_id"),
        "school_id": klass.get("school_id") or assignment.get("school_id"),
        "mantenedora_id": klass.get("mantenedora_id") or assignment.get("mantenedora_id"),
    }


def _periods_overlap(valid_from: Optional[str], valid_until: Optional[str], start: str, end: str) -> bool:
    if not valid_from:
        return False
    return max(valid_from, start) <= min(valid_until or "9999-12-31", end)


def assignment_overlaps_grade_period(
    assignment: Mapping[str, Any],
    field: str,
    periods: Mapping[int, tuple[str, str]],
) -> bool:
    """Confirma que o vínculo teve vigência no período pedagógico do dado.

    ``observations`` não possui período próprio e é autorizado pela vigência
    corrente do assignment. Campos bimestrais/recuperações exigem interseção com
    o período correspondente, impedindo que um vínculo iniciado em B3 reivindique
    automaticamente B1/B2.
    """
    period_number = GRADE_PERIOD.get(field)
    if period_number is None:
        return True
    period = periods.get(period_number)
    if not period:
        # Sem calendário confiável, não inventamos intervalo para autoria.
        return False
    return _periods_overlap(
        str(assignment.get("valid_from") or "")[:10] or None,
        str(assignment.get("valid_until") or "")[:10] or None,
        period[0],
        period[1],
    )


async def _enforce_shared_grade_owner(
    db,
    access: DiaryAssignmentAccessContext,
    *,
    course_id: str,
    on_date: str,
) -> None:
    if access.settings.profile is not DiaryProfile.SHARED:
        return
    if access.settings.student_scope is StudentScope.GROUP:
        raise GradeAssignmentScopeError(
            "GRADE_GROUP_SCOPE_UNRESOLVED",
            "Vínculo shared/group não pode lançar avaliação até existir lista canônica e auditável dos membros.",
        )

    assignment = access.assignment
    class_id = assignment.get("class_id")
    # A responsabilidade oficial de avaliação em co-docência é explícita. Um
    # flag top-level no próprio teacher_class_assignment evita coleção paralela.
    owners = await db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "diary_settings.profile": DiaryProfile.SHARED.value,
            "grades_official_owner": True,
            "valid_from": {"$lte": on_date},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": on_date}}],
        },
        {"_id": 0, "id": 1, "component_id": 1},
    ).to_list(50)
    owners = [
        item for item in owners
        if item.get("component_id") in (None, course_id)
    ]
    if not owners:
        raise GradeAssignmentScopeError(
            "SHARED_GRADE_OWNER_REQUIRED",
            "Vínculo shared exige um único assignment marcado como responsável oficial pela avaliação.",
        )
    if len(owners) != 1:
        raise GradeAssignmentScopeError(
            "SHARED_GRADE_OWNER_AMBIGUOUS",
            "Há mais de um vínculo shared marcado como responsável oficial pela avaliação.",
        )
    if owners[0].get("id") != assignment.get("id"):
        raise GradeAssignmentScopeError(
            "SHARED_GRADE_OWNER_DENIED",
            "Este vínculo shared não é o responsável oficial pela avaliação.",
        )


async def resolve_grade_assignment(
    db,
    current_user: Mapping[str, Any],
    assignment_id: str,
    *,
    class_id: str,
    course_id: str,
    on_date: Optional[str] = None,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> GradeAssignmentContext:
    reference_date = on_date or date.today().isoformat()
    try:
        access = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=DiaryAction.GRADES,
            on_date=reference_date,
            expected_class_id=class_id,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise _scope_error(exc) from exc

    assignment_component = access.assignment.get("component_id")
    if assignment_component not in (None, course_id):
        raise GradeAssignmentScopeError(
            "COMPONENT_MISMATCH",
            "O vínculo não pertence ao componente avaliado.",
        )

    await _enforce_shared_grade_owner(
        db,
        access,
        course_id=course_id,
        on_date=reference_date,
    )
    snapshot = _snapshot_from_access(access, course_id)
    return GradeAssignmentContext(
        access=access,
        assignment_id=assignment_id,
        class_id=class_id,
        course_id=course_id,
        profile=access.settings.profile,
        student_scope=access.settings.student_scope,
        snapshot=snapshot,
    )


async def resolve_own_grade_assignment(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    course_id: str,
    on_date: Optional[str] = None,
    active_mantenedora_id: Optional[str] = None,
) -> Optional[GradeAssignmentContext]:
    """Resolve automaticamente o assignment do professor quando não há spoof do frontend.

    Retorna ``None`` apenas quando não existe DVD próprio aplicável. Múltiplos
    vínculos válidos falham fechado. Perfis sem capability de notas são ignorados
    como candidatos, mas a existência de um vínculo grade-capable ambíguo nunca é
    arbitrada por ordem de consulta.
    """
    reference_date = on_date or date.today().isoformat()
    teacher_id = current_user.get("id")
    if not teacher_id:
        return None
    cursor = db.teacher_class_assignments.find(
        {
            "teacher_id": teacher_id,
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "valid_from": {"$lte": reference_date},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": reference_date}}],
        },
        {"_id": 0, "id": 1, "component_id": 1},
    )
    candidates = await cursor.to_list(100)
    contexts: list[GradeAssignmentContext] = []
    hard_errors: list[GradeAssignmentScopeError] = []
    for item in candidates:
        if item.get("component_id") not in (None, course_id):
            continue
        try:
            context = await resolve_grade_assignment(
                db,
                current_user,
                item["id"],
                class_id=class_id,
                course_id=course_id,
                on_date=reference_date,
                active_mantenedora_id=active_mantenedora_id,
            )
            contexts.append(context)
        except GradeAssignmentScopeError as exc:
            # Integrator/CAPABILITY_DENIED não é candidato de avaliação. Erros de
            # owner shared, tenant ou inconsistência são relevantes e fail-closed.
            if exc.code == "CAPABILITY_DENIED":
                continue
            hard_errors.append(exc)

    if len(contexts) == 1:
        return contexts[0]
    if len(contexts) > 1:
        raise GradeAssignmentScopeError(
            "GRADE_ASSIGNMENT_AMBIGUOUS",
            "Há mais de um vínculo docente válido para esta avaliação; a gestão deve reconciliar a responsabilidade.",
        )
    if hard_errors:
        raise hard_errors[0]
    return None


def changed_grade_fields(existing: Optional[Mapping[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any]:
    existing = existing or {}
    changes: dict[str, Any] = {}
    for field in GRADE_OWNERSHIP_FIELDS:
        if field not in payload:
            continue
        incoming = payload.get(field)
        if existing.get(field) != incoming:
            changes[field] = incoming
    return changes


async def apply_grade_field_ownership(
    db,
    current_user: Mapping[str, Any],
    existing: Optional[Mapping[str, Any]],
    changes: Mapping[str, Any],
    context: GradeAssignmentContext,
    *,
    periods: Mapping[int, tuple[str, str]],
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> dict[str, Any]:
    """Valida escrita e devolve o mapa de ownership resultante.

    - campo legado não-nulo sem proveniência nunca é apropriado automaticamente;
    - professor só altera campo pertencente ao próprio assignment;
    - correção gerencial preserva owner já existente e não reivindica legado;
    - campo novo recebe snapshot imutável do vínculo responsável;
    - vínculo precisa ter interseção com o período pedagógico do campo.
    """
    existing = existing or {}
    ownership = dict(existing.get("grade_ownership") or {})

    for field, new_value in changes.items():
        if field not in GRADE_OWNERSHIP_FIELDS:
            continue
        if not assignment_overlaps_grade_period(context.assignment, field, periods):
            raise GradeAssignmentScopeError(
                "GRADE_PERIOD_OUTSIDE_ASSIGNMENT",
                f"O vínculo não possui vigência no período correspondente a {field}.",
            )

        owner = ownership.get(field)
        if owner:
            owner_assignment_id = owner.get("assignment_id")
            if owner_assignment_id != context.assignment_id and not allow_management_override:
                raise GradeAssignmentScopeError(
                    "GRADE_FIELD_OWNED_BY_OTHER_ASSIGNMENT",
                    f"O campo {field} pertence a outro vínculo docente.",
                )
            try:
                await authorize_assignment_snapshot_access(
                    db,
                    current_user,
                    owner,
                    action=DiaryAction.GRADES,
                    allow_management_override=allow_management_override,
                    active_mantenedora_id=active_mantenedora_id,
                )
            except DiaryAssignmentSnapshotAccessError as exc:
                raise _scope_error(exc) from exc
            # Correções não mudam autoria pedagógica.
            continue

        old_value = existing.get(field)
        if old_value is not None and not allow_management_override:
            raise GradeAssignmentScopeError(
                "GRADE_LEGACY_FIELD_REQUIRES_REVIEW",
                f"O campo {field} possui valor legado sem proveniência e não será atribuído automaticamente.",
            )

        # Gestão pode corrigir legado sem converter autoria operacional em autoria
        # pedagógica. O campo permanece sem ownership até reconciliação própria.
        if allow_management_override:
            continue

        # Não cria autoria para uma ausência que continua ausente.
        if old_value is None and new_value is None:
            continue
        ownership[field] = dict(context.snapshot)

    return ownership


def ownership_for_field(grade: Mapping[str, Any], field: str) -> Optional[Mapping[str, Any]]:
    return (grade.get("grade_ownership") or {}).get(field)


def owned_fields_for_assignment(grade: Mapping[str, Any], assignment_id: str) -> set[str]:
    return {
        field
        for field, snapshot in (grade.get("grade_ownership") or {}).items()
        if isinstance(snapshot, Mapping) and snapshot.get("assignment_id") == assignment_id
    }
