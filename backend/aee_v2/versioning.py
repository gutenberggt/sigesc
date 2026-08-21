"""AEE v2 — persistência sidecar versionada e imutável.

Fase 2.

Princípios:
- ``planos_aee`` continua intacta; nenhum método deste módulo escreve nela;
- cada salvamento cria um snapshot imutável em ``aee_dossier_v2_snapshots``;
- ``aee_dossier_v2_heads`` guarda somente ponteiros para o snapshot vigente e o
  snapshot em elaboração/revisão;
- optimistic locking usa ``head_revision`` + ``working_snapshot_id``;
- versões históricas nunca são sobrescritas nem excluídas;
- o hash SHA-256 do snapshot encadeia o histórico pelo hash do snapshot pai.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    AEEDossierV2,
    AEEPAEE,
    AEEPEI,
    AEESchedule,
    AEEStudyCase,
)
from .legacy_mapper import evaluate_minimum_gaps, project_legacy_plan


SnapshotOperation = Literal[
    "bootstrap",
    "update_study_case",
    "update_paee",
    "update_pei",
    "update_schedule",
    "start_revision",
    "activate",
]


class AEEV2PersistenceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AEEV2SnapshotSummary(AEEV2PersistenceBase):
    id: str
    legacy_plano_id: str
    document_version: int
    revision: int
    operation: SnapshotOperation
    snapshot_hash: str
    parent_snapshot_id: Optional[str] = None
    parent_hash: Optional[str] = None
    base_active_snapshot_id: Optional[str] = None
    created_at: str
    created_by: Optional[str] = None


class AEEV2Snapshot(AEEV2SnapshotSummary):
    schema_version: Literal[2] = 2
    dossier: AEEDossierV2
    changed_section: Optional[Literal["study_case", "paee", "pei", "schedule", "lifecycle"]] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None


class AEEV2Head(AEEV2PersistenceBase):
    id: str
    legacy_plano_id: str
    student_id: str
    school_id: str
    academic_year: int
    active_snapshot_id: Optional[str] = None
    working_snapshot_id: Optional[str] = None
    head_revision: int = 1
    next_document_version: int = 2
    created_at: str
    created_by: Optional[str] = None
    updated_at: str
    updated_by: Optional[str] = None


class AEEV2State(AEEV2PersistenceBase):
    legacy_plano_id: str
    effective_source: Literal["legacy", "sidecar_active"]
    head: Optional[AEEV2Head] = None
    active_snapshot: Optional[AEEV2Snapshot] = None
    working_snapshot: Optional[AEEV2Snapshot] = None


class AEEV2ExpectedHead(BaseModel):
    expected_head_revision: int = Field(ge=1)
    expected_working_snapshot_id: str


class AEEV2StudyCaseUpdate(AEEV2ExpectedHead):
    section: AEEStudyCase


class AEEV2PAEEUpdate(AEEV2ExpectedHead):
    section: AEEPAEE


class AEEV2PEIUpdate(AEEV2ExpectedHead):
    section: AEEPEI


class AEEV2ScheduleUpdate(AEEV2ExpectedHead):
    section: AEESchedule


class AEEV2ActivationRequest(AEEV2ExpectedHead):
    pass


class AEEV2ActivationValidation(AEEV2PersistenceBase):
    ready: bool
    blockers: list[dict[str, Any]] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    """Serialização determinística usada para integridade do snapshot."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_snapshot_hash(
    *,
    snapshot_id: str,
    legacy_plano_id: str,
    document_version: int,
    revision: int,
    operation: str,
    parent_hash: Optional[str],
    dossier: AEEDossierV2,
) -> str:
    payload = {
        "id": snapshot_id,
        "legacy_plano_id": legacy_plano_id,
        "document_version": document_version,
        "revision": revision,
        "operation": operation,
        "parent_hash": parent_hash,
        "dossier": dossier.model_dump(mode="json"),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _actor_fields(actor: Optional[dict]) -> dict[str, Optional[str]]:
    actor = actor or {}
    return {
        "created_by": actor.get("id"),
        "actor_name": actor.get("full_name") or actor.get("email"),
        "actor_role": actor.get("role"),
    }


def make_snapshot(
    *,
    legacy_plano_id: str,
    dossier: AEEDossierV2,
    document_version: int,
    revision: int,
    operation: SnapshotOperation,
    actor: Optional[dict],
    parent_snapshot: Optional[dict] = None,
    base_active_snapshot_id: Optional[str] = None,
    changed_section: Optional[str] = None,
) -> dict:
    """Cria documento append-only pronto para persistência."""
    snapshot_id = str(uuid.uuid4())
    parent_hash = (parent_snapshot or {}).get("snapshot_hash")
    parent_snapshot_id = (parent_snapshot or {}).get("id")
    now = utc_now_iso()

    # A versão documental é distinta da versão do schema.
    dossier = dossier.model_copy(deep=True)
    dossier.lifecycle.version = document_version

    snapshot_hash = compute_snapshot_hash(
        snapshot_id=snapshot_id,
        legacy_plano_id=legacy_plano_id,
        document_version=document_version,
        revision=revision,
        operation=operation,
        parent_hash=parent_hash,
        dossier=dossier,
    )

    return {
        "id": snapshot_id,
        "legacy_plano_id": legacy_plano_id,
        "schema_version": 2,
        "document_version": document_version,
        "revision": revision,
        "operation": operation,
        "changed_section": changed_section,
        "parent_snapshot_id": parent_snapshot_id,
        "parent_hash": parent_hash,
        "base_active_snapshot_id": base_active_snapshot_id,
        "snapshot_hash": snapshot_hash,
        "dossier": dossier.model_dump(mode="json"),
        "created_at": now,
        **_actor_fields(actor),
    }


def verify_snapshot_hash(snapshot: dict) -> bool:
    try:
        dossier = AEEDossierV2.model_validate(snapshot["dossier"])
        expected = compute_snapshot_hash(
            snapshot_id=snapshot["id"],
            legacy_plano_id=snapshot["legacy_plano_id"],
            document_version=int(snapshot["document_version"]),
            revision=int(snapshot["revision"]),
            operation=snapshot["operation"],
            parent_hash=snapshot.get("parent_hash"),
            dossier=dossier,
        )
    except (KeyError, TypeError, ValueError):
        return False
    return expected == snapshot.get("snapshot_hash")


def activation_validation(dossier: AEEDossierV2) -> AEEV2ActivationValidation:
    blockers: list[dict[str, Any]] = []

    for section_name in ("study_case", "paee", "pei"):
        section = getattr(dossier, section_name)
        if section.state != "complete":
            blockers.append(
                {
                    "code": "AEE_V2_SECTION_NOT_COMPLETE",
                    "section": section_name,
                    "field": "state",
                    "message": "A seção deve estar marcada como concluída antes da vigência.",
                }
            )

    for gap in evaluate_minimum_gaps(dossier):
        if gap.severity == "required":
            blockers.append(
                {
                    "code": gap.code,
                    "section": gap.section,
                    "field": gap.field,
                    "message": gap.description,
                }
            )

    return AEEV2ActivationValidation(ready=not blockers, blockers=blockers)


def dossier_with_section(
    snapshot: dict,
    *,
    section_name: Literal["study_case", "paee", "pei", "schedule"],
    section: BaseModel,
    actor_id: Optional[str],
) -> AEEDossierV2:
    dossier = AEEDossierV2.model_validate(deepcopy(snapshot["dossier"]))
    setattr(dossier, section_name, section)
    dossier.provenance.projection_mode = "native_v2"
    dossier.provenance.updated_by = actor_id
    dossier.provenance.updated_at = utc_now_iso()
    return dossier


def bootstrap_documents(plano: dict, *, actor: Optional[dict]) -> tuple[dict, dict]:
    """Gera head + snapshot inicial a partir do legado, sem escrever no legado."""
    projection = project_legacy_plan(plano)
    dossier = projection.dossier.model_copy(deep=True)
    dossier.lifecycle.status = "draft"
    dossier.lifecycle.version = 1

    legacy_plano_id = str(plano.get("id") or "")
    if not legacy_plano_id:
        raise ValueError("Plano AEE legado sem id")

    snapshot = make_snapshot(
        legacy_plano_id=legacy_plano_id,
        dossier=dossier,
        document_version=1,
        revision=1,
        operation="bootstrap",
        actor=actor,
    )
    now = utc_now_iso()
    head = {
        "id": str(uuid.uuid4()),
        "legacy_plano_id": legacy_plano_id,
        "student_id": dossier.student_id,
        "school_id": dossier.school_id,
        "academic_year": dossier.academic_year,
        "active_snapshot_id": None,
        "working_snapshot_id": snapshot["id"],
        "head_revision": 1,
        "next_document_version": 2,
        "created_at": now,
        "created_by": (actor or {}).get("id"),
        "updated_at": now,
        "updated_by": (actor or {}).get("id"),
    }
    return head, snapshot
