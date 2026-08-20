"""Especificação de índices da coleção `assessment_policies`.

Nenhum índice é criado automaticamente nesta sprint. O futuro startup hook
consumirá esta lista somente após aprovação do Registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class IndexSpec:
    name: str
    keys: Tuple[Tuple[str, int], ...]
    unique: bool = False


ASSESSMENT_POLICY_INDEXES = (
    IndexSpec(
        name="uq_assessment_policy_tenant_id",
        keys=(("mantenedora_id", 1), ("id", 1)),
        unique=True,
    ),
    IndexSpec(
        name="uq_assessment_policy_tenant_key_version",
        keys=(("mantenedora_id", 1), ("policy_key", 1), ("version", 1)),
        unique=True,
    ),
    IndexSpec(
        name="ix_assessment_policy_resolution_window",
        keys=(
            ("mantenedora_id", 1),
            ("status", 1),
            ("academic_year", 1),
            ("effective_from", 1),
            ("effective_until", 1),
        ),
    ),
    # Índices de escopo ficam separados: combinar múltiplos arrays em um mesmo
    # índice composto criaria restrições de multikey no MongoDB.
    IndexSpec(
        name="ix_assessment_policy_scope_school",
        keys=(
            ("mantenedora_id", 1),
            ("status", 1),
            ("academic_year", 1),
            ("scope.school_ids", 1),
        ),
    ),
    IndexSpec(
        name="ix_assessment_policy_scope_class",
        keys=(
            ("mantenedora_id", 1),
            ("status", 1),
            ("academic_year", 1),
            ("scope.class_ids", 1),
        ),
    ),
    IndexSpec(
        name="ix_assessment_policy_scope_component",
        keys=(
            ("mantenedora_id", 1),
            ("status", 1),
            ("academic_year", 1),
            ("scope.component_ids", 1),
        ),
    ),
    IndexSpec(
        name="ix_assessment_policy_scope_series",
        keys=(
            ("mantenedora_id", 1),
            ("status", 1),
            ("academic_year", 1),
            ("scope.series", 1),
        ),
    ),
)
