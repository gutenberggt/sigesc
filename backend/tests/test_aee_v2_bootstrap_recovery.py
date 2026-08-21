"""Fase 2 — recuperação de bootstrap parcial do sidecar AEE v2."""

import asyncio
from copy import deepcopy

from pymongo.errors import DuplicateKeyError

from aee_v2.repository import AEEV2Repository
from aee_v2.versioning import bootstrap_documents


class FakeCollection:
    def __init__(self, kind):
        self.kind = kind
        self.docs = []

    async def create_index(self, *args, **kwargs):
        return kwargs.get("name", "index")

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                result = deepcopy(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    async def insert_one(self, doc):
        if self.kind == "heads":
            if any(d.get("legacy_plano_id") == doc.get("legacy_plano_id") for d in self.docs):
                raise DuplicateKeyError("duplicate head")
        else:
            version_key = (
                doc.get("legacy_plano_id"),
                doc.get("document_version"),
                doc.get("revision"),
            )
            if any(
                (
                    d.get("legacy_plano_id"),
                    d.get("document_version"),
                    d.get("revision"),
                ) == version_key
                for d in self.docs
            ):
                raise DuplicateKeyError("duplicate snapshot version")
        self.docs.append(deepcopy(doc))
        return object()


class FakeDB:
    def __init__(self):
        self.collections = {
            "aee_dossier_v2_heads": FakeCollection("heads"),
            "aee_dossier_v2_snapshots": FakeCollection("snapshots"),
        }

    def __getitem__(self, name):
        return self.collections[name]


def test_bootstrap_repairs_snapshot_without_head():
    legacy = {
        "id": "legacy-partial-1",
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "professor_aee_id": "prof-1",
        "status": "ativo",
    }
    actor = {"id": "prof-1", "role": "professor", "full_name": "Professora AEE"}

    async def scenario():
        db = FakeDB()
        repo = AEEV2Repository(db)

        # Simula queda do processo depois da inserção do snapshot v1.r1 e antes
        # da inserção do head.
        _head, stranded_snapshot = bootstrap_documents(legacy, actor=actor)
        await db[repo.SNAPSHOTS].insert_one(stranded_snapshot)
        assert await repo.get_head("legacy-partial-1") is None

        state = await repo.bootstrap(legacy, actor=actor)

        assert state.head is not None
        assert state.head.legacy_plano_id == "legacy-partial-1"
        assert state.head.working_snapshot_id == stranded_snapshot["id"]
        assert state.working_snapshot.id == stranded_snapshot["id"]
        assert state.active_snapshot is None
        assert state.effective_source == "legacy"
        assert len(db[repo.SNAPSHOTS].docs) == 1
        assert len(db[repo.HEADS].docs) == 1

    asyncio.run(scenario())
