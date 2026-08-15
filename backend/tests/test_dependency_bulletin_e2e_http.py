"""E2E HTTP tests — Boletim de Dependência (Fase 3a, Jan/2026).

Cobre os endpoints novos via URL pública:
- GET /api/students/{id}/bulletins-index?academic_year=YYYY
- GET /api/students/{id}/dependency-bulletin?target_class_id=&academic_year=
- Smoke do endpoint regular já existente /api/students/{id}/bulletin
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import requests
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PWD = "@Celta2007"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PWD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token") or s.cookies.get("csrf_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


@pytest_asyncio.fixture
async def world():
    """Seed um aluno com 1 turma regular + 2 turmas de dependência."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    suf = uuid.uuid4().hex[:8]
    ids = {
        "student": f"e2e_dep_stu_{suf}",
        "class_reg": f"e2e_dep_cls_reg_{suf}",
        "class_dep_a": f"e2e_dep_cls_depA_{suf}",
        "school": f"e2e_dep_school_{suf}",
        "course_mat": f"e2e_dep_course_mat_{suf}",
        "course_cie": f"e2e_dep_course_cie_{suf}",
        "mant": None,
    }
    # Reusa mantenedora existente (preferindo SEMED para evitar choque de tenant)
    mant = await db.mantenedoras.find_one({}, {"_id": 0, "id": 1})
    ids["mant"] = mant["id"] if mant else None

    await db.schools.insert_one({
        "id": ids["school"], "name": "Escola E2E DEP",
        "mantenedora_id": ids["mant"],
    })
    await db.classes.insert_many([
        {"id": ids["class_reg"], "name": "7A REG E2E", "school_id": ids["school"],
         "course_ids": [ids["course_mat"]], "academic_year": 2026,
         "grade_level": "7º ano", "nivel_ensino": "fundamental_anos_finais",
         "mantenedora_id": ids["mant"]},
        {"id": ids["class_dep_a"], "name": "8A DEP E2E", "school_id": ids["school"],
         "academic_year": 2026, "grade_level": "8º ano",
         "nivel_ensino": "fundamental_anos_finais",
         "mantenedora_id": ids["mant"]},
    ])
    await db.courses.insert_many([
        {"id": ids["course_mat"], "name": "Matemática E2E", "active": True,
         "mantenedora_id": ids["mant"]},
        {"id": ids["course_cie"], "name": "Ciências E2E", "active": True,
         "mantenedora_id": ids["mant"]},
    ])
    await db.students.insert_one({
        "id": ids["student"], "full_name": "ALUNO E2E DEP",
        "class_id": ids["class_reg"], "school_id": ids["school"],
        "dependency_mode": "with_dependency",
        "academic_year": 2026,
        "mantenedora_id": ids["mant"],
    })
    await db.student_dependencies.insert_one({
        "id": f"e2e_dep_{suf}", "student_id": ids["student"],
        "class_id": ids["class_dep_a"], "course_id": ids["course_cie"],
        "academic_year": 2026, "status": "active",
        "mantenedora_id": ids["mant"],
    })

    yield ids

    # cleanup
    await db.schools.delete_many({"id": ids["school"]})
    await db.classes.delete_many({"id": {"$in": [ids["class_reg"], ids["class_dep_a"]]}})
    await db.courses.delete_many({"id": {"$regex": f"_{suf}$"}})
    await db.students.delete_many({"id": ids["student"]})
    await db.student_dependencies.delete_many({"student_id": ids["student"]})
    client.close()


# ----------------------- bulletins-index -----------------------

def test_bulletins_index_returns_regular_plus_dep(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/bulletins-index",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data["student_id"] == sid
    assert data["academic_year"] == 2026
    items = data["items"]
    assert isinstance(items, list)
    assert data["total"] == len(items)
    types = [i["type"] for i in items]
    assert "regular" in types, f"expected regular in {types}"
    assert "dependency" in types, f"expected dependency in {types}"
    # dep deve carregar class_id correto
    deps = [i for i in items if i["type"] == "dependency"]
    assert any(d["class_id"] == world["class_dep_a"] for d in deps)


def test_bulletins_index_invalid_year_returns_422(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/bulletins-index",
        params={"academic_year": 1800},
        timeout=30,
    )
    assert r.status_code == 422


def test_bulletins_index_no_auth_returns_401_or_403(world):
    sid = world["student"]
    r = requests.get(
        f"{BASE_URL}/api/students/{sid}/bulletins-index",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"got {r.status_code}"


# ----------------------- dependency-bulletin -----------------------

def test_dependency_bulletin_returns_dependency_type(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/dependency-bulletin",
        params={"academic_year": 2026, "target_class_id": world["class_dep_a"]},
        timeout=30,
    )
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data.get("bulletin_type") == "dependency"
    assert data.get("target_class_id") == world["class_dep_a"]
    assert data.get("student") is not None
    assert data["student"]["id"] == sid


def test_dependency_bulletin_missing_target_class_returns_422(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/dependency-bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 422


def test_dependency_bulletin_unknown_class_returns_warning(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/dependency-bulletin",
        params={"academic_year": 2026, "target_class_id": "turma_inexistente_xyz"},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    codes = {w.get("code") for w in (data.get("warnings") or [])}
    assert "DEPENDENCY_CLASS_NOT_FOUND" in codes or "NO_ACTIVE_DEPENDENCIES" in codes


# ----------------------- regular bulletin smoke -----------------------

def test_regular_bulletin_still_works(session, world):
    sid = world["student"]
    r = session.get(
        f"{BASE_URL}/api/students/{sid}/bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data.get("student") is not None
    assert data["student"]["id"] == sid
    # boletim regular não deve ter bulletin_type='dependency'
    assert data.get("bulletin_type") != "dependency"
