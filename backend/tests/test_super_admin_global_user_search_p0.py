"""P0 Auth — busca global de usuários para o Modo de Teste."""

import importlib.util
from pathlib import Path
import re
import sys

import pytest
from fastapi import HTTPException


BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
MODULE_PATH = BACKEND / "routers" / "auth_impersonation_search.py"
SPEC = importlib.util.spec_from_file_location("auth_impersonation_search_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
search_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = search_mod
SPEC.loader.exec_module(search_mod)

CONTROL_UI = (REPO / "frontend" / "src" / "components" / "ImpersonationControl.jsx").read_text(encoding="utf-8")
SESSION_UI = (REPO / "frontend" / "src" / "services" / "impersonationSession.js").read_text(encoding="utf-8")


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.sort_spec = None
        self.limit_value = None
        self.to_list_length = None

    def sort(self, spec):
        self.sort_spec = spec
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length=None):
        self.to_list_length = length
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs
        self.last_query = None
        self.last_projection = None
        self.last_cursor = None

    def find(self, query, projection):
        self.last_query = query
        self.last_projection = projection
        self.last_cursor = FakeCursor(self.docs)
        return self.last_cursor


class FakeDb:
    def __init__(self, docs):
        self.users = FakeCollection(docs)


def current_super_admin(**overrides):
    user = {"id": "super-1", "role": "super_admin", "email": "super@example.org"}
    user.update(overrides)
    return user


def candidate(user_id, name, role, roles=None):
    return {
        "id": user_id,
        "full_name": name,
        "email": f"{user_id}@example.org",
        "role": role,
        "roles": roles or [role],
        "status": "active",
        "mantenedora_id": f"tenant-{user_id}",
    }


def test_query_global_nao_usa_tenant_e_escapa_regex_do_cliente():
    query = search_mod._build_global_user_query("super-1", "Ari.*(x)")
    assert "mantenedora_id" not in repr(query)
    assert query["status"] == "active"
    assert query["id"] == {"$ne": "super-1"}
    assert query["role"] == {"$ne": "super_admin"}
    assert query["roles"] == {"$ne": "super_admin"}

    patterns = [item[next(iter(item))] for item in query["$or"]]
    assert all(isinstance(pattern, re.Pattern) for pattern in patterns)
    assert all(pattern.pattern == re.escape("Ari.*(x)") for pattern in patterns)


def test_candidato_publico_aceita_qualquer_perfil_e_bloqueia_super_admin():
    for role in ("professor", "secretario", "diretor", "responsavel", "admin"):
        item = search_mod._public_candidate(candidate(f"u-{role}", f"Usuário {role}", role))
        assert item is not None
        assert role in item["roles"]

    assert search_mod._public_candidate(
        candidate("super-2", "Outro Super", "admin", roles=["admin", "super_admin"])
    ) is None


def test_busca_exige_super_admin_e_nao_permite_pesquisa_durante_teste():
    with pytest.raises(HTTPException) as exc:
        search_mod._assert_search_access({"id": "u-1", "role": "admin"})
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        search_mod._assert_search_access(current_super_admin(impersonation=True))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_busca_global_retorna_perfis_diversos_sem_catalogo_completo():
    db = FakeDb([
        candidate("teacher-1", "Ariedna Fixture", "professor"),
        candidate("secretary-1", "Secretária Fixture", "secretario"),
        candidate("guardian-1", "Responsável Fixture", "responsavel"),
        candidate("super-2", "Super Oculto", "super_admin", roles=["super_admin"]),
    ])

    items = await search_mod.search_global_test_users(
        db,
        current_user=current_super_admin(),
        query="Ariedna",
        limit=100,
    )

    assert {item["role"] for item in items} == {"professor", "secretario", "responsavel"}
    assert db.users.last_cursor.limit_value == search_mod.SEARCH_MAX_LIMIT
    assert db.users.last_cursor.to_list_length == search_mod.SEARCH_MAX_LIMIT
    assert "mantenedora_id" not in repr(db.users.last_query)


@pytest.mark.asyncio
async def test_busca_curta_nao_consulta_mongo():
    db = FakeDb([])
    items = await search_mod.search_global_test_users(
        db,
        current_user=current_super_admin(),
        query="A",
    )
    assert items == []
    assert db.users.last_query is None


def test_frontend_substitui_lista_por_filtro_global_de_busca():
    assert "usersAPI.getAll" not in CONTROL_UI
    assert "impersonation-target-select" not in CONTROL_UI
    assert "impersonation-user-search" in CONTROL_UI
    assert "impersonation-search-results" in CONTROL_UI
    assert "searchImpersonationUsers" in CONTROL_UI
    assert "não se limita a professores" in CONTROL_UI
    assert "/auth/impersonation/users/search" in SESSION_UI
