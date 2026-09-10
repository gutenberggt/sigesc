from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from services import enrollment_rectification_saga_ordinal_runtime as runtime
from services.enrollment_rectification_attendance_ordinal import OrdinalAttendanceError


class _Runs:
    def __init__(self, doc):
        self.doc = deepcopy(doc)

    async def find_one(self, query, projection=None):
        if str(query.get("_id")) != str(self.doc.get("_id")):
            return None
        if str(query.get("tenant_id")) != str(self.doc.get("tenant_id")):
            return None
        return deepcopy(self.doc)

    async def update_one(self, query, update):
        assert str(query.get("_id")) == str(self.doc.get("_id"))
        for key, value in (update.get("$set") or {}).items():
            self.doc[key] = deepcopy(value)
        for key in (update.get("$unset") or {}):
            self.doc.pop(key, None)
        for key, value in (update.get("$push") or {}).items():
            self.doc.setdefault(key, []).append(deepcopy(value))
        return type("R", (), {"modified_count": 1})()


class _DB:
    def __init__(self, run):
        self.runs = _Runs(run)

    def __getitem__(self, name):
        assert name == runtime._saga.RUNS_COLLECTION
        return self.runs


def _run(state="APPLIED"):
    return {
        "_id": "prepare-12345678901234567890",
        "prepare_id": "prepare-12345678901234567890",
        "tenant_id": "tenant-1",
        "protocol": "protocol-1",
        "student_id": "student-1",
        "source_class_id": "class-a",
        "destination_class_id": "class-b",
        "academic_year": 2026,
        "state": state,
        "actor": {"id": "admin-1", "role": "super_admin"},
        "checkpoints": [],
    }


def _plan(validated=False):
    destination = {"id": "att-b-1", "date": "2026-02-10", "aula_numero": 1}
    if validated:
        destination["validated_by"] = "teacher-1"
    return {
        "blockers": [],
        "components": [{
            "target_course_id": "course-b",
            "pairs": [{"ordinal": 1, "source": {}, "destination": destination}],
        }],
        "totals": {"source_records": 52, "applied_capacity": 47, "ignored_excess": 5},
    }


@pytest.mark.asyncio
async def test_attendance_checkpoint_materializes_ordinal_before_base_checkpoint(monkeypatch):
    db = _DB(_run("APPLYING"))
    ordinal_apply = AsyncMock(return_value={
        "state": "APPLIED",
        "summary": {"source_records": 52, "applied": 47, "ignored_excess": 5},
    })
    base_checkpoint = AsyncMock()
    monkeypatch.setattr(runtime, "build_ordinal_attendance_plan", AsyncMock(return_value=_plan()))
    monkeypatch.setattr(runtime, "apply_ordinal_attendance_from_ledger", ordinal_apply)
    monkeypatch.setattr(runtime, "_BASE_CHECKPOINT", base_checkpoint)

    await runtime._checkpoint_with_ordinal(
        db,
        run_id=db.runs.doc["prepare_id"],
        tenant_id="tenant-1",
        name="ATTENDANCE_APPLIED",
        detail={"items": 52},
    )

    ordinal_apply.assert_awaited_once()
    base_checkpoint.assert_awaited_once()
    assert db.runs.doc["ordinal_attendance_state"] == "APPLIED"
    assert db.runs.doc["ordinal_attendance_summary"]["ignored_excess"] == 5
    assert any(cp.get("name") == "ATTENDANCE_ORDINAL_APPLIED" for cp in db.runs.doc["checkpoints"])
    assert base_checkpoint.await_args.kwargs["detail"]["ordinal_summary"]["applied"] == 47


@pytest.mark.asyncio
async def test_validated_destination_requires_audit_context_before_write(monkeypatch):
    db = _DB(_run("APPLYING"))
    apply = AsyncMock()
    monkeypatch.setattr(runtime, "build_ordinal_attendance_plan", AsyncMock(return_value=_plan(validated=True)))
    monkeypatch.setattr(runtime, "apply_ordinal_attendance_from_ledger", apply)

    with pytest.raises(runtime.RectificationSagaError) as exc:
        await runtime._apply_ordinal_for_run(
            db,
            run=db.runs.doc,
            actor={"id": "admin-1", "role": "super_admin"},
            request=None,
            audit_service=None,
        )

    assert exc.value.code == "RECTIFICATION_ORDINAL_AUDIT_CONTEXT_REQUIRED"
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_applied_replay_materializes_ordinal_under_dedicated_lock(monkeypatch):
    db = _DB(_run("APPLIED"))
    base_execute = AsyncMock(return_value={"state": "APPLIED", "idempotent_replay": True})
    ordinal_apply = AsyncMock(return_value={
        "state": "APPLIED",
        "summary": {"source_records": 52, "applied": 47, "ignored_excess": 5},
    })
    acquire = AsyncMock(return_value=(True, {}))
    release = AsyncMock()
    monkeypatch.setattr(runtime._runtime, "execute_rectification_saga", base_execute)
    monkeypatch.setattr(runtime, "build_ordinal_attendance_plan", AsyncMock(return_value=_plan()))
    monkeypatch.setattr(runtime, "apply_ordinal_attendance_from_ledger", ordinal_apply)
    monkeypatch.setattr(runtime._saga, "acquire_lock", acquire)
    monkeypatch.setattr(runtime._saga, "release_lock", release)

    out = await runtime.execute_rectification_saga(
        db,
        prepare_id=db.runs.doc["prepare_id"],
        tenant_id="tenant-1",
        actor={"id": "admin-1", "role": "super_admin"},
        document_acknowledgement="ack",
    )

    assert out["state"] == "APPLIED"
    assert out["idempotent_replay"] is True
    assert out["attendance_ordinal_state"] == "APPLIED"
    assert out["attendance_ordinal_summary"]["ignored_excess"] == 5
    assert db.runs.doc["ordinal_attendance_state"] == "APPLIED"
    acquire.assert_awaited_once()
    release.assert_awaited_once()
    ordinal_apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_historical_recovery_failure_never_rolls_back_existing_enrollment(monkeypatch):
    db = _DB(_run("APPLIED"))
    monkeypatch.setattr(
        runtime._runtime,
        "execute_rectification_saga",
        AsyncMock(return_value={"state": "APPLIED", "idempotent_replay": True}),
    )
    monkeypatch.setattr(runtime, "build_ordinal_attendance_plan", AsyncMock(return_value=_plan()))
    monkeypatch.setattr(
        runtime,
        "apply_ordinal_attendance_from_ledger",
        AsyncMock(side_effect=OrdinalAttendanceError("ORDINAL_PLAN_BLOCKED", "blocked")),
    )
    monkeypatch.setattr(runtime, "compensate_ordinal_attendance", AsyncMock(return_value={}))
    monkeypatch.setattr(runtime._saga, "acquire_lock", AsyncMock(return_value=(True, {})))
    monkeypatch.setattr(runtime._saga, "release_lock", AsyncMock())
    rollback = AsyncMock(return_value={"state": "ROLLED_BACK"})
    monkeypatch.setattr(runtime._runtime, "rollback_rectification_saga", rollback)

    with pytest.raises(runtime.RectificationSagaError) as exc:
        await runtime.execute_rectification_saga(
            db,
            prepare_id=db.runs.doc["prepare_id"],
            tenant_id="tenant-1",
            actor={"id": "admin-1", "role": "super_admin"},
            document_acknowledgement="ack",
        )

    assert exc.value.code == "RECTIFICATION_ORDINAL_RECOVERY_FAILED"
    rollback.assert_not_awaited()
    assert db.runs.doc["state"] == "APPLIED"
    assert db.runs.doc["ordinal_attendance_state"] == "FAILED_RECOVERABLE"


@pytest.mark.asyncio
async def test_compensation_runs_ordinal_before_base_academic_compensation(monkeypatch):
    order = []

    async def ordinal(db, *, run):
        order.append("ordinal")
        return {"ordinal_attendance_compensated": 3}

    async def base(db, *, run):
        order.append("base")
        return {"attendance_revalidation_pending": False}

    monkeypatch.setattr(runtime, "compensate_ordinal_attendance", ordinal)
    monkeypatch.setattr(runtime, "_BASE_COMPENSATE_ACADEMIC", base)
    out = await runtime._compensate_academic_with_ordinal(object(), run=_run("APPLIED"))

    assert order == ["ordinal", "base"]
    assert out["ordinal_attendance_compensated"] == 3
    assert out["attendance_revalidation_pending"] is False


def test_router_uses_ordinal_runtime():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "routers" / "enrollment_rectification_saga.py").read_text(encoding="utf-8")
    assert "services.enrollment_rectification_saga_ordinal_runtime" in src
    assert "from services.enrollment_rectification_saga_runtime import" not in src
