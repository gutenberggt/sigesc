"""
Teste de ACEITAÇÃO (Fase 1.5) — critério do usuário:

  Turma na Escola A → transferida para Escola B (jul/2026).
  - Relatório de período ANTERIOR à transferência → permanece em A.
  - Relatório de período POSTERIOR → aparece em B.

Cobre Frequência (record-level por data) e Rendimento (ano-base, início do ano)
via analytics, consumindo o serviço central de escopo temporal.
"""
from __future__ import annotations

import os
import uuid
import requests
import pytest
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://autosave-drafts.preview.emergentagent.com").rstrip("/")
EMAIL, PASSWORD = "gutenberg@sigesc.com", "@Celta2007"
MANT = "a991c1ac-56b1-46a8-b122-effedbe19b21"
TRANSFER_DATE = "2026-07-01T00:00:00+00:00"

_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    s.headers.update({"Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
                      "X-CSRF-Token": d.get("csrf_token") or "", "Content-Type": "application/json"})
    return s


@pytest.fixture
def world():
    sfx = uuid.uuid4().hex[:8]
    A, B = f"A-{sfx}", f"B-{sfx}"
    cid, stu, course = f"cls-{sfx}", f"stu-{sfx}", f"crs-{sfx}"
    _db.schools.insert_many([
        {"id": A, "name": f"Escola A {sfx}", "status": "active", "mantenedora_id": MANT},
        {"id": B, "name": f"Escola B {sfx}", "status": "active", "mantenedora_id": MANT},
    ])
    # turma transferida A→B em jul/2026 (class_id estável, school_id atual = B)
    _db.classes.insert_one({
        "id": cid, "school_id": B, "academic_year": 2026, "mantenedora_id": MANT,
        "grade_level": "5º ano", "education_level": "fundamental_anos_iniciais",
        "course_ids": [course],
        "school_history": [
            {"school_id": A, "start_date": "2026-02-05T00:00:00+00:00", "end_date": TRANSFER_DATE},
            {"school_id": B, "start_date": TRANSFER_DATE, "end_date": None},
        ],
    })
    _db.courses.insert_one({"id": course, "name": f"Matemática {sfx}"})
    # frequência: 1 aula em MAIO (pré) e 1 em SETEMBRO (pós)
    _db.attendance.insert_many([
        {"id": f"att-mai-{sfx}", "class_id": cid, "academic_year": 2026, "date": "2026-05-15",
         "dependency_id": None, "records": [{"student_id": stu, "status": "P", "dependency_id": None}]},
        {"id": f"att-set-{sfx}", "class_id": cid, "academic_year": 2026, "date": "2026-09-15",
         "dependency_id": None, "records": [{"student_id": stu, "status": "P", "dependency_id": None}]},
    ])
    # nota do ano 2026 (ano-base)
    _db.grades.insert_one({
        "id": f"grd-{sfx}", "class_id": cid, "student_id": stu, "academic_year": 2026,
        "course_id": course, "final_average": 7.0, "b1": 7, "b2": 7, "b3": 7, "b4": 7,
        "dependency_id": None,
    })
    ctx = {"A": A, "B": B, "cid": cid, "course": course}
    yield ctx
    _db.schools.delete_many({"id": {"$in": [A, B]}})
    _db.classes.delete_one({"id": cid})
    _db.courses.delete_one({"id": course})
    _db.attendance.delete_many({"class_id": cid})
    _db.grades.delete_many({"class_id": cid})


def _months(auth, school_id):
    r = auth.get(f"{BASE_URL}/api/analytics/attendance/monthly",
                 params={"academic_year": 2026, "school_id": school_id}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return {row["month_num"]: row for row in r.json()}


# ---------------------------------------------------------------- FREQUÊNCIA (record-level)
def test_frequencia_anterior_fica_na_origem(auth, world):
    a = _months(auth, world["A"])
    # Maio (05) pertence à origem A; Setembro (09) NÃO deve aparecer em A
    assert "05" in a, f"Maio deveria contar para A: {a}"
    assert "09" not in a, f"Setembro NÃO deveria contar para A: {a}"


def test_frequencia_posterior_aparece_no_destino(auth, world):
    b = _months(auth, world["B"])
    assert "09" in b, f"Setembro deveria contar para B: {b}"
    assert "05" not in b, f"Maio NÃO deveria contar para B: {b}"


# ---------------------------------------------------------------- RENDIMENTO (ano-base → origem)
def test_rendimento_ano_atribuido_a_origem(auth, world):
    ra = auth.get(f"{BASE_URL}/api/analytics/grades/by-subject",
                  params={"academic_year": 2026, "school_id": world["A"]}, timeout=30)
    rb = auth.get(f"{BASE_URL}/api/analytics/grades/by-subject",
                  params={"academic_year": 2026, "school_id": world["B"]}, timeout=30)
    assert ra.status_code == 200 and rb.status_code == 200
    names_a = {row.get("course_name") or row.get("subject") or row.get("name") for row in ra.json()}
    # A nota do ano 2026 é atribuída à ORIGEM (escola onde o ano foi conduzido)
    assert any("Matemática" in (n or "") for n in names_a), f"Rendimento 2026 deveria estar em A: {ra.json()}"
    assert rb.json() == [], f"Destino B não deveria ter rendimento 2026 desta turma: {rb.json()}"
