"""Testes do sync offline (Jun/2026): CSRF + isolamento multi-tenant.

Cobre os achados corrigidos:
  - P0-a (CSRF): POST /api/sync/push exige X-CSRF-Token (o que o Service Worker
    passou a enviar). Sem ele → 403; com ele → 200.
  - P0-b (multi-tenant): push create carimba mantenedora_id do servidor;
    update/delete NÃO tocam registro de outro tenant; pull não vaza outro tenant;
    status conta apenas o tenant ativo.

Estratégia: super_admin atua sob um tenant específico via header X-Mantenedora-Id.
Semeia 2 grades em 2 mantenedoras isoladas (IDs de teste) e valida o isolamento.
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

TENANT_A = "sync-test-tenant-A"
TENANT_B = "sync-test-tenant-B"
GRADE_A = "sync-test-grade-A"
GRADE_B = "sync-test-grade-B"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["access_token"], d["csrf_token"]


def _headers(token, csrf=None, tenant=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    if tenant:
        h["X-Mantenedora-Id"] = tenant
    return h


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await _cleanup(db)
    await db.grades.insert_many([
        {"id": GRADE_A, "mantenedora_id": TENANT_A, "class_id": "c-A",
         "student_id": "s-A", "academic_year": 2099, "final_average": 5.0},
        {"id": GRADE_B, "mantenedora_id": TENANT_B, "class_id": "c-B",
         "student_id": "s-B", "academic_year": 2099, "final_average": 9.0},
    ])
    c.close()


async def _cleanup(db=None):
    own = db is None
    if own:
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.grades.delete_many({"mantenedora_id": {"$in": [TENANT_A, TENANT_B]}})
    await db.grades.delete_many({"id": {"$regex": "^sync-test-"}})
    if own:
        db.client.close()


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.get_event_loop().run_until_complete(_seed())
    yield
    asyncio.get_event_loop().run_until_complete(_cleanup())


# ---------- P0-a: CSRF ----------

def test_push_sem_csrf_retorna_403():
    token, _ = _login()
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token),  # SEM csrf
                      json={"operations": []}, timeout=30)
    assert r.status_code == 403, r.text[:200]


def test_push_com_csrf_passa():
    token, csrf = _login()
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token, csrf, TENANT_A),
                      json={"operations": []}, timeout=30)
    assert r.status_code == 200, r.text[:200]


# ---------- P0-b: multi-tenant ----------

def test_create_carimba_mantenedora_do_servidor():
    token, csrf = _login()
    rid = f"sync-test-grade-{uuid.uuid4().hex[:8]}"
    op = {"collection": "grades", "operation": "create", "recordId": rid,
          "timestamp": "2099-01-01T00:00:00Z",
          # cliente tenta forçar tenant B — servidor deve IGNORAR
          "data": {"id": rid, "mantenedora_id": TENANT_B, "class_id": "c-A",
                   "student_id": "s-A", "academic_year": 2099, "final_average": 7.0}}
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token, csrf, TENANT_A),
                      json={"operations": [op]}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    # Verifica no banco que ficou em TENANT_A (não B)
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    doc = asyncio.get_event_loop().run_until_complete(db.grades.find_one({"id": rid}))
    db.client.close()
    assert doc is not None
    assert doc["mantenedora_id"] == TENANT_A, doc.get("mantenedora_id")


def test_update_nao_toca_registro_de_outro_tenant():
    token, csrf = _login()
    # Atuando como TENANT_A, tenta atualizar a grade do TENANT_B
    op = {"collection": "grades", "operation": "update", "recordId": GRADE_B,
          "timestamp": "2099-01-01T00:00:00Z",
          "data": {"final_average": 0.0}}
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token, csrf, TENANT_A),
                      json={"operations": [op]}, timeout=30)
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["success"] is False  # não encontrado no escopo do tenant A
    # E a nota do tenant B continua intacta (9.0)
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    doc = asyncio.get_event_loop().run_until_complete(db.grades.find_one({"id": GRADE_B}))
    db.client.close()
    assert doc["final_average"] == 9.0


def test_delete_nao_remove_registro_de_outro_tenant():
    token, csrf = _login()
    op = {"collection": "grades", "operation": "delete", "recordId": GRADE_B,
          "timestamp": "2099-01-01T00:00:00Z"}
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token, csrf, TENANT_A),
                      json={"operations": [op]}, timeout=30)
    assert r.status_code == 200
    assert r.json()["results"][0]["success"] is False
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    doc = asyncio.get_event_loop().run_until_complete(db.grades.find_one({"id": GRADE_B}))
    db.client.close()
    assert doc is not None  # ainda existe


def test_pull_nao_vaza_outro_tenant():
    token, csrf = _login()
    r = requests.post(f"{BASE_URL}/api/sync/pull",
                      headers=_headers(token, csrf, TENANT_A),
                      json={"collections": ["grades"], "academicYear": "2099", "pageSize": 500},
                      timeout=60)
    assert r.status_code == 200, r.text[:200]
    grades = r.json()["data"].get("grades", [])
    ids = {g.get("id") for g in grades}
    mids = {g.get("mantenedora_id") for g in grades}
    assert GRADE_B not in ids, "Vazou registro do tenant B no pull do tenant A!"
    assert TENANT_B not in mids
