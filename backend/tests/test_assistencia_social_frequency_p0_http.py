"""P0 — homologação HTTP da frequência exibida à Assistência Social.

Usa backend real + Mongo efêmero no workflow. Não toca produção.
Cobre autorização, multi-tenancy, calendário legado, atestado e consolidação
diária de frequência por componente.
"""
from __future__ import annotations

import os
import time

import pytest
import requests
from jose import jwt
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "sigesc_ci")
SECRET = os.environ["JWT_SECRET_KEY"]

YEAR = 2026
TENANT_A = "social-p0-tenant-a"
TENANT_B = "social-p0-tenant-b"
SCHOOL_A = "social-p0-school-a"
SCHOOL_B = "social-p0-school-b"
CLASS_A = "social-p0-class-a"
STUDENT_A = "social-p0-student-a"
ENROLL_A = "social-p0-enroll-a"

PREFIX = "social-p0-"


def _token(*, user_id: str, role: str, tenant_id: str | None, school_ids: list[str]) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "school_ids": school_ids,
        "email": f"{user_id}@ci.local",
        "mantenedora_id": tenant_id,
        "type": "access",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _headers(
    *,
    user_id: str,
    role: str,
    tenant_id: str | None,
    school_ids: list[str] | None = None,
    active_tenant: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_token(user_id=user_id, role=role, tenant_id=tenant_id, school_ids=school_ids or [])}"
    }
    if active_tenant:
        headers["X-Mantenedora-Id"] = active_tenant
    return headers


def _url(student_id: str = STUDENT_A) -> str:
    return f"{BASE_URL}/api/attendance/frequency/student/{student_id}?academic_year={YEAR}"


def _cleanup(db) -> None:
    for collection in (
        "medical_certificates",
        "attendance",
        "calendar_events",
        "calendario_letivo",
        "enrollments",
        "students",
        "classes",
        "schools",
        "mantenedoras",
    ):
        db[collection].delete_many({
            "$or": [
                {"id": {"$regex": f"^{PREFIX}"}},
                {"student_id": {"$regex": f"^{PREFIX}"}},
                {"mantenedora_id": {"$in": [TENANT_A, TENANT_B]}},
            ]
        })


def _attendance_doc(doc_id: str, tenant_id: str, date: str, status: str, course_id: str | None = None) -> dict:
    doc = {
        "id": doc_id,
        "mantenedora_id": tenant_id,
        "class_id": CLASS_A,
        "academic_year": YEAR,
        "date": date,
        "attendance_type": "by_course",
        "records": [{"student_id": STUDENT_A, "status": status}],
    }
    if course_id:
        doc["course_id"] = course_id
    return doc


def _seed(db) -> None:
    db.mantenedoras.insert_many([
        {"id": TENANT_A, "nome": "Tenant Social A"},
        {"id": TENANT_B, "nome": "Tenant Social B"},
    ])
    db.schools.insert_many([
        {"id": SCHOOL_A, "mantenedora_id": TENANT_A, "name": "Escola Social A", "status": "active"},
        {"id": SCHOOL_B, "mantenedora_id": TENANT_B, "name": "Escola Social B", "status": "active"},
    ])
    db.classes.insert_one({
        "id": CLASS_A,
        "mantenedora_id": TENANT_A,
        "school_id": SCHOOL_A,
        "name": "7º ANO A",
        "grade_level": "7º ANO",
        "education_level": "fundamental_anos_finais",
        "academic_year": YEAR,
    })
    db.students.insert_one({
        "id": STUDENT_A,
        "mantenedora_id": TENANT_A,
        "school_id": SCHOOL_A,
        "class_id": CLASS_A,
        "full_name": "Estudante Social P0",
        "status": "active",
        "student_series": "7º ANO",
    })
    db.enrollments.insert_one({
        "id": ENROLL_A,
        "mantenedora_id": TENANT_A,
        "student_id": STUDENT_A,
        "school_id": SCHOOL_A,
        "class_id": CLASS_A,
        "academic_year": YEAR,
        "status": "active",
    })

    # Período fechado em 27/08/2026: o denominador permanece determinístico
    # em qualquer rerun futuro. O feriado de 25/08 não possui end_date,
    # reproduzindo o formato legado que derrubava a implementação antiga.
    db.calendario_letivo.insert_one({
        "id": f"{PREFIX}calendar-a",
        "mantenedora_id": TENANT_A,
        "ano_letivo": YEAR,
        "school_id": None,
        "bimestre_1_inicio": "2026-08-24",
        "bimestre_1_fim": "2026-08-27",
        "bimestre_4_fim": "2026-08-27",
    })
    db.calendar_events.insert_one({
        "id": f"{PREFIX}holiday-a",
        "mantenedora_id": TENANT_A,
        "academic_year": YEAR,
        "event_type": "feriado_municipal",
        "is_school_day": False,
        "start_date": "2026-08-25",
        # end_date ausente intencionalmente
    })

    db.attendance.insert_many([
        _attendance_doc(f"{PREFIX}att-a-1", TENANT_A, "2026-08-24", "presente", "course-1"),
        # Atestado vence esta ausência.
        _attendance_doc(f"{PREFIX}att-a-2", TENANT_A, "2026-08-25", "absent", "course-1"),
        # 26/08: 1 presença + 1 falta = 50% => dia presente pela regra canônica.
        _attendance_doc(f"{PREFIX}att-a-3", TENANT_A, "2026-08-26", "P", "course-1"),
        _attendance_doc(f"{PREFIX}att-a-4", TENANT_A, "2026-08-26", "F", "course-2"),
        # 27/08: duas faltas => exatamente 1 falta diária.
        _attendance_doc(f"{PREFIX}att-a-5", TENANT_A, "2026-08-27", "F", "course-1"),
        _attendance_doc(f"{PREFIX}att-a-6", TENANT_A, "2026-08-27", "absent", "course-2"),
        # Documento malicioso/corrompido de outro tenant apontando para o mesmo
        # student_id. Sem apply_tenant_filter ele faria 26/08 virar falta.
        _attendance_doc(f"{PREFIX}att-b-cross", TENANT_B, "2026-08-26", "F", "course-x"),
    ])
    db.medical_certificates.insert_one({
        "id": f"{PREFIX}medical-a",
        "student_id": STUDENT_A,
        "start_date": "2026-08-25",
        "end_date": "2026-08-25",
        "reason": "Atestado CI",
    })


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    database = client[DB_NAME]
    _cleanup(database)
    _seed(database)
    yield database
    _cleanup(database)
    client.close()


def test_ass_social_reads_real_frequency_with_daily_consolidation_and_tenant_isolation(db):
    before = list(db.attendance.find({"id": {"$regex": f"^{PREFIX}"}}, {"_id": 0}).sort("id", 1))

    response = requests.get(
        _url(),
        headers=_headers(user_id="social-p0-ass", role="ass_social", tenant_id=TENANT_A),
        timeout=20,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["calculation_version"] == "social_daily_canonical_v2"
    assert body["summary"]["school_days_until_today"] == 3
    assert body["summary"]["absences"] == 1
    assert body["summary"]["medical"] == 1
    assert body["summary"]["attendance_percentage"] == 66.7

    after = list(db.attendance.find({"id": {"$regex": f"^{PREFIX}"}}, {"_id": 0}).sort("id", 1))
    assert after == before, "A consulta social não pode alterar attendance"


def test_ass_social_2_is_authorized(db):
    response = requests.get(
        _url(),
        headers=_headers(user_id="social-p0-ass2", role="ass_social_2", tenant_id=TENANT_A),
        timeout=20,
    )
    assert response.status_code == 200, response.text


def test_professor_cannot_use_social_frequency_endpoint(db):
    response = requests.get(
        _url(),
        headers=_headers(
            user_id="social-p0-prof",
            role="professor",
            tenant_id=TENANT_A,
            school_ids=[SCHOOL_A],
        ),
        timeout=20,
    )
    assert response.status_code == 403, response.text


def test_other_tenant_cannot_resolve_student(db):
    response = requests.get(
        _url(),
        headers=_headers(user_id="social-p0-admin-b", role="admin", tenant_id=TENANT_B),
        timeout=20,
    )
    assert response.status_code == 404, response.text


def test_scoped_superadmin_cannot_escape_active_tenant(db):
    response = requests.get(
        _url(),
        headers=_headers(
            user_id="social-p0-super",
            role="super_admin",
            tenant_id=None,
            active_tenant=TENANT_B,
        ),
        timeout=20,
    )
    assert response.status_code == 404, response.text
