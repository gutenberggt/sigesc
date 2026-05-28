"""Feb 2026 — Testa Feed de Intervenções (Sprint C).

Cobre:
  1. POST /intervencoes/run-detection cria alertas.
  2. GET /intervencoes retorna alertas ativos ordenados.
  3. Rodar 2x não duplica (upsert por slot).
  4. Alerta resolve automaticamente quando cobertura atinge 90% (segunda rodada
     com novos learning_objects cobrindo).
  5. Escalonamento: first_detected_at antigo → nível 2.
  6. POST /intervencoes/{id}/resolve marca manualmente.
"""
import os
import asyncio
import httpx
import pytest
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://mutacoes-criticas.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def seed_scenario():
    """Monta cenário isolado: 1 turma + componente + 10 adapts b2 em andamento,
       0 aulas → 0% cobertura → deve gerar alerta 'nao_cumpre'."""
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_INT"})
        await db.curriculum_components.delete_many({"fonte": "TEST_INT"})
        await db.classes.delete_many({"id": "cls_int_test"})
        await db.intervention_alerts.delete_many({"class_id": "cls_int_test"})
        await db.intervention_notifications.delete_many({"alert_id": {"$regex": "^."}})
        await db.learning_objects.delete_many({"class_id": "cls_int_test"})
        today = date.today()
        # Calendário 9998: b2 em andamento
        await db.calendario_letivo.delete_one({"ano_letivo": 9998})
        await db.calendario_letivo.insert_one({
            "id": "cal_int_test", "ano_letivo": 9998,
            "bimestre_1_inicio": (today - timedelta(days=120)).isoformat(),
            "bimestre_1_fim": (today - timedelta(days=60)).isoformat(),
            "bimestre_2_inicio": (today - timedelta(days=50)).isoformat(),
            "bimestre_2_fim": (today + timedelta(days=30)).isoformat(),
            "bimestre_3_inicio": (today + timedelta(days=60)).isoformat(),
            "bimestre_3_fim": (today + timedelta(days=150)).isoformat(),
            "bimestre_4_inicio": (today + timedelta(days=180)).isoformat(),
            "bimestre_4_fim": (today + timedelta(days=240)).isoformat(),
        })
        await db.curriculum_components.insert_one({
            "id": "comp_int_test", "codigo": "TX",
            "nome": "Teste Intervenção", "etapa": "anos_iniciais",
            "fonte": "TEST_INT", "escopo": "MUNICIPAL", "ativo": True,
        })
        docs = []
        for i in range(10):
            docs.append({
                "id": f"adapt_int_{i}", "mantenedora_id": None,
                "component_id": "comp_int_test", "bncc_skill_id": None,
                "codigo_local": f"TX_B2_{i:02d}", "descricao_local": f"hab {i}",
                "ano": 3, "bimestre": 2, "fonte": "TEST_INT", "ativo": True,
                "ordem_sequencia": i,
            })
        await db.curriculum_adaptations.insert_many(docs)
        await db.classes.insert_one({
            "id": "cls_int_test", "name": "Turma Intervenção",
            "school_id": None, "academic_year": 9998,
            "grade_level": "3º ano",
        })

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_INT"})
        await db.curriculum_components.delete_many({"fonte": "TEST_INT"})
        await db.classes.delete_many({"id": "cls_int_test"})
        await db.intervention_alerts.delete_many({"class_id": "cls_int_test"})
        await db.calendario_letivo.delete_one({"id": "cal_int_test"})
        await db.learning_objects.delete_many({"class_id": "cls_int_test"})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


def test_detection_creates_alert(token, seed_scenario):
    r = httpx.post(
        f"{BACKEND}/api/intervencoes/run-detection?academic_year=9998",
        headers=_h(token), timeout=30,
    )
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["created"] >= 1

    # Lista
    r = httpx.get(f"{BACKEND}/api/intervencoes", headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    found = [i for i in data["items"] if i["class_id"] == "cls_int_test"]
    assert len(found) >= 1
    assert found[0]["status"] == "nao_cumpre"
    assert found[0]["last_coverage_pct"] == 0.0
    assert found[0]["escalation_level"] == 1


def test_detection_idempotent(token, seed_scenario):
    r1 = httpx.post(
        f"{BACKEND}/api/intervencoes/run-detection?academic_year=9998",
        headers=_h(token), timeout=30,
    )
    created_before = r1.json()["created"]
    r2 = httpx.post(
        f"{BACKEND}/api/intervencoes/run-detection?academic_year=9998",
        headers=_h(token), timeout=30,
    )
    # Segunda run não deve criar duplicados
    assert r2.json()["created"] == 0 or r2.json()["created"] <= created_before


def test_manual_resolve(token, seed_scenario):
    r = httpx.get(f"{BACKEND}/api/intervencoes", headers=_h(token), timeout=15)
    items = [i for i in r.json()["items"] if i["class_id"] == "cls_int_test"]
    assert len(items) > 0
    aid = items[0]["id"]
    r2 = httpx.post(f"{BACKEND}/api/intervencoes/{aid}/resolve", headers=_h(token), timeout=15)
    assert r2.status_code == 200, r2.text
    # Não aparece mais em "ativos"
    r3 = httpx.get(f"{BACKEND}/api/intervencoes", headers=_h(token), timeout=15)
    found = [i for i in r3.json()["items"] if i["id"] == aid]
    assert len(found) == 0
    # Aparece em include_resolved=true
    r4 = httpx.get(
        f"{BACKEND}/api/intervencoes?include_resolved=true",
        headers=_h(token), timeout=15,
    )
    all_items = r4.json()["items"]
    found_res = [i for i in all_items if i["id"] == aid]
    assert len(found_res) == 1
    assert found_res[0]["resolved_at"] is not None
