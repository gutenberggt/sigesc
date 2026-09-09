"""F2.0 — regressão do núcleo seguro da Retificação de Matrícula/Turma.

A suíte prova que PREPARED pode ser criado, mas nenhuma coleção acadêmica é
alterada. A execução real continua inexistente/desabilitada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from auth_utils import hash_password
from services.enrollment_rectification import build_rectification_dry_run
from services.enrollment_rectification_execution import (
    CONFIRMATION_PHRASE,
    LOCKS_COLLECTION,
    RUNS_COLLECTION,
    RectificationExecutionError,
    _lock_target,
    academic_execution_enabled,
    prepare_rectification_execution,
    revalidate_rectification_preconditions,
    validate_state_transition,
    verify_rectification_dry_run_token,
)

YEAR = 2026
TENANT = "TENANT-F2"
SCHOOL = "SCHOOL-F2"
SOURCE = "CLASS-6A-F2"
DEST = "CLASS-7A-F2"
STUDENT = "STUDENT-F2-SYNTH"
COURSE_SOURCE = "COURSE-PT6-F2"
COURSE_DEST = "COURSE-PT7-F2"
SECRET = "f2-secret-" + ("x" * 64)
PASSWORD = "Senha-Segura-F2!"
ACTOR = {"id": "ADMIN-F2", "email": "admin-f2@example.test", "role": "admin"}
JUSTIFICATION = "Correção documental comprovada da turma originalmente cadastrada por engano."
BASE_NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_retification_f2_test"]


async def seed_base(db):
    await db.mantenedoras.insert_one({"id": TENANT, "name": "Tenant F2", "status": "active"})
    await db.schools.insert_one(
        {"id": SCHOOL, "name": "Escola F2", "mantenedora_id": TENANT, "status": "active"}
    )
    await db.users.insert_one(
        {
            "id": ACTOR["id"],
            "email": ACTOR["email"],
            "role": ACTOR["role"],
            "password_hash": hash_password(PASSWORD),
            "mantenedora_id": TENANT,
        }
    )
    await db.students.insert_one(
        {
            "id": STUDENT,
            "full_name": "Estudante Sintética F2",
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "class_id": SOURCE,
            "status": "active",
        }
    )
    await db.classes.insert_many(
        [
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
        ]
    )
    await db.enrollments.insert_one(
        {
            "id": "ENR-F2",
            "student_id": STUDENT,
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "class_id": SOURCE,
            "academic_year": YEAR,
            "enrollment_date": "2026-01-20",
            "enrollment_number": "20260077",
            "student_series": "6º ANO",
            "status": "active",
        }
    )
    await db.courses.insert_many(
        [
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
        ]
    )
    await db.grades.insert_one(
        {
            "id": "GRADE-F2",
            "student_id": STUDENT,
            "class_id": SOURCE,
            "course_id": COURSE_SOURCE,
            "academic_year": YEAR,
            "b1": 8.0,
            "grade_ownership": {"b1": {"assignment_id": "ASSIGN-SOURCE-F2"}},
            "mantenedora_id": TENANT,
        }
    )
    await db.attendance.insert_one(
        {
            "id": "ATT-F2",
            "class_id": SOURCE,
            "course_id": COURSE_SOURCE,
            "academic_year": YEAR,
            "date": "2026-03-12",
            "aula_numero": 2,
            "version": 4,
            "records": [
                {"student_id": STUDENT, "status": "P"},
                {"student_id": "OTHER", "status": "F"},
            ],
            "mantenedora_id": TENANT,
        }
    )


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


async def academic_snapshot(db):
    out = {}
    for name in (
        "students",
        "enrollments",
        "attendance",
        "grades",
        "student_history",
        "attendance_rectifications",
    ):
        docs = await db[name].find({}, {"_id": 0}).to_list(None)
        out[name] = sorted(docs, key=lambda item: repr(sorted(item.items())))
    return out


@pytest.mark.asyncio
async def test_valid_token_is_verified_and_execution_remains_disabled(db, monkeypatch):
    await seed_base(db)
    dry = await make_dry_run(db)
    claims = verify_rectification_dry_run_token(
        dry["dry_run_token"], tenant_id=TENANT, now=BASE_NOW, secret=SECRET
    )
    assert claims["student_id"] == STUDENT
    assert claims["source_class_id"] == SOURCE
    assert claims["destination_class_id"] == DEST
    assert claims["precondition_hash"] == dry["precondition_hash"]

    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "true")
    assert academic_execution_enabled() is False


@pytest.mark.asyncio
async def test_tampered_expired_and_cross_tenant_tokens_fail_closed(db):
    await seed_base(db)
    dry = await make_dry_run(db)
    token = dry["dry_run_token"]
    altered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(RectificationExecutionError) as exc:
        verify_rectification_dry_run_token(altered, tenant_id=TENANT, now=BASE_NOW, secret=SECRET)
    assert exc.value.code == "RECTIFICATION_DRY_RUN_TOKEN_SIGNATURE_INVALID"

    with pytest.raises(RectificationExecutionError) as exc:
        verify_rectification_dry_run_token(
            token,
            tenant_id=TENANT,
            now=BASE_NOW + timedelta(minutes=31),
            secret=SECRET,
        )
    assert exc.value.code == "RECTIFICATION_DRY_RUN_TOKEN_EXPIRED"

    with pytest.raises(RectificationExecutionError) as exc:
        verify_rectification_dry_run_token(token, tenant_id="OTHER-TENANT", now=BASE_NOW, secret=SECRET)
    assert exc.value.code == "RECTIFICATION_DRY_RUN_TENANT_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["grade", "attendance"])
async def test_toctou_detects_grade_or_attendance_change(db, mutation):
    await seed_base(db)
    dry = await make_dry_run(db)
    claims = verify_rectification_dry_run_token(
        dry["dry_run_token"], tenant_id=TENANT, now=BASE_NOW, secret=SECRET
    )
    if mutation == "grade":
        await db.grades.update_one({"id": "GRADE-F2"}, {"$set": {"b2": 7.5}})
    else:
        await db.attendance.update_one(
            {"id": "ATT-F2"},
            {"$set": {"records.0.status": "F", "version": 5}},
        )

    with pytest.raises(RectificationExecutionError) as exc:
        await revalidate_rectification_preconditions(
            db,
            claims=claims,
            tenant_id=TENANT,
            actor=ACTOR,
            now=BASE_NOW,
            secret=SECRET,
        )
    assert exc.value.code == "RECTIFICATION_PRECONDITION_CHANGED"


@pytest.mark.asyncio
async def test_toctou_detects_enrollment_change_after_dry_run(db):
    """A matrícula de origem pode mudar (ex.: ficar inativa) entre o dry-run e a
    preparação. `build_rectification_dry_run` recusa com um `RectificationDryRunError`
    de domínio (`PRIMARY_ENROLLMENT_CARDINALITY_INVALID`); a revalidação F2.0 deve
    converter isso em `RECTIFICATION_PRECONDITION_CHANGED` sem vazar o contrato F1
    cru, preservando o detalhe original para diagnóstico.
    """
    await seed_base(db)
    dry = await make_dry_run(db)
    claims = verify_rectification_dry_run_token(
        dry["dry_run_token"], tenant_id=TENANT, now=BASE_NOW, secret=SECRET
    )
    await db.enrollments.update_one({"id": "ENR-F2"}, {"$set": {"status": "transferred"}})

    with pytest.raises(RectificationExecutionError) as exc:
        await revalidate_rectification_preconditions(
            db,
            claims=claims,
            tenant_id=TENANT,
            actor=ACTOR,
            now=BASE_NOW,
            secret=SECRET,
        )
    assert exc.value.code == "RECTIFICATION_PRECONDITION_CHANGED"
    assert exc.value.detail["source_error_code"] == "PRIMARY_ENROLLMENT_CARDINALITY_INVALID"


@pytest.mark.asyncio
async def test_prepare_creates_only_control_plane_journal_and_is_idempotent(db):
    await seed_base(db)
    dry = await make_dry_run(db)
    before = await academic_snapshot(db)

    first = await prepare_rectification_execution(
        db,
        dry_run_token=dry["dry_run_token"],
        tenant_id=TENANT,
        actor=ACTOR,
        password=PASSWORD,
        confirmation=CONFIRMATION_PHRASE,
        justification=JUSTIFICATION,
        idempotency_key="rectification-f2-idempotency-001",
        now=BASE_NOW,
        secret=SECRET,
    )
    after = await academic_snapshot(db)

    assert before == after, "F2.0 não pode alterar coleções acadêmicas"
    assert first["state"] == "PREPARED"
    assert first["execution_enabled"] is False
    assert first["academic_mutation_performed"] is False
    assert first["idempotent_replay"] is False
    assert len(first["snapshot_digest"]) == 64
    assert await db[RUNS_COLLECTION].count_documents({}) == 1
    assert await db[LOCKS_COLLECTION].count_documents({}) == 0

    second = await prepare_rectification_execution(
        db,
        dry_run_token=dry["dry_run_token"],
        tenant_id=TENANT,
        actor=ACTOR,
        password=PASSWORD,
        confirmation=CONFIRMATION_PHRASE,
        justification=JUSTIFICATION,
        idempotency_key="rectification-f2-idempotency-001",
        now=BASE_NOW,
        secret=SECRET,
    )
    assert second["prepare_id"] == first["prepare_id"]
    assert second["protocol"] == first["protocol"]
    assert second["idempotent_replay"] is True
    assert await db[RUNS_COLLECTION].count_documents({}) == 1

    stored = await db[RUNS_COLLECTION].find_one({"prepare_id": first["prepare_id"]}, {"_id": 0})
    assert stored["academic_mutation_enabled"] is False
    assert stored["academic_mutation_performed"] is False
    assert stored["snapshot_is_final_for_mutation"] is False
    assert "password" not in repr(stored).lower()


@pytest.mark.asyncio
async def test_human_gates_and_reauthentication_fail_closed(db):
    await seed_base(db)
    dry = await make_dry_run(db)
    common = dict(
        db=db,
        dry_run_token=dry["dry_run_token"],
        tenant_id=TENANT,
        actor=ACTOR,
        idempotency_key="rectification-f2-human-gate",
        now=BASE_NOW,
        secret=SECRET,
    )

    with pytest.raises(RectificationExecutionError) as exc:
        await prepare_rectification_execution(
            **common,
            password=PASSWORD,
            confirmation="CONFIRMO",
            justification=JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_CONFIRMATION_MISMATCH"

    with pytest.raises(RectificationExecutionError) as exc:
        await prepare_rectification_execution(
            **common,
            password=PASSWORD,
            confirmation=CONFIRMATION_PHRASE,
            justification="curta",
        )
    assert exc.value.code == "RECTIFICATION_JUSTIFICATION_TOO_SHORT"

    with pytest.raises(RectificationExecutionError) as exc:
        await prepare_rectification_execution(
            **common,
            password="senha-incorreta",
            confirmation=CONFIRMATION_PHRASE,
            justification=JUSTIFICATION,
        )
    assert exc.value.code == "RECTIFICATION_REAUTH_FAILED"


@pytest.mark.asyncio
async def test_existing_student_lock_blocks_prepare(db, monkeypatch):
    await seed_base(db)
    dry = await make_dry_run(db)

    async def deny_lock(_db, target, holder, collection):
        assert target == _lock_target(TENANT, STUDENT)
        return False, {"holder": "other", "expires_at": BASE_NOW + timedelta(minutes=5)}

    monkeypatch.setattr(
        "services.enrollment_rectification_execution.acquire_lock",
        deny_lock,
    )
    with pytest.raises(RectificationExecutionError) as exc:
        await prepare_rectification_execution(
            db,
            dry_run_token=dry["dry_run_token"],
            tenant_id=TENANT,
            actor=ACTOR,
            password=PASSWORD,
            confirmation=CONFIRMATION_PHRASE,
            justification=JUSTIFICATION,
            idempotency_key="rectification-f2-lock-test",
            now=BASE_NOW,
            secret=SECRET,
        )
    assert exc.value.code == "RECTIFICATION_STUDENT_LOCKED"


def test_lock_scope_and_state_machine_are_explicit():
    assert _lock_target(TENANT, "STUDENT-A") != _lock_target(TENANT, "STUDENT-B")
    validate_state_transition("PREPARED", "APPLYING")
    validate_state_transition("APPLYING", "APPLIED")
    validate_state_transition("APPLIED", "ROLLING_BACK")
    validate_state_transition("ROLLING_BACK", "ROLLED_BACK")
    with pytest.raises(RectificationExecutionError) as exc:
        validate_state_transition("PREPARED", "APPLIED")
    assert exc.value.code == "RECTIFICATION_RUN_TRANSITION_FORBIDDEN"


def test_structural_guard_has_no_academic_writer_and_no_execute_route():
    service = Path("services/enrollment_rectification_execution.py").read_text(encoding="utf-8")
    f1_router = Path("routers/enrollment_rectification.py").read_text(encoding="utf-8")
    f2_router = Path("routers/enrollment_rectification_execution.py").read_text(encoding="utf-8")

    academic_collections = (
        "students",
        "enrollments",
        "attendance",
        "grades",
        "student_history",
        "attendance_rectifications",
    )
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
        for collection in academic_collections
        for method in write_methods
    ]
    found = [token for token in forbidden if token in service]
    assert not found, f"F2.0 contém writer acadêmico proibido: {found}"

    # F1 permanece estritamente read-only: só expõe /dry-run.
    assert '@router.post("/dry-run")' in f1_router
    assert '@router.post("/prepare-execution")' not in f1_router
    assert '@router.post("/execute")' not in f1_router
    assert '@router.post("/rollback")' not in f1_router

    # F2 é um router irmão dedicado: só expõe /prepare-execution.
    assert '@router.post("/prepare-execution")' in f2_router
    assert '@router.post("/dry-run")' not in f2_router
    assert '@router.post("/execute")' not in f2_router
    assert '@router.post("/rollback")' not in f2_router
