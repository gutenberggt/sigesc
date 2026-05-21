"""Feb 2026 — Testa Fase 2 do Plano de Ação: enriquecimento via IA.

Abordagem: mockamos `LlmChat.send_message` para não gastar EMERGENT_LLM_KEY
na CI. Cobrimos:
  1. Fallback gracioso quando IA retorna None (sem EMERGENT_LLM_KEY)
  2. Enriquecimento OK com JSON válido (análise executiva, insight, extras)
  3. Cache de 24h (segundo call não chama Claude novamente)
  4. force_refresh=true ignora o cache
  5. Validação de schema (strings cortadas, extras limitadas a 2)
  6. Histórico do gestor agregado corretamente
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://class-filter-bf.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

SCHOOL_ID = "school_plan_ai_test"
CLASS_ID = "cls_plan_ai_1"


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def seed_ai():
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.intervention_alerts.delete_many({"school_id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.curriculum_components.delete_many({"fonte": "TEST_AI"})
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_AI"})
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})

        await db.schools.insert_one({"id": SCHOOL_ID, "name": "Escola IA Teste"})
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "Turma IA", "school_id": SCHOOL_ID,
            "academic_year": 9996, "grade_level": "3º ano",
        })
        await db.curriculum_components.insert_one({
            "id": "comp_ai", "codigo": "MA",
            "nome": "Matemática", "etapa": "anos_iniciais",
            "fonte": "TEST_AI", "escopo": "NACIONAL", "ativo": True,
        })
        # Cria cobertura baixa (0/10) para disparar regra determinística
        docs = [{
            "id": f"adp_ai_{i}", "component_id": "comp_ai",
            "bncc_skill_id": None, "codigo_local": f"EF03MA_AI_{i:02d}",
            "descricao_local": f"hab {i}", "ano": 3, "bimestre": 1,
            "fonte": "TEST_AI", "ativo": True, "mantenedora_id": None,
            "ordem_sequencia": i,
        } for i in range(10)]
        await db.curriculum_adaptations.insert_many(docs)

        # 3 alertas resolvidos (histórico do gestor) + 2 ativos
        now = datetime.now(timezone.utc)
        alerts = []
        for i in range(3):
            alerts.append({
                "id": f"alrt_ai_r_{i}", "mantenedora_id": None,
                "school_id": SCHOOL_ID, "class_id": CLASS_ID,
                "class_name": "Turma IA", "component_id": "comp_ai",
                "componente_codigo": "MA", "ano": 3, "bimestre": 1,
                "status": "em_risco", "last_coverage_pct": 80.0,
                "escalation_level": 1,
                "first_detected_at": (now - timedelta(days=20 + i)).isoformat(),
                "resolved_at": (now - timedelta(days=15)).isoformat(),
                "last_notified_at": (now - timedelta(days=20 + i)).isoformat(),
                "updated_at": now.isoformat(),
            })
        for i in range(2):
            alerts.append({
                "id": f"alrt_ai_a_{i}", "mantenedora_id": None,
                "school_id": SCHOOL_ID, "class_id": CLASS_ID,
                "class_name": "Turma IA", "component_id": "comp_ai",
                "componente_codigo": "MA", "ano": 3, "bimestre": 1,
                "status": "nao_cumpre", "last_coverage_pct": 20.0,
                "escalation_level": 2,
                "first_detected_at": (now - timedelta(days=10)).isoformat(),
                "resolved_at": None,
                "last_notified_at": (now - timedelta(days=5)).isoformat(),
                "updated_at": now.isoformat(),
            })
        await db.intervention_alerts.insert_many(alerts)

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.intervention_alerts.delete_many({"school_id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.curriculum_components.delete_many({"fonte": "TEST_AI"})
        await db.curriculum_adaptations.delete_many({"fonte": "TEST_AI"})
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


@pytest.fixture
def clear_cache():
    async def _clear():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
    asyncio.run(_clear())


# ---------- Direct service tests (via Python) ----------

def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


def test_ai_plan_fallback_when_no_key(seed_ai, clear_cache, monkeypatch):
    """Sem EMERGENT_LLM_KEY, enrich deve retornar None (fallback gracioso)."""
    from services.plano_acao_ai import enrich_plan_with_ai

    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    db = _db()

    async def run():
        return await enrich_plan_with_ai(
            db,
            mantenedora_id=None,
            school_id=SCHOOL_ID,
            school_name="Escola IA Teste",
            period="30d",
            contexto={"received": 5, "resolved": 3, "active": 2,
                      "level_3_active": 0, "avg_resolution_days": 4.0,
                      "resolution_rate": 0.6, "coverage_pct": 0.0,
                      "coverage_missing_total": 10, "lancamento_rate": 0.5},
            acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                    "prioridade": 1, "prazo_dias": 7}],
            force=True,
        )
    out = asyncio.run(run())
    assert out is None


_FAKE_AI_JSON = json.dumps({
    "analise_executiva": "Escola com cobertura crítica em Matemática e tempo de resposta aceitável. Necessário foco em regularização do bimestre.",
    "insight_historico": "Gestor apresenta taxa de resolução boa (60%), mas acumula alertas de Matemática — categoria consistentemente deixada por último.",
    "recomendacoes_extra": [
        {"titulo": "Rodada de reuniões por turma",
         "descricao": "Agendar reuniões individuais com os professores de Matemática ainda esta semana para destravar lançamentos pendentes.",
         "prioridade": 2, "impacto": "medio",
         "prazo_dias": 7, "responsavel": "coordenador",
         "metrica_sucesso": "100% dos professores de MA com plano de recuperação em 7 dias."},
    ],
    "acoes_enriquecidas": {
        "1": "Nas últimas semanas, Matemática não avançou. Priorize destravar este bimestre antes do próximo fechamento.",
    },
}, ensure_ascii=False)


def test_ai_plan_enrich_success(seed_ai, clear_cache, monkeypatch):
    """Com Claude mockado, enrich deve persistir e retornar estrutura válida."""
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-test")

    async def run():
        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = AsyncMock(return_value=_FAKE_AI_JSON)

            out = await plano_acao_ai.enrich_plan_with_ai(
                _db(),
                mantenedora_id=None,
                school_id=SCHOOL_ID,
                school_name="Escola IA Teste",
                period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
                force=True,
            )
            return out, inst.send_message.call_count

    out, calls = asyncio.run(run())
    assert out is not None
    assert calls == 1
    ai = out["ai"]
    assert "cobertura crítica" in ai["analise_executiva"]
    assert ai["insight_historico"]
    assert len(ai["recomendacoes_extra"]) == 1
    assert ai["acoes_enriquecidas"].get("1")
    assert out["gestor"]["received_90d"] == 5
    assert out["gestor"]["resolved_90d"] == 3


def test_ai_plan_uses_cache_second_call(seed_ai, clear_cache, monkeypatch):
    """Segunda chamada dentro de 24h NÃO deve chamar Claude novamente."""
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-test")

    async def run():
        calls = {"n": 0}

        async def fake_send(_msg):
            calls["n"] += 1
            return _FAKE_AI_JSON

        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = fake_send

            # 1ª chamada: grava cache
            await plano_acao_ai.enrich_plan_with_ai(
                _db(), mantenedora_id=None, school_id=SCHOOL_ID,
                school_name="Escola IA Teste", period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
                force=True,
            )
            # 2ª chamada: deve vir do cache
            out2 = await plano_acao_ai.enrich_plan_with_ai(
                _db(), mantenedora_id=None, school_id=SCHOOL_ID,
                school_name="Escola IA Teste", period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
                force=False,
            )
            return out2, calls["n"]

    out2, n_calls = asyncio.run(run())
    assert out2 is not None
    assert out2.get("from_cache") is True
    assert out2.get("cache_age_hours") is not None
    assert n_calls == 1  # Claude só foi chamado na primeira


def test_ai_plan_force_refresh_bypasses_cache(seed_ai, clear_cache, monkeypatch):
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-test")

    async def run():
        calls = {"n": 0}

        async def fake_send(_msg):
            calls["n"] += 1
            return _FAKE_AI_JSON

        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = fake_send

            kwargs = dict(
                mantenedora_id=None, school_id=SCHOOL_ID,
                school_name="Escola IA Teste", period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
            )
            await plano_acao_ai.enrich_plan_with_ai(_db(), force=True, **kwargs)
            await plano_acao_ai.enrich_plan_with_ai(_db(), force=True, **kwargs)
            return calls["n"]

    n = asyncio.run(run())
    assert n == 2  # force_refresh sempre chama Claude


def test_ai_plan_validates_and_caps_extras(seed_ai, clear_cache, monkeypatch):
    """IA retornando 5 extras deve ser cortada para 2; strings longas truncadas."""
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-test")

    bad_json = json.dumps({
        "analise_executiva": "A" * 2000,  # deve cortar para 600
        "insight_historico": "B" * 2000,  # deve cortar para 400
        "recomendacoes_extra": [
            {"titulo": f"Extra {i}", "descricao": "x", "prioridade": 1,
             "impacto": "alto", "prazo_dias": 7, "responsavel": "coordenador",
             "metrica_sucesso": "m"}
            for i in range(5)
        ],
        "acoes_enriquecidas": {"1": "ok"},
    }, ensure_ascii=False)

    async def run():
        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = AsyncMock(return_value=bad_json)
            return await plano_acao_ai.enrich_plan_with_ai(
                _db(), mantenedora_id=None, school_id=SCHOOL_ID,
                school_name="Escola IA Teste", period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
                force=True,
            )

    out = asyncio.run(run())
    ai = out["ai"]
    assert len(ai["analise_executiva"]) <= 600
    assert len(ai["insight_historico"]) <= 400
    assert len(ai["recomendacoes_extra"]) == 2


def test_ai_plan_parses_markdown_wrapped_json(seed_ai, clear_cache, monkeypatch):
    """Modelo às vezes embrulha em ```json — deve conseguir parsear."""
    from services import plano_acao_ai

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake-test")
    wrapped = "```json\n" + _FAKE_AI_JSON + "\n```"

    async def run():
        with patch.object(plano_acao_ai, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = AsyncMock(return_value=wrapped)
            return await plano_acao_ai.enrich_plan_with_ai(
                _db(), mantenedora_id=None, school_id=SCHOOL_ID,
                school_name="Escola IA Teste", period="30d",
                contexto={"received": 5, "resolved": 3, "active": 2,
                          "level_3_active": 0, "avg_resolution_days": 4.0,
                          "resolution_rate": 0.6, "coverage_pct": 0.0,
                          "coverage_missing_total": 10, "lancamento_rate": 0.5},
                acoes=[{"ordem": 1, "categoria": "cobertura", "titulo": "X",
                        "prioridade": 1, "prazo_dias": 7}],
                force=True,
            )

    out = asyncio.run(run())
    assert out is not None
    assert "cobertura crítica" in out["ai"]["analise_executiva"]


# ---------- HTTP endpoint tests ----------

def test_endpoint_without_ai_param_keeps_backward_compat(token, seed_ai):
    """`ai=false` (default) mantém estrutura antiga."""
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id={SCHOOL_ID}&period=30d",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ai_enriched"] is False
    assert "ai" not in data
    assert "acoes" in data


def test_endpoint_with_ai_true_but_claude_unreachable_fallback(token, seed_ai, clear_cache):
    """Com EMERGENT_LLM_KEY real mas Claude potencialmente falhando (rede),
    endpoint deve retornar 200 com `ai_enriched` false ou true (gracioso)."""
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/plano-acao?school_id={SCHOOL_ID}&period=30d&ai=true",
        headers=_h(token), timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    # Não deve quebrar seja qual for o resultado da IA
    assert "acoes" in data
    assert "ai_enriched" in data
    # Se enriquecido, estrutura correta
    if data["ai_enriched"]:
        assert "ai" in data
        assert "analise_executiva" in data["ai"]
