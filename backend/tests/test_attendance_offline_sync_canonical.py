"""Fase A (Jun/2026) — Sincronização offline de frequência pelo MOTOR CANÔNICO.

Valida os achados P0 da auditoria offline:
  - A2: `/api/sync/push` de frequência roteia pelo MESMO motor do `POST /api/attendance`
    (não grava documento cru). Resultado canônico: 1 doc por chave natural.
  - A3: idempotência — reenviar a MESMA chamada NÃO duplica; N edições convergem
    para o estado final (Cenário 4 do critério de aceite).
  - Multi-aula (Anos Finais): cada aula é um doc; reenviar a aula 1 não duplica.

Estratégia: super_admin atua sob um tenant de teste via X-Mantenedora-Id. O tenant
é derivado server-side a partir da turma semeada (mantenedora_id da turma).
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

TENANT = "attn-sync-test-tenant"
SCHOOL = "attn-sync-test-school"
CLASS_DAILY = "attn-sync-test-class-daily"
CLASS_FINAIS = "attn-sync-test-class-finais"
COURSE = "attn-sync-test-course"
DATE = "2099-03-10"
S1 = "attn-sync-s1"
S2 = "attn-sync-s2"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["access_token"], d["csrf_token"]


def _headers(token, csrf=None, tenant=TENANT):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    if tenant:
        h["X-Mantenedora-Id"] = tenant
    return h


async def _seed():
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await _cleanup_db(db)
    await db.classes.insert_many([
        {"id": CLASS_DAILY, "mantenedora_id": TENANT, "school_id": SCHOOL,
         "name": "TESTE DIÁRIO", "education_level": "fundamental_anos_iniciais",
         "academic_year": 2099},
        {"id": CLASS_FINAIS, "mantenedora_id": TENANT, "school_id": SCHOOL,
         "name": "TESTE FINAIS", "education_level": "fundamental_anos_finais",
         "academic_year": 2099},
    ])
    await db.students.insert_many([
        {"id": S1, "mantenedora_id": TENANT, "school_id": SCHOOL, "class_id": CLASS_DAILY,
         "full_name": "Aluno Um", "status": "active"},
        {"id": S2, "mantenedora_id": TENANT, "school_id": SCHOOL, "class_id": CLASS_DAILY,
         "full_name": "Aluno Dois", "status": "active"},
    ])
    db.client.close()


async def _cleanup_db(db=None):
    own = db is None
    if own:
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.classes.delete_many({"id": {"$in": [CLASS_DAILY, CLASS_FINAIS]}})
    await db.students.delete_many({"id": {"$in": [S1, S2]}})
    await db.attendance.delete_many({"class_id": {"$in": [CLASS_DAILY, CLASS_FINAIS]}})
    if own:
        db.client.close()


def _count_attendance(query):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    n = asyncio.get_event_loop().run_until_complete(db.attendance.count_documents(query))
    db.client.close()
    return n


def _find_attendance(query):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    doc = asyncio.get_event_loop().run_until_complete(db.attendance.find_one(query, {"_id": 0}))
    db.client.close()
    return doc


def _push(token, csrf, data, operation="update", record_id=None):
    op = {
        "collection": "attendance",
        "operation": operation,
        "recordId": record_id or f"nk:{uuid.uuid4().hex}",
        "timestamp": "2099-03-10T08:00:00Z",
        "data": data,
    }
    r = requests.post(f"{BASE_URL}/api/sync/push",
                      headers=_headers(token, csrf), json={"operations": [op]}, timeout=60)
    return r


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.get_event_loop().run_until_complete(_seed())
    yield
    asyncio.get_event_loop().run_until_complete(_cleanup_db())


def _daily_payload(records):
    return {
        "class_id": CLASS_DAILY, "date": DATE, "academic_year": 2099,
        "attendance_type": "daily", "course_id": None, "period": "regular",
        "number_of_classes": 1, "records": records,
    }


# ---------- A2: roteia pelo motor canônico (doc bem-formado) ----------

def test_push_frequencia_cria_doc_canonico():
    token, csrf = _login()
    data = _daily_payload([{"student_id": S1, "status": "present"},
                           {"student_id": S2, "status": "absent"}])
    r = _push(token, csrf, data, record_id="nk:daily-1")
    assert r.status_code == 200, r.text[:300]
    res = r.json()["results"][0]
    assert res["success"] is True, res
    doc = _find_attendance({"class_id": CLASS_DAILY, "date": DATE})
    assert doc is not None
    # Documento canônico: tem version, attendance_type e mantenedora derivada do servidor
    assert doc.get("version") == 1
    assert doc.get("attendance_type") == "daily"
    assert doc.get("mantenedora_id") == TENANT
    assert {r_["student_id"] for r_ in doc["records"]} == {S1, S2}


# ---------- A3: idempotência (Cenário 4) ----------

def test_push_repetido_nao_duplica():
    token, csrf = _login()
    data = _daily_payload([{"student_id": S1, "status": "present"},
                           {"student_id": S2, "status": "present"}])
    # Reenvia 3x a mesma chave natural (simula 3 edições offline)
    for _ in range(3):
        r = _push(token, csrf, data, record_id="nk:daily-1")
        assert r.status_code == 200, r.text[:300]
        assert r.json()["results"][0]["success"] is True
    # Apenas 1 documento para a chave natural turma+data
    assert _count_attendance({"class_id": CLASS_DAILY, "date": DATE}) == 1
    # Estado final aplicado (ambos present)
    doc = _find_attendance({"class_id": CLASS_DAILY, "date": DATE})
    statuses = {r_["student_id"]: r_["status"] for r_ in doc["records"]}
    assert statuses[S1] == "present" and statuses[S2] == "present"
    # Versão evoluiu (motor canônico aplicou updates)
    assert doc.get("version", 1) >= 2


# ---------- Multi-aula (Anos Finais) ----------

def test_push_multiaula_um_doc_por_aula_idempotente():
    token, csrf = _login()

    def aula_payload(aula, status):
        return {
            "class_id": CLASS_FINAIS, "date": DATE, "academic_year": 2099,
            "attendance_type": "by_component", "course_id": COURSE, "period": "regular",
            "number_of_classes": 1, "aula_numero": aula,
            "records": [{"student_id": S1, "status": status}],
        }

    r1 = _push(token, csrf, aula_payload(1, "present"), record_id="nk:finais-a1")
    r2 = _push(token, csrf, aula_payload(2, "absent"), record_id="nk:finais-a2")
    assert r1.json()["results"][0]["success"] is True, r1.text[:300]
    assert r2.json()["results"][0]["success"] is True, r2.text[:300]
    # 2 documentos (um por aula)
    assert _count_attendance({"class_id": CLASS_FINAIS, "date": DATE}) == 2
    # Reenviar a aula 1 NÃO cria um terceiro doc
    r3 = _push(token, csrf, aula_payload(1, "absent"), record_id="nk:finais-a1")
    assert r3.json()["results"][0]["success"] is True
    assert _count_attendance({"class_id": CLASS_FINAIS, "date": DATE}) == 2
    # Estado final da aula 1 aplicado
    doc = _find_attendance({"class_id": CLASS_FINAIS, "date": DATE, "aula_numero": 1})
    assert doc["records"][0]["status"] == "absent"
