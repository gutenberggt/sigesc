"""P1.0-D — Motor canônico de Conteúdo (`save_content_canonical`).

Valida o motor ÚNICO de escrita de conteúdo pedagógico antes da migração LO→CE:
  - conteúdo válido (create draft, version 1, mantenedora derivada)
  - bimestre encerrado → 403 (lock de calendário portado)
  - ano letivo fechado → 403 (lock portado)
  - optimistic locking (upsert por chave natural: 409 sem force, sobrescreve com force+nota)
  - multi-tenant: mantenedora_id derivada da TURMA (server-authoritative), não do header

Usa a conta de professor (role 'professor' aciona ambos os locks). Anos de teste
isolados (2091/2020/2090) para não colidir com dados reais de 2026.
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

PROF_EMAIL = "professor.teste@sigesc.com"
PROF_PASSWORD = "Professor@2026"
SEMED = "a991c1ac-56b1-46a8-b122-effedbe19b21"  # tenant do professor

SCHOOL = "p10-content-school"
CLASS_OK = "p10-class-open-2091"
CLASS_YEAR_CLOSED = "p10-class-closed-2090"
CLASS_BIM_CLOSED = "p10-class-bim-2020"
COMPONENT = "p10-component-x"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PROF_EMAIL, "password": PROF_PASSWORD}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["access_token"], d.get("csrf_token")


def _headers(token, csrf=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    h["X-Mantenedora-Id"] = SEMED
    return h


async def _seed():
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await _cleanup_db(db)
    await db.schools.insert_one({
        "id": SCHOOL, "mantenedora_id": SEMED, "name": "ESCOLA TESTE P1.0 CONTENT",
        "anos_letivos": {
            "2091": {"status": "aberto"},
            "2090": {"status": "fechado"},
        },
    })
    await db.classes.insert_many([
        {"id": CLASS_OK, "mantenedora_id": SEMED, "school_id": SCHOOL,
         "name": "TURMA OK 2091", "education_level": "fundamental_anos_iniciais", "academic_year": 2091},
        {"id": CLASS_YEAR_CLOSED, "mantenedora_id": SEMED, "school_id": SCHOOL,
         "name": "TURMA ANO FECHADO 2090", "education_level": "fundamental_anos_iniciais", "academic_year": 2090},
        {"id": CLASS_BIM_CLOSED, "mantenedora_id": SEMED, "school_id": SCHOOL,
         "name": "TURMA BIM FECHADO 2020", "education_level": "fundamental_anos_iniciais", "academic_year": 2020},
    ])
    # Calendário 2020 com bimestre 1 cuja data-limite já passou (encerrado)
    await db.calendario_letivo.insert_one({
        "ano_letivo": 2020,
        "bimestre_1_inicio": "2020-02-01",
        "bimestre_1_fim": "2020-04-30",
        "bimestre_1_data_limite": "2020-05-01",
    })
    db.client.close()


async def _cleanup_db(db=None):
    own = db is None
    if own:
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.schools.delete_many({"id": SCHOOL})
    await db.classes.delete_many({"id": {"$in": [CLASS_OK, CLASS_YEAR_CLOSED, CLASS_BIM_CLOSED]}})
    await db.calendario_letivo.delete_many({"ano_letivo": 2020})
    await db.content_entries.delete_many({"class_id": {"$in": [CLASS_OK, CLASS_YEAR_CLOSED, CLASS_BIM_CLOSED]}})
    if own:
        db.client.close()


def _find_ce(query):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    doc = asyncio.get_event_loop().run_until_complete(db.content_entries.find_one(query, {"_id": 0}))
    db.client.close()
    return doc


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.get_event_loop().run_until_complete(_seed())
    yield
    asyncio.get_event_loop().run_until_complete(_cleanup_db())


def _create(token, csrf, class_id, date, content="Aula sobre frações", extra=None):
    payload = {"class_id": class_id, "date": date, "component_id": COMPONENT, "content": content}
    if extra:
        payload.update(extra)
    return requests.post(f"{BASE_URL}/api/content-entries",
                         headers=_headers(token, csrf), json=payload, timeout=30)


# ---------- conteúdo válido ----------

def test_conteudo_valido_cria_draft():
    token, csrf = _login()
    r = _create(token, csrf, CLASS_OK, "2091-03-10")
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d["status"] == "draft"
    assert d["version"] == 1
    assert d["content"] == "Aula sobre frações"
    # mantenedora derivada da turma (server-authoritative)
    doc = _find_ce({"id": d["id"]})
    assert doc["mantenedora_id"] == SEMED
    assert doc["academic_year"] == 2091


# ---------- ano letivo fechado ----------

def test_ano_letivo_fechado_bloqueia():
    token, csrf = _login()
    r = _create(token, csrf, CLASS_YEAR_CLOSED, "2090-03-10")
    assert r.status_code == 403, r.text[:400]
    assert "fechado" in r.text.lower()


# ---------- bimestre encerrado ----------

def test_bimestre_encerrado_bloqueia():
    token, csrf = _login()
    r = _create(token, csrf, CLASS_BIM_CLOSED, "2020-03-10")
    assert r.status_code == 403, r.text[:400]
    assert "prazo" in r.text.lower() or "bimestre" in r.text.lower()


# ---------- optimistic locking + idempotência por chave natural ----------

def test_optimistic_locking_e_upsert_idempotente():
    token, csrf = _login()
    # cria v1
    r1 = _create(token, csrf, CLASS_OK, "2091-04-15", content="versão 1")
    assert r1.status_code == 200, r1.text[:400]
    assert r1.json()["version"] == 1

    # mesma chave natural com expected_version errado e SEM force → 409
    r2 = _create(token, csrf, CLASS_OK, "2091-04-15",
                 content="versão conflitante", extra={"expected_version": 99})
    assert r2.status_code == 409, r2.text[:400]
    assert "CONTENT_VERSION_CONFLICT" in r2.text

    # com force_overwrite + change_note → sobrescreve, version 2, SEM duplicar
    r3 = _create(token, csrf, CLASS_OK, "2091-04-15",
                 content="versão final",
                 extra={"expected_version": 99, "force_overwrite": True, "change_note": "correção QA"})
    assert r3.status_code == 200, r3.text[:400]
    assert r3.json()["version"] == 2
    assert r3.json()["content"] == "versão final"

    # idempotência: apenas 1 doc para a chave natural (turma+data)
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    n = asyncio.get_event_loop().run_until_complete(
        db.content_entries.count_documents({"class_id": CLASS_OK, "date": "2091-04-15", "deleted": False})
    )
    db.client.close()
    assert n == 1


# ---------- multi-tenant: header não sobrepõe a turma ----------

def test_multitenant_mantenedora_derivada_da_turma():
    token, csrf = _login()
    # envia header de OUTRO tenant — o motor deve ignorar e usar a mantenedora da TURMA
    h = _headers(token, csrf)
    h["X-Mantenedora-Id"] = "tenant-falso-xyz"
    payload = {"class_id": CLASS_OK, "date": "2091-05-20", "component_id": COMPONENT, "content": "isolamento"}
    r = requests.post(f"{BASE_URL}/api/content-entries", headers=h, json=payload, timeout=30)
    # Ou cria com mantenedora correta, OU bloqueia por tenant — nunca grava com tenant falso.
    if r.status_code == 200:
        doc = _find_ce({"id": r.json()["id"]})
        assert doc["mantenedora_id"] == SEMED, "mantenedora deve vir da turma, não do header"
    else:
        assert r.status_code in (403, 404), r.text[:300]
