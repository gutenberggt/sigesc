"""Contratos puros do Operational Binding da Assessment Policy v1.

Este módulo NÃO acessa MongoDB, HTTP, autenticação, routers ou o runtime de
Notas. O binding descreve, de forma versionada, como campos do schema
operacional alimentam uma AssessmentPolicy específica.

Invariantes da Sprint 008/Fase 1:
- mapping não integra o rule_hash normativo da policy;
- mapping_hash reutiliza a canonicalização do Shadow v1;
- binding é tenant-scoped e vinculado ao rule_hash exato da policy;
- nenhuma inferência de campo legado, recuperação ou frequência;
- nenhum publish, cutover ou runtime.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import calculate_rule_hash
from .exceptions import AssessmentPolicyError
from .models import AssessmentPolicy
from .shadow import (
    LegacyGradeFieldMapping,
    calculate_mapping_hash,
    canonical_mapping_json,
    validate_shadow_mapping,
)


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"

BINDING_POLICY_IDENTITY_MISMATCH = "ASSESSMENT_POLICY_BINDING_POLICY_IDENTITY_MISMATCH"
BINDING_POLICY_RULE_HASH_MISMATCH = "ASSESSMENT_POLICY_BINDING_POLICY_RULE_HASH_MISMATCH"
BINDING_POLICY_HASH_INVALID = "ASSESSMENT_POLICY_BINDING_POLICY_HASH_INVALID"
BINDING_MAPPING_INVALID = "ASSESSMENT_POLICY_BINDING_MAPPING_INVALID"
BINDING_MAPPING_HASH_MISMATCH = "ASSESSMENT_POLICY_BINDING_MAPPING_HASH_MISMATCH"


class OperationalBindingStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SUPERSEDED = "superseded"


def _clean_field_map(value: Dict[str, str], *, field_name: str) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for raw_source, raw_target in value.items():
        source = str(raw_source or "").strip()
        target = str(raw_target or "").strip()
        if not source or not target:
            raise ValueError(f"{field_name} não pode conter campo/código vazio")
        if source in cleaned:
            raise ValueError(
                f"{field_name} contém campo duplicado após normalização: {source}"
            )
        cleaned[source] = target

    targets = list(cleaned.values())
    if len(targets) != len(set(targets)):
        raise ValueError(
            f"{field_name} não pode mapear dois campos operacionais para o mesmo código"
        )
    return cleaned


class AssessmentPolicyOperationalBinding(BaseModel):
    """Binding versionado entre uma policy exata e o schema operacional."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    mantenedora_id: str = Field(min_length=1, max_length=160)
    policy_id: str = Field(min_length=1, max_length=160)
    policy_key: str = Field(min_length=1, max_length=120)
    policy_version: int = Field(ge=1)
    policy_rule_hash: str = Field(pattern=SHA256_PATTERN)

    binding_version: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    source_schema: str = Field(min_length=1, max_length=160)

    period_field_map: Dict[str, str] = Field(default_factory=dict)
    recovery_field_map: Dict[str, str] = Field(default_factory=dict)

    status: OperationalBindingStatus = OperationalBindingStatus.DRAFT
    mapping_hash: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)

    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None

    @field_validator(
        "id",
        "mantenedora_id",
        "policy_id",
        "policy_key",
        "source_schema",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value

    @field_validator("period_field_map", "recovery_field_map")
    @classmethod
    def clean_field_maps(cls, value: Dict[str, str], info) -> Dict[str, str]:
        return _clean_field_map(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_binding_contract(self):
        reused_sources = sorted(
            set(self.period_field_map) & set(self.recovery_field_map)
        )
        if reused_sources:
            raise ValueError(
                "um campo operacional não pode alimentar simultaneamente "
                f"período e recuperação: {', '.join(reused_sources)}"
            )

        if self.status == OperationalBindingStatus.DRAFT:
            if self.mapping_hash is not None:
                raise ValueError("binding draft não deve carregar mapping_hash persistido")
            if self.validated_by is not None or self.validated_at is not None:
                raise ValueError("binding draft não deve carregar metadados de validação")
        else:
            if self.mapping_hash is None:
                raise ValueError("binding validated/superseded exige mapping_hash")
            if not str(self.validated_by or "").strip() or self.validated_at is None:
                raise ValueError(
                    "binding validated/superseded exige validated_by e validated_at"
                )
        return self

    def to_runtime_mapping(self) -> LegacyGradeFieldMapping:
        return LegacyGradeFieldMapping(
            period_field_map=dict(self.period_field_map),
            recovery_field_map=dict(self.recovery_field_map),
        )


class OperationalBindingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    field: str
    message: str
    details: Optional[object] = None


class OperationalBindingValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    calculated_policy_rule_hash: str
    calculated_mapping_hash: Optional[str] = None
    issues: List[OperationalBindingIssue] = Field(default_factory=list)


def canonical_operational_mapping_json(
    binding: AssessmentPolicyOperationalBinding,
) -> str:
    """Canonicalização do mapping delegada ao algoritmo já usado pelo Shadow."""

    return canonical_mapping_json(binding.to_runtime_mapping())


def calculate_operational_mapping_hash(
    binding: AssessmentPolicyOperationalBinding,
) -> str:
    """Hash do mapping com exatamente a mesma semântica do Shadow v1."""

    return calculate_mapping_hash(binding.to_runtime_mapping())


def canonical_operational_binding_payload(
    binding: AssessmentPolicyOperationalBinding,
) -> dict:
    """Conteúdo operacional efetivo, sem lifecycle/autoria/concorrência.

    `mapping_hash` também fica fora: ele é derivado do mapping. A função não cria
    um segundo hash normativo; apenas fornece serialização estável para auditoria.
    """

    mapping_payload = json.loads(canonical_operational_mapping_json(binding))
    return {
        "mantenedora_id": binding.mantenedora_id,
        "policy_id": binding.policy_id,
        "policy_key": binding.policy_key,
        "policy_version": binding.policy_version,
        "policy_rule_hash": binding.policy_rule_hash,
        "binding_version": binding.binding_version,
        "source_schema": binding.source_schema,
        "period_field_map": mapping_payload["period_field_map"],
        "recovery_field_map": mapping_payload["recovery_field_map"],
    }


def canonical_operational_binding_json(
    binding: AssessmentPolicyOperationalBinding,
) -> str:
    return json.dumps(
        canonical_operational_binding_payload(binding),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validate_operational_binding(
    policy: AssessmentPolicy,
    binding: AssessmentPolicyOperationalBinding,
) -> OperationalBindingValidationReport:
    """Valida vínculo e mapping sem IO e sem alterar lifecycle.

    A policy pode estar draft ou validated: o vínculo usa sempre o conteúdo
    canônico atual (`calculate_rule_hash`). Se esse conteúdo mudar, o binding
    anterior fica objetivamente stale por divergência de `policy_rule_hash`.
    """

    issues: List[OperationalBindingIssue] = []
    calculated_policy_hash = calculate_rule_hash(policy)

    identity_mismatch = {}
    expected_identity = {
        "mantenedora_id": policy.mantenedora_id,
        "policy_id": policy.id,
        "policy_key": policy.policy_key,
        "policy_version": policy.version,
    }
    received_identity = {
        "mantenedora_id": binding.mantenedora_id,
        "policy_id": binding.policy_id,
        "policy_key": binding.policy_key,
        "policy_version": binding.policy_version,
    }
    for field, expected in expected_identity.items():
        received = received_identity[field]
        if received != expected:
            identity_mismatch[field] = {
                "expected": expected,
                "received": received,
            }

    if identity_mismatch:
        issues.append(
            OperationalBindingIssue(
                severity="error",
                code=BINDING_POLICY_IDENTITY_MISMATCH,
                field="policy_identity",
                message="OperationalBinding não corresponde à identidade da policy.",
                details=identity_mismatch,
            )
        )

    if binding.policy_rule_hash != calculated_policy_hash:
        issues.append(
            OperationalBindingIssue(
                severity="error",
                code=BINDING_POLICY_RULE_HASH_MISMATCH,
                field="policy_rule_hash",
                message=(
                    "OperationalBinding está vinculado a conteúdo normativo "
                    "diferente da policy recebida."
                ),
                details={
                    "expected": calculated_policy_hash,
                    "received": binding.policy_rule_hash,
                },
            )
        )

    if policy.rule_hash is not None and policy.rule_hash != calculated_policy_hash:
        issues.append(
            OperationalBindingIssue(
                severity="error",
                code=BINDING_POLICY_HASH_INVALID,
                field="policy.rule_hash",
                message="rule_hash persistido da policy não corresponde ao conteúdo canônico.",
                details={
                    "expected": calculated_policy_hash,
                    "received": policy.rule_hash,
                },
            )
        )

    calculated_mapping_hash: Optional[str] = None
    try:
        validated_mapping = validate_shadow_mapping(
            policy,
            binding.to_runtime_mapping(),
        )
        calculated_mapping_hash = calculate_mapping_hash(validated_mapping)
    except AssessmentPolicyError as exc:
        issues.append(
            OperationalBindingIssue(
                severity="error",
                code=BINDING_MAPPING_INVALID,
                field="mapping",
                message=exc.message,
                details={
                    "source_code": exc.code,
                    "source_details": exc.details,
                },
            )
        )

    if (
        calculated_mapping_hash is not None
        and binding.mapping_hash is not None
        and binding.mapping_hash != calculated_mapping_hash
    ):
        issues.append(
            OperationalBindingIssue(
                severity="error",
                code=BINDING_MAPPING_HASH_MISMATCH,
                field="mapping_hash",
                message="mapping_hash persistido não corresponde ao mapping canônico.",
                details={
                    "expected": calculated_mapping_hash,
                    "received": binding.mapping_hash,
                },
            )
        )

    return OperationalBindingValidationReport(
        valid=not any(issue.severity == "error" for issue in issues),
        calculated_policy_rule_hash=calculated_policy_hash,
        calculated_mapping_hash=calculated_mapping_hash,
        issues=issues,
    )
