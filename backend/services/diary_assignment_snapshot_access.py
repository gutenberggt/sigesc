"""Autorização histórica por snapshot do Diário por Vínculo Docente.

Criação de dados pedagógicos usa `authorize_assignment_access` e exige vínculo
vivo/vigente/habilitado. Depois que um registro é criado, sua proveniência não
pode depender de configurações mutáveis do assignment. Este serviço autoriza o
snapshot persistido sem reclassificar retroativamente o histórico.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    GLOBAL_SCHOOL_ROLES,
    MANAGEMENT_EDIT_ROLES,
    MANAGEMENT_VIEW_ROLES,
    PEDAGOGICAL_OWNER_ROLES,
)
from services.diary_assignment_contract import DiaryProfile, capabilities_for


class DiaryAssignmentSnapshotAccessError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HistoricalDiaryAssignmentAccessContext:
    snapshot: Mapping[str, Any]
    profile: DiaryProfile
    action: DiaryAction
    is_owner: bool
    management_override: bool


def _snapshot_school_access(user: Mapping[str, Any], school_id: Optional[str]) -> bool:
    if not school_id:
        return False
    if user.get("role") in GLOBAL_SCHOOL_ROLES:
        return True
    return school_id in (user.get("school_ids") or [])


def _snapshot_tenant_access(
    user: Mapping[str, Any],
    resource_tenant: Optional[str],
    active_mantenedora_id: Optional[str],
) -> bool:
    if user.get("role") == "super_admin":
        if active_mantenedora_id is None:
            return True
        return bool(resource_tenant) and resource_tenant == active_mantenedora_id
    user_tenant = user.get("mantenedora_id")
    if not user_tenant or not resource_tenant:
        return False
    return user_tenant == resource_tenant


def _snapshot_action_supported(profile: DiaryProfile, action: DiaryAction) -> bool:
    capabilities = capabilities_for(profile)
    if action is DiaryAction.VIEW:
        return True
    if action is DiaryAction.CONTENT:
        return capabilities.content_enabled
    if action is DiaryAction.ATTENDANCE:
        return capabilities.attendance_enabled
    if action is DiaryAction.GRADES:
        return capabilities.grades_enabled
    return False


async def authorize_assignment_snapshot_access(
    db,
    current_user: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    action: DiaryAction | str = DiaryAction.VIEW,
    allow_management_override: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> HistoricalDiaryAssignmentAccessContext:
    """Autoriza um registro pedagógico já constituído por snapshot imutável.

    Campos esperados no snapshot:
    - assignment_id;
    - teacher_id;
    - class_id;
    - school_id;
    - mantenedora_id;
    - assignment_profile_at_record;
    - assignment_schema_version_at_record.

    O assignment vivo é consultado apenas para verificar identidade estável
    (`id`, `teacher_id`, `class_id`) e pode estar expirado, desabilitado ou
    soft-deleted. Componentes, perfil e validade atuais não reclassificam o
    registro histórico.
    """
    try:
        normalized_action = DiaryAction(action)
    except ValueError as exc:
        raise DiaryAssignmentSnapshotAccessError(
            "INVALID_ACTION", "Ação de diário histórica inválida."
        ) from exc

    assignment_id = snapshot.get("assignment_id")
    teacher_id = snapshot.get("teacher_id")
    class_id = snapshot.get("class_id")
    school_id = snapshot.get("school_id")
    resource_tenant = snapshot.get("mantenedora_id")
    profile_raw = snapshot.get("assignment_profile_at_record")
    schema_version = snapshot.get("assignment_schema_version_at_record")

    if not assignment_id or not teacher_id or not class_id or not profile_raw:
        raise DiaryAssignmentSnapshotAccessError(
            "INCOMPLETE_ASSIGNMENT_SNAPSHOT",
            "Registro DVD sem snapshot mínimo de proveniência pedagógica.",
        )
    if schema_version != 1:
        raise DiaryAssignmentSnapshotAccessError(
            "UNSUPPORTED_DIARY_SCHEMA",
            "Versão histórica do vínculo docente não suportada.",
        )
    try:
        profile = DiaryProfile(profile_raw)
    except ValueError as exc:
        raise DiaryAssignmentSnapshotAccessError(
            "INVALID_DIARY_PROFILE", "Perfil histórico do vínculo docente é inválido."
        ) from exc

    live_identity = await db.teacher_class_assignments.find_one(
        {"id": assignment_id},
        {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1},
    )
    if not live_identity:
        raise DiaryAssignmentSnapshotAccessError(
            "ASSIGNMENT_SNAPSHOT_ORPHAN",
            "Vínculo de origem do registro histórico não foi encontrado.",
        )
    if (
        live_identity.get("teacher_id") != teacher_id
        or live_identity.get("class_id") != class_id
    ):
        raise DiaryAssignmentSnapshotAccessError(
            "ASSIGNMENT_SNAPSHOT_MISMATCH",
            "Identidade histórica do vínculo diverge do assignment persistido.",
        )

    if not _snapshot_school_access(current_user, school_id):
        raise DiaryAssignmentSnapshotAccessError(
            "SCHOOL_ACCESS_DENIED", "Usuário sem acesso à escola do registro histórico."
        )
    if not _snapshot_tenant_access(current_user, resource_tenant, active_mantenedora_id):
        raise DiaryAssignmentSnapshotAccessError(
            "TENANT_ACCESS_DENIED",
            "Registro histórico pertence a outra mantenedora ou não possui tenant resolvível.",
        )

    role = current_user.get("role")
    is_owner = teacher_id == current_user.get("id") and role in PEDAGOGICAL_OWNER_ROLES
    management_override = False
    if not is_owner:
        if normalized_action is DiaryAction.VIEW and role in MANAGEMENT_VIEW_ROLES:
            pass
        elif allow_management_override and role in MANAGEMENT_EDIT_ROLES:
            management_override = True
        else:
            raise DiaryAssignmentSnapshotAccessError(
                "ASSIGNMENT_ACCESS_DENIED",
                "Usuário não é proprietário pedagógico do registro histórico.",
            )

    if not _snapshot_action_supported(profile, normalized_action):
        raise DiaryAssignmentSnapshotAccessError(
            "CAPABILITY_DENIED",
            f"O perfil histórico {profile.value} não permite a ação {normalized_action.value}.",
        )

    return HistoricalDiaryAssignmentAccessContext(
        snapshot=snapshot,
        profile=profile,
        action=normalized_action,
        is_owner=is_owner,
        management_override=management_override,
    )
