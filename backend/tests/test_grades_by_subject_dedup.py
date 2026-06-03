"""Regressão de /analytics/grades/by-subject ("Média por Componente Curricular").

Regras (Jun/2026):
  - Cada componente aparece UMA única vez (mescla course_ids de mesmo nome).
  - Ordem decrescente por média (maior no topo).
  - Considera apenas 3º ao 9º Ano e EJA (exclui Ed. Infantil, 1º e 2º Ano).

Semeia dados isolados no ano 2099 e valida via HTTP, limpando ao final.
"""
import os
import asyncio
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"

YEAR = 2099
SCHOOL = "bs-school-2099"
CLS_OK = "bs-cls-3ano-2099"     # 3º Ano → elegível
CLS_EXCL = "bs-cls-1ano-2099"   # 1º Ano → excluída
C1 = "bs-course-mat-1"          # Matemática (dup 1)
C2 = "bs-course-mat-2"          # Matemática (dup 2)
C3 = "bs-course-hist"           # História


def _token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await _cleanup(db)
    await db.classes.insert_many([
        {"id": CLS_OK, "school_id": SCHOOL, "academic_year": YEAR, "grade_level": "3º Ano", "name": "3º Ano A"},
        {"id": CLS_EXCL, "school_id": SCHOOL, "academic_year": YEAR, "grade_level": "1º Ano", "name": "1º Ano A"},
    ])
    await db.courses.insert_many([
        {"id": C1, "name": "Matemática"},
        {"id": C2, "name": "Matemática"},
        {"id": C3, "name": "História"},
    ])
    g = lambda cid, course, st, avg: {  # noqa: E731
        "id": str(uuid.uuid4()), "class_id": cid, "course_id": course,
        "student_id": st, "academic_year": YEAR, "final_average": avg}
    await db.grades.insert_many([
        g(CLS_OK, C1, "s1", 8.0),   # Matemática
        g(CLS_OK, C2, "s2", 6.0),   # Matemática (outro course_id, mesmo nome)
        g(CLS_OK, C3, "s1", 9.0),   # História
        g(CLS_EXCL, C1, "s3", 2.0),  # turma EXCLUÍDA → não conta
    ])
    c.close()


async def _cleanup(db=None):
    own = db is None
    if own:
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.classes.delete_many({"id": {"$in": [CLS_OK, CLS_EXCL]}})
    await db.courses.delete_many({"id": {"$in": [C1, C2, C3]}})
    await db.grades.delete_many({"class_id": {"$in": [CLS_OK, CLS_EXCL]}})
    if own:
        db.client.close()


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.get_event_loop().run_until_complete(_seed())
    yield
    asyncio.get_event_loop().run_until_complete(_cleanup())


def _fetch():
    r = requests.get(f"{BASE_URL}/api/analytics/grades/by-subject",
                     params={"academic_year": YEAR, "school_id": SCHOOL},
                     headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_componente_aparece_uma_vez():
    data = _fetch()
    names = [d["course_name"] for d in data]
    assert names.count("Matemática") == 1, names
    assert names.count("História") == 1, names
    assert len(data) == 2, data


def test_media_mesclada_correta_e_exclui_1o_2o_ano():
    data = _fetch()
    mat = next(d for d in data if d["course_name"] == "Matemática")
    # (8.0 + 6.0)/2 = 7.0 — o 2.0 da turma de 1º Ano NÃO entra
    assert mat["avg_grade"] == 7.0, mat
    assert mat["total_students"] == 2, mat


def test_ordem_decrescente_por_media():
    data = _fetch()
    medias = [d["avg_grade"] for d in data]
    assert medias == sorted(medias, reverse=True), medias
    assert data[0]["course_name"] == "História"  # 9.0 no topo
