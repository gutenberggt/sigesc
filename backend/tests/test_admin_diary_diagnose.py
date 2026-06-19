"""Diagnose admin da grade horária — Fase 9 (Fev/2026).

Cobertura:
  1. Turma inexistente → 404
  2. Turma sem assignments → recommendation=CADASTRAR_GRADE
  3. Turma com assignment cadastrado em maio (valid_from=2026-05-01)
     + attendance em fev/2026 → recommendation=AJUSTAR_VALID_FROM,
     órfão detectado, mês fev com is_suspicious=true
  4. Role não autorizado (professor) → 403
"""
import asyncio
import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://school-reorganize.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
PROFESSOR = {"email": "professor.teste@sigesc.com", "password": "Professor@2026"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    if r.status_code != 200:
        return None
    d = r.json()
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
        "X-CSRF-Token": d.get("csrf_token") or "",
        "Content-Type": "application/json",
    })
    return s


@pytest.fixture(scope="module")
def session():
    s = _login(ADMIN)
    assert s is not None, "Admin login falhou"
    return s


@pytest.fixture(scope="module")
def professor_session():
    s = _login(PROFESSOR)
    if s is None:
        pytest.skip("Professor de teste indisponível")
    return s


@pytest.fixture(scope="module")
def db():
    # Não retorna Motor — apenas a URL/dbname; cada _run cria seu client
    return {
        "url": os.environ['MONGO_URL'],
        "name": os.environ['DB_NAME'],
    }


def _run(coro_factory):
    """coro_factory recebe um db e retorna uma coroutine.

    Cada chamada cria novo Motor client no mesmo loop, evitando
    'future belongs to a different loop'.
    """
    async def _inner():
        client = AsyncIOMotorClient(os.environ['MONGO_URL'])
        try:
            return await coro_factory(client[os.environ['DB_NAME']])
        finally:
            client.close()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


# ===========================================================================
def test_unknown_class_returns_404(session):
    r = session.get(
        f"{BASE_URL}/api/admin/diary/grade-diagnose/{uuid.uuid4()}",
        timeout=15,
    )
    assert r.status_code == 404


# ===========================================================================
def test_class_without_assignments_recommends_cadastrar(session, db):
    class_id = str(uuid.uuid4())
    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "Diagnose Test Class",
        "school_id": "diagnose-school-test",
        "academic_year": 2026, "shift": "morning",
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/admin/diary/grade-diagnose/{class_id}",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["assignments_inventory"]["total"] == 0
        assert payload["diagnosis"]["recommendation"] == "CADASTRAR_GRADE"
        assert payload["class"]["academic_year"] == 2026
    finally:
        _run(lambda d: d.classes.delete_one({"id": class_id}))


# ===========================================================================
def test_class_with_late_valid_from_detects_problem(session, db):
    class_id = str(uuid.uuid4())
    assignment_id = str(uuid.uuid4())
    att_id = str(uuid.uuid4())

    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "Diagnose Late VF",
        "school_id": "diagnose-school-test",
        "academic_year": 2026, "shift": "morning",
    }))
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": assignment_id, "class_id": class_id,
        "component_id": "MAT", "teacher_id": "T1", "teacher_name": "Prof Teste",
        "valid_from": "2026-05-01", "valid_until": None,
        "deleted": False,
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 1,
             "start_time": "07:00", "end_time": "07:45"},
        ],
    }))
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": class_id,
        "date": "2026-02-09", "aula_numero": 1, "records": [],
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/admin/diary/grade-diagnose/{class_id}",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        payload = r.json()
        inv = payload["assignments_inventory"]
        assert inv["active"] == 1
        assert inv["earliest_valid_from"] == "2026-05-01"
        assert payload["diagnosis"]["recommendation"] == "AJUSTAR_VALID_FROM"

        orphans = payload["orphans"]
        assert orphans["attendance_dates_count"] >= 1
        assert "2026-02-09" in orphans["attendance_dates_sample"]

        feb = next(m for m in payload["monthly_coverage"] if m["month"] == "2026-02")
        assert feb["n_assignments_active"] == 0
        assert feb["n_attendance"] == 1
        assert feb["is_suspicious"] is True
    finally:
        _run(lambda d: d.classes.delete_one({"id": class_id}))
        _run(lambda d: d.teacher_class_assignments.delete_one({"id": assignment_id}))
        _run(lambda d: d.attendance.delete_one({"id": att_id}))


# ===========================================================================
def test_forbidden_for_professor(professor_session):
    r = professor_session.get(
        f"{BASE_URL}/api/admin/diary/grade-diagnose/{uuid.uuid4()}",
        timeout=15,
    )
    assert r.status_code == 403
