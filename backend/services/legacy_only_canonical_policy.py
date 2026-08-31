"""Política pura F2.10A para casos LEGACY_ONLY / NO_CANONICAL_TEMPLATE.

Esta camada NÃO escreve no banco, NÃO habilita DVD e NÃO é storage-ready.
Ela formaliza a decisão arquitetural de separar:

- entitlement pedagógico canônico; e
- configuração/capacidades operacionais do Diário por Vínculo (DVD).

Um caso bloqueado exclusivamente por ``NO_CANONICAL_TEMPLATE`` pode ser
reclassificado como candidato a ``CANONICAL_ENTITLEMENT`` sem inferir perfil,
horário, validade temporal, substituição, escopo de estudantes ou ownership de
notas. Casos com qualquer outro bloqueador permanecem em revisão.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


REQUIRES_REVIEW = "REQUIRES_REVIEW"
NO_CANONICAL_TEMPLATE = "NO_CANONICAL_TEMPLATE"
CANONICAL_ENTITLEMENT = "CANONICAL_ENTITLEMENT"


class LegacyOnlyPolicyDecision(str, Enum):
    PLAN_CANONICAL_ENTITLEMENT_ONLY = "PLAN_CANONICAL_ENTITLEMENT_ONLY"
    KEEP_REVIEW = "KEEP_REVIEW"
    NOOP_NOT_TARGET = "NOOP_NOT_TARGET"


@dataclass(frozen=True)
class LegacyOnlyPolicyResult:
    decision: LegacyOnlyPolicyDecision
    reason: str


_REQUIRED_ID_FIELDS = (
    "teacher_id",
    "class_id",
    "component_id",
    "mantenedora_id",
    "school_id",
)

# Estes campos pertencem ao envelope operacional DVD. A F2.10A os mantém
# explicitamente desconhecidos no entitlement-only e proíbe qualquer default.
_DVD_ONLY_FIELDS = (
    "diary_settings",
    "weekly_slots",
    "valid_from",
    "valid_until",
    "is_substitute",
    "grades_official_owner",
    "shift",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _review_reasons(case: Mapping[str, Any]) -> set[str]:
    values = case.get("review_reasons")
    if values is None:
        values = [case.get("reason")] if case.get("reason") else []
    elif isinstance(values, str):
        values = [values]
    return {_norm(value) for value in values if _norm(value)}


def decide_legacy_only_policy(case: Mapping[str, Any]) -> LegacyOnlyPolicyResult:
    """Decide se o caso pode virar entitlement-only sem inferência semântica.

    O upstream (F2.9A/F2.10C) continua responsável por provar identidade,
    tenant, escola, turma, componente e ausência de duplicidades/drift. Esta
    função somente aceita o caso quando ``NO_CANONICAL_TEMPLATE`` é o único
    motivo de revisão e os identificadores estruturais mínimos estão presentes.
    """
    if _norm(case.get("action")) != REQUIRES_REVIEW:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.NOOP_NOT_TARGET,
            "ACTION_NOT_REQUIRES_REVIEW",
        )

    reasons = _review_reasons(case)
    if NO_CANONICAL_TEMPLATE not in reasons:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.NOOP_NOT_TARGET,
            "NO_CANONICAL_TEMPLATE_NOT_PRESENT",
        )

    extra_reasons = sorted(reasons - {NO_CANONICAL_TEMPLATE})
    if extra_reasons:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.KEEP_REVIEW,
            "ADDITIONAL_REVIEW_REASON:" + ",".join(extra_reasons),
        )

    missing = [field for field in _REQUIRED_ID_FIELDS if not _norm(case.get(field))]
    if missing:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.KEEP_REVIEW,
            "STRUCTURAL_ID_MISSING:" + ",".join(missing),
        )

    try:
        academic_year = int(case.get("academic_year"))
    except (TypeError, ValueError):
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.KEEP_REVIEW,
            "ACADEMIC_YEAR_INVALID",
        )
    if academic_year < 2000 or academic_year > 2100:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.KEEP_REVIEW,
            "ACADEMIC_YEAR_INVALID",
        )

    legacy_binding_count = case.get("legacy_binding_count")
    if legacy_binding_count is not None and int(legacy_binding_count) != 1:
        return LegacyOnlyPolicyResult(
            LegacyOnlyPolicyDecision.KEEP_REVIEW,
            "LEGACY_BINDING_NOT_UNIQUE",
        )

    return LegacyOnlyPolicyResult(
        LegacyOnlyPolicyDecision.PLAN_CANONICAL_ENTITLEMENT_ONLY,
        "NO_CANONICAL_TEMPLATE_IS_NOT_AN_ENTITLEMENT_BLOCKER",
    )


def build_entitlement_only_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    """Gera projeção conceitual, deliberadamente NÃO persistível nesta fase.

    ``academic_year`` é preservado como escopo institucional do entitlement.
    Campos do envelope DVD permanecem ``None``. A F2.10B deverá definir o schema
    persistido e o discriminador semântico antes de qualquer backfill.
    """
    decision = decide_legacy_only_policy(case)
    if decision.decision is not LegacyOnlyPolicyDecision.PLAN_CANONICAL_ENTITLEMENT_ONLY:
        raise ValueError(f"LEGACY_ONLY_POLICY_NOT_PLANNABLE:{decision.reason}")

    projection: dict[str, Any] = {
        "storage_ready": False,
        "policy_version": "F2.10A-v1",
        "assignment_semantics": CANONICAL_ENTITLEMENT,
        "teacher_id": _norm(case.get("teacher_id")),
        "class_id": _norm(case.get("class_id")),
        "component_id": _norm(case.get("component_id")),
        "mantenedora_id": _norm(case.get("mantenedora_id")),
        "school_id": _norm(case.get("school_id")),
        "academic_year": int(case.get("academic_year")),
    }
    projection.update({field: None for field in _DVD_ONLY_FIELDS})
    return projection


def assert_entitlement_only_projection(projection: Mapping[str, Any]) -> None:
    """Falha se alguém transformar a política em um DVD implícito por default."""
    if projection.get("storage_ready") is not False:
        raise ValueError("F2_10A_STORAGE_MUST_REMAIN_DISABLED")
    if projection.get("assignment_semantics") != CANONICAL_ENTITLEMENT:
        raise ValueError("F2_10A_SEMANTIC_KIND_INVALID")
    for field in _DVD_ONLY_FIELDS:
        if projection.get(field) is not None:
            raise ValueError(f"F2_10A_DVD_FIELD_MUST_BE_UNKNOWN:{field}")
