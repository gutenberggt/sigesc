"""Escopo canônico da Frequência por Vínculo Docente — DVD Fase 4.

A frequência oficial permanece na coleção histórica `attendance`. Registros
`pdf_only` do perfil integrador são fisicamente isolados em
`attendance_documentary`, reforçando a invariante de que jamais produzem efeitos
acadêmicos/estatísticos.

Esta camada não conhece FastAPI. Ela resolve vínculo, modo, natureza, sessão,
snapshot histórico e índices lógicos para os consumidores HTTP/offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)
from services.diary_assignment_contract import (
    AttendanceMode,
    AttendancePurpose,
    DiaryProfile,
    StudentScope,
    capabilities_for,
)
from services.diary_assignment_snapshot_access import (
    DiaryAssignmentSnapshotAccessError,
    HistoricalDiaryAssignmentAccessContext,
    authorize_assignment_snapshot_access,
)


OFFICIAL_ATTENDANCE_COLLECTION = "attendance"
DOCUMENTARY_ATTENDANCE_COLLECTION = "attendance_documentary"
ASSIGNMENT_SESSION_KEY_SCOPE = "assignment_session"


class AttendanceAssignmentScopeError(PermissionError):
    """Erro estável da integração DVD/Frequência."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AttendanceAssignmentContext:
    assignment: Mapping[str, Any]
    class_info: Mapping[str, Any]
    profile: DiaryProfile
    student_scope: StudentScope
    attendance_mode: AttendanceMode
    attendance_purpose: AttendancePurpose
    effective_course_id: Optional[str]
    session_slots: tuple[Mapping[str, Any], ...]
    storage_collection: str
    snapshot: Mapping[str, Any]

    @property
    def is_official(self) -> bool:
        return self.attendance_purpose is AttendancePurpose.OFFICIAL


@dataclass(frozen=True)
class HistoricalAttendanceContext:
    historical_access: HistoricalDiaryAssignmentAccessContext
    attendance_mode: AttendanceMode
    attendance_purpose: AttendancePurpose
    student_scope: StudentScope
    storage_collection: str


def _scope_error(exc: Exception) -> AttendanceAssignmentScopeError:
    return AttendanceAssignmentScopeError(
        getattr(exc, "code", "ATTENDANCE_ASSIGNMENT_ACCESS_DENIED"),
        getattr(exc, "message", str(exc)),
    )


def _session_slots_for_date(assignment: Mapping[str, Any], on_date: str) -> tuple[Mapping[str, Any], ...]:
    """Retorna os slots do vínculo no dia da semana da data, ordenados.

    `weekly_slots.weekday` usa ISO 1=segunda ... 7=domingo. O vínculo pode ter
    mais de um slot no mesmo dia; nesse caso o chamador deverá escolher
    explicitamente `aula_numero` para não colapsar duas sessões diferentes.
    """
    try:
        weekday = date.fromisoformat(on_date[:10]).isoweekday()
    except (TypeError, ValueError) as exc:
        raise AttendanceAssignmentScopeError(
            "INVALID_ATTENDANCE_DATE", "Data da frequência deve usar YYYY-MM-DD."
        ) from exc

    matches = []
    seen = set()
    for raw in assignment.get("weekly_slots") or []:
        if raw.get("weekday") != weekday:
            continue
        key = (raw.get("aula_numero"), raw.get("start_time"), raw.get("end_time"))
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "aula_numero": raw.get("aula_numero"),
            "start_time": raw.get("start_time"),
            "end_time": raw.get("end_time"),
        })
    matches.sort(key=lambda s: (
        s.get("aula_numero") if s.get("aula_numero") is not None else 999,
        s.get("start_time") or "",
    ))
    return tuple(matches)


def _build_snapshot(
    assignment: Mapping[str, Any],
    class_info: Mapping[str, Any],
    *,
    profile: DiaryProfile,
    student_scope: StudentScope,
    schema_version: int,
) -> dict:
    return {
        "assignment_id": assignment.get("id"),
        "assignment_profile_at_record": profile.value,
        "assignment_schema_version_at_record": schema_version,
        "assignment_student_scope_at_record": student_scope.value,
        "teacher_id": assignment.get("teacher_id"),
        "teacher_name": assignment.get("teacher_name"),
        "class_id": assignment.get("class_id"),
        "component_id": assignment.get("component_id"),
        "school_id": class_info.get("school_id") or assignment.get("school_id"),
        "mantenedora_id": class_info.get("mantenedora_id") or assignment.get("mantenedora_id"),
    }


async def resolve_attendance_assignment(
    db,
    current_user: Mapping[str, Any],
    assignment_id: str,
    *,
    class_id: Optional[str] = None,
    on_date: Optional[str] = None,
    active_mantenedora_id: Optional[str] = None,
) -> AttendanceAssignmentContext:
    """Resolve o comportamento efetivo de frequência de um vínculo vivo.

    Anti-spoof: modo, natureza, componente e proprietário são sempre derivados
    do assignment autorizado; nenhum desses valores é aceito do cliente.
    """
    reference_date = on_date or date.today().isoformat()
    try:
        access = await authorize_assignment_access(
            db,
            current_user,
            assignment_id,
            action=DiaryAction.ATTENDANCE,
            on_date=reference_date,
            expected_class_id=class_id,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentAccessError as exc:
        raise _scope_error(exc) from exc

    settings = access.settings
    capabilities = settings.capabilities
    assignment = access.assignment
    class_info = access.class_info

    # Há contrato para group, mas ainda não há no SIGESC uma fonte de verdade
    # auditável dos membros do grupo. Liberar a turma inteira seria vazamento.
    if settings.student_scope is StudentScope.GROUP:
        raise AttendanceAssignmentScopeError(
            "ATTENDANCE_GROUP_SCOPE_UNRESOLVED",
            "Vínculo shared/group ainda não possui lista canônica de estudantes; frequência bloqueada até a gestão definir os membros do grupo.",
        )

    mode = capabilities.attendance_mode
    purpose = capabilities.attendance_purpose
    if mode is None or purpose is None:
        raise AttendanceAssignmentScopeError(
            "ATTENDANCE_CAPABILITY_INCOMPLETE",
            "Perfil do vínculo não possui modo/natureza de frequência resolvidos.",
        )

    # class_daily é canônico por turma/data: componente do vínculo não fragmenta
    # a frequência oficial. assignment_session conserva o componente do vínculo.
    effective_course_id = (
        assignment.get("component_id")
        if mode is AttendanceMode.ASSIGNMENT_SESSION
        else None
    )

    school_id = class_info.get("school_id") or assignment.get("school_id")
    tenant_id = class_info.get("mantenedora_id") or assignment.get("mantenedora_id")
    if not school_id or not tenant_id:
        raise AttendanceAssignmentScopeError(
            "ATTENDANCE_RESOURCE_SCOPE_UNRESOLVED",
            "Turma do vínculo não possui escola/mantenedora resolvíveis para frequência.",
        )

    slots = (
        _session_slots_for_date(assignment, reference_date)
        if mode is AttendanceMode.ASSIGNMENT_SESSION
        else tuple()
    )
    storage = (
        OFFICIAL_ATTENDANCE_COLLECTION
        if purpose is AttendancePurpose.OFFICIAL
        else DOCUMENTARY_ATTENDANCE_COLLECTION
    )
    snapshot = _build_snapshot(
        assignment,
        class_info,
        profile=settings.profile,
        student_scope=settings.student_scope,
        schema_version=settings.schema_version,
    )

    return AttendanceAssignmentContext(
        assignment=assignment,
        class_info=class_info,
        profile=settings.profile,
        student_scope=settings.student_scope,
        attendance_mode=mode,
        attendance_purpose=purpose,
        effective_course_id=effective_course_id,
        session_slots=slots,
        storage_collection=storage,
        snapshot=snapshot,
    )


def resolve_session_aula_numero(
    context: AttendanceAssignmentContext,
    requested_aula_numero: Optional[int],
) -> Optional[int]:
    """Valida/resolve a sessão selecionada dentro do horário do assignment."""
    if context.attendance_mode is AttendanceMode.CLASS_DAILY:
        if requested_aula_numero is not None:
            raise AttendanceAssignmentScopeError(
                "CLASS_DAILY_SESSION_FORBIDDEN",
                "Frequência class_daily não aceita sessão/aula por vínculo.",
            )
        return None

    slots = context.session_slots
    if not slots:
        # Exceções de calendário/substituições podem ocorrer fora do slot semanal;
        # há no máximo uma sessão não programada do vínculo naquela data.
        if requested_aula_numero is not None:
            raise AttendanceAssignmentScopeError(
                "ASSIGNMENT_SESSION_SLOT_INVALID",
                "Aula informada não pertence aos slots do vínculo nesta data.",
            )
        return None

    allowed = {slot.get("aula_numero") for slot in slots if slot.get("aula_numero") is not None}
    if requested_aula_numero is None:
        if len(allowed) == 1:
            return next(iter(allowed))
        raise AttendanceAssignmentScopeError(
            "ASSIGNMENT_SESSION_SLOT_REQUIRED",
            "O vínculo possui mais de uma sessão nesta data; selecione a aula antes de registrar a frequência.",
        )
    if requested_aula_numero not in allowed:
        raise AttendanceAssignmentScopeError(
            "ASSIGNMENT_SESSION_SLOT_INVALID",
            "Aula informada não pertence aos slots do vínculo nesta data.",
        )
    return requested_aula_numero


def logical_attendance_query(
    context: AttendanceAssignmentContext,
    *,
    on_date: str,
    aula_numero: Optional[int],
    period: str = "regular",
) -> dict:
    """Monta a chave natural sem permitir multiplicação de class_daily."""
    query: dict[str, Any] = {
        "class_id": context.assignment.get("class_id"),
        "date": on_date,
    }
    if period != "regular":
        query["period"] = period

    if context.attendance_mode is AttendanceMode.CLASS_DAILY:
        # `None` casa campo ausente/null e preserva a chave canônica histórica.
        query["course_id"] = None
        return query

    query.update({
        "assignment_id": context.assignment.get("id"),
        "course_id": context.effective_course_id,
        "aula_numero": aula_numero,
    })
    if context.is_official:
        query["attendance_key_scope"] = ASSIGNMENT_SESSION_KEY_SCOPE
    return query


def attendance_provenance_fields(
    context: AttendanceAssignmentContext,
    *,
    aula_numero: Optional[int],
) -> dict:
    fields = dict(context.snapshot)
    fields.update({
        "attendance_mode": context.attendance_mode.value,
        "attendance_purpose": context.attendance_purpose.value,
        "course_id": context.effective_course_id,
        "aula_numero": aula_numero,
    })
    if context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION and context.is_official:
        fields["attendance_key_scope"] = ASSIGNMENT_SESSION_KEY_SCOPE
    return fields


async def authorize_historical_attendance(
    db,
    current_user: Mapping[str, Any],
    attendance_doc: Mapping[str, Any],
    *,
    action: DiaryAction | str = DiaryAction.ATTENDANCE,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> HistoricalAttendanceContext:
    """Autoriza documento DVD constituído e valida semântica imutável."""
    try:
        historical = await authorize_assignment_snapshot_access(
            db,
            current_user,
            attendance_doc,
            action=action,
            allow_management_override=allow_management_override,
            active_mantenedora_id=active_mantenedora_id,
        )
    except DiaryAssignmentSnapshotAccessError as exc:
        raise _scope_error(exc) from exc

    capabilities = capabilities_for(historical.profile)
    expected_mode = capabilities.attendance_mode
    expected_purpose = capabilities.attendance_purpose
    stored_mode = attendance_doc.get("attendance_mode")
    stored_purpose = attendance_doc.get("attendance_purpose")
    if (
        expected_mode is None
        or expected_purpose is None
        or stored_mode != expected_mode.value
        or stored_purpose != expected_purpose.value
    ):
        raise AttendanceAssignmentScopeError(
            "ATTENDANCE_PROVENANCE_MISMATCH",
            "Modo/natureza da frequência divergem do perfil histórico do vínculo.",
        )

    scope_raw = attendance_doc.get("assignment_student_scope_at_record", StudentScope.ALL.value)
    try:
        student_scope = StudentScope(scope_raw)
    except ValueError as exc:
        raise AttendanceAssignmentScopeError(
            "INVALID_STUDENT_SCOPE", "Escopo histórico de estudantes é inválido."
        ) from exc
    if student_scope is StudentScope.GROUP:
        raise AttendanceAssignmentScopeError(
            "ATTENDANCE_GROUP_SCOPE_UNRESOLVED",
            "Registro shared/group não possui lista canônica de membros para edição segura.",
        )

    storage = (
        OFFICIAL_ATTENDANCE_COLLECTION
        if expected_purpose is AttendancePurpose.OFFICIAL
        else DOCUMENTARY_ATTENDANCE_COLLECTION
    )
    return HistoricalAttendanceContext(
        historical_access=historical,
        attendance_mode=expected_mode,
        attendance_purpose=expected_purpose,
        student_scope=student_scope,
        storage_collection=storage,
    )


async def professor_has_active_dvd_for_class(
    db,
    current_user: Mapping[str, Any],
    *,
    class_id: str,
    on_date: str,
) -> bool:
    """Guard anti-bypass para o fluxo legado do professor comum."""
    if current_user.get("role") != "professor" or not current_user.get("id"):
        return False
    query = {
        "teacher_id": current_user.get("id"),
        "class_id": class_id,
        "deleted": False,
        "diary_settings.enabled": True,
        "valid_from": {"$lte": on_date},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": on_date}}],
    }
    return bool(await db.teacher_class_assignments.find_one(query, {"_id": 0, "id": 1}))


async def ensure_attendance_assignment_indexes(db) -> None:
    """Evolui a unicidade de frequência sem reescrever documentos históricos.

    - legado + class_daily continuam na chave histórica turma/data/componente/aula;
    - assignment_session oficial sai dessa chave e ganha unicidade por assignment;
    - pdf_only vive na coleção documental e jamais disputa a coleção oficial.
    """
    legacy_partial = {"attendance_key_scope": None}
    info = await db.attendance.index_information()
    current = info.get("ux_attendance_class_date_course_aula")
    if current and current.get("partialFilterExpression") != legacy_partial:
        await db.attendance.drop_index("ux_attendance_class_date_course_aula")

    await db.attendance.create_index(
        [("class_id", 1), ("date", 1), ("course_id", 1), ("aula_numero", 1)],
        unique=True,
        partialFilterExpression=legacy_partial,
        name="ux_attendance_class_date_course_aula",
        background=True,
    )
    await db.attendance.create_index(
        [("class_id", 1), ("assignment_id", 1), ("date", 1), ("course_id", 1), ("aula_numero", 1)],
        unique=True,
        partialFilterExpression={"attendance_key_scope": ASSIGNMENT_SESSION_KEY_SCOPE},
        name="ux_attendance_assignment_session",
        background=True,
    )
    await db.attendance.create_index(
        [("assignment_id", 1), ("date", -1)],
        sparse=True,
        name="ix_attendance_assignment_date",
        background=True,
    )

    documentary = db[DOCUMENTARY_ATTENDANCE_COLLECTION]
    await documentary.create_index("id", unique=True, background=True)
    await documentary.create_index(
        [("class_id", 1), ("assignment_id", 1), ("date", 1), ("course_id", 1), ("aula_numero", 1)],
        unique=True,
        name="ux_attendance_documentary_assignment_session",
        background=True,
    )
    await documentary.create_index(
        [("mantenedora_id", 1), ("assignment_id", 1), ("date", -1)],
        name="ix_attendance_documentary_tenant_assignment_date",
        background=True,
    )
