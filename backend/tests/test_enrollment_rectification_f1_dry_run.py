"""F1.0 — regressão do dry-run read-only de Retificação de Matrícula/Turma.

Os testes usam Mongo em memória e exercitam o serviço real. O cenário principal
simula 6º→7º com datas de frequência que não existem no destino, comprovando
que o dry-run inventaria impactos mas não cria sessão, matrícula, nota ou ledger.
"""
from __future__ import annotations

import importlib.util
import inspect
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from mongomock_motor import AsyncMongoMockClient

from auth_middleware import AuthMiddleware
from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)
import services.enrollment_rectification as service_mod


YEAR = 2026
TENANT_A = "TENANT-A"
TENANT_B = "TENANT-B"
SCHOOL_A = "SCHOOL-A"
SOURCE = "CLASS-6A"
DEST = "CLASS-7A"
STUDENT = "STUDENT-EMANUELLE-SYNTH"
COURSE_PT6 = "COURSE-PT-6"
COURSE_PT7 = "COURSE-PT-7"
COURSE_MAT6 = "COURSE-MAT-6"
COURSE_MAT7 = "COURSE-MAT-7"
SECRET = "r" * 64


_ROUTER_PATH = os.path.join(os.path.dirname(__file__), "..", "routers", "enrollment_rectification.py")
_spec = importlib.util.spec_from_file_location("enrollment_rectification_router_under_test", _ROUTER_PATH)
router_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router_mod)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_retification_f1_test"]


def make_request(path: str, *, tenant: str | None = None) -> Request:
    headers = [(b"authorization", b"Bearer test")]
    if tenant:
        headers.append((b"x-mantenedora-id", tenant.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def seed_base(db, *, destination_school: str = SCHOOL_A, special_destination: bool = False):
    await db.mantenedoras.insert_many(
        [
            {"id": TENANT_A, "name": "Tenant A", "status": "active"},
            {"id": TENANT_B, "name": "Tenant B", "status": "active"},
        ]
    )
    schools = [
        {"id": SCHOOL_A, "name": "Escola A", "mantenedora_id": TENANT_A, "status": "active"}
    ]
    if destination_school != SCHOOL_A:
        schools.append(
            {"id": destination_school, "name": "Escola B", "mantenedora_id": TENANT_A, "status": "active"}
        )
    await db.schools.insert_many(schools)

    await db.students.insert_one(
        {
            "id": STUDENT,
            "full_name": "Estudante Sintética",
            "mantenedora_id": TENANT_A,
            "school_id": SCHOOL_A,
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
                "academic_year": YEAR,
                "school_id": SCHOOL_A,
                "mantenedora_id": TENANT_A,
                "course_ids": [COURSE_PT6, COURSE_MAT6],
            },
            {
                "id": DEST,
                "name": "7º ANO A",
                "grade_level": "7º ANO",
                "nivel_ensino": "fundamental_anos_finais",
                "academic_year": YEAR,
                "school_id": destination_school,
                "mantenedora_id": TENANT_A,
                "course_ids": [COURSE_PT7, COURSE_MAT7],
                "atendimento_programa": "aee" if special_destination else "",
            },
        ]
    )
    await db.enrollments.insert_one(
        {
            "id": "ENR-1",
            "student_id": STUDENT,
            "mantenedora_id": TENANT_A,
            "school_id": SCHOOL_A,
            "class_id": SOURCE,
            "academic_year": YEAR,
            "enrollment_date": "2026-01-20",
            "enrollment_number": "20260001",
            "student_series": "6º ANO",
            "status": "active",
        }
    )
    await db.courses.insert_many(
        [
            {
                "id": COURSE_PT6,
                "name": "Língua Portuguesa",
                "code": "LP",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º ANO"],
                "mantenedora_id": TENANT_A,
            },
            {
                "id": COURSE_PT7,
                "name": "Língua Portuguesa",
                "code": "LP",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["7º ANO"],
                "mantenedora_id": TENANT_A,
            },
            {
                "id": COURSE_MAT6,
                "name": "Matemática",
                "code": "MAT",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º ANO"],
                "mantenedora_id": TENANT_A,
            },
            {
                "id": COURSE_MAT7,
                "name": "Matemática",
                "code": "MAT",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["7º ANO"],
                "mantenedora_id": TENANT_A,
            },
        ]
    )
    await db.grades.insert_one(
        {
            "id": "GRADE-PT6",
            "student_id": STUDENT,
            "class_id": SOURCE,
            "course_id": COURSE_PT6,
            "academic_year": YEAR,
            "b1": 8.5,
            "b2": 9.0,
            "grade_ownership": {"b1": {"assignment_id": "ASSIGN-ORIGIN"}},
            "mantenedora_id": TENANT_A,
        }
    )
    await db.attendance.insert_one(
        {
            "id": "ATT-MAT6-2026-03-12-2",
            "class_id": SOURCE,
            "course_id": COURSE_MAT6,
            "academic_year": YEAR,
            "date": "2026-03-12",
            "aula_numero": 2,
            "assignment_id": "ASSIGN-ORIGIN",
            "version": 7,
            "records": [
                {"student_id": STUDENT, "status": "P"},
                {"student_id": "OTHER-STUDENT", "status": "F"},
            ],
            "mantenedora_id": TENANT_A,
        }
    )


async def snapshot(db):
    names = sorted(await db.list_collection_names())
    out = {}
    for name in names:
        docs = await db[name].find({}, {"_id": 0}).to_list(None)
        out[name] = sorted(docs, key=lambda d: repr(sorted(d.items())))
    return out


@pytest.mark.asyncio
async def test_happy_path_maps_courses_and_is_strictly_read_only(db):
    await seed_base(db)
    before = await snapshot(db)

    result = await build_rectification_dry_run(
        db,
        student_id=STUDENT,
        destination_class_id=DEST,
        tenant_id=TENANT_A,
        actor={"id": "ADMIN-1", "email": "admin@example.test"},
        secret=SECRET,
    )

    after = await snapshot(db)
    assert after == before, "F1.0 dry-run não pode produzir qualquer write"
    assert result["execution_enabled"] is False
    assert result["can_execute_later"] is True
    assert result["origin_class"]["id"] == SOURCE
    assert result["destination_class"]["id"] == DEST
    assert result["enrollment"]["id"] == "ENR-1"
    assert "." in result["dry_run_token"]
    assert len(result["precondition_hash"]) == 64

    mapped = {m["source_course_id"]: m for m in result["course_map"]}
    assert mapped[COURSE_PT6]["target_course_id"] == COURSE_PT7
    assert mapped[COURSE_PT6]["method"] == "unique_code"
    assert mapped[COURSE_MAT6]["target_course_id"] == COURSE_MAT7

    att = result["attendance_manifest"][0]
    assert att["source_date"] == "2026-03-12"
    assert att["source_aula_numero"] == 2
    assert att["target_course_id"] == COURSE_MAT7
    assert att["destination_overlap_count"] == 0
    assert await db.attendance.count_documents({"class_id": DEST}) == 0
    assert await db.attendance_rectifications.count_documents({}) == 0


@pytest.mark.asyncio
async def test_ambiguous_curriculum_mapping_blocks(db):
    await seed_base(db)
    await db.courses.insert_one(
        {
            "id": "COURSE-PT7-DUP",
            "name": "Português Alternativo",
            "code": "LP",
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["7º ANO"],
            "mantenedora_id": TENANT_A,
        }
    )
    await db.classes.update_one({"id": DEST}, {"$push": {"course_ids": "COURSE-PT7-DUP"}})

    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    codes = {b["code"] for b in result["blockers"]}
    assert "COURSE_MAPPING_AMBIGUOUS" in codes
    assert result["can_execute_later"] is False


@pytest.mark.asyncio
async def test_destination_grade_value_collision_blocks(db):
    await seed_base(db)
    await db.grades.insert_one(
        {
            "id": "GRADE-PT7",
            "student_id": STUDENT,
            "class_id": DEST,
            "course_id": COURSE_PT7,
            "academic_year": YEAR,
            "b1": 7.0,
            "mantenedora_id": TENANT_A,
        }
    )
    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    assert "GRADE_DESTINATION_VALUE_PRESENT" in {b["code"] for b in result["blockers"]}


@pytest.mark.asyncio
async def test_destination_attendance_overlap_blocks_without_modifying_either_class(db):
    await seed_base(db)
    await db.attendance.insert_one(
        {
            "id": "ATT-DEST",
            "class_id": DEST,
            "course_id": COURSE_MAT7,
            "academic_year": YEAR,
            "date": "2026-03-12",
            "aula_numero": 5,
            "records": [{"student_id": STUDENT, "status": "P"}],
            "mantenedora_id": TENANT_A,
        }
    )
    before = await snapshot(db)
    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    assert "ATTENDANCE_OVERLAP_DESTINATION" in {b["code"] for b in result["blockers"]}
    assert await snapshot(db) == before


@pytest.mark.asyncio
async def test_dependencies_and_academic_events_are_fail_closed(db):
    await seed_base(db)
    await db.student_dependencies.insert_one(
        {
            "id": "DEP-1",
            "student_id": STUDENT,
            "class_id": SOURCE,
            "course_id": COURSE_PT6,
            "status": "active",
            "mantenedora_id": TENANT_A,
        }
    )
    await db.academic_events.insert_one(
        {
            "id": "EV-1",
            "student_id": STUDENT,
            "event_type": "remanejamento",
            "origin_class_id": SOURCE,
            "destination_class_id": "OTHER",
            "effective_date": "2026-02-10",
            "mantenedora_id": TENANT_A,
        }
    )
    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    codes = {b["code"] for b in result["blockers"]}
    assert "STUDENT_DEPENDENCY_REVIEW_REQUIRED" in codes
    assert "ACADEMIC_EVENT_REVIEW_REQUIRED" in codes


@pytest.mark.asyncio
async def test_document_manifest_reports_known_ledgers_and_explicit_coverage_gap(db):
    await seed_base(db)
    await db.school_documents_log.insert_one(
        {
            "id": "DOCLOG-1",
            "student_id": STUDENT,
            "class_id": SOURCE,
            "academic_year": YEAR,
            "mantenedora_id": TENANT_A,
        }
    )
    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    assert result["documents"]["coverage_complete"] is False
    assert result["documents"]["tracked_counts"]["school_documents_log"] == 1
    assert result["documents"]["coverage_gap"]["code"] == "SYNC_PDF_LEDGER_GAP"
    assert "DOCUMENT_RESOLUTION_REQUIRED_F1_3" in {b["code"] for b in result["blockers"]}


@pytest.mark.asyncio
async def test_same_school_and_regular_class_are_v1_requirements(db):
    await seed_base(db, destination_school="SCHOOL-OTHER", special_destination=True)
    result = await build_rectification_dry_run(
        db, student_id=STUDENT, destination_class_id=DEST, tenant_id=TENANT_A, secret=SECRET
    )
    codes = {b["code"] for b in result["blockers"]}
    assert "DIFFERENT_SCHOOL" in codes
    assert "DESTINATION_SPECIAL_CLASS" in codes


@pytest.mark.asyncio
async def test_cross_tenant_destination_is_invisible(db):
    await seed_base(db)
    await db.classes.insert_one(
        {
            "id": "DEST-B",
            "name": "7º B",
            "grade_level": "7º ANO",
            "academic_year": YEAR,
            "school_id": "SCHOOL-B",
            "mantenedora_id": TENANT_B,
        }
    )
    with pytest.raises(RectificationDryRunError) as exc:
        await build_rectification_dry_run(
            db,
            student_id=STUDENT,
            destination_class_id="DEST-B",
            tenant_id=TENANT_A,
            secret=SECRET,
        )
    assert exc.value.code == "DESTINATION_CLASS_NOT_FOUND"
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_without_selected_tenant_fails_closed(db, monkeypatch):
    await db.mantenedoras.insert_one({"id": TENANT_A, "name": "Tenant A", "status": "active"})

    async def fake_user(_request):
        return {"id": "SUPER", "role": "super_admin", "email": "super@example.test"}

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_user))
    request = make_request("/api/admin/enrollment-rectification/dry-run")
    with pytest.raises(HTTPException) as exc:
        await router_mod.require_rectification_context(db, request)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TENANT_CONTEXT_REQUIRED"


@pytest.mark.asyncio
async def test_admin_cannot_override_own_tenant_with_header(db, monkeypatch):
    await db.mantenedoras.insert_many(
        [
            {"id": TENANT_A, "name": "Tenant A", "status": "active"},
            {"id": TENANT_B, "name": "Tenant B", "status": "active"},
        ]
    )

    async def fake_user(_request):
        return {"id": "ADMIN", "role": "admin", "mantenedora_id": TENANT_A}

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_user))
    request = make_request("/api/admin/enrollment-rectification/dry-run", tenant=TENANT_B)
    _user, tenant = await router_mod.require_rectification_context(db, request)
    assert tenant.id == TENANT_A
    assert tenant.source == "user"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin_teste", "secretario", "diretor", "professor"])
async def test_non_authorized_roles_are_rejected(db, monkeypatch, role):
    async def fake_user(_request):
        return {"id": "USER", "role": role, "mantenedora_id": TENANT_A}

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_user))
    request = make_request("/api/admin/enrollment-rectification/dry-run", tenant=TENANT_A)
    with pytest.raises(HTTPException) as exc:
        await router_mod.require_rectification_context(db, request)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "RECTIFICATION_ROLE_FORBIDDEN"


def test_f1_service_has_no_mongo_write_calls():
    source = inspect.getsource(service_mod)
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".find_one_and_update(",
        ".bulk_write(",
    )
    assert not [token for token in forbidden if token in source]


def test_f1_router_exposes_dry_run_only(db):
    router = router_mod.setup_router(db)
    paths = {route.path for route in router.routes}
    assert paths == {"/admin/enrollment-rectification/dry-run"}
    assert not any("execute" in path or "rollback" in path for path in paths)
