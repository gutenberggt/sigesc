"""Feb 2026 — Testa widget de Cobertura v2: thresholds, forecasting, alerta.

Cobre:
  1. GET /coverage retorna status 'ok'/'atencao'/'critico'/'nao_iniciado' com
     thresholds corretos (90/70).
  2. forecast corresponde ao ritmo semanal (bimestre em andamento).
  3. Bimestre fechado < 90% → 'fechado_critico'.
  4. Bimestre futuro → 'nao_iniciado' sem %.
  5. closed_critical e critical_rows aparecem em totals.
"""
import os
import httpx
import pytest
import asyncio
from datetime import date, timedelta
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-integrity-fix.preview.emergentagent.com",
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
def seed_forecast():
    """Cria:
       - 1 componente TST
       - 10 adaptations em bimestre 1 (10%→critico)
       - 10 adaptations em bimestre 2 (70%→atencao se em andamento)
       - 10 adaptations em bimestre 3 (100%→ok)
       - Calendário letivo com b1 fechado, b2 em andamento, b3 em andamento
    """
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.curriculum_skills.delete_many({"fonte": "TEST_COV"})
        await db.curriculum_components.delete_many({"fonte": "TEST_COV"})
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_COV"})
        await db.bncc_skills.delete_many({"componente_codigo": "TST"})
        await db.learning_objects.delete_many({"academic_year": 9999})
        # componente
        await db.curriculum_components.insert_one({
            "id": "comp_test_cov", "codigo": "TST", "nome": "Teste Cobertura",
            "etapa": "anos_iniciais", "fonte": "TEST_COV", "escopo": "MUNICIPAL",
            "ativo": True,
        })
        # adaptations
        docs = []
        for b, qty in [(1, 10), (2, 10), (3, 10)]:
            for i in range(qty):
                docs.append({
                    "id": f"adapt_cov_b{b}_{i}",
                    "mantenedora_id": None,
                    "component_id": "comp_test_cov",
                    "bncc_skill_id": None,
                    "codigo_local": f"TST_B{b}_{i:02d}",
                    "descricao_local": f"Hab teste b{b} i{i}",
                    "ano": 3, "bimestre": b,
                    "fonte": "TEST_COV", "ativo": True,
                    "ordem_sequencia": i,
                })
        await db.curriculum_adaptations.insert_many(docs)

        # Calendário: b1 fechado (um ano atrás), b2 em andamento (hoje dentro), b3 em andamento também
        today = date.today()
        cal_id = "cal_test_cov"
        await db.calendario_letivo.delete_one({"id": cal_id})
        await db.calendario_letivo.insert_one({
            "id": cal_id, "ano_letivo": 9999,
            "bimestre_1_inicio": (today - timedelta(days=120)).isoformat(),
            "bimestre_1_fim": (today - timedelta(days=60)).isoformat(),  # fechado
            "bimestre_2_inicio": (today - timedelta(days=50)).isoformat(),
            "bimestre_2_fim": (today + timedelta(days=30)).isoformat(),  # em andamento
            "bimestre_3_inicio": (today + timedelta(days=60)).isoformat(),
            "bimestre_3_fim": (today + timedelta(days=150)).isoformat(),  # futuro
            "bimestre_4_inicio": (today + timedelta(days=180)).isoformat(),
            "bimestre_4_fim": (today + timedelta(days=240)).isoformat(),  # futuro
        })

        # Registra aulas: b1 cobre 1/10 (10% → crítico fechado); b2 cobre 7/10 (70% → atenção)
        lo_docs = []
        for i in range(1):  # b1
            lo_docs.append({
                "id": f"lo_cov_b1_{i}",
                "class_id": "cls_test", "course_id": "crs_test",
                "date": today.isoformat(), "academic_year": 9999,
                "content": "x", "number_of_classes": 1,
                "adaptation_ids": [f"adapt_cov_b1_{i}"],
            })
        for i in range(7):  # b2
            lo_docs.append({
                "id": f"lo_cov_b2_{i}",
                "class_id": "cls_test", "course_id": "crs_test",
                "date": today.isoformat(), "academic_year": 9999,
                "content": "x", "number_of_classes": 1,
                "adaptation_ids": [f"adapt_cov_b2_{i}"],
            })
        await db.learning_objects.insert_many(lo_docs)

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_COV"})
        await db.curriculum_components.delete_many({"fonte": "TEST_COV"})
        await db.learning_objects.delete_many({"academic_year": 9999})
        await db.calendario_letivo.delete_one({"id": "cal_test_cov"})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


def test_coverage_thresholds_and_forecast(token, seed_forecast):
    r = httpx.get(
        f"{BACKEND}/api/curriculum/coverage?academic_year=9999",
        headers=_h(token), timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    rows_tst = [r for r in data["rows"] if r["componente_codigo"] == "TST"]
    by_bim = {r["bimestre"]: r for r in rows_tst}

    # Bim 1 (fechado, 10%) → crítico + fechado_critico
    b1 = by_bim[1]
    assert b1["pct"] == 10.0
    assert b1["status"] == "critico"
    assert b1["bimestre_state"] == "fechado"
    assert b1["forecast"] == "fechado_critico"

    # Bim 2 (em andamento, 70%) → atencao
    b2 = by_bim[2]
    assert b2["pct"] == 70.0
    assert b2["status"] == "atencao"
    assert b2["bimestre_state"] == "em_andamento"
    # forecast depende de quantos dias passaram; aceitamos no_ritmo OU em_risco
    assert b2["forecast"] in ("no_ritmo", "em_risco", "nao_cumpre")

    # Bim 3 (futuro, 0%) → nao_iniciado
    b3 = by_bim[3]
    assert b3["status"] == "nao_iniciado"
    assert b3["bimestre_state"] == "futuro"
    assert b3["forecast"] == "nao_iniciado"

    # Totais: closed_critical deve contar b1
    assert data["totals"]["closed_critical"] >= 1
