"""Regressão — Matrícula cancelada não pode aparecer na turma (notas/frequência).

Bug/pedido: aluno com matrícula CANCELADA não deve aparecer em nenhuma lista da
turma onde foi cancelado (nem notas, nem frequência). Antes, os endpoints incluíam
matrículas com status 'cancelled' na fonte "inativos", exibindo o aluno com selo.

Cenário: turma + componente + 2 alunos ativos. Cancela um via
POST /api/enrollments/cancel-enrollment e valida que ele some de
/grades/by-class e /attendance/by-class, restando só o ativo.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not _BACKEND_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BACKEND_URL = line.split("=", 1)[1].strip().strip('"')
                break
BASE_URL = _BACKEND_URL.rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
TENANT_ID = "a991c1ac-56b1-46a8-b122-effedbe19b21"
DB_NAME = "sigesc"
YEAR = datetime.now().year

CLASS_ID = "qa-cancel-" + uuid.uuid4().hex[:8]
COURSE_ID = "qa-cancel-crs-" + uuid.uuid4().hex[:8]


def _mongo_url():
    with open("/app/backend/.env") as fh:
        for line in fh:
            if line.startswith("MONGO_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MONGO_URL not found")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return {
        "Authorization": f"Bearer {d['access_token']}",
        "X-CSRF-Token": d["csrf_token"],
        "X-Mantenedora-Id": TENANT_ID,
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def scenario():
    client = AsyncIOMotorClient(_mongo_url())
    db = client[DB_NAME]
    students = {}

    async def setup():
        sch = await db.schools.find_one({}, {"_id": 0, "id": 1})
        school_id = sch["id"]
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "QA Cancel Turma", "school_id": school_id,
            "mantenedora_id": TENANT_ID, "grade_level": "1º ANO",
            "academic_year": YEAR, "status": "active", "education_level": "FUNDAMENTAL",
        })
        await db.courses.insert_one({
            "id": COURSE_ID, "name": "QA Cancel Comp", "school_id": school_id,
            "mantenedora_id": TENANT_ID, "grade_levels": ["1º ANO"],
        })
        for name in ["QA CANCEL Ativo", "QA CANCEL Cancelado"]:
            sid = str(uuid.uuid4())
            students[name] = sid
            await db.students.insert_one({
                "id": sid, "full_name": name, "school_id": school_id,
                "mantenedora_id": TENANT_ID, "class_id": CLASS_ID, "status": "active",
                "enrollment_number": f"QAC{sid[:4]}",
            })
            await db.enrollments.insert_one({
                "id": str(uuid.uuid4()), "student_id": sid, "school_id": school_id,
                "mantenedora_id": TENANT_ID, "class_id": CLASS_ID, "academic_year": YEAR,
                "status": "active", "enrollment_number": f"QAC{sid[:4]}",
                "enrollment_date": datetime.now(timezone.utc).isoformat(),
            })

    async def teardown():
        ids = list(students.values())
        await db.classes.delete_many({"id": CLASS_ID})
        await db.courses.delete_many({"id": COURSE_ID})
        await db.students.delete_many({"id": {"$in": ids}})
        await db.enrollments.delete_many({"student_id": {"$in": ids}})

    _run(setup())
    yield {"db": db, "students": students}
    _run(teardown())


def test_cancelled_student_hidden_from_grades_and_attendance(scenario, admin_headers):
    cid = scenario["students"]["QA CANCEL Cancelado"]

    # Antes: ambos aparecem em notas
    r = requests.get(f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    names = {x["student"]["full_name"] for x in r.json()}
    assert "QA CANCEL Cancelado" in names and "QA CANCEL Ativo" in names

    # Cancela o vínculo
    c = requests.post(f"{BASE_URL}/api/enrollments/cancel-enrollment", headers=admin_headers,
                      json={"student_id": cid, "class_id": CLASS_ID, "reason": "teste"}, timeout=30)
    assert c.status_code == 200, c.text[:200]

    # Depois: notas só com o ativo
    r2 = requests.get(f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}",
                      headers=admin_headers, timeout=30)
    names2 = {x["student"]["full_name"] for x in r2.json()}
    assert "QA CANCEL Cancelado" not in names2, "cancelado não pode aparecer em notas"
    assert "QA CANCEL Ativo" in names2

    # Depois: frequência só com o ativo
    a = requests.get(f"{BASE_URL}/api/attendance/by-class/{CLASS_ID}/{YEAR}-06-15?academic_year={YEAR}",
                     headers=admin_headers, timeout=30)
    assert a.status_code == 200, a.text[:200]
    payload = a.json()
    studs = payload.get("students") if isinstance(payload, dict) else payload
    att_names = {(s.get("full_name") or (s.get("student") or {}).get("full_name")) for s in (studs or [])}
    assert "QA CANCEL Cancelado" not in att_names, "cancelado não pode aparecer em frequência"
    assert "QA CANCEL Ativo" in att_names
