"""
May 2026 — Sprint A: testes do módulo de Currículo (BNCC/DCM).

Cobre:
  1. Seed de Computação é idempotente (rodar 2x não duplica).
  2. GET /api/curriculum/stats reflete os totais corretos (3 componentes, 41 skills, 8 métodos).
  3. GET /api/curriculum/skills/{codigo} traz a habilidade + componente aninhado.
  4. Busca por filtro `ano=4` retorna 4 habilidades (1º bimestre x 4 eixos no 4º ano da BNCC Computação).
  5. CRUD completo de Componente (super_admin only).
  6. Busca textual (q=algoritmo) encontra pelo menos 1 resultado.
"""
import os
import pytest
import httpx


BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://history-rebuild-2.preview.emergentagent.com",
).rstrip("/")

SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_stats_after_seed(token):
    r = httpx.get(f"{BACKEND}/api/curriculum/stats", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["components"] >= 3
    assert data["skills"] >= 41
    assert data["methods"] >= 8
    assert data["by_fonte"]["BNCC_COMPUTACAO"] >= 41


def test_get_skill_by_codigo(token):
    r = httpx.get(f"{BACKEND}/api/curriculum/skills/EF03CO01", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["codigo"] == "EF03CO01"
    assert data["ano"] == 3
    assert data["fonte"] == "BNCC_COMPUTACAO"
    assert data["componente"]["codigo"] == "CO"
    assert data["componente"]["etapa"] == "anos_iniciais"


def test_filter_skills_by_ano(token):
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?ano=4",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 4
    assert all(item["ano"] == 4 for item in data["items"])


def test_text_search(token):
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?q=algoritmo",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    assert any("algoritmo" in item["descricao"].lower() for item in data["items"])


def test_get_skill_404_unknown(token):
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills/XX99XX99",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 404


def test_component_crud_super_admin(token):
    """Cria → atualiza → soft-deletes (sem skills, deve hard-delete)."""
    payload = {
        "codigo": "TST",
        "nome": "Componente de Teste",
        "etapa": "anos_iniciais",
        "fonte": "MUNICIPAL",
        "descricao": "Componente criado pelo pytest.",
    }
    r = httpx.post(
        f"{BACKEND}/api/curriculum/components",
        headers=_h(token),
        json=payload,
        timeout=20,
    )
    assert r.status_code == 201, r.text
    comp = r.json()
    cid = comp["id"]

    # Update
    r = httpx.put(
        f"{BACKEND}/api/curriculum/components/{cid}",
        headers=_h(token),
        json={"nome": "Comp Teste Renomeado"},
        timeout=20,
    )
    assert r.status_code == 200, r.text

    # Delete (sem skills → hard delete)
    r = httpx.delete(
        f"{BACKEND}/api/curriculum/components/{cid}",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("deleted") is True


def test_seed_idempotency(token):
    """Roda o seed 2x e verifica que stats não mudam."""
    from seeds.seed_computacao_bncc import seed_computacao
    from motor.motor_asyncio import AsyncIOMotorClient
    import asyncio

    async def run():
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = client[os.environ.get("DB_NAME", "sigesc_db")]
        before = await db.curriculum_skills.count_documents({"fonte": "BNCC_COMPUTACAO"})
        await seed_computacao(db)
        after = await db.curriculum_skills.count_documents({"fonte": "BNCC_COMPUTACAO"})
        return before, after

    before, after = asyncio.run(run())
    assert before == after, f"Seed não é idempotente: {before} → {after}"


def test_skills_pagination(token):
    """Verifica que limit/offset funcionam."""
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?limit=5&offset=0",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) <= 5
    assert data["limit"] == 5
    assert data["offset"] == 0
