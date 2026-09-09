"""F2.2 — regressão da saga executável da Retificação de Matrícula/Turma.

Cobre: flag desabilitada = zero writes, happy path completo sem documentos,
replay idempotente de preparação e execução, TOCTOU obsoleto = zero write,
falhas com compensação (antes e depois da matrícula mover), resíduo antes de
qualquer revogação documental, tenant/ator inválidos (incluindo admin_teste),
identidade histórica da matrícula preservada, projeção via SSoT, rollback
elegível e bloqueado (revogação irreversível / nova emissão), falha de
compensação exigindo recuperação manual, e composição das rotas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from auth_utils import hash_password
from services.enrollment_rectification import build_rectification_dry_run
from services.enrollment_rectification_documents import DOCUMENT_ACKNOWLEDGEMENT
from services.enrollment_rectification_execution import (
    CONFIRMATION_PHRASE,
    RUNS_COLLECTION,
)
from services.enrollment_rectification_saga import (
    RectificationSagaError,
    execute_rectification_saga,
    prepare_rectification_saga_execution,
    rollback_rectification_saga,
    saga_execution_enabled,
)

YEAR = 2026
TENANT = "TENANT-F22"
SCHOOL = "SCHOOL-F22"
SOURCE = "CLASS-6A-F22"
DEST = "CLASS-7A-F22"
STUDENT = "STUDENT-F22-SYNTH"
OTHER_STUDENT = "OTHER-STUDENT-F22"
COURSE_SOURCE = "COURSE-PT6-F22"
COURSE_DEST = "COURSE-PT7-F22"
SECRET = "f22-secret-" + ("x" * 64)
PASSWORD = "Senha-Segura-F22!"
ACTOR = {"id": "ADMIN-F22", "email": "admin-f22@example.test", "role": "admin"}
JUSTIFICATION = "Correção documental comprovada da turma originalmente cadastrada por engano em 2026."
ROLLBACK_JUSTIFICATION = "Reversão solicitada após identificação de novo erro cadastral relevante."
BASE_NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_rectification_f22_test"]


async def seed_base(db):
    await db.mantenedoras.insert_one({"id": TENANT, "name": "Tenant F2.2", "status": "active"})
    await db.schools.insert_one({"id": SCHOOL, "name": "Escola F2.2", "mantenedora_id": TENANT, "status": "active"})
    await db.users.insert_one({
        "id": ACTOR["id"],
        "email": ACTOR["email"],
        "role": ACTOR["role"],
        "password_hash": hash_password(PASSWORD),
        "mantenedora_id": TENANT,
    })
    await db.students.insert_one({
        "id": STUDENT,
        "full_name": "Estudante Sintética F2.2",
        "mantenedora_id": TENANT,
        "school_id": SCHOOL,
        "class_id": SOURCE,
        "status": "active",
    })
    await db.classes.insert_many([
        {
            "id": SOURCE,
            "name": "6º ANO A",
            "grade_level": "6º ANO",
            "nivel_ensino": "fundamental_anos_finais",
            "education_level": "fundamental_anos_finais",
            "academic_year": YEAR,
            "school_id": SCHOOL,
            "mantenedora_id": TENANT,
            "course_ids": [COURSE_SOURCE],
        },
        {
            "id": DEST,
            "name": "7º ANO A",
            "grade_level": "7º ANO",
            "nivel_ensino": "fundamental_anos_finais",
            "education_level": "fundamental_anos_finais",
            "academic_year": YEAR,
            "school_id": SCHOOL,
            "mantenedora_id": TENANT,
            "course_ids": [COURSE_DEST],
        },
    ])
    await db.enrollments.insert_one({
        "id": "ENR-F22",
        "student_id": STUDENT,
        "mantenedora_id": TENANT,
        "school_id": SCHOOL,
        "class_id": SOURCE,
        "academic_year": YEAR,
        "enrollment_date": "2026-01-20",
        "enrollment_number": "20260099",
        "student_series": "6º ANO",
        "status": "active",
        "created_at": "2026-01-20T09:00:00+00:00",
    })
    await db.courses.insert_many([
        {
            "id": COURSE_SOURCE,
            "name": "Língua Portuguesa",
            "code": "LP",
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["6º ANO"],
            "mantenedora_id": TENANT,
        },
        {
            "id": COURSE_DEST,
            "name": "Língua Portuguesa",
            "code": "LP",
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["7º ANO"],
            "mantenedora_id": TENANT,
        },
    ])
    await db.grades.insert_one({
        "id": "GRADE-F22",
        "student_id": STUDENT,
        "class_id": SOURCE,
        "course_id": COURSE_SOURCE,
        "academic_year": YEAR,
        "b1": 8.0,
        "mantenedora_id": TENANT,
    })
    await db.attendance.insert_one({
        "id": "ATT-F22",
        "class_id": SOURCE,
        "course_id": COURSE_SOURCE,
        "academic_year": YEAR,
        "date": "2026-03-12",
        "aula_numero": 2,
        "version": 1,
        "records": [
            {"student_id": STUDENT, "status": "P"},
            {"student_id": OTHER_STUDENT, "status": "F"},
        ],
        "mantenedora_id": TENANT,
    })


async def make_dry_run(db, *, now=BASE_NOW):
    return await build_rectification_dry_run(
        db,
        student_id=STUDENT,
        destination_class_id=DEST,
        tenant_id=TENANT,
        actor=ACTOR,
        now=now,
        secret=SECRET,
    )


async def prepare(db, *, key="rect-f22-key-0001", now=BASE_NOW, actor=None):
    dry = await make_dry_run(db, now=now)
    return await prepare_rectification_saga_execution(
        db,
        dry_run_token=dry["dry_run_token"],
        tenant_id=TENANT,
        actor=actor or ACTOR,
        password=PASSWORD,
        confirmation=CONFIRMATION_PHRASE,
        justification=JUSTIFICATION,
        idempotency_key=key,
        now=now,
        secret=SECRET,
    )


async def academic_snapshot(db):
    out = {}
    for name in (
        "students",
        "enrollments",
        "attendance",
        "grades",
        "student_history",
        "attendance_rectifications",
        "grade_rectifications",
        "document_rectifications",
    ):
        docs = await db[name].find({}, {"_id": 0}).to_list(None)
        out[name] = sorted(docs, key=lambda item: repr(sorted(item.items())))
    return out


@pytest.mark.asyncio
async def test_execute_disabled_by_default_is_zero_write(db, monkeypatch):
    monkeypatch.delenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", raising=False)
    await seed_base(db)
    prepared = await prepare(db)
    before = await academic_snapshot(db)

    assert saga_execution_enabled() is False
    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.code == "RECTIFICATION_EXECUTION_DISABLED"
    assert exc.value.status_code == 503
    after = await academic_snapshot(db)
    assert before == after


@pytest.mark.asyncio
async def test_happy_path_without_documents_applies_and_preserves_identity(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    original_enrollment = await db.enrollments.find_one({"id": "ENR-F22"}, {"_id": 0})

    prepared = await prepare(db)
    assert prepared["state"] == "PREPARED"

    result = await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    assert result["state"] == "APPLIED"
    assert result["attendance_items_applied"] == 1
    assert result["grade_items_applied"] == 1
    assert result["documents_revoked"] == 0
    assert result["origin_residues"] == {
        "active_enrollment_in_source": 0,
        "attendance_records_in_source": 0,
        "grades_in_source": 0,
        "student_projection_in_source": 0,
    }

    enrollment = await db.enrollments.find_one({"id": "ENR-F22"}, {"_id": 0})
    assert enrollment["class_id"] == DEST
    assert enrollment["id"] == original_enrollment["id"]
    assert enrollment["enrollment_number"] == original_enrollment["enrollment_number"]
    assert enrollment["enrollment_date"] == original_enrollment["enrollment_date"]
    assert enrollment["academic_year"] == original_enrollment["academic_year"]
    assert enrollment["created_at"] == original_enrollment["created_at"]

    student = await db.students.find_one({"id": STUDENT}, {"_id": 0})
    assert student["class_id"] == DEST

    assert await db.attendance.count_documents({"class_id": DEST}) == 0
    origin_attendance = await db.attendance.find_one({"id": "ATT-F22"}, {"_id": 0})
    assert all(r["student_id"] != STUDENT for r in origin_attendance["records"])
    assert await db.attendance_rectifications.count_documents({"state": "APPLIED"}) == 1

    dest_grade = await db.grades.find_one({"student_id": STUDENT, "class_id": DEST}, {"_id": 0})
    assert dest_grade is not None
    assert dest_grade["b1"] == 8.0
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": SOURCE}) == 0

    run = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    assert run["state"] == "APPLIED"
    assert run["contract_version"] == "F2.2"


@pytest.mark.asyncio
async def test_prepare_is_idempotent_on_replay(db):
    await seed_base(db)
    first = await prepare(db, key="rect-f22-replay-key")
    second = await prepare(db, key="rect-f22-replay-key")
    assert second["prepare_id"] == first["prepare_id"]
    assert second["protocol"] == first["protocol"]
    assert second["idempotent_replay"] is True
    assert await db[RUNS_COLLECTION].count_documents({}) == 1


@pytest.mark.asyncio
async def test_execute_is_idempotent_when_already_applied(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    first = await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    assert first["idempotent_replay"] is False
    second = await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    assert second["state"] == "APPLIED"
    assert second["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_stale_toctou_blocks_execute_with_zero_writes(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    await db.grades.update_one({"id": "GRADE-F22"}, {"$set": {"b2": 9.0}})
    before = await academic_snapshot(db)

    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.code == "RECTIFICATION_PRECONDITION_CHANGED"
    after = await academic_snapshot(db)
    assert before == after


@pytest.mark.asyncio
async def test_grade_failure_after_attendance_compensates_without_moving_enrollment(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated grade failure")

    monkeypatch.setattr("services.enrollment_rectification_saga.apply_grade_rectification_item", boom)

    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.code == "RECTIFICATION_SAGA_APPLY_FAILED"
    assert exc.value.detail["run_state"] == "FAILED_COMPENSATED"

    run = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    assert run["state"] == "FAILED_COMPENSATED"

    enrollment = await db.enrollments.find_one({"id": "ENR-F22"}, {"_id": 0})
    assert enrollment["class_id"] == SOURCE
    student = await db.students.find_one({"id": STUDENT}, {"_id": 0})
    assert student["class_id"] == SOURCE
    origin_attendance = await db.attendance.find_one({"id": "ATT-F22"}, {"_id": 0})
    assert any(r["student_id"] == STUDENT for r in origin_attendance["records"])
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": SOURCE}) == 1
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": DEST}) == 0


@pytest.mark.asyncio
async def test_residue_failure_blocks_before_document_resolution_and_compensates(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    await db.bulletin_verifications.insert_one({
        "id": "BUL-F22",
        "student_id": STUDENT,
        "academic_year": YEAR,
        "mantenedora_id": TENANT,
        "revoked_at": None,
        "created_at": "2026-03-02T10:00:00+00:00",
    })
    prepared = await prepare(db)

    async def fake_residues(*args, **kwargs):
        return {
            "ok": False,
            "residues": {
                "active_enrollment_in_source": 1,
                "attendance_records_in_source": 0,
                "grades_in_source": 0,
                "student_projection_in_source": 1,
            },
        }

    monkeypatch.setattr(
        "services.enrollment_rectification_saga.detect_rectification_origin_residues", fake_residues
    )

    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.detail["run_state"] == "FAILED_COMPENSATED"

    # A revogação documental NUNCA pode ocorrer antes da pós-condição de origem zero.
    assert await db.document_rectifications.count_documents({}) == 0
    bulletin = await db.bulletin_verifications.find_one({"id": "BUL-F22"}, {"_id": 0})
    assert bulletin["revoked_at"] is None

    enrollment = await db.enrollments.find_one({"id": "ENR-F22"}, {"_id": 0})
    assert enrollment["class_id"] == SOURCE
    student = await db.students.find_one({"id": STUDENT}, {"_id": 0})
    assert student["class_id"] == SOURCE
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": SOURCE}) == 1
    origin_attendance = await db.attendance.find_one({"id": "ATT-F22"}, {"_id": 0})
    assert any(r["student_id"] == STUDENT for r in origin_attendance["records"])


@pytest.mark.asyncio
async def test_admin_teste_actor_forbidden_on_prepare_execute_rollback(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    sandbox_actor = {"id": "SANDBOX-F22", "role": "admin_teste"}

    dry = await make_dry_run(db)
    with pytest.raises(RectificationSagaError) as exc:
        await prepare_rectification_saga_execution(
            db,
            dry_run_token=dry["dry_run_token"],
            tenant_id=TENANT,
            actor=sandbox_actor,
            password=PASSWORD,
            confirmation=CONFIRMATION_PHRASE,
            justification=JUSTIFICATION,
            idempotency_key="rect-f22-admin-teste",
            now=BASE_NOW,
            secret=SECRET,
        )
    assert exc.value.code == "RECTIFICATION_SAGA_ACTOR_FORBIDDEN"

    prepared = await prepare(db, key="rect-f22-real-admin")
    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=sandbox_actor,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.code == "RECTIFICATION_SAGA_ACTOR_FORBIDDEN"

    with pytest.raises(RectificationSagaError) as exc:
        await rollback_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=sandbox_actor,
            password=PASSWORD,
            justification=ROLLBACK_JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_SAGA_ACTOR_FORBIDDEN"


@pytest.mark.asyncio
async def test_tenant_mismatch_run_not_found(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id="OTHER-TENANT",
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.code == "RECTIFICATION_RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_rollback_eligible_restores_source_state(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )

    result = await rollback_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        password=PASSWORD,
        justification=ROLLBACK_JUSTIFICATION,
    )
    assert result["state"] == "ROLLED_BACK"

    enrollment = await db.enrollments.find_one({"id": "ENR-F22"}, {"_id": 0})
    assert enrollment["class_id"] == SOURCE
    student = await db.students.find_one({"id": STUDENT}, {"_id": 0})
    assert student["class_id"] == SOURCE
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": SOURCE}) == 1
    assert await db.grades.count_documents({"student_id": STUDENT, "class_id": DEST}) == 0
    origin_attendance = await db.attendance.find_one({"id": "ATT-F22"}, {"_id": 0})
    assert any(r["student_id"] == STUDENT for r in origin_attendance["records"])

    run = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    assert run["state"] == "ROLLED_BACK"


@pytest.mark.asyncio
async def test_rollback_requires_correct_reauthentication(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )

    with pytest.raises(RectificationSagaError) as exc:
        await rollback_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            password="senha-errada",
            justification=ROLLBACK_JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_ROLLBACK_PREMUTATION_FAILED"
    run = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    assert run["state"] == "APPLIED"


@pytest.mark.asyncio
async def test_rollback_blocked_by_irreversible_document_revocation(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    await db.verifiable_documents.insert_one({
        "code": "SIGESC-F22-0001",
        "verification_token": "a" * 32,
        "mantenedora_id": TENANT,
        "student_id": STUDENT,
        "entity_id": STUDENT,
        "revoked": False,
        "revoked_at": None,
        "superseded_at": None,
        "created_at": "2026-03-01T10:00:00+00:00",
    })
    prepared = await prepare(db)
    result = await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    assert result["documents_revoked"] == 1

    with pytest.raises(RectificationSagaError) as exc:
        await rollback_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            password=PASSWORD,
            justification=ROLLBACK_JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_ROLLBACK_BLOCKED"
    assert "ROLLBACK_DOCUMENT_REVOCATION_IRREVERSIBLE" in {b["code"] for b in exc.value.detail["blockers"]}


@pytest.mark.asyncio
async def test_rollback_blocked_by_new_document_after_execution(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)
    await execute_rectification_saga(
        db,
        prepare_id=prepared["prepare_id"],
        tenant_id=TENANT,
        actor=ACTOR,
        document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    run_after_execute = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    executed_at = datetime.fromisoformat(run_after_execute["executed_at"])
    new_emitted_at = (executed_at + timedelta(days=1)).isoformat()

    await db.verifiable_documents.insert_one({
        "code": "SIGESC-F22-0002",
        "mantenedora_id": TENANT,
        "student_id": STUDENT,
        "entity_id": STUDENT,
        "revoked": False,
    })
    await db.school_documents_log.insert_one({
        "id": "LOG-F22-NEW",
        "student_id": STUDENT,
        "mantenedora_id": TENANT,
        "class_id": SOURCE,
        "code": "SIGESC-F22-0002",
        "emitted_at": new_emitted_at,
    })

    with pytest.raises(RectificationSagaError) as exc:
        await rollback_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            password=PASSWORD,
            justification=ROLLBACK_JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_ROLLBACK_BLOCKED"
    assert "ROLLBACK_NEW_DOCUMENT_ISSUANCE" in {b["code"] for b in exc.value.detail["blockers"]}


@pytest.mark.asyncio
async def test_compensation_failure_marks_manual_recovery(db, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    await seed_base(db)
    prepared = await prepare(db)

    async def boom_grade(*args, **kwargs):
        raise RuntimeError("simulated grade failure")

    async def boom_compensation(*args, **kwargs):
        raise RuntimeError("simulated compensation failure")

    monkeypatch.setattr("services.enrollment_rectification_saga.apply_grade_rectification_item", boom_grade)
    monkeypatch.setattr("services.enrollment_rectification_saga._compensate_academic", boom_compensation)

    with pytest.raises(RectificationSagaError) as exc:
        await execute_rectification_saga(
            db,
            prepare_id=prepared["prepare_id"],
            tenant_id=TENANT,
            actor=ACTOR,
            document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
        )
    assert exc.value.detail["run_state"] == "FAILED_MANUAL_RECOVERY"
    run = await db[RUNS_COLLECTION].find_one({"_id": prepared["prepare_id"]}, {"_id": 0})
    assert run["state"] == "FAILED_MANUAL_RECOVERY"
    assert run["compensation_failure"]


def test_saga_router_exposes_prepare_execute_rollback_only():
    from routers.enrollment_rectification_saga import setup_router

    db = AsyncMongoMockClient()["sigesc_rectification_f22_router_test"]
    router = setup_router(db)
    paths = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
    assert ("/admin/enrollment-rectification/prepare-execution", ("POST",)) in paths
    assert ("/admin/enrollment-rectification/execute", ("POST",)) in paths
    assert ("/admin/enrollment-rectification/rollback", ("POST",)) in paths
    assert len(paths) == 3


def test_structural_guard_saga_never_writes_students_class_students_or_events():
    text = Path("services/enrollment_rectification_saga.py").read_text(encoding="utf-8")
    write_methods = (
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "find_one_and_update",
        "bulk_write",
    )
    forbidden = [
        f"db.{collection}.{method}("
        for collection in ("students", "class_students", "academic_events")
        for method in write_methods
    ]
    found = [token for token in forbidden if token in text]
    assert not found, f"F2.2 saga contém write proibido: {found}"

    assert "rebuild_student_home_projection" in text
    assert "apply_attendance_rectification_item" in text
    assert "apply_grade_rectification_item" in text
    assert "resolve_rectification_documents" in text
    assert "detect_rectification_origin_residues" in text
    assert "saga_execution_enabled()" in text

    router_text = Path("routers/enrollment_rectification_saga.py").read_text(encoding="utf-8")
    assert '@router.post("/prepare-execution")' in router_text
    assert '@router.post("/execute")' in router_text
    assert '@router.post("/rollback")' in router_text

    f1_router_text = Path("routers/enrollment_rectification.py").read_text(encoding="utf-8")
    assert '@router.post("/dry-run")' in f1_router_text
    assert '@router.post("/execute")' not in f1_router_text
    assert '@router.post("/rollback")' not in f1_router_text
