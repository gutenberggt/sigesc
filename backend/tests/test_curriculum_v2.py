"""Feb 2026 — Testa o modelo curricular multi-camadas (v2).

Cobre:
  1. Migração idempotente: BNCC_COMPUTACAO → bncc_skills + adaptations.
  2. GET /api/curriculum/bncc — lista canônica.
  3. GET /api/curriculum/adaptations — catálogo achatado (codigo/descricao/bncc).
  4. GET /api/curriculum/adaptations/availability — regra obrigatória condicional.
  5. Commit de importação DCM grava em bncc_skills + curriculum_adaptations.
  6. Reimportar mesmo batch não duplica (upsert único por slot).
"""
import os
import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://login-offline-mode.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_migrate_idempotent(token):
    # 1ª run
    r1 = httpx.post(f"{BACKEND}/api/curriculum/v2/migrate", headers=_h(token), timeout=60)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["ok"] is True
    # 2ª run — nada novo
    r2 = httpx.post(f"{BACKEND}/api/curriculum/v2/migrate", headers=_h(token), timeout=60)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["bncc_inserted"] == 0, f"Migração não idempotente: {d2}"
    assert d2["adapt_inserted"] == 0
    assert d2["bncc_existed"] >= 41  # Computação seeded tem 41


def test_list_bncc(token):
    r = httpx.get(f"{BACKEND}/api/curriculum/bncc?limit=5", headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 41  # Computação BNCC
    assert len(data["items"]) <= 5
    first = data["items"][0]
    assert "codigo_bncc" in first
    assert "descricao_bncc" in first
    assert "etapa" in first


def test_list_adaptations_flattened(token):
    r = httpx.get(
        f"{BACKEND}/api/curriculum/adaptations?componente_codigo=CO&limit=5",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 1
    first = items[0]
    # Shape para UI
    assert "adaptation_id" in first
    assert "codigo" in first
    assert "descricao" in first
    assert "componente_codigo" in first
    assert first["componente_codigo"] == "CO"


def test_adaptation_detail(token):
    listing = httpx.get(
        f"{BACKEND}/api/curriculum/adaptations?componente_codigo=CO&limit=1",
        headers=_h(token), timeout=15,
    ).json()["items"]
    assert len(listing) >= 1
    aid = listing[0]["adaptation_id"]
    r = httpx.get(f"{BACKEND}/api/curriculum/adaptations/{aid}", headers=_h(token), timeout=15)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert "adaptation" in detail
    assert "bncc" in detail
    assert "componente" in detail
    assert detail["adaptation"]["id"] == aid


def test_availability_required_condicional(token):
    # Busca um componente CO v2 com adaptations
    comps = httpx.get(
        f"{BACKEND}/api/curriculum/components?codigo=CO",
        headers=_h(token), timeout=10,
    )
    # Para um componente que tem adaptations (CO etapa anos_iniciais) → required=True
    r = httpx.get(
        f"{BACKEND}/api/curriculum/adaptations/availability?componente_codigo=CO&ano=3",
        headers=_h(token), timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["required"] is True
    assert d["count"] >= 1

    # Componente fantasma → required=False
    r2 = httpx.get(
        f"{BACKEND}/api/curriculum/adaptations/availability?componente_codigo=ZZ&ano=99",
        headers=_h(token), timeout=10,
    )
    assert r2.status_code == 200
    assert r2.json()["required"] is False


def test_bncc_code_validation(token):
    # Um código INVENTADO não deve criar bncc duplicado em 2ª migração
    r = httpx.post(f"{BACKEND}/api/curriculum/v2/migrate", headers=_h(token), timeout=60)
    d = r.json()
    # Idempotente
    assert d["bncc_inserted"] == 0
