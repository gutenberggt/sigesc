"""Regressão — Turmas multisseriadas: nenhum aluno some dos PDFs/telas de notas.

Bug original: em turma multisseriada (ex.: "Maternal I e II", 14 alunos), os PDFs
por etapa listavam só 7 alunos. Causa: o endpoint de PDF filtrava por igualdade
EXATA de `enrollments.student_series`, descartando alunos com série vazia ou com
divergência de case/espaços. Além disso, a propagação de série em "Editar Aluno"
era travada por `academic_year == ano_atual`, então a matrícula não refletia.

Este teste cria um cenário determinístico via Mongo (setup/teardown próprios),
exercita os endpoints reais e valida:
  1. /grades/by-class retorna TODOS os matriculados (sem filtro de série).
  2. PUT /students/{id} com student_series propaga para a matrícula ativa.
  3. /grades/pdf?student_series=... passa a incluir o aluno recém-classificado.
  4. Fallback: aluno com série só no cadastro (matrícula vazia) e com case
     divergente ainda aparece no PDF da etapa correta.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

try:
    import pdfplumber  # noqa
    _HAS_PDFPLUMBER = True
except Exception:
    _HAS_PDFPLUMBER = False

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not _BACKEND_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BACKEND_URL = line.split("=", 1)[1].strip().strip('"')
                break
assert _BACKEND_URL, "REACT_APP_BACKEND_URL not set"
BASE_URL = _BACKEND_URL.rstrip("/")

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
TENANT_ID = "a991c1ac-56b1-46a8-b122-effedbe19b21"
DB_NAME = "sigesc"
YEAR = datetime.now().year

CLASS_ID = "qa-multi-" + uuid.uuid4().hex[:8]
COURSE_ID = "qa-course-" + uuid.uuid4().hex[:8]


def _mongo_url():
    with open("/app/backend/.env") as fh:
        for line in fh:
            if line.startswith("MONGO_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MONGO_URL not found")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def scenario():
    """Cria turma multisseriada + 6 alunos (2 Etapa I, 2 Etapa II, 2 sem série)."""
    client = AsyncIOMotorClient(_mongo_url())
    db = client[DB_NAME]
    school_id = None
    students = []

    async def setup():
        nonlocal school_id
        sch = await db.schools.find_one({}, {"_id": 0, "id": 1})
        school_id = sch["id"]
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "QA Multi Etapas", "school_id": school_id,
            "mantenedora_id": TENANT_ID, "is_multi_grade": True,
            "series": ["Etapa I", "Etapa II"], "grade_level": "Etapa I",
            "academic_year": YEAR, "education_level": "INFANTIL",
            "nivel_ensino": "INFANTIL", "status": "active",
        })
        await db.courses.insert_one({
            "id": COURSE_ID, "name": "QA Componente", "school_id": school_id,
            "mantenedora_id": TENANT_ID, "grade_levels": ["Etapa I", "Etapa II"],
            "nivel_ensino": "INFANTIL",
        })
        specs = [("QA SER A", "Etapa I"), ("QA SER B", "Etapa I"),
                 ("QA SER C", "Etapa II"), ("QA SER D", "Etapa II"),
                 ("QA SER E", None), ("QA SER F", None)]
        for i, (name, serie) in enumerate(specs):
            sid = str(uuid.uuid4())
            students.append({"id": sid, "name": name, "series": serie})
            await db.students.insert_one({
                "id": sid, "full_name": name, "school_id": school_id,
                "mantenedora_id": TENANT_ID, "class_id": CLASS_ID,
                "status": "active", "student_series": serie,
                "enrollment_number": f"QASER{2000 + i}",
            })
            await db.enrollments.insert_one({
                "id": str(uuid.uuid4()), "student_id": sid, "school_id": school_id,
                "mantenedora_id": TENANT_ID, "class_id": CLASS_ID,
                "academic_year": YEAR, "status": "active",
                "student_series": serie, "enrollment_number": f"QASER{2000 + i}",
                "enrollment_date": datetime.now(timezone.utc).isoformat(),
            })

    async def teardown():
        await db.classes.delete_many({"id": CLASS_ID})
        await db.courses.delete_many({"id": COURSE_ID})
        ids = [s["id"] for s in students]
        await db.students.delete_many({"id": {"$in": ids}})
        await db.enrollments.delete_many({"student_id": {"$in": ids}})

    _run(setup())
    yield {"db": db, "students": students}
    _run(teardown())


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


def _pdf_names(content: bytes, names):
    import io
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return {n: (n in txt) for n in names}


def test_grades_by_class_returns_all_enrolled(scenario, admin_headers):
    r = requests.get(f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    names = {row["student"]["full_name"] for row in r.json()}
    for n in ["QA SER A", "QA SER B", "QA SER C", "QA SER D", "QA SER E", "QA SER F"]:
        assert n in names, f"{n} ausente em by-class ({names})"


@pytest.mark.skipif(not _HAS_PDFPLUMBER, reason="pdfplumber não instalado")
def test_pdf_excludes_unclassified_then_includes_after_edit(scenario, admin_headers):
    all_names = ["QA SER A", "QA SER B", "QA SER C", "QA SER D", "QA SER E", "QA SER F"]
    # Antes: Etapa I = A,B (E/F sem série não aparecem)
    r = requests.get(f"{BASE_URL}/api/grades/pdf/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}&student_series=Etapa%20I",
                     headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text[:200]
    present = _pdf_names(r.content, all_names)
    assert present["QA SER A"] and present["QA SER B"]
    assert not present["QA SER E"], "E (sem série) não deveria aparecer antes da edição"

    # Edita o aluno E -> Etapa I (deve propagar para a matrícula)
    e = next(s for s in scenario["students"] if s["name"] == "QA SER E")
    pr = requests.put(f"{BASE_URL}/api/students/{e['id']}", headers=admin_headers,
                      json={"student_series": "Etapa I"}, timeout=30)
    assert pr.status_code == 200, pr.text
    enr = _run(scenario["db"].enrollments.find_one({"student_id": e["id"], "status": "active"}))
    assert enr["student_series"] == "Etapa I", "propagação para matrícula falhou"

    # Depois: Etapa I = A,B,E
    r2 = requests.get(f"{BASE_URL}/api/grades/pdf/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}&student_series=Etapa%20I",
                      headers=admin_headers, timeout=60)
    present2 = _pdf_names(r2.content, all_names)
    assert present2["QA SER E"], "E deveria aparecer no PDF após edição em Editar Aluno"


@pytest.mark.skipif(not _HAS_PDFPLUMBER, reason="pdfplumber não instalado")
def test_pdf_fallback_to_student_record_and_normalized_case(scenario, admin_headers):
    """Aluno com série só no cadastro (matrícula vazia) e case divergente aparece."""
    all_names = ["QA SER A", "QA SER B", "QA SER C", "QA SER D", "QA SER F"]
    f = next(s for s in scenario["students"] if s["name"] == "QA SER F")
    _run(scenario["db"].students.update_one({"id": f["id"]}, {"$set": {"student_series": "ETAPA II"}}))
    _run(scenario["db"].enrollments.update_one({"student_id": f["id"], "status": "active"},
                                               {"$set": {"student_series": None}}))
    r = requests.get(f"{BASE_URL}/api/grades/pdf/{CLASS_ID}/{COURSE_ID}?academic_year={YEAR}&student_series=Etapa%20II",
                     headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text[:200]
    present = _pdf_names(r.content, all_names)
    assert present["QA SER C"] and present["QA SER D"]
    assert present["QA SER F"], "F deveria aparecer via fallback (cadastro) + normalização de case"


def test_students_list_ano_column_fallback_to_record(scenario, admin_headers):
    """Coluna "ANO" da listagem deve usar a série do CADASTRO quando a matrícula
    estiver sem série (bug: list_students sobrescrevia com o valor vazio da matrícula).
    """
    a = next(s for s in scenario["students"] if s["name"] == "QA SER A")  # série "Etapa I"
    # Zera a série da matrícula ativa (mantém a do cadastro)
    _run(scenario["db"].enrollments.update_one(
        {"student_id": a["id"], "status": "active"}, {"$set": {"student_series": None}}))
    r = requests.get(f"{BASE_URL}/api/students?search=QA%20SER%20A&page=1&page_size=10",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    items = r.json().get("items") or r.json().get("students") or []
    target = next((it for it in items if it["full_name"] == "QA SER A"), None)
    assert target is not None, f"QA SER A não retornado ({[i['full_name'] for i in items]})"
    assert target.get("student_series") == "Etapa I", (
        f"coluna ANO deveria cair no cadastro: {target.get('student_series')!r}")
