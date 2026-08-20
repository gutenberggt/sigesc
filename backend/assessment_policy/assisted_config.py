"""Configuração assistida da Assessment Policy v1.

Esta camada é pura: não acessa MongoDB, HTTP, autenticação ou o runtime de Notas.
Ela avalia uma policy candidata e seu mapping legado explícito antes de qualquer
persistência, validação formal ou dry-run.

Invariantes da Sprint 007:
- nenhuma publicação automática;
- nenhuma regra municipal inferida;
- nenhum mapping legado inferido;
- policies published/superseded/retired são somente leitura;
- validação normativa não depende do schema legado;
- dry-run só fica liberado quando policy + mapping satisfazem o contrato completo.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .exceptions import AssessmentPolicyError
from .models import AssessmentPolicy, PolicyStatus
from .shadow import (
    LegacyGradeFieldMapping,
    calculate_mapping_hash,
    validate_shadow_mapping,
)
from .validator import validate_policy


ASSISTED_STATUS_NOT_EDITABLE = "ASSESSMENT_ASSISTED_STATUS_NOT_EDITABLE"
ASSISTED_DRAFT_HASH_FORBIDDEN = "ASSESSMENT_ASSISTED_DRAFT_HASH_FORBIDDEN"
ASSISTED_MAPPING_INVALID = "ASSESSMENT_ASSISTED_MAPPING_INVALID"


class LegacyFieldMappingConfig(BaseModel):
    """Representação serializável do mapping legado usado pelo Shadow Engine."""

    model_config = ConfigDict(extra="forbid")

    period_field_map: Dict[str, str] = Field(default_factory=dict)
    recovery_field_map: Dict[str, str] = Field(default_factory=dict)

    def to_runtime(self) -> LegacyGradeFieldMapping:
        return LegacyGradeFieldMapping(
            period_field_map=dict(self.period_field_map),
            recovery_field_map=dict(self.recovery_field_map),
        )


class AssistedPolicyConfiguration(BaseModel):
    """Policy candidata + evidência de compatibilidade com o schema legado."""

    model_config = ConfigDict(extra="forbid")

    policy: AssessmentPolicy
    legacy_mapping: LegacyFieldMappingConfig
    tolerance: str = "0.01"


class AssistedConfigurationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    field: str
    message: str
    details: Optional[object] = None


class AssistedConfigurationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    policy_key: str
    policy_version: int
    policy_status: str
    can_save_draft: bool
    can_validate: bool
    can_dry_run: bool
    calculated_rule_hash: Optional[str]
    mapping_hash: Optional[str]
    issues: List[AssistedConfigurationIssue] = Field(default_factory=list)


def preview_assisted_configuration(
    configuration: AssistedPolicyConfiguration,
) -> AssistedConfigurationPreview:
    """Avalia completude sem persistir ou alterar lifecycle.

    `can_validate` representa apenas o contrato normativo da AssessmentPolicy.
    O mapping legado é infraestrutura de compatibilidade e não integra a norma.
    Já `can_dry_run` exige simultaneamente policy completa e mapping explícito.
    """

    policy = configuration.policy
    issues: list[AssistedConfigurationIssue] = []
    policy_error_codes: set[str] = set()

    editable_statuses = {PolicyStatus.DRAFT, PolicyStatus.VALIDATED}
    if policy.status not in editable_statuses:
        issue = AssistedConfigurationIssue(
            severity="error",
            code=ASSISTED_STATUS_NOT_EDITABLE,
            field="policy.status",
            message=(
                "Configuração assistida não edita policy publicada/histórica; "
                "crie uma nova versão em draft."
            ),
            details={"status": policy.status.value},
        )
        issues.append(issue)
        policy_error_codes.add(issue.code)

    if policy.status == PolicyStatus.DRAFT and policy.rule_hash is not None:
        issue = AssistedConfigurationIssue(
            severity="error",
            code=ASSISTED_DRAFT_HASH_FORBIDDEN,
            field="policy.rule_hash",
            message="Draft não deve carregar rule_hash persistido.",
        )
        issues.append(issue)
        policy_error_codes.add(issue.code)

    policy_report = validate_policy(policy, for_publish=True)
    for item in policy_report.issues:
        issue = AssistedConfigurationIssue(
            severity=item.severity,
            code=item.code,
            field=item.field,
            message=item.message,
        )
        issues.append(issue)
        if item.severity == "error":
            policy_error_codes.add(item.code)

    mapping_hash: Optional[str] = None
    mapping_valid = False
    try:
        runtime_mapping = validate_shadow_mapping(
            policy,
            configuration.legacy_mapping.to_runtime(),
        )
        mapping_hash = calculate_mapping_hash(runtime_mapping)
        mapping_valid = True
    except AssessmentPolicyError as exc:
        issues.append(
            AssistedConfigurationIssue(
                severity="error",
                code=ASSISTED_MAPPING_INVALID,
                field="legacy_mapping",
                message=exc.message,
                details={"source_code": exc.code, "source_details": exc.details},
            )
        )

    has_policy_errors = bool(policy_error_codes)
    can_save_draft = policy.status == PolicyStatus.DRAFT and policy.rule_hash is None
    can_validate = can_save_draft and not has_policy_errors
    can_dry_run = (
        policy.status in editable_statuses
        and not has_policy_errors
        and mapping_valid
        and mapping_hash is not None
    )

    return AssistedConfigurationPreview(
        policy_id=policy.id,
        policy_key=policy.policy_key,
        policy_version=policy.version,
        policy_status=policy.status.value,
        can_save_draft=can_save_draft,
        can_validate=can_validate,
        can_dry_run=can_dry_run,
        calculated_rule_hash=policy_report.calculated_rule_hash,
        mapping_hash=mapping_hash,
        issues=issues,
    )
