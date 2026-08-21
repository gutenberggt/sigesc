"""Repositório sidecar do Dossiê AEE v2.

Somente as coleções ``aee_dossier_v2_heads`` e ``aee_dossier_v2_snapshots`` são
escritas. ``planos_aee`` é lida pelo router para bootstrap, nunca alterada aqui.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .contracts import AEEDossierV2
from .versioning import (
    AEEV2State,
    activation_validation,
    bootstrap_documents,
    dossier_with_section,
    make_snapshot,
    utc_now_iso,
    verify_snapshot_hash,
)


class AEEV2RepositoryError(RuntimeError):
    code = "AEE_V2_REPOSITORY_ERROR"


class AEEV2Conflict(AEEV2RepositoryError):
    code = "AEE_V2_OPTIMISTIC_LOCK_CONFLICT"


class AEEV2IntegrityError(AEEV2RepositoryError):
    code = "AEE_V2_SNAPSHOT_INTEGRITY_ERROR"


class AEEV2NotFound(AEEV2RepositoryError):
    code = "AEE_V2_NOT_FOUND"


class AEEV2ValidationError(AEEV2RepositoryError):
    code = "AEE_V2_ACTIVATION_BLOCKED"

    def __init__(self, message: str, *, blockers: Optional[list[dict[str, Any]]] = None):
        super().__init__(message)
        self.blockers = blockers or []


class AEEV2Repository:
    HEADS = "aee_dossier_v2_heads"
    SNAPSHOTS = "aee_dossier_v2_snapshots"

    def __init__(self, db):
        self.db = db
        self.heads = db[self.HEADS]
        self.snapshots = db[self.SNAPSHOTS]
        self._indexes_ready = False

    async def ensure_indexes(self):
        if self._indexes_ready:
            return

        await self.heads.create_index(
            [("legacy_plano_id", ASCENDING)],
            unique=True,
            name="uq_aee_v2_head_legacy_plano",
        )
        await self.heads.create_index(
            [("school_id", ASCENDING), ("academic_year", DESCENDING)],
            name="ix_aee_v2_head_school_year",
        )
        await self.snapshots.create_index(
            [("id", ASCENDING)],
            unique=True,
            name="uq_aee_v2_snapshot_id",
        )
        await self.snapshots.create_index(
            [
                ("legacy_plano_id", ASCENDING),
                ("document_version", ASCENDING),
                ("revision", ASCENDING),
            ],
            unique=True,
            name="uq_aee_v2_snapshot_version_revision",
        )
        await self.snapshots.create_index(
            [("legacy_plano_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_aee_v2_snapshot_history",
        )
        self._indexes_ready = True

    async def get_head(self, legacy_plano_id: str) -> Optional[dict]:
        return await self.heads.find_one({"legacy_plano_id": legacy_plano_id}, {"_id": 0})

    async def get_snapshot(self, snapshot_id: Optional[str]) -> Optional[dict]:
        if not snapshot_id:
            return None
        snapshot = await self.snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if snapshot and not verify_snapshot_hash(snapshot):
            raise AEEV2IntegrityError(
                f"Falha de integridade no snapshot AEE v2 {snapshot_id}."
            )
        return snapshot

    async def get_state(self, legacy_plano_id: str) -> AEEV2State:
        head = await self.get_head(legacy_plano_id)
        if not head:
            return AEEV2State(
                legacy_plano_id=legacy_plano_id,
                effective_source="legacy",
            )

        active = await self.get_snapshot(head.get("active_snapshot_id"))
        working = await self.get_snapshot(head.get("working_snapshot_id"))
        return AEEV2State(
            legacy_plano_id=legacy_plano_id,
            effective_source="sidecar_active" if active else "legacy",
            head=head,
            active_snapshot=active,
            working_snapshot=working,
        )

    async def bootstrap(self, plano: dict, *, actor: Optional[dict]) -> AEEV2State:
        await self.ensure_indexes()
        legacy_plano_id = str(plano.get("id") or "")
        if not legacy_plano_id:
            raise ValueError("Plano AEE legado sem id")

        existing = await self.get_head(legacy_plano_id)
        if existing:
            return await self.get_state(legacy_plano_id)

        head, snapshot = bootstrap_documents(plano, actor=actor)
        try:
            await self.snapshots.insert_one(deepcopy(snapshot))
            await self.heads.insert_one(deepcopy(head))
        except DuplicateKeyError as exc:
            # Corrida concorrente: o primeiro bootstrap válido vence. Nenhum
            # documento legado é tocado; o chamador recarrega o head vencedor.
            winner = await self.get_head(legacy_plano_id)
            if winner:
                return await self.get_state(legacy_plano_id)
            raise AEEV2Conflict("Bootstrap concorrente do Dossiê AEE v2.") from exc

        return await self.get_state(legacy_plano_id)

    async def save_section(
        self,
        legacy_plano_id: str,
        *,
        section_name: str,
        section,
        expected_head_revision: int,
        expected_working_snapshot_id: str,
        actor: Optional[dict],
    ) -> AEEV2State:
        await self.ensure_indexes()
        head = await self.get_head(legacy_plano_id)
        if not head:
            raise AEEV2NotFound("Dossiê AEE v2 ainda não foi inicializado.")
        if (
            head.get("head_revision") != expected_head_revision
            or head.get("working_snapshot_id") != expected_working_snapshot_id
        ):
            raise AEEV2Conflict("O Dossiê foi alterado por outra sessão. Recarregue antes de salvar.")

        parent = await self.get_snapshot(expected_working_snapshot_id)
        if not parent:
            raise AEEV2NotFound("Snapshot de trabalho não encontrado.")

        dossier = dossier_with_section(
            parent,
            section_name=section_name,
            section=section,
            actor_id=(actor or {}).get("id"),
        )
        operation = {
            "study_case": "update_study_case",
            "paee": "update_paee",
            "pei": "update_pei",
            "schedule": "update_schedule",
        }[section_name]
        new_snapshot = make_snapshot(
            legacy_plano_id=legacy_plano_id,
            dossier=dossier,
            document_version=int(parent["document_version"]),
            revision=int(parent["revision"]) + 1,
            operation=operation,
            actor=actor,
            parent_snapshot=parent,
            base_active_snapshot_id=head.get("active_snapshot_id"),
            changed_section=section_name,
        )

        try:
            await self.snapshots.insert_one(deepcopy(new_snapshot))
        except DuplicateKeyError as exc:
            raise AEEV2Conflict(
                "Já existe uma revisão concorrente para esta versão do Dossiê."
            ) from exc

        now = utc_now_iso()
        updated = await self.heads.find_one_and_update(
            {
                "legacy_plano_id": legacy_plano_id,
                "head_revision": expected_head_revision,
                "working_snapshot_id": expected_working_snapshot_id,
            },
            {
                "$set": {
                    "working_snapshot_id": new_snapshot["id"],
                    "updated_at": now,
                    "updated_by": (actor or {}).get("id"),
                },
                "$inc": {"head_revision": 1},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise AEEV2Conflict(
                "O ponteiro do Dossiê mudou durante o salvamento. Recarregue antes de continuar."
            )
        return await self.get_state(legacy_plano_id)

    async def start_revision(
        self,
        legacy_plano_id: str,
        *,
        expected_head_revision: int,
        actor: Optional[dict],
    ) -> AEEV2State:
        await self.ensure_indexes()
        head = await self.get_head(legacy_plano_id)
        if not head:
            raise AEEV2NotFound("Dossiê AEE v2 ainda não foi inicializado.")
        if head.get("head_revision") != expected_head_revision:
            raise AEEV2Conflict("O Dossiê foi alterado por outra sessão.")
        if head.get("working_snapshot_id"):
            raise AEEV2Conflict("Já existe uma versão em elaboração ou revisão.")
        active = await self.get_snapshot(head.get("active_snapshot_id"))
        if not active:
            raise AEEV2Conflict("Não há versão v2 vigente para iniciar uma nova revisão.")

        document_version = int(head.get("next_document_version") or 1)
        dossier = AEEDossierV2.model_validate(deepcopy(active["dossier"]))
        dossier.lifecycle.status = "review"
        dossier.lifecycle.version = document_version
        dossier.provenance.projection_mode = "native_v2"
        dossier.provenance.updated_by = (actor or {}).get("id")
        dossier.provenance.updated_at = utc_now_iso()

        new_snapshot = make_snapshot(
            legacy_plano_id=legacy_plano_id,
            dossier=dossier,
            document_version=document_version,
            revision=1,
            operation="start_revision",
            actor=actor,
            parent_snapshot=active,
            base_active_snapshot_id=active["id"],
            changed_section="lifecycle",
        )
        try:
            await self.snapshots.insert_one(deepcopy(new_snapshot))
        except DuplicateKeyError as exc:
            raise AEEV2Conflict("Já existe uma revisão documental concorrente.") from exc

        updated = await self.heads.find_one_and_update(
            {
                "legacy_plano_id": legacy_plano_id,
                "head_revision": expected_head_revision,
                "working_snapshot_id": None,
                "active_snapshot_id": active["id"],
            },
            {
                "$set": {
                    "working_snapshot_id": new_snapshot["id"],
                    "updated_at": utc_now_iso(),
                    "updated_by": (actor or {}).get("id"),
                },
                "$inc": {"head_revision": 1, "next_document_version": 1},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise AEEV2Conflict("O Dossiê mudou durante a abertura da revisão.")
        return await self.get_state(legacy_plano_id)

    async def validate_working_for_activation(self, legacy_plano_id: str):
        head = await self.get_head(legacy_plano_id)
        if not head or not head.get("working_snapshot_id"):
            raise AEEV2NotFound("Não há versão em elaboração para validar.")
        working = await self.get_snapshot(head["working_snapshot_id"])
        if not working:
            raise AEEV2NotFound("Snapshot de trabalho não encontrado.")
        dossier = AEEDossierV2.model_validate(working["dossier"])
        return activation_validation(dossier)

    async def activate(
        self,
        legacy_plano_id: str,
        *,
        expected_head_revision: int,
        expected_working_snapshot_id: str,
        actor: Optional[dict],
    ) -> AEEV2State:
        await self.ensure_indexes()
        head = await self.get_head(legacy_plano_id)
        if not head:
            raise AEEV2NotFound("Dossiê AEE v2 ainda não foi inicializado.")
        if (
            head.get("head_revision") != expected_head_revision
            or head.get("working_snapshot_id") != expected_working_snapshot_id
        ):
            raise AEEV2Conflict("O Dossiê foi alterado por outra sessão.")

        working = await self.get_snapshot(expected_working_snapshot_id)
        if not working:
            raise AEEV2NotFound("Snapshot de trabalho não encontrado.")
        dossier = AEEDossierV2.model_validate(deepcopy(working["dossier"]))
        validation = activation_validation(dossier)
        if not validation.ready:
            raise AEEV2ValidationError(
                "A versão ainda possui requisitos obrigatórios pendentes.",
                blockers=validation.blockers,
            )

        dossier.lifecycle.status = "active"
        dossier.provenance.projection_mode = "native_v2"
        dossier.provenance.updated_by = (actor or {}).get("id")
        dossier.provenance.updated_at = utc_now_iso()
        active_snapshot = make_snapshot(
            legacy_plano_id=legacy_plano_id,
            dossier=dossier,
            document_version=int(working["document_version"]),
            revision=int(working["revision"]) + 1,
            operation="activate",
            actor=actor,
            parent_snapshot=working,
            base_active_snapshot_id=head.get("active_snapshot_id"),
            changed_section="lifecycle",
        )
        try:
            await self.snapshots.insert_one(deepcopy(active_snapshot))
        except DuplicateKeyError as exc:
            raise AEEV2Conflict("Já existe uma ativação concorrente desta versão.") from exc

        updated = await self.heads.find_one_and_update(
            {
                "legacy_plano_id": legacy_plano_id,
                "head_revision": expected_head_revision,
                "working_snapshot_id": expected_working_snapshot_id,
            },
            {
                "$set": {
                    "active_snapshot_id": active_snapshot["id"],
                    "working_snapshot_id": None,
                    "updated_at": utc_now_iso(),
                    "updated_by": (actor or {}).get("id"),
                },
                "$inc": {"head_revision": 1},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise AEEV2Conflict("O Dossiê mudou durante a ativação.")
        return await self.get_state(legacy_plano_id)

    async def list_snapshots(self, legacy_plano_id: str, *, limit: int = 100) -> list[dict]:
        cursor = self.snapshots.find(
            {"legacy_plano_id": legacy_plano_id},
            {"_id": 0, "dossier": 0},
        ).sort([("document_version", DESCENDING), ("revision", DESCENDING)]).limit(limit)
        return await cursor.to_list(length=limit)
