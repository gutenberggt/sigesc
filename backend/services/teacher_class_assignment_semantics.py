"""Semântica canônica de ``teacher_class_assignments`` para auditorias P0.

O campo ``teacher_id`` possui semânticas históricas persistidas distintas:
- vínculos DVD operacionais: ``users.id``;
- materializações de grade legada com professor: ``staff.id``;
- materializações de grade legada sem professor: ``teacher_id=None`` e id ``::none``.

As duas populações ``legacy_migration`` NÃO representam propriedade pedagógica
DVD. São artefatos sintéticos criados pela migração definitiva da grade horária
e só podem ser excluídos de auditorias de identidade quando seus marcadores
institucionais continuam íntegros. Qualquer drift permanece fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

LEGACY_MIGRATION_SOURCE = "legacy_migration"
OPERATIONAL_DVD = "OPERATIONAL_DVD"
LEGACY_MIGRATION_SYNTHETIC = "LEGACY_MIGRATION_SYNTHETIC"
LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED = "LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED"
LEGACY_MIGRATION_DRIFT = "LEGACY_MIGRATION_DRIFT"


@dataclass(frozen=True)
class AssignmentSemantic:
    kind: str
    drift_reasons: tuple[str, ...] = ()


def _norm(value: Any) -> str:
    return str(value or "").strip()


def classify_teacher_class_assignment(row: Mapping[str, Any]) -> AssignmentSemantic:
    """Classifica um documento sem inferência por nome.

    Apenas ``source=legacy_migration`` entra na trilha sintética. Para ser
    reconhecido como artefato válido, o documento precisa manter os marcadores
    produzidos pelo writer oficial. O bridge oficial admite explicitamente
    componente de grade sem professor, persistido como ``teacher_id=None`` e id
    determinístico terminado em ``::none``. Esse estado é sintético legítimo,
    não drift e não vínculo DVD operacional.
    """
    if _norm(row.get("source")) != LEGACY_MIGRATION_SOURCE:
        return AssignmentSemantic(OPERATIONAL_DVD)

    reasons: list[str] = []
    assignment_id = _norm(row.get("id"))
    teacher_id = _norm(row.get("teacher_id"))

    if not assignment_id.startswith("legacy::"):
        reasons.append("ID_NOT_LEGACY_DETERMINISTIC")
    if row.get("migrated_from_legacy") is not True:
        reasons.append("MIGRATED_FROM_LEGACY_NOT_TRUE")
    if row.get("synthetic_validity") is not True:
        reasons.append("SYNTHETIC_VALIDITY_NOT_TRUE")
    if _norm(row.get("created_by")) != LEGACY_MIGRATION_SOURCE:
        reasons.append("CREATED_BY_MISMATCH")
    if (row.get("diary_settings") or {}).get("enabled") is True:
        reasons.append("DVD_ENABLED_TRUE")
    if not _norm(row.get("class_id")):
        reasons.append("CLASS_ID_MISSING")
    if not _norm(row.get("component_id")):
        reasons.append("COMPONENT_ID_MISSING")

    if not teacher_id:
        if assignment_id and not assignment_id.endswith("::none"):
            reasons.append("UNASSIGNED_ID_NOT_NONE")
        if reasons:
            return AssignmentSemantic(
                LEGACY_MIGRATION_DRIFT,
                tuple(sorted(set(reasons))),
            )
        return AssignmentSemantic(LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED)

    if assignment_id.endswith("::none"):
        reasons.append("TEACHER_PRESENT_WITH_NONE_ID")

    if reasons:
        return AssignmentSemantic(LEGACY_MIGRATION_DRIFT, tuple(sorted(set(reasons))))
    return AssignmentSemantic(LEGACY_MIGRATION_SYNTHETIC)


def partition_teacher_class_assignments(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {
        OPERATIONAL_DVD: [],
        LEGACY_MIGRATION_SYNTHETIC: [],
        LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED: [],
        LEGACY_MIGRATION_DRIFT: [],
    }
    for row in rows:
        result[classify_teacher_class_assignment(row).kind].append(row)
    return result


def semantic_projection() -> dict[str, int]:
    """Campos mínimos para validar a semântica sem carregar payloads amplos."""
    return {
        "_id": 0,
        "id": 1,
        "teacher_id": 1,
        "class_id": 1,
        "component_id": 1,
        "source": 1,
        "migrated_from_legacy": 1,
        "synthetic_validity": 1,
        "created_by": 1,
        "migration_run_id": 1,
        "diary_settings": 1,
        "valid_from": 1,
        "valid_until": 1,
        "deleted": 1,
    }
