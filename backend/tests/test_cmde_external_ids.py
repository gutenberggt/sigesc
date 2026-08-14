import asyncio

import pytest
from pymongo.errors import DuplicateKeyError

from mig.cmde.external_ids import (
    COLLECTION,
    SgpExternalIdConflict,
    SgpExternalIdError,
    SgpExternalIdStore,
    normalize_sgp_external_id,
)


class _InsertResult:
    inserted_id = "fake"


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))
        return kwargs.get("name")

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    async def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, document):
        # Emula os dois UNIQUE compostos relevantes da B.5.
        for current in self.docs:
            same_scope = all(
                current.get(key) == document.get(key)
                for key in ("provider", "namespace", "tenant_id", "entity_type")
            )
            if not same_scope:
                continue
            if current.get("internal_id") == document.get("internal_id"):
                raise DuplicateKeyError("internal link duplicate")
            if current.get("external_id") == document.get("external_id"):
                raise DuplicateKeyError("external link duplicate")
        self.docs.append(dict(document))
        return _InsertResult()


class FakeDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeAudit:
    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(dict(event))
        return dict(event)


def run(coro):
    return asyncio.run(coro)


def build_store():
    db = FakeDB()
    audit = FakeAudit()
    return db, audit, SgpExternalIdStore(db, audit=audit)


def test_normalize_sgp_external_id_accepts_positive_integer_and_decimal_string():
    assert normalize_sgp_external_id(123456) == "123456"
    assert normalize_sgp_external_id(" 00123456 ") == "123456"


@pytest.mark.parametrize("value", [None, True, False, 0, -1, "", "0", "abc", "12-3"])
def test_normalize_sgp_external_id_rejects_invalid_values(value):
    with pytest.raises(SgpExternalIdError):
        normalize_sgp_external_id(value)


def test_ensure_indexes_creates_internal_and_external_unique_constraints():
    db, _, store = build_store()
    run(store.ensure_indexes())

    indexes = db[COLLECTION].indexes
    by_name = {options.get("name"): (keys, options) for keys, options in indexes}

    assert by_name["ux_sgp_internal_link"][1]["unique"] is True
    assert by_name["ux_sgp_external_link"][1]["unique"] is True
    assert "ix_sgp_tenant_entity_updated" in by_name


def test_link_persists_in_mig_collection_without_touching_school_entities():
    db, audit, store = build_store()

    result = run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
            correlation_id="corr-1",
        )
    )

    assert result.created is True
    assert result.idempotent is False
    assert result.record.internal_id == "student-1"
    assert result.record.external_id == "123456"
    assert len(db[COLLECTION].docs) == 1
    assert db["students"].docs == []
    assert db["enrollments"].docs == []

    assert len(audit.events) == 1
    assert audit.events[0]["operation"] == "external_id.link.student"
    assert "external_id" not in audit.events[0]


def test_repeating_same_link_is_idempotent_and_does_not_duplicate_document():
    db, _, store = build_store()

    first = run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id="123456",
            source="cmde_lookup",
        )
    )
    second = run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="lot_reconciliation",
        )
    )

    assert first.created is True
    assert second.created is False
    assert second.idempotent is True
    assert second.record.id == first.record.id
    assert len(db[COLLECTION].docs) == 1


def test_same_internal_id_cannot_be_silently_rebound_to_another_sgp_id():
    _, audit, store = build_store()

    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
        )
    )

    with pytest.raises(SgpExternalIdConflict, match="já possui outro ID SGP"):
        run(
            store.link(
                tenant_id="tenant-a",
                entity_type="student",
                internal_id="student-1",
                external_id=654321,
                source="cmde_lookup",
            )
        )

    assert audit.events[-1]["status"] == "error"
    assert audit.events[-1]["error_code"] == "external_id_internal_conflict"


def test_same_external_id_cannot_point_to_two_internal_students_in_same_tenant():
    _, _, store = build_store()

    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
        )
    )

    with pytest.raises(SgpExternalIdConflict, match="outro registro SIGESC"):
        run(
            store.link(
                tenant_id="tenant-a",
                entity_type="student",
                internal_id="student-2",
                external_id=123456,
                source="cmde_lookup",
            )
        )


def test_tenant_scope_prevents_cross_network_collision():
    db, _, store = build_store()

    a = run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
        )
    )
    b = run(
        store.link(
            tenant_id="tenant-b",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
        )
    )

    assert a.record.tenant_id == "tenant-a"
    assert b.record.tenant_id == "tenant-b"
    assert len(db[COLLECTION].docs) == 2


def test_student_and_enrollment_namespaces_do_not_collide():
    db, _, store = build_store()

    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="same-internal-text",
            external_id=123456,
            source="cmde_lookup",
        )
    )
    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="enrollment",
            internal_id="same-internal-text",
            external_id=123456,
            source="cmde_lookup",
        )
    )

    assert len(db[COLLECTION].docs) == 2


def test_resolve_pair_returns_external_ids_without_replacing_internal_ids():
    _, _, store = build_store()

    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="student",
            internal_id="student-1",
            external_id=123456,
            source="cmde_lookup",
        )
    )
    run(
        store.link(
            tenant_id="tenant-a",
            entity_type="enrollment",
            internal_id="enrollment-1",
            external_id=987654,
            source="cmde_lookup",
        )
    )

    pair = run(
        store.resolve_pair(
            tenant_id="tenant-a",
            student_internal_id="student-1",
            enrollment_internal_id="enrollment-1",
        )
    )

    assert pair.student_external_id == "123456"
    assert pair.enrollment_external_id == "987654"


def test_resolve_pair_preserves_none_when_external_link_is_unknown():
    _, _, store = build_store()

    pair = run(
        store.resolve_pair(
            tenant_id="tenant-a",
            student_internal_id="student-unknown",
            enrollment_internal_id="enrollment-unknown",
        )
    )

    assert pair.student_external_id is None
    assert pair.enrollment_external_id is None
