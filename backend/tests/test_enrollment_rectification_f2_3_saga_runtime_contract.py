from __future__ import annotations

import pytest

from services import enrollment_rectification_saga as saga
from services import enrollment_rectification_saga_runtime as runtime


class _InsertResult:
    inserted_id = "ok"


class _RunsCollection:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    async def find_one(self, query, projection=None):
        doc = self.docs.get(query.get("_id"))
        if not doc:
            return None
        if query.get("tenant_id") and doc.get("tenant_id") != query.get("tenant_id"):
            return None
        copy = dict(doc)
        if projection and projection.get("_id") == 0:
            copy.pop("_id", None)
        return copy

    async def insert_one(self, doc):
        self.docs[doc["_id"]] = dict(doc)
        return _InsertResult()


class _DB:
    def __init__(self):
        self.runs = _RunsCollection()

    def __getitem__(self, name):
        if name != saga.RUNS_COLLECTION:
            raise AssertionError(f"unexpected collection access: {name}")
        return self.runs


@pytest.mark.asyncio
async def test_prepare_runtime_uses_student_scoped_id_and_snapshot_digest(monkeypatch):
    db = _DB()
    claims = {
        "student_id": "student-1",
        "source_enrollment_id": "enrollment-1",
        "source_class_id": "class-source",
        "destination_class_id": "class-destination",
        "academic_year": 2026,
        "precondition_hash": "a" * 64,
    }
    canonical_snapshot = {
        "student": {"id": "student-1"},
        "enrollments": [],
        "attendance_documents": [],
        "grades": [],
    }

    monkeypatch.setattr(
        saga,
        "verify_rectification_dry_run_token",
        lambda *args, **kwargs: dict(claims),
    )
    monkeypatch.setattr(
        runtime,
        "_core_validate_human_gates",
        lambda **kwargs: "Justificativa operacional válida para o piloto controlado.",
    )

    async def fake_reauth(*args, **kwargs):
        return None

    async def fake_plan(*args, **kwargs):
        return ({"precondition_hash": "a" * 64}, {"inventory_digest": "doc-digest"})

    async def fake_snapshot(*args, **kwargs):
        return dict(canonical_snapshot)

    async def fake_acquire(*args, **kwargs):
        return True, {}

    async def fake_release(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime, "_core_reauthenticate", fake_reauth)
    monkeypatch.setattr(saga, "_current_saga_plan", fake_plan)
    monkeypatch.setattr(runtime, "_core_build_compensating_snapshot", fake_snapshot)
    monkeypatch.setattr(saga, "acquire_lock", fake_acquire)
    monkeypatch.setattr(saga, "release_lock", fake_release)

    result = await runtime.prepare_rectification_saga_execution(
        db,
        dry_run_token="signed-dry-run-token",
        tenant_id="tenant-1",
        actor={"id": "operator-1", "role": "super_admin", "email": "operator@example.invalid"},
        password="secret",
        confirmation="confirm",
        justification="Justificativa operacional válida para o piloto controlado.",
        idempotency_key="pilot-key-123456",
    )

    expected_prepare_id = runtime._core_prepare_id(
        "tenant-1", "student-1", "pilot-key-123456"
    )
    stored = db.runs.docs[expected_prepare_id]

    assert stored["prepare_id"] == expected_prepare_id
    assert stored["student_id"] == "student-1"
    assert stored["actor"]["id"] == "operator-1"
    assert stored["state"] == "PREPARED"
    assert stored["academic_mutation_performed"] is False
    assert stored["snapshot_digest"] == runtime._core_snapshot_digest(canonical_snapshot)
    assert stored["pre_execution_snapshot"]["snapshot_digest"] == stored["snapshot_digest"]
    assert result["prepare_id"] == expected_prepare_id
    assert result["snapshot_digest"] == stored["snapshot_digest"]
    assert result["idempotent_replay"] is False

    replay = await runtime.prepare_rectification_saga_execution(
        db,
        dry_run_token="signed-dry-run-token",
        tenant_id="tenant-1",
        actor={"id": "operator-1", "role": "super_admin", "email": "operator@example.invalid"},
        password="secret",
        confirmation="confirm",
        justification="Justificativa operacional válida para o piloto controlado.",
        idempotency_key="pilot-key-123456",
    )
    assert replay["prepare_id"] == expected_prepare_id
    assert replay["idempotent_replay"] is True
    assert len(db.runs.docs) == 1


@pytest.mark.asyncio
async def test_snapshot_adapter_accepts_f22_call_shape_and_adds_digest(monkeypatch):
    canonical = {
        "student": {"id": "student-1"},
        "enrollments": [{"id": "enrollment-1"}],
        "attendance_documents": [],
        "grades": [],
    }

    async def fake_snapshot(*args, **kwargs):
        assert kwargs == {"claims": {"student_id": "student-1"}, "tenant_id": "tenant-1"}
        return dict(canonical)

    monkeypatch.setattr(runtime, "_core_build_compensating_snapshot", fake_snapshot)
    adapted = await runtime.build_compensating_snapshot(
        object(),
        claims={"student_id": "student-1"},
        tenant_id="tenant-1",
        current_dry_run={"ignored": True},
    )

    assert adapted["student"] == canonical["student"]
    assert adapted["snapshot_digest"] == runtime._core_snapshot_digest(canonical)
    assert "snapshot_digest" not in canonical


def test_execute_uses_runtime_snapshot_binding():
    assert saga.build_compensating_snapshot is runtime.build_compensating_snapshot


@pytest.mark.asyncio
async def test_prepare_rejects_short_idempotency_key_without_journal(monkeypatch):
    db = _DB()
    monkeypatch.setattr(
        saga,
        "verify_rectification_dry_run_token",
        lambda *args, **kwargs: {
            "student_id": "student-1",
            "precondition_hash": "a" * 64,
        },
    )
    monkeypatch.setattr(
        runtime,
        "_core_validate_human_gates",
        lambda **kwargs: "Justificativa operacional válida com mais de trinta caracteres.",
    )

    async def fake_reauth(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime, "_core_reauthenticate", fake_reauth)

    with pytest.raises(runtime.RectificationSagaError) as caught:
        await runtime.prepare_rectification_saga_execution(
            db,
            dry_run_token="signed-dry-run-token",
            tenant_id="tenant-1",
            actor={"id": "operator-1", "role": "super_admin"},
            password="secret",
            confirmation="confirm",
            justification="Justificativa operacional válida com mais de trinta caracteres.",
            idempotency_key="short",
        )

    assert caught.value.code == "RECTIFICATION_IDEMPOTENCY_KEY_REQUIRED"
    assert caught.value.status_code == 422
    assert db.runs.docs == {}
