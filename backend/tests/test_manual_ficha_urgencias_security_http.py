"""Homologação HTTP negativa de permissões e isolamento da Ficha de Urgências.

Usa backend real + Mongo efêmero do workflow. Não toca produção.
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

TENANT_A = "urg-sec-tenant-a"
TENANT_B = "urg-sec-tenant-b"
SCHOOL_A = "urg-sec-school-a"
SCHOOL_A2 = "urg-sec-school-a2"
SCHOOL_B = "urg-sec-school-b"
CLASS_A = "urg-sec-class-a"
CLASS_A2 = "urg-sec-class-a2"
CLASS_B = "urg-sec-class-b"
STUDENT_A = "urg-sec-student-a"
ENROLL_A = "urg-sec-enroll-a"
YEAR = 2026


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


def _headers(*, user_id: str, role: str, tenant_id: str | None, school_ids: list[str], active_tenant: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_token(user_id=user_id, role=role, tenant_id=tenant_id, school_ids=school_ids)}"
    }
    if active_tenant:
        headers["X-Mantenedora-Id"] = active_tenant
    return headers


def _cleanup(db) -> None:
    db.enrollments.delete_many({"id": ENROLL_A})
    db.students.delete_many({"id": STUDENT_A})
    db.classes.delete_many({"id": {"$in": [CLASS_A, CLASS_A2, CLASS_B]}})
    db.schools.delete_many({"id": {"$in": [SCHOOL_A, SCHOOL_A2, SCHOOL_B]}})
    db.mantenedoras.delete_many({"id": {"$in": [TENANT_A, TENANT_B]}})


def _seed(db) -> None:
    db.mantenedoras.insert_many([
        {"id": TENANT_A, "nome": "Tenant A"},
        {"id": TENANT_B, "nome": "Tenant B"},
    ])
    db.schools.insert_many([
        {"id": SCHOOL_A, "mantenedora_id": TENANT_A, "name": "Escola A", "status": "active"},
        {"id": SCHOOL_A2, "mantenedora_id": TENANT_A, "name": "Escola A2", "status": "active"},
        {"id": SCHOOL_B, "mantenedora_id": TENANT_B, "name": "Escola B", "status": "active"},
    ])
    db.classes.insert_many([
        {"id": CLASS_A, "mantenedora_id": TENANT_A, "school_id": SCHOOL_A, "name": "6º A", "academic_year": YEAR, "grade_level": "6º ANO"},
        {"id": CLASS_A2, "mantenedora_id": TENANT_A, "school_id": SCHOOL_A2, "name": "6º B", "academic_year": YEAR, "grade_level": "6º ANO"},
        {"id": CLASS_B, "mantenedora_id": TENANT_B, "school_id": SCHOOL_B, "name": "6º C", "academic_year": YEAR, "grade_level": "6º ANO"},
    ])
    db.students.insert_one({
        "id": STUDENT_A,
        "mantenedora_id": TENANT_A,
        "school_id": SCHOOL_A,
        "class_id": CLASS_A,
        "full_name": "Estudante Segurança A",
        "status": "active",
        "student_series": "6º ANO",
    })
    db.enrollments.insert_one({
        "id": ENROLL_A,
        "mantenedora_id": TENANT_A,
        "student_id": STUDENT_A,
        "school_id": SCHOOL_A,
        "class_id": CLASS_A,
        "academic_year": YEAR,
        "student_series": "6º ANO",
        "status": "active",
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


def _students_url(school_id: str, class_id: str) -> str:
    return f"{BASE_URL}/api/documents/ficha-individual-manual/students?school_id={school_id}&class_id={class_id}"


def test_authorized_school_role_can_access_own_school(db):
    response = requests.get(
        _students_url(SCHOOL_A, CLASS_A),
        headers=_headers(
            user_id="urg-sec-diretor-ok",
            role="diretor",
            tenant_id=TENANT_A,
            school_ids=[SCHOOL_A],
        ),
        timeout=20,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [STUDENT_A]


def test_professor_is_denied_even_inside_own_school(db):
    response = requests.get(
        _students_url(SCHOOL_A, CLASS_A),
        headers=_headers(
            user_id="urg-sec-professor",
            role="professor",
            tenant_id=TENANT_A,
            school_ids=[SCHOOL_A],
        ),
        timeout=20,
    )
    assert response.status_code == 403, response.text


def test_diretor_cannot_cross_school_scope(db):
    response = requests.get(
        _students_url(SCHOOL_A2, CLASS_A2),
        headers=_headers(
            user_id="urg-sec-diretor",
            role="diretor",
            tenant_id=TENANT_A,
            school_ids=[SCHOOL_A],
        ),
        timeout=20,
    )
    assert response.status_code == 403, response.text


def test_admin_cannot_cross_tenant(db):
    response = requests.get(
        _students_url(SCHOOL_B, CLASS_B),
        headers=_headers(
            user_id="urg-sec-admin",
            role="admin",
            tenant_id=TENANT_A,
            school_ids=[],
        ),
        timeout=20,
    )
    assert response.status_code == 404, response.text


def test_scoped_super_admin_cannot_escape_active_tenant(db):
    response = requests.get(
        _students_url(SCHOOL_B, CLASS_B),
        headers=_headers(
            user_id="urg-sec-super",
            role="super_admin",
            tenant_id=None,
            school_ids=[],
            active_tenant=TENANT_A,
        ),
        timeout=20,
    )
    assert response.status_code == 404, response.text
