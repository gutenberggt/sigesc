"""[Fase 2 — Fev/2026] Testes da migração `class_schedules` → `teacher_class_assignments`.

Chama o serviço diretamente (não HTTP) com cenários legacy isolados em
academic_year=2099. Cobre: preview, apply idempotente, invariante de
não-sobrescrita, duplicidade determinística inesperada (falha), rollback
com CAS e filtro por escola.
"""
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from services.grade_legacy_migration_service import (
    MIGRATION_SOURCE,
    UnexpectedDeterministicDuplicate,
    build_migration_diagnostic,
    execute_migration,
    execute_rollback,
)

load_dotenv()

AY = 2099
RUNS_COLLECTION = "grade_legacy_migration_runs"


@pytest.fixture
def db():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


@pytest.fixture
def cleanup():
    tag = f"test-gradmig-{uuid.uuid4().hex[:8]}"
    created = {
        "class_ids": [], "schedule_ids": [], "ta_ids": [], "staff_ids": [],
        "school_ids": [], "assignment_ids": [], "run_ids": [], "tag": tag,
    }
    yield created
    from pymongo import MongoClient
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if created["class_ids"]:
        sync.classes.delete_many({"id": {"$in": created["class_ids"]}})
    if created["schedule_ids"]:
        sync.class_schedules.delete_many({"id": {"$in": created["schedule_ids"]}})
    if created["ta_ids"]:
        sync.teacher_assignments.delete_many({"id": {"$in": created["ta_ids"]}})
    if created["staff_ids"]:
        sync.staff.delete_many({"id": {"$in": created["staff_ids"]}})
    if created["school_ids"]:
        sync.schools.delete_many({"id": {"$in": created["school_ids"]}})
    if created["run_ids"]:
        sync[RUNS_COLLECTION].delete_many({"run_id": {"$in": created["run_ids"]}})
    # Limpa quaisquer assignments de migração criados para as turmas de teste
    if created["class_ids"]:
        sync.teacher_class_assignments.delete_many({"class_id": {"$in": created["class_ids"]}})
    if created["assignment_ids"]:
        sync.teacher_class_assignments.delete_many({"id": {"$in": created["assignment_ids"]}})


async def _make_legacy_class(db, cleanup, *, school_id=None, course_id=None, teacher_staff_id=None):
    """Cria turma + class_schedules (2 slots, 1 curso) + teacher_assignments + staff."""
    school_id = school_id or str(uuid.uuid4())
    course_id = course_id or str(uuid.uuid4())
    teacher_staff_id = teacher_staff_id or str(uuid.uuid4())
    cid = str(uuid.uuid4())
    schedule_id = str(uuid.uuid4())
    ta_id = str(uuid.uuid4())

    await db.schools.update_one(
        {"id": school_id},
        {"$setOnInsert": {"id": school_id, "name": f"Escola {cleanup['tag']}"}},
        upsert=True,
    )
    if school_id not in cleanup["school_ids"]:
        cleanup["school_ids"].append(school_id)

    await db.classes.insert_one({
        "id": cid, "name": f"Turma {cleanup['tag']}", "school_id": school_id,
        "academic_year": AY, "status": "active", "shift": "morning",
        "mantenedora_id": "mant-test",
    })
    cleanup["class_ids"].append(cid)

    await db.staff.insert_one({"id": teacher_staff_id, "full_name": f"Prof {cleanup['tag']}"})
    cleanup["staff_ids"].append(teacher_staff_id)

    await db.class_schedules.insert_one({
        "id": schedule_id, "class_id": cid, "academic_year": AY, "shift": "morning",
        "slot_times": {"1": {"start": "07:00", "end": "07:50"},
                       "2": {"start": "08:00", "end": "08:50"}},
        "schedule_slots": [
            {"course_id": course_id, "course_name": "Matemática", "slot_number": 1, "day": "segunda"},
            {"course_id": course_id, "course_name": "Matemática", "slot_number": 2, "day": "terca"},
        ],
    })
    cleanup["schedule_ids"].append(schedule_id)

    await db.teacher_assignments.insert_one({
        "id": ta_id, "class_id": cid, "course_id": course_id, "staff_id": teacher_staff_id,
        "status": "ativo", "academic_year": AY, "created_at": "2099-02-01T00:00:00+00:00",
    })
    cleanup["ta_ids"].append(ta_id)

    det_id = f"legacy::{cid}::{course_id}::{teacher_staff_id}"
    return {"class_id": cid, "school_id": school_id, "course_id": course_id,
            "teacher_id": teacher_staff_id, "det_id": det_id}


# ===========================================================================
@pytest.mark.asyncio
async def test_preview_counts_and_sample(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    diag = await build_migration_diagnostic(db, {"academic_year": AY, "school_id": ctx["school_id"]})
    assert diag["total_classes_affected"] == 1
    assert diag["total_assignments_to_create"] == 1  # 1 curso × 1 professor agrupado
    assert diag["ignored_classes_with_new_model"] == 0
    assert len(diag["sample_synthesized"]) == 1
    sample = diag["sample_synthesized"][0]
    assert sample["source"] == MIGRATION_SOURCE
    assert sample["migrated_from_legacy"] is True
    assert len(sample["weekly_slots"]) == 2
    assert any(s["school_id"] == ctx["school_id"] for s in diag["by_school"])


@pytest.mark.asyncio
async def test_apply_creates_and_is_idempotent(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    scope = {"academic_year": AY, "school_id": ctx["school_id"]}

    r1 = await execute_migration(db, scope, dry_run=False, run_id="run-apply-1")
    assert r1["summary"]["created"] == 1
    assert r1["mode"] == "apply"
    doc = await db.teacher_class_assignments.find_one({"id": ctx["det_id"]}, {"_id": 0})
    assert doc is not None
    assert doc["source"] == MIGRATION_SOURCE
    assert doc["migration_run_id"] == "run-apply-1"
    assert doc["created_at"] == doc["updated_at"]  # CAS anchor

    # Re-run → idempotente, nada criado, sem duplicar
    r2 = await execute_migration(db, scope, dry_run=False, run_id="run-apply-2")
    assert r2["summary"]["created"] == 0
    assert r2["summary"]["already_present_idempotent"] == 1
    count = await db.teacher_class_assignments.count_documents({"id": ctx["det_id"]})
    assert count == 1


@pytest.mark.asyncio
async def test_dry_run_creates_nothing(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    r = await execute_migration(db, {"academic_year": AY, "school_id": ctx["school_id"]},
                                dry_run=True, run_id="run-dry")
    assert r["mode"] == "dry_run"
    assert r["summary"]["created"] == 0
    assert await db.teacher_class_assignments.count_documents({"id": ctx["det_id"]}) == 0


@pytest.mark.asyncio
async def test_invariant_skips_class_with_real_new_model(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    # Insere assignment REAL (não-migração) na turma
    real_id = str(uuid.uuid4())
    await db.teacher_class_assignments.insert_one({
        "id": real_id, "class_id": ctx["class_id"], "school_id": ctx["school_id"],
        "deleted": False, "source": "manual", "weekly_slots": [],
    })
    cleanup["assignment_ids"].append(real_id)

    diag = await build_migration_diagnostic(db, {"academic_year": AY, "school_id": ctx["school_id"]})
    assert diag["total_classes_affected"] == 0
    assert diag["ignored_classes_with_new_model"] == 1


@pytest.mark.asyncio
async def test_unexpected_deterministic_duplicate_aborts(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    # Pré-insere um doc NÃO-migração com o MESMO id determinístico, mas
    # vinculado a outra turma (para não acionar o invariante de skip).
    await db.teacher_class_assignments.insert_one({
        "id": ctx["det_id"], "class_id": "outra-turma", "source": "manual",
        "deleted": False, "weekly_slots": [],
    })
    cleanup["assignment_ids"].append(ctx["det_id"])

    with pytest.raises(UnexpectedDeterministicDuplicate):
        await execute_migration(db, {"academic_year": AY, "school_id": ctx["school_id"]},
                                dry_run=False, run_id="run-dup")


@pytest.mark.asyncio
async def test_rollback_deletes_created_with_cas(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    scope = {"academic_year": AY, "school_id": ctx["school_id"]}
    run_id = "run-rollback-src"
    r = await execute_migration(db, scope, dry_run=False, run_id=run_id)
    assert r["summary"]["created"] == 1
    # grava run real p/ o execute_rollback marcar
    run_doc = {"run_id": run_id, "mode": "apply", "diff": r["diff"]}
    await db[RUNS_COLLECTION].insert_one(dict(run_doc))
    cleanup["run_ids"].append(run_id)

    rb = await execute_rollback(db, run_doc, "rb-1", RUNS_COLLECTION)
    assert rb["summary"]["reverted"] == 1
    assert rb["summary"]["skipped_manual_edit"] == 0
    assert await db.teacher_class_assignments.count_documents({"id": ctx["det_id"]}) == 0
    # run original marcado como revertido
    updated = await db[RUNS_COLLECTION].find_one({"run_id": run_id}, {"_id": 0})
    assert updated["diff"]["rollback"]["reversed_by_run_id"] == "rb-1"


@pytest.mark.asyncio
async def test_rollback_preserves_manually_edited_doc(db, cleanup):
    ctx = await _make_legacy_class(db, cleanup)
    scope = {"academic_year": AY, "school_id": ctx["school_id"]}
    run_id = "run-rollback-edit"
    r = await execute_migration(db, scope, dry_run=False, run_id=run_id)
    assert r["summary"]["created"] == 1
    # Simula edição MANUAL pós-migração (bumpa updated_at ≠ created_at)
    await db.teacher_class_assignments.update_one(
        {"id": ctx["det_id"]}, {"$set": {"updated_at": "2099-12-31T23:59:59+00:00"}}
    )
    run_doc = {"run_id": run_id, "mode": "apply", "diff": r["diff"]}
    await db[RUNS_COLLECTION].insert_one(dict(run_doc))
    cleanup["run_ids"].append(run_id)

    rb = await execute_rollback(db, run_doc, "rb-2", RUNS_COLLECTION)
    assert rb["summary"]["reverted"] == 0
    assert rb["summary"]["skipped_manual_edit"] == 1
    # Doc editado NÃO foi apagado
    assert await db.teacher_class_assignments.count_documents({"id": ctx["det_id"]}) == 1


@pytest.mark.asyncio
async def test_school_filter_scopes_migration(db, cleanup):
    ctx_a = await _make_legacy_class(db, cleanup)
    ctx_b = await _make_legacy_class(db, cleanup)
    # Preview só da escola A
    diag = await build_migration_diagnostic(db, {"academic_year": AY, "school_id": ctx_a["school_id"]})
    affected = diag["_affected_class_ids"]
    assert ctx_a["class_id"] in affected
    assert ctx_b["class_id"] not in affected


@pytest.mark.asyncio
async def test_apply_multi_class_no_objectid_leak(db, cleanup):
    """Regressão do bug de prod: insert_many injeta `_id` (ObjectId) nos dicts;
    com 2 turmas na mesma escola, o sample_synthesized vazava ObjectId e
    quebrava a serialização JSON (500). Garante que NÃO vaza."""
    import json
    from bson import ObjectId

    school = str(uuid.uuid4())
    ctx1 = await _make_legacy_class(db, cleanup, school_id=school)
    ctx2 = await _make_legacy_class(db, cleanup, school_id=school)
    scope = {"academic_year": AY, "school_id": school}

    r = await execute_migration(db, scope, dry_run=False, run_id="run-multi")
    assert r["summary"]["created"] == 2  # 2 turmas × 1 componente
    # Nenhum doc do sample pode conter ObjectId / chave _id
    for doc in r["payload"]["sample_synthesized"]:
        assert "_id" not in doc
        assert not any(isinstance(v, ObjectId) for v in doc.values())
    # O payload inteiro precisa ser serializável (sem ObjectId)
    json.dumps(r["payload"], default=str)  # não deve depender de default p/ ObjectId
    assert all(
        not isinstance(v, ObjectId)
        for doc in r["payload"]["sample_synthesized"] for v in doc.values()
    )
    # Ambas as turmas foram gravadas
    assert await db.teacher_class_assignments.count_documents({"id": ctx1["det_id"]}) == 1
    assert await db.teacher_class_assignments.count_documents({"id": ctx2["det_id"]}) == 1


@pytest.mark.asyncio
async def test_preview_excludes_already_migrated(db, cleanup):
    """Após migrar, o preview deve descontar o já-migrado (progresso real)."""
    ctx = await _make_legacy_class(db, cleanup)
    scope = {"academic_year": AY, "school_id": ctx["school_id"]}

    await execute_migration(db, scope, dry_run=False, run_id="run-prog")
    diag = await build_migration_diagnostic(db, scope)
    assert diag["total_classes_affected"] == 0
    assert diag["total_assignments_to_create"] == 0
    assert diag["already_migrated_assignments"] == 1
