"""Regressão da coluna "Diários (60%)" em /analytics/teachers/performance.

A coluna deixou de ser apenas a cobertura de objetos de conhecimento e passou
a ser a MÉDIA PONDERADA de 3 SLAs (normalizada 0–100%):

    SLA Frequência (peso 4) = lançamentos de frequência em até 3 dias / total
    SLA Conteúdo   (peso 3) = objetos de conhecimento registrados / previstos
    SLA Notas      (peso 3) = placeholder 100%

    Diários = (SLA_Freq×4 + SLA_Conteúdo×3 + SLA_Notas×3) / 10

IMPORTANTE: essa regra vale SOMENTE para o desempenho do professor; o
"Ranking de Escolas – Score V2.1" NÃO muda.

Estratégia: semeia dados isolados no ano 2099 (sem calendário real → dias
letivos = fallback 200) e valida o cálculo ponta-a-ponta via HTTP, limpando
tudo ao final.
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

YEAR = 2099  # ano isolado: sem calendário → total_dias_letivos = 200 (fallback)
SCHOOL_ID = "sla-test-school-2099"
CLASS_ID = "sla-test-class-2099"
COURSE_ID = "sla-test-course-2099"
TEACHER_ID = "sla-test-teacher-2099"

# 20 objetos de conhecimento / (1 turma × 200 dias) = 10.0%
N_LEARNING_OBJECTS = 20
EXPECTED_SLA_CONTEUDO = 10.0
# 2 de 3 frequências no prazo → 66.7%
EXPECTED_SLA_FREQ = round(2 / 3 * 100, 1)
EXPECTED_SLA_NOTAS = 100.0
EXPECTED_DIARIOS = round(
    (EXPECTED_SLA_FREQ * 4 + EXPECTED_SLA_CONTEUDO * 3 + EXPECTED_SLA_NOTAS * 3) / 10, 1
)


def _token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await _cleanup(db)
    await db.staff.insert_one({"id": TEACHER_ID, "nome": "Prof Teste SLA"})
    await db.teacher_assignments.insert_one({
        "id": str(uuid.uuid4()),
        "staff_id": TEACHER_ID,
        "staff_name": "Prof Teste SLA",
        "class_id": CLASS_ID,
        "course_id": COURSE_ID,
        "school_id": SCHOOL_ID,
        "academic_year": YEAR,
    })
    # 20 objetos de conhecimento
    await db.learning_objects.insert_many([
        {"id": str(uuid.uuid4()), "class_id": CLASS_ID, "academic_year": YEAR,
         "number_of_classes": 1}
        for _ in range(N_LEARNING_OBJECTS)
    ])
    # 3 frequências: 2 no prazo (<=3 dias), 1 atrasada (10 dias)
    await db.attendance.insert_many([
        {"id": str(uuid.uuid4()), "class_id": CLASS_ID, "course_id": COURSE_ID,
         "academic_year": YEAR, "date": "2099-03-01",
         "created_at": "2099-03-02T10:00:00+00:00", "records": []},
        {"id": str(uuid.uuid4()), "class_id": CLASS_ID, "course_id": COURSE_ID,
         "academic_year": YEAR, "date": "2099-03-05",
         "created_at": "2099-03-06T10:00:00+00:00", "records": []},
        {"id": str(uuid.uuid4()), "class_id": CLASS_ID, "course_id": COURSE_ID,
         "academic_year": YEAR, "date": "2099-03-10",
         "created_at": "2099-03-20T10:00:00+00:00", "records": []},
    ])
    c.close()


async def _cleanup(db=None):
    own = db is None
    if own:
        c = AsyncIOMotorClient(MONGO_URL)
        db = c[DB_NAME]
    await db.staff.delete_many({"id": TEACHER_ID})
    await db.teacher_assignments.delete_many({"school_id": SCHOOL_ID})
    await db.learning_objects.delete_many({"class_id": CLASS_ID})
    await db.attendance.delete_many({"class_id": CLASS_ID})
    if own:
        db.client.close()


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.get_event_loop().run_until_complete(_seed())
    yield
    asyncio.get_event_loop().run_until_complete(_cleanup())


def _fetch_teacher():
    r = requests.get(
        f"{BASE_URL}/api/analytics/teachers/performance",
        params={"academic_year": YEAR, "school_id": SCHOOL_ID},
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json().get("data", [])
    rows = [t for t in data if t["teacher_id"] == TEACHER_ID]
    assert rows, f"Professor de teste não encontrado: {data}"
    return rows[0]


def test_sla_freq_pontualidade():
    t = _fetch_teacher()
    assert t["sla_freq"] == EXPECTED_SLA_FREQ, t


def test_sla_notas_placeholder_100():
    t = _fetch_teacher()
    assert t["sla_notas"] == EXPECTED_SLA_NOTAS, t


def test_sla_conteudo_cobertura():
    t = _fetch_teacher()
    assert t["sla_conteudo"] == EXPECTED_SLA_CONTEUDO, t


def test_diarios_media_ponderada():
    t = _fetch_teacher()
    # Composição correta da média ponderada dos 3 SLAs
    recomputed = round(
        (t["sla_freq"] * 4 + t["sla_conteudo"] * 3 + t["sla_notas"] * 3) / 10, 1
    )
    assert t["diario_pct"] == recomputed, t
    assert t["diario_pct"] == EXPECTED_DIARIOS, t
