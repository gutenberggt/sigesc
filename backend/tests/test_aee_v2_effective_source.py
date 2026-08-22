"""Fase 6.1A — regressão do resolver central read-only da fonte efetiva."""

import asyncio
from copy import deepcopy

import pytest

from aee_v2.effective_source import resolve_effective_dossier
from aee_v2.legacy_mapper import project_legacy_plan
from aee_v2.repository import AEEV2IntegrityError, AEEV2NotFound, AEEV2Repository
from aee_v2.versioning import make_snapshot


LEGACY_PLAN = {
    "id": "legacy-1",
    "student_id": "student-1",
    "school_id": "school-1",
    "academic_year": 2026,
    "professor_aee_id": "prof-1",
    "professor_aee_nome": "Professor AEE",
    "status": "rascunho",
    "dias_atendimento": ["segunda-feira"],
    "horario_inicio": "08:00",
    "horario_fim": "09:00",
    "local_atendimento": "Sala AEE",
}


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.find_one_calls = []

    async def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                result = deepcopy(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None


class FakeDB:
    def __init__(self, *, plans=None, heads=None, snapshots=None):
        self.planos_aee = FakeCollection(plans)
        self.collections = {
            AEEV2Repository.HEADS: FakeCollection(heads),
            AEEV2Repository.SNAPSHOTS: FakeCollection(snapshots),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _head(*, active_snapshot_id=None, working_snapshot_id=None):
    return {
        "id": "head-1",
        "legacy_plano_id": LEGACY_PLAN["id"],
        "student_id": LEGACY_PLAN["student_id"],
        "school_id": LEGACY_PLAN["school_id"],
        "academic_year": LEGACY_PLAN["academic_year"],
        "active_snapshot_id": active_snapshot_id,
        "working_snapshot_id": working_snapshot_id,
        "head_revision": 14,
        "next_document_version": 2,
        "created_at": "2026-08-22T12:00:00+00:00",
        "updated_at": "2026-08-22T12:00:00+00:00",
    }


def _active_snapshot():
    dossier = project_legacy_plan(LEGACY_PLAN).dossier
    dossier.study_case.demanda_inicial_contexto = "Conteúdo do V2 vigente"
    dossier.lifecycle.status = "active"
    return make_snapshot(
        legacy_plano_id=LEGACY_PLAN["id"],
        dossier=dossier,
        document_version=1,
        revision=14,
        operation="activate",
        actor={"id": "user-1", "full_name": "Usuário", "role": "super_admin"},
        changed_section="lifecycle",
    )


def test_resolver_without_v2_head_uses_legacy_projection():
    db = FakeDB(plans=[LEGACY_PLAN])

    resolved = asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))

    assert resolved.source == "legacy"
    assert resolved.active_snapshot_id is None
    assert resolved.document_version is None
    assert resolved.revision is None
    assert resolved.legacy_mapping_report is not None
    assert resolved.dossier.student_id == LEGACY_PLAN["student_id"]
    assert resolved.dossier.provenance.legacy_plano_id == LEGACY_PLAN["id"]


def test_resolver_with_working_only_keeps_legacy_as_effective_source():
    db = FakeDB(
        plans=[LEGACY_PLAN],
        heads=[_head(active_snapshot_id=None, working_snapshot_id="working-1")],
    )

    resolved = asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))

    assert resolved.source == "legacy"
    assert resolved.active_snapshot_id is None
    assert resolved.legacy_mapping_report is not None
    # Working snapshot não participa da decisão da fonte efetiva.
    assert db.collections[AEEV2Repository.SNAPSHOTS].find_one_calls == []


def test_resolver_with_valid_active_snapshot_uses_sidecar_active():
    snapshot = _active_snapshot()
    db = FakeDB(
        plans=[LEGACY_PLAN],
        heads=[_head(active_snapshot_id=snapshot["id"], working_snapshot_id=None)],
        snapshots=[snapshot],
    )

    resolved = asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))

    assert resolved.source == "sidecar_active"
    assert resolved.active_snapshot_id == snapshot["id"]
    assert resolved.document_version == 1
    assert resolved.revision == 14
    assert resolved.legacy_mapping_report is None
    assert resolved.dossier.lifecycle.status == "active"
    assert resolved.dossier.study_case.demanda_inicial_contexto == "Conteúdo do V2 vigente"


def test_resolver_blocks_silent_legacy_fallback_when_active_snapshot_is_missing():
    db = FakeDB(
        plans=[LEGACY_PLAN],
        heads=[_head(active_snapshot_id="missing-active", working_snapshot_id=None)],
    )

    with pytest.raises(AEEV2IntegrityError, match="fallback legado foi bloqueado"):
        asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))


def test_resolver_blocks_corrupted_active_snapshot():
    snapshot = _active_snapshot()
    corrupted = deepcopy(snapshot)
    corrupted["dossier"]["study_case"]["demanda_inicial_contexto"] = "violação do hash"

    db = FakeDB(
        plans=[LEGACY_PLAN],
        heads=[_head(active_snapshot_id=corrupted["id"], working_snapshot_id=None)],
        snapshots=[corrupted],
    )

    with pytest.raises(AEEV2IntegrityError, match="Falha de integridade no snapshot"):
        asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))


def test_resolver_rejects_orphan_v2_head_without_legacy_anchor():
    db = FakeDB(
        plans=[],
        heads=[_head(active_snapshot_id=None, working_snapshot_id="working-1")],
    )

    with pytest.raises(AEEV2IntegrityError, match="sem o Plano AEE legado"):
        asyncio.run(resolve_effective_dossier(db, LEGACY_PLAN["id"]))


def test_resolver_reports_missing_plan_when_no_legacy_and_no_head():
    db = FakeDB()

    with pytest.raises(AEEV2NotFound, match="Plano AEE legado não encontrado"):
        asyncio.run(resolve_effective_dossier(db, "legacy-inexistente"))
