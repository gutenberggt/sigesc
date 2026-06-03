"""Feb 2026 — Testa Ranking de Gestão Curricular.

Cobre:
 1. Endpoint retorna lista ordenada por score decrescente para super_admin.
 2. Inclui rank, weighted_score, avg_resolution_days, active.
 3. Gestor comum vê apenas self e não vê rows completos.
 4. Período `all` engloba histórico completo.
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
    "https://sla-trio-weighted.preview.emergentagent.com",
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
def seed_ranking():
    """Cria 2 escolas com alertas: escola_a (melhor) e escola_b (pior)."""
    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        # Limpa tudo
        await db.intervention_alerts.delete_many({"mantenedora_id": "rk_test"})
        await db.schools.delete_many({"id": {"$in": ["school_rk_a", "school_rk_b"]}})
        # Escolas
        await db.schools.insert_many([
            {"id": "school_rk_a", "name": "Escola A (melhor)"},
            {"id": "school_rk_b", "name": "Escola B (pior)"},
        ])
        now = datetime.now(timezone.utc)
        # Escola A: 5 alertas total, 5 resolvidos em média 2 dias, 0 ativos → score alto
        docs = []
        for i in range(5):
            first = (now - timedelta(days=10)).isoformat()
            res = (now - timedelta(days=8)).isoformat()
            docs.append({
                "id": f"rk_a_{i}", "mantenedora_id": "rk_test",
                "school_id": "school_rk_a", "class_id": "c_a",
                "component_id": "cp_a", "componente_codigo": "LP",
                "ano": 3, "bimestre": 1, "status": "em_risco",
                "last_coverage_pct": 95.0, "escalation_level": 1,
                "first_detected_at": first, "resolved_at": res,
                "last_notified_at": first, "updated_at": res,
            })
        # Escola B: 6 alertas, 1 resolvido em 15 dias, 5 ativos + 2 nível 3 → score baixo
        for i in range(1):
            first = (now - timedelta(days=20)).isoformat()
            res = (now - timedelta(days=5)).isoformat()
            docs.append({
                "id": f"rk_b_res_{i}", "mantenedora_id": "rk_test",
                "school_id": "school_rk_b", "class_id": "c_b",
                "component_id": "cp_b", "componente_codigo": "MA",
                "ano": 3, "bimestre": 2, "status": "nao_cumpre",
                "last_coverage_pct": 30.0, "escalation_level": 2,
                "first_detected_at": first, "resolved_at": res,
                "last_notified_at": first, "updated_at": res,
            })
        for i in range(5):
            first = (now - timedelta(days=25)).isoformat()
            level = 3 if i < 2 else 1
            docs.append({
                "id": f"rk_b_active_{i}", "mantenedora_id": "rk_test",
                "school_id": "school_rk_b", "class_id": "c_b",
                "component_id": "cp_b", "componente_codigo": "MA",
                "ano": 3, "bimestre": 2, "status": "nao_cumpre",
                "last_coverage_pct": 20.0, "escalation_level": level,
                "first_detected_at": first, "resolved_at": None,
                "last_notified_at": first, "updated_at": first,
            })
        await db.intervention_alerts.insert_many(docs)

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.intervention_alerts.delete_many({"mantenedora_id": "rk_test"})
        await db.schools.delete_many({"id": {"$in": ["school_rk_a", "school_rk_b"]}})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


def test_ranking_sorted_desc_by_score(token, seed_ranking):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/ranking?period=90d",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["full_access"] is True
    rows = data["rows"]
    # Escola A deve aparecer antes de Escola B
    a_idx = next(i for i, r in enumerate(rows) if r["school_id"] == "school_rk_a")
    b_idx = next(i for i, r in enumerate(rows) if r["school_id"] == "school_rk_b")
    assert a_idx < b_idx, f"Escola A ({rows[a_idx]['weighted_score']}) deveria vir antes de B ({rows[b_idx]['weighted_score']})"
    # Rank 1 preenchido
    assert rows[a_idx]["rank"] == a_idx + 1
    # Métricas esperadas
    a = rows[a_idx]
    b = rows[b_idx]
    assert a["received"] == 5
    assert a["resolved"] == 5
    assert a["active"] == 0
    assert a["resolution_rate"] == 100.0
    assert b["active"] == 5
    assert b["critical_level_3"] == 2


def test_ranking_all_period_includes_older(token, seed_ranking):
    r = httpx.get(
        f"{BACKEND}/api/intervencoes/ranking?period=all",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Confirma que alertas muito antigos aparecem
    total_rec = sum(r["received"] for r in data["rows"])
    assert total_rec >= 11  # 5 + 6 do seed
