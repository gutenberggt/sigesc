"""Autorização central do Diário por Vínculo Docente — Fase 1.

Este serviço é deliberadamente independente de FastAPI/Request. Ele recebe o
usuário autenticado já resolvido e valida o vínculo pedagógico no banco.

A integração com Attendance/Grades/Content/PDFs ocorre somente nas fases
seguintes. Nesta fase o serviço estabelece a fonte única das decisões de acesso.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Optional

from services.diary_assignment_contract import (
    AttendancePurpose,
    DiaryCapabilities,
    DiaryProfile,
    StudentScope,
    capabilities_for,
    is_class_in_scope,
)


class DiaryAction(str, Enum):
    VIEW = "view"
    CONTENT = "content"
    ATTENDANCE = "attendance"
    GRADES = "grades"


class DiaryAssignmentAccessError(PermissionError):
    """Erro de autorização previsível, com código estável para futuros routers."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EffectiveDiarySettings:
    enabled: bool
    schema_version: int
    profile: DiaryProfile
    student_scope: StudentScope
    capabilities: DiaryCapabilities


@dataclass(frozen=True)
class DiaryAssignmentAccessContext:
    assignment: Mapping[str, Any]
    class_info: Mapping[str, Any]
    settings: EffectiveDiarySettings
    action: DiaryAction
    is_owner: bool
    management_override: bool


# Papéis que podem visualizar o contexto consolidado, desde que respeitem a
# escola/tenant. Professor comum nunca ganha visão consolidada por este conjunto.
MANAGEMENT_VIEW_ROLES = frozenset({
    "super_admin",
    "admin",
    "admin_teste",
    "gerente",
    "secretario",
    "semed3",
    "coordenador",
    "apoio_pedagogico",
    "diretor",
})

# Escrita gerencial não é implícita. Só é admitida quando o chamador futuro
# solicitar explicitamente allow_management_override=True.
MANAGEMENT_EDIT_ROLES = frozenset({
    "super_admin",
    "admin",
    "admin_teste",
    "gerente",
    "semed3",
    "coordenador",
    "apoio_pedagogico",
})

# Espelha a política institucional de leitura por escola já usada no SIGESC.
GLOBAL_SCHOOL_ROLES = frozenset({
    "super_admin",
    "admin",
    "admin_teste",
    "gerente",
    "semed",
    "semed1",
    "semed2",
    "semed3",
    "ass_social",
    "ass_social_2",
    "agente_vacinas",
})


def effective_diary_settings(assignment: Mapping[str, Any]) -> EffectiveDiarySettings:
    """Normaliza a configuração persistida do vínculo.

    Ausência de `diary_settings` NÃO ativa o DVD implicitamente. Isso é essencial
    para que vínculos legados continuem sob o comportamento atual até a futura
    migração/ativação explícita.
    """
    raw = assignment.get("diary_settings") or {}
    enabled = raw.get("enabled") is True

    try:
        profile = DiaryProfile(raw.get("profile", DiaryProfile.REGULAR.value))
    except ValueError as exc:
        raise DiaryAssignmentAccessError(
            "INVALID_DIARY_PROFILE", "Perfil de diário inválido no vínculo."
        ) from exc

    try:
        student_scope = StudentScope(raw.get("student_scope", StudentScope.ALL.value))
    except ValueError as exc:
        raise DiaryAssignmentAccessError(
            "INVALID_STUDENT_SCOPE", "Escopo de estudantes inválido no vínculo."
        ) from exc

    schema_version = raw.get("schema_version", 1)
    if schema_version != 1:
        raise DiaryAssignmentAccessError(
            "UNSUPPORTED_DIARY_SCHEMA", "Versão de configuração do diário não suportada."
        )

    if student_scope is StudentScope.GROUP and profile is not DiaryProfile.SHARED:
        raise DiaryAssignmentAccessError(
            "INVALID_GROUP_SCOPE",
            "student_scope=group é permitido apenas para vínculo shared.",
        )

    return EffectiveDiarySettings(
        enabled=enabled,
        schema_version=1,
        profile=profile,
        student_scope=student_scope,
        capabilities=capabilities_for(profile),
    )


def is_assignment_active_on(assignment: Mapping[str, Any], on_date: str) -> bool:
    """Validade temporal inclusiva; `valid_until=None` significa vigente."""
    valid_from = assignment.get("valid_from")
    valid_until = assignment.get("valid_until")
    if not valid_from:
        return False
    return valid_from <= on_date and (valid_until is None or valid_until >= on_date)


def _user_can_access_school(user: Mapping[str, Any], school_id: Optional[str]) -> bool:
    if not school_id:
        return False
    role = user.get("role")
    if role in GLOBAL_SCHOOL_ROLES:
        return True
    return school_id in (user.get("school_ids") or [])


def _tenant_matches(
    user: Mapping[str, Any], assignment: Mapping[str, Any], class_info: Mapping[str, Any]
) -> bool:
    if user.get("role") == "super_admin":
        return True
    user_tenant = user.get("mantenedora_id")
    resource_tenant = class_info.get("mantenedora_id") or assignment.get("mantenedora_id")
    # Compatibilidade com documentos legados ainda sem mantenedora_id.
    if not user_tenant or not resource_tenant:
        return True
    return user_tenant == resource_tenant


def _action_supported(settings: EffectiveDiarySettings, action: DiaryAction) -> bool:
    if action is DiaryAction.VIEW:
        return True
    if action is DiaryAction.CONTENT:
        return settings.capabilities.content_enabled
    if action is DiaryAction.ATTENDANCE:
        return settings.capabilities.attendance_enabled
    if action is DiaryAction.GRADES:
        return settings.capabilities.grades_enabled
    return False


async def authorize_assignment_access(
    db,
    current_user: Mapping[str, Any],
    assignment_id: str,
    *,
    action: DiaryAction | str = DiaryAction.VIEW,
    on_date: Optional[str] = None,
    expected_class_id: Optional[str] = None,
    expected_component_id: Optional[str] = None,
    allow_management_override: bool = False,
) -> DiaryAssignmentAccessContext:
    """Autoriza acesso ao diário por `assignment_id`.

    Regras centrais:
    - vínculo precisa existir e não estar excluído;
    - DVD precisa estar explicitamente habilitado no vínculo;
    - turma precisa pertencer ao escopo aprovado da v1 e não ser AEE;
    - vínculo precisa estar vigente na data solicitada;
    - professor/ator pedagógico proprietário usa apenas seu próprio vínculo;
    - gestão pode visualizar de forma consolidada respeitando escola/tenant;
    - escrita gerencial exige opt-in explícito do chamador;
    - a capability do perfil sempre limita a ação (integrador não lança notas).
    """
    try:
        normalized_action = DiaryAction(action)
    except ValueError as exc:
        raise DiaryAssignmentAccessError("INVALID_ACTION", "Ação de diário inválida.") from exc

    assignment = await db.teacher_class_assignments.find_one(
        {"id": assignment_id, "deleted": False}, {"_id": 0}
    )
    if not assignment:
        raise DiaryAssignmentAccessError(
            "ASSIGNMENT_NOT_FOUND", "Vínculo docente não encontrado ou inativo por exclusão."
        )

    if expected_class_id and assignment.get("class_id") != expected_class_id:
        raise DiaryAssignmentAccessError(
            "CLASS_MISMATCH", "O vínculo não pertence à turma informada."
        )
    if expected_component_id and assignment.get("component_id") != expected_component_id:
        raise DiaryAssignmentAccessError(
            "COMPONENT_MISMATCH", "O vínculo não pertence ao componente informado."
        )

    class_info = await db.classes.find_one(
        {"id": assignment.get("class_id")},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "education_level": 1,
            "nivel_ensino": 1,
            "grade_level": 1,
            "grade": 1,
            "atendimento_programa": 1,
        },
    )
    if not class_info:
        raise DiaryAssignmentAccessError("CLASS_NOT_FOUND", "Turma do vínculo não encontrada.")
    if not is_class_in_scope(class_info):
        raise DiaryAssignmentAccessError(
            "CLASS_OUT_OF_DVD_SCOPE", "A turma não pertence ao escopo do Diário por Vínculo v1."
        )

    settings = effective_diary_settings(assignment)
    if not settings.enabled:
        raise DiaryAssignmentAccessError(
            "DVD_NOT_ENABLED", "O vínculo ainda não foi habilitado para o Diário por Vínculo."
        )

    reference_date = on_date or date.today().isoformat()
    if not is_assignment_active_on(assignment, reference_date):
        raise DiaryAssignmentAccessError(
            "ASSIGNMENT_NOT_ACTIVE", "O vínculo não está vigente na data solicitada."
        )

    school_id = assignment.get("school_id") or class_info.get("school_id")
    if not _user_can_access_school(current_user, school_id):
        raise DiaryAssignmentAccessError(
            "SCHOOL_ACCESS_DENIED", "O usuário não possui acesso à escola do vínculo."
        )
    if not _tenant_matches(current_user, assignment, class_info):
        raise DiaryAssignmentAccessError(
            "TENANT_ACCESS_DENIED", "O vínculo pertence a outra mantenedora."
        )

    is_owner = assignment.get("teacher_id") == current_user.get("id")
    management_override = False

    if not is_owner:
        role = current_user.get("role")
        if normalized_action is DiaryAction.VIEW and role in MANAGEMENT_VIEW_ROLES:
            pass
        elif allow_management_override and role in MANAGEMENT_EDIT_ROLES:
            management_override = True
        else:
            raise DiaryAssignmentAccessError(
                "ASSIGNMENT_ACCESS_DENIED",
                "O usuário não é proprietário deste vínculo docente.",
            )

    if not _action_supported(settings, normalized_action):
        raise DiaryAssignmentAccessError(
            "CAPABILITY_DENIED",
            f"O perfil {settings.profile.value} não permite a ação {normalized_action.value}.",
        )

    return DiaryAssignmentAccessContext(
        assignment=assignment,
        class_info=class_info,
        settings=settings,
        action=normalized_action,
        is_owner=is_owner,
        management_override=management_override,
    )


def attendance_is_official_for_context(context: DiaryAssignmentAccessContext) -> bool:
    """Atalho seguro para consumidores futuros: somente purpose=official conta."""
    return context.settings.capabilities.attendance_purpose is AttendancePurpose.OFFICIAL
