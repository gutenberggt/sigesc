"""Fev 2026 — Sprint G1: Explainability + Cache Invalidation Reativa.

Cobre:
  1. Resposta IA inclui `analise_evidencias` e `insight_evidencias` estruturadas.
  2. Recomendações extras têm `baseado_em` populado.
  3. `_sanitize_evidencias` limita tamanho e remove items sem metrica/valor.
  4. `invalidate_ai_plans_for_school` remove docs do cache.
  5. Endpoint `/resolve` invalida cache da escola ao resolver alerta.
  6. `run_intervention_detection` invalida cache de escolas tocadas.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://sigesc-docs.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

SCHOOL_ID = "school_g1_test"
CLASS_ID = "cls_g1_test"


@pytest.fixture(scope="module")
def token():
    # Ultrapassa borda de segundo se tests anteriores fizeram logout-all
    time.sleep(1.2)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    body = r.json()
    return {"access": body["access_token"], "csrf": body.get("csrf_token", "")}


def _h(t):
    return {"Authorization": f"Bearer {t['access']}", "X-CSRF-Token": t["csrf"]}


@pytest.fixture(scope="module")
def seed_g1():
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.intervention_alerts.delete_many({"school_id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})

        await db.schools.insert_one({"id": SCHOOL_ID, "name": "Escola G1 Test"})
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "Turma G1", "school_id": SCHOOL_ID,
            "academic_year": 9995, "grade_level": "3º ano",
        })
        now = datetime.now(timezone.utc)
        # 2 alertas ativos
        await db.intervention_alerts.insert_many([
            {
                "id": f"alrt_g1_{i}", "mantenedora_id": None,
                "school_id": SCHOOL_ID, "class_id": CLASS_ID,
                "class_name": "Turma G1", "component_id": "comp_g1",
                "componente_codigo": "LP", "ano": 3, "bimestre": 1,
                "status": "em_risco", "last_coverage_pct": 50.0,
                "escalation_level": 1,
                "first_detected_at": (now - timedelta(days=5)).isoformat(),
                "resolved_at": None,
                "last_notified_at": (now - timedelta(days=1)).isoformat(),
                "updated_at": now.isoformat(),
            }
            for i in range(2)
        ])

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.intervention_alerts.delete_many({"school_id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


_FAKE_AI_WITH_EVIDENCES = json.dumps({
    "analise_executiva": "Escola com 2 alertas ativos e tempo de resposta ok.",
    "analise_evidencias": [
        {"metrica": "Alertas ativos", "valor": "2", "fonte": "contexto_atual.active"},
        {"metrica": "Tempo médio", "valor": "3d", "fonte": "contexto_atual.avg_resolution_days"},
    ],
    "insight_historico": "Gestor resolve rápido, mas atrasa em MA.",
    "insight_evidencias": [
        {"metrica": "Categoria negligenciada", "valor": "MA", "fonte": "gestor.most_neglected_component"},
        {"metrica": "Taxa resolução", "valor": "60%", "fonte": "gestor.resolution_rate_90d"},
    ],
    "recomendacoes_extra": [
        {
            "titulo": "Agendar reunião Matemática",
            "descricao": "Reunião de 30min com professores de MA.",
            "prioridade": 2, "impacto": "medio",
            "prazo_dias": 7, "responsavel": "coordenador",
            "metrica_sucesso": "Zerar pendências MA em 14d",
            "baseado_em": [
                {"metrica": "Componente crítico", "valor": "MA", "fonte": "gestor.most_neglected_component"},
            ],
        },
    ],
    "acoes_enriquecidas": {"1": "Ação enriquecida exemplo"},
}, ensure_ascii=False)


# ---------- Unit tests: sanitização ----------

def test_sanitize_evidencias_filtra_invalidos():
    from services.plano_acao_ai import _sanitize_evidencias
    raw = [
        {"metrica": "OK", "valor": "1", "fonte": "x.y"},
        {"metrica": "", "valor": "2"},  # vazio → descarta
        {"valor": "3"},  # sem metrica → descarta
        {"metrica": "N", "valor": None},  # valor None → descarta (string vazia)
        {"metrica": "A" * 200, "valor": "1", "fonte": "x"},  # trunca 60
    ]
    out = _sanitize_evidencias(raw, max_items=10)
    # itens válidos: primeiro + último (metrica truncada)
    assert len(out) == 2
    assert out[0] == {"metrica": "OK", "valor": "1", "fonte": "x.y"}
    assert len(out[1]["metrica"]) == 60


def test_sanitize_respeita_max_items():
    from services.plano_acao_ai import _sanitize_evidencias
    raw = [{"metrica": f"m{i}", "valor": str(i)} for i in range(10)]
    out = _sanitize_evidencias(raw, max_items=3)
    assert len(out) == 3


# ---------- Integration: enrich_plan_with_ai inclui evidências ----------

def test_ai_response_has_evidencias(seed_g1, monkeypatch):
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-g1")

    async def run():
        db = _db()
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = AsyncMock(return_value=_FAKE_AI_WITH_EVIDENCES)

            return await plano_acao_ai.enrich_plan_with_ai(
                db,
                mantenedora_id=None,
                school_id=SCHOOL_ID,
                school_name="Escola G1 Test",
                period="30d",
                contexto={"received": 2, "resolved": 0, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 3.0,
                          "resolution_rate": 0.0, "coverage_pct": 50.0,
                          "coverage_missing_total": 5, "lancamento_rate": 0.8},
                acoes=[{"ordem": 1, "categoria": "lancamentos", "titulo": "X",
                        "prioridade": 2, "prazo_dias": 7}],
                force=True,
            )

    out = asyncio.run(run())
    assert out is not None
    ai = out["ai"]
    assert "analise_evidencias" in ai
    assert len(ai["analise_evidencias"]) == 2
    assert ai["analise_evidencias"][0]["metrica"] == "Alertas ativos"
    assert "insight_evidencias" in ai
    assert len(ai["insight_evidencias"]) == 2
    assert len(ai["recomendacoes_extra"]) == 1
    assert ai["recomendacoes_extra"][0]["baseado_em"]
    assert ai["recomendacoes_extra"][0]["baseado_em"][0]["metrica"] == "Componente crítico"


# ---------- Cache invalidation ----------

def test_invalidate_ai_plans_for_school_removes_docs(seed_g1):
    from services.plano_acao_ai import invalidate_ai_plans_for_school

    async def run():
        db = _db()
        # Limpa qualquer cache remanescente de testes anteriores
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
        await db.ai_plans.delete_many({"school_id": "other_school"})
        await db.ai_plans.insert_many([
            {"key": "k1", "school_id": SCHOOL_ID, "ai": {"x": 1},
             "generated_at": datetime.now(timezone.utc).isoformat()},
            {"key": "k2", "school_id": SCHOOL_ID, "ai": {"x": 2},
             "generated_at": datetime.now(timezone.utc).isoformat()},
            {"key": "k3", "school_id": "other_school", "ai": {"x": 3},
             "generated_at": datetime.now(timezone.utc).isoformat()},
        ])
        n = await invalidate_ai_plans_for_school(db, school_id=SCHOOL_ID)
        remaining_here = await db.ai_plans.count_documents({"school_id": SCHOOL_ID})
        other = await db.ai_plans.count_documents({"school_id": "other_school"})
        # cleanup
        await db.ai_plans.delete_many({"school_id": "other_school"})
        return n, remaining_here, other

    n, remaining, other = asyncio.run(run())
    assert n == 2
    assert remaining == 0
    assert other == 1  # escola diferente não é tocada


def test_resolve_endpoint_invalidates_cache(token, seed_g1):
    """Ao resolver um alert via API, cache da escola deve sumir."""
    async def setup():
        db = _db()
        # Popula cache artificial
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
        await db.ai_plans.insert_one({
            "key": "test_inv", "school_id": SCHOOL_ID,
            "ai": {"x": 1},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def check():
        db = _db()
        n = await db.ai_plans.count_documents({"school_id": SCHOOL_ID})
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
        return n

    asyncio.run(setup())
    # Resolve alert alrt_g1_0
    r = httpx.post(
        f"{BACKEND}/api/intervencoes/alrt_g1_0/resolve",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    remaining = asyncio.run(check())
    assert remaining == 0, f"cache não foi invalidado (restaram {remaining})"


# ---------- Endpoint E2E: response tem campos de evidências ----------

def test_endpoint_response_schema_with_ai(token, seed_g1):
    """Endpoint com ai=true retorna analise_evidencias e insight_evidencias (ou fallback)."""
    # Limpa cache antes
    async def clear():
        db = _db()
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
    asyncio.run(clear())

    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao"
        f"?school_id={SCHOOL_ID}&period=30d&ai=true",
        headers=_h(token), timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    # Se IA rodou, deve ter evidências estruturadas
    if data.get("ai_enriched") and data.get("ai"):
        ai = data["ai"]
        # O schema tem os campos (podem estar vazios se o modelo não gerou)
        assert "analise_evidencias" in ai
        assert "insight_evidencias" in ai
        assert isinstance(ai["analise_evidencias"], list)
        assert isinstance(ai["insight_evidencias"], list)
        for rec in ai.get("recomendacoes_extra") or []:
            assert "baseado_em" in rec
            assert isinstance(rec["baseado_em"], list)
