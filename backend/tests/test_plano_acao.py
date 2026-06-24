"""Feb 2026 — Testa Plano de Ação Automático (Sprint E).

Cobre:
  1. Endpoint retorna ações quando escola tem problemas reais.
  2. Regra de cobertura baixa gera ação de prioridade 1 com `link` direto.
  3. Regra de N3 gera ação imediata (prazo 3 dias).
  4. Classificação correta (Crítico/Atenção/Adequado).
  5. Limite de 5 ações respeitado.
  6. Retorno contém contexto (score, coverage, alertas).
"""
import os
import httpx
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://autosave-drafts.preview.emergentagent.com",
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
def seed_plano():
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": "school_plan_test"})
        await db.intervention_alerts.delete_many({"school_id": "school_plan_test"})
        await db.classes.delete_many({"school_id": "school_plan_test"})
        await db.curriculum_components.delete_many({"fonte": "TEST_PLAN"})
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_PLAN"})
        await db.learning_objects.delete_many({"class_id": "cls_plan_1"})

        await db.schools.insert_one({"id": "school_plan_test", "name": "Escola Plano Teste"})
        await db.classes.insert_many([
            {"id": "cls_plan_1", "name": "Turma Plano", "school_id": "school_plan_test",
             "academic_year": 9997, "grade_level": "3º ano"},
        ])
        await db.curriculum_components.insert_one({
            "id": "comp_plan", "codigo": "LP",
            "nome": "Língua Portuguesa", "etapa": "anos_iniciais",
            "fonte": "TEST_PLAN", "escopo": "NACIONAL", "ativo": True,
        })
        # 10 adaptations b1, 0 cobertas → cobertura 0% (<70%)
        docs = [{
            "id": f"adp_plan_{i}", "component_id": "comp_plan",
            "bncc_skill_id": None, "codigo_local": f"EF03LP_PLAN_{i:02d}",
            "descricao_local": f"hab {i}", "ano": 3, "bimestre": 1,
            "fonte": "TEST_PLAN", "ativo": True, "mantenedora_id": None,
            "ordem_sequencia": i,
        } for i in range(10)]
        await db.curriculum_adaptations.insert_many(docs)

        # 4 alertas N3 ativos
        now = datetime.now(timezone.utc)
        alerts = []
        for i in range(4):
            alerts.append({
                "id": f"alrt_plan_{i}", "mantenedora_id": None,
                "school_id": "school_plan_test", "class_id": "cls_plan_1",
                "class_name": f"Turma {i}", "component_id": "comp_plan",
                "componente_codigo": "LP", "ano": 3, "bimestre": 1,
                "status": "nao_cumpre", "last_coverage_pct": 10.0,
                "escalation_level": 3,
                "first_detected_at": (now - timedelta(days=40)).isoformat(),
                "resolved_at": None, "last_notified_at": (now - timedelta(days=10)).isoformat(),
                "updated_at": now.isoformat(),
            })
        # 1 resolvido com tempo alto (10 dias)
        alerts.append({
            "id": "alrt_plan_res", "mantenedora_id": None,
            "school_id": "school_plan_test", "class_id": "cls_plan_1",
            "class_name": "Turma R", "component_id": "comp_plan",
            "componente_codigo": "LP", "ano": 3, "bimestre": 1,
            "status": "em_risco", "last_coverage_pct": 90.0, "escalation_level": 1,
            "first_detected_at": (now - timedelta(days=15)).isoformat(),
            "resolved_at": (now - timedelta(days=5)).isoformat(),
            "last_notified_at": (now - timedelta(days=15)).isoformat(),
            "updated_at": now.isoformat(),
        })
        await db.intervention_alerts.insert_many(alerts)

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": "school_plan_test"})
        await db.intervention_alerts.delete_many({"school_id": "school_plan_test"})
        await db.classes.delete_many({"school_id": "school_plan_test"})
        await db.curriculum_components.delete_many({"fonte": "TEST_PLAN"})
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_PLAN"})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


def test_plan_generates_actions(token, seed_plano):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id=school_plan_test&period=90d",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["school_id"] == "school_plan_test"
    assert plan["classificacao"] in ("Crítico", "Atenção")
    # Deve ter pelo menos: cobertura baixa + N3 + lançamentos baixos
    cats = [a["categoria"] for a in plan["acoes"]]
    assert "cobertura" in cats
    assert "nivel_3" in cats
    assert len(plan["acoes"]) <= 5


def test_plan_coverage_action_has_link_and_metric(token, seed_plano):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id=school_plan_test&period=90d",
        headers=_h(token), timeout=15,
    )
    cov_action = next(
        (a for a in r.json()["acoes"] if a["categoria"] == "cobertura"),
        None,
    )
    assert cov_action is not None
    assert cov_action["prioridade"] == 1
    assert cov_action["link"].startswith("/admin/curriculo/cobertura")
    assert cov_action["prazo_dias"] > 0
    assert cov_action["metrica_sucesso"]
    # Título deve conter algum código de componente
    assert any(c in cov_action["titulo"] for c in ("LP", "MA", "CO", "CI", "GE", "HI", "EF"))


def test_plan_n3_action_urgent(token, seed_plano):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id=school_plan_test&period=90d",
        headers=_h(token), timeout=15,
    )
    n3 = next((a for a in r.json()["acoes"] if a["categoria"] == "nivel_3"), None)
    assert n3 is not None
    assert n3["prazo_dias"] <= 3
    assert n3["impacto"] == "alto"
    assert n3["responsavel"] == "diretor"


def test_plan_context_populated(token, seed_plano):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id=school_plan_test&period=90d",
        headers=_h(token), timeout=15,
    )
    plan = r.json()
    ctx = plan["contexto"]
    assert ctx["level_3_active"] == 4
    assert ctx["received"] == 5
    assert ctx["resolved"] == 1
    assert ctx["coverage_pct"] == 0.0
    assert plan["score"] < 60
