"""May 2026 — Filtro `bimestre` no GET /api/curriculum/skills.

Garante:
 1. ?bimestre=1 retorna skills do 1º bimestre + skills SEM bimestre (Computação).
 2. Combinação ?q=algoritmo&bimestre=1 retorna apenas itens com algoritmo
    que estejam no 1º bimestre OU sem bimestre.
 3. Filtro estrito: skills do 2º bimestre não aparecem em ?bimestre=1
    se elas TÊM bimestre definido.
"""
import os
import asyncio
import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://legacy-bridge-compat.preview.emergentagent.com",
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
def seed_bimestres():
    """Insere 2 skills sintéticas com bimestre fixo + 1 sem bimestre."""
    from motor.motor_asyncio import AsyncIOMotorClient

    async def setup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        # Limpa antigos
        await db.curriculum_skills.delete_many({"id": {"$regex": "^skill_test_bim"}})
        # Cria componente fictício se não existe
        await db.curriculum_components.update_one(
            {"id": "comp_test_bim"},
            {"$setOnInsert": {
                "id": "comp_test_bim",
                "codigo": "TX",
                "nome": "Teste Bimestres",
                "etapa": "anos_iniciais",
                "fonte": "TEST_BIM",
                "ativo": True,
            }},
            upsert=True,
        )
        await db.curriculum_skills.insert_many([
            {"id": "skill_test_bim_1", "codigo": "EF03TX01",
             "descricao": "habilidade de algoritmo no primeiro bimestre",
             "componente_id": "comp_test_bim", "componente_codigo": "TX",
             "ano": 3, "bimestre": 1, "fonte": "TEST_BIM", "ativo": True},
            {"id": "skill_test_bim_2", "codigo": "EF03TX02",
             "descricao": "habilidade do segundo bimestre",
             "componente_id": "comp_test_bim", "componente_codigo": "TX",
             "ano": 3, "bimestre": 2, "fonte": "TEST_BIM", "ativo": True},
            {"id": "skill_test_bim_3", "codigo": "EF03TX03",
             "descricao": "habilidade transversal sem bimestre",
             "componente_id": "comp_test_bim", "componente_codigo": "TX",
             "ano": 3, "bimestre": None, "fonte": "TEST_BIM", "ativo": True},
        ])
        return c

    client = asyncio.run(setup())
    yield

    async def teardown():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.curriculum_skills.delete_many({"fonte": "TEST_BIM"})
        await db.curriculum_components.delete_many({"fonte": "TEST_BIM"})

    asyncio.run(teardown())


def test_bimestre_inclui_null(token, seed_bimestres):
    """?bimestre=1 deve retornar a skill do bim=1 e a SEM bimestre."""
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?fonte=TEST_BIM&bimestre=1",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    codigos = {item["codigo"] for item in r.json()["items"]}
    assert "EF03TX01" in codigos
    assert "EF03TX03" in codigos  # sem bimestre - transversal
    assert "EF03TX02" not in codigos  # bim=2 deve sumir


def test_bimestre_combinado_com_q(token, seed_bimestres):
    """?q=algoritmo&bimestre=1 retorna só a skill 1 (algoritmo + bim 1)."""
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?fonte=TEST_BIM&bimestre=1&q=algoritmo",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    codigos = {item["codigo"] for item in r.json()["items"]}
    assert codigos == {"EF03TX01"}


def test_bimestre_2_isola(token, seed_bimestres):
    """?bimestre=2 retorna a skill bim=2 e a SEM bimestre, mas não a bim=1."""
    r = httpx.get(
        f"{BACKEND}/api/curriculum/skills?fonte=TEST_BIM&bimestre=2",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    codigos = {item["codigo"] for item in r.json()["items"]}
    assert "EF03TX02" in codigos
    assert "EF03TX03" in codigos
    assert "EF03TX01" not in codigos
