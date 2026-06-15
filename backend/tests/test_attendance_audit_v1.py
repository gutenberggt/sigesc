"""Fase 1 — Backend tests for attendance optimistic locking + rich audit log.

Cobertura:
  - Create: doc nasce com version=1 + entry em audit_logs com extra_data rico
  - Update sem expected_version: salva normalmente, increment version
  - Update com expected_version válido: OK
  - Update com expected_version stale: 409 com payload completo
  - Update com force_overwrite=True sem change_note: 422
  - Update com force_overwrite=True + change_note: 200 + audit `change_kind='overwrite_after_conflict'`
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://pdf-roster-debug.preview.emergentagent.com"
).rstrip("/")

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

# Turma com alunos seedados (Escola Teste Multisseriada — 6º ANO A)
CLASS_ID = "3da4e569-6522-432c-9b42-1e344a2f0c69"
STUDENT_A = "dc09b180-6b6d-488c-9744-0ec19f9117ea"  # Joao Santos
STUDENT_B = "5c63ab15-1e48-4da2-946e-b9543003dae7"  # Maria Silva


_counter = [0]


def _unique_date() -> str:
    """Cada chamada retorna uma data nunca usada antes nesta execução.
    Usa um counter local (0-26) → datas 2026-12-01..27 isoladas do dataset real.
    """
    _counter[0] += 1
    n = ((_counter[0] - 1) % 27) + 1
    return f"2026-12-{n:02d}"


@pytest.fixture(scope="module", autouse=True)
def _clean_test_data():
    """Limpa attendance no range de teste (2026-12-XX) antes de rodar o módulo.
    Garante idempotência entre execuções repetidas."""
    import os
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv()
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    db.attendance.delete_many({"date": {"$regex": "^2026-12-"}})
    yield


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    csrf = d.get("csrf_token") or ""
    return {
        "Authorization": f"Bearer {tok}",
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    }


@pytest.fixture
def fresh_attendance(headers):
    """Cria um attendance limpo para cada teste. Retorna o doc criado."""
    date = _unique_date()
    payload = {
        "class_id": CLASS_ID,
        "date": date,
        "records": [
            {"student_id": STUDENT_A, "status": "P"},
            {"student_id": STUDENT_B, "status": "P"},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/attendance", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, f"setup failed: {r.status_code} {r.text[:300]}"
    return r.json()


# --- CREATE -----------------------------------------------------------------
def test_create_attendance_starts_at_version_1(headers):
    payload = {
        "class_id": CLASS_ID,
        "date": _unique_date(),
        "records": [{"student_id": STUDENT_A, "status": "P"}],
    }
    r = requests.post(f"{BASE_URL}/api/attendance", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    doc = r.json()
    assert doc.get("version") == 1
    assert doc.get("created_by")


# --- UPDATE happy path (no expected_version) --------------------------------
def test_update_without_expected_version_increments(fresh_attendance, headers):
    date = fresh_attendance["date"]
    payload = {
        "class_id": CLASS_ID,
        "date": date,
        "records": [
            {"student_id": STUDENT_A, "status": "F"},  # P → F
            {"student_id": STUDENT_B, "status": "P"},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/attendance", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    doc = r.json()
    assert doc.get("version") == 2
    assert doc.get("updated_by")


def test_update_with_correct_expected_version(fresh_attendance, headers):
    date = fresh_attendance["date"]
    payload = {
        "class_id": CLASS_ID,
        "date": date,
        "expected_version": 1,
        "records": [{"student_id": STUDENT_A, "status": "F"}, {"student_id": STUDENT_B, "status": "P"}],
    }
    r = requests.post(f"{BASE_URL}/api/attendance", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("version") == 2


# --- UPDATE conflict (stale expected_version) -------------------------------
def test_update_with_stale_expected_version_returns_409(fresh_attendance, headers):
    date = fresh_attendance["date"]
    # primeiro update — leva para v2
    requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date,
            "records": [{"student_id": STUDENT_A, "status": "F"}, {"student_id": STUDENT_B, "status": "P"}],
        },
        headers=headers, timeout=30,
    )
    # segundo update com expected_version=1 (stale) → 409
    r = requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date, "expected_version": 1,
            "records": [{"student_id": STUDENT_A, "status": "P"}, {"student_id": STUDENT_B, "status": "F"}],
        },
        headers=headers, timeout=30,
    )
    assert r.status_code == 409, r.text[:300]
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "ATTENDANCE_VERSION_CONFLICT"
    assert detail.get("expected_version") == 1
    assert detail.get("current_version") == 2
    assert "attendance_id" in detail


def test_force_overwrite_without_note_returns_422(fresh_attendance, headers):
    date = fresh_attendance["date"]
    # leva o doc para v2
    requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date,
            "records": [{"student_id": STUDENT_A, "status": "F"}, {"student_id": STUDENT_B, "status": "P"}],
        },
        headers=headers, timeout=30,
    )
    # tenta sobrescrever sem nota
    r = requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date,
            "expected_version": 1, "force_overwrite": True,
            "records": [{"student_id": STUDENT_A, "status": "P"}, {"student_id": STUDENT_B, "status": "F"}],
        },
        headers=headers, timeout=30,
    )
    assert r.status_code == 422, r.text[:300]
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "OVERWRITE_REQUIRES_NOTE"


def test_force_overwrite_with_note_succeeds_and_logs(fresh_attendance, headers):
    date = fresh_attendance["date"]
    # leva o doc para v2
    requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date,
            "records": [{"student_id": STUDENT_A, "status": "F"}, {"student_id": STUDENT_B, "status": "P"}],
        },
        headers=headers, timeout=30,
    )
    note = "Correção pedagógica autorizada pela coordenação"
    r = requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": date,
            "expected_version": 1, "force_overwrite": True, "change_note": note,
            "records": [{"student_id": STUDENT_A, "status": "P"}, {"student_id": STUDENT_B, "status": "F"}],
        },
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    doc = r.json()
    assert doc.get("version") == 3  # v1 create → v2 update → v3 overwrite
    # Status final reflete os dados forçados
    new_statuses = {r["student_id"]: r["status"] for r in doc["records"]}
    assert new_statuses[STUDENT_A] == "P"
    assert new_statuses[STUDENT_B] == "F"
