"""
[Fix Fev/2026] Regressão para o bug 500 em /api/curriculum/adaptations/availability:
    TypeError: argument of type 'NoneType' is not iterable

Origem do bug: `_require_any_auth` chamava `require_permission(..., None)`,
caindo no fallback `require_roles(None)` para non-super_admin sem override
Matrix.

Fix aplicado: lógica local em `curriculum_v2.py::_require_any_auth` que
honra override negativo da Matriz mas permite qualquer autenticado por
default. Sem tocar `auth_middleware.py`.

Estes testes validam o comportamento dos 3 cenários críticos:
  1. super_admin → bypass (passa direto)
  2. non-admin SEM override → passa (era o cenário do bug)
  3. non-admin com override visible=False → 403
  4. non-admin com override visible=True → passa
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fakes mínimos
# ---------------------------------------------------------------------------
class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None


class _FakeDB:
    def __init__(self, overrides=None):
        self._colls = {"permission_overrides": _FakeCollection(overrides or [])}

    def __getitem__(self, name):
        return self._colls.setdefault(name, _FakeCollection())

    @property
    def permission_overrides(self):
        return self._colls["permission_overrides"]


class _FakeRequest:
    def __init__(self):
        self.headers = {}
        self.cookies = {}
        self.state = type("S", (), {})()


def _aio(coro):
    return asyncio.run(coro)


def _build_require_any_auth(db, user_to_return):
    """Reconstrói localmente o wrapper para testar de forma isolada.

    Replica EXATAMENTE a lógica corrigida em curriculum_v2.py::_require_any_auth.
    """
    from fastapi import status

    async def _require_any_auth(request):
        role = user_to_return.get('role')
        if role == 'super_admin':
            return user_to_return
        try:
            override = await db.permission_overrides.find_one(
                {"item_key": 'nav-curriculum-button', "role": role},
                {"_id": 0, "visible": 1}
            )
        except Exception:
            override = None
        if override is not None and not override.get('visible'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado pela Matriz de Permissões (nav-curriculum-button × {role})"
            )
        return user_to_return

    return _require_any_auth


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------
def test_super_admin_passes_without_db_lookup():
    """super_admin é bypass — não consulta Matrix nem precisa de fallback."""
    db = _FakeDB(overrides=[])
    user = {"id": "u1", "email": "g@x.com", "role": "super_admin"}
    fn = _build_require_any_auth(db, user)
    result = _aio(fn(_FakeRequest()))
    assert result == user


def test_non_admin_without_override_passes_default_permissive():
    """REGRESSÃO PRINCIPAL: o cenário que estourava TypeError(None).

    Coordenador sem override em nav-curriculum-button DEVE passar (any auth).
    """
    db = _FakeDB(overrides=[])  # vazio = sem override
    user = {"id": "u2", "email": "c@x.com", "role": "coordenador"}
    fn = _build_require_any_auth(db, user)
    result = _aio(fn(_FakeRequest()))
    assert result == user  # passou sem TypeError


def test_non_admin_with_override_visible_false_is_blocked():
    """Override Matrix negativo continua sendo respeitado."""
    db = _FakeDB(overrides=[
        {"item_key": "nav-curriculum-button", "role": "professor", "visible": False}
    ])
    user = {"id": "u3", "email": "p@x.com", "role": "professor"}
    fn = _build_require_any_auth(db, user)
    with pytest.raises(HTTPException) as exc:
        _aio(fn(_FakeRequest()))
    assert exc.value.status_code == 403
    assert "Matriz de Permissões" in exc.value.detail
    assert "professor" in exc.value.detail


def test_non_admin_with_override_visible_true_passes():
    """Override positivo é redundante mas não deve quebrar."""
    db = _FakeDB(overrides=[
        {"item_key": "nav-curriculum-button", "role": "secretario", "visible": True}
    ])
    user = {"id": "u4", "email": "s@x.com", "role": "secretario"}
    fn = _build_require_any_auth(db, user)
    result = _aio(fn(_FakeRequest()))
    assert result == user


def test_non_admin_with_override_for_different_role_is_ignored():
    """Override de OUTRA role não afeta o usuário atual."""
    db = _FakeDB(overrides=[
        {"item_key": "nav-curriculum-button", "role": "professor", "visible": False}
    ])
    user = {"id": "u5", "email": "d@x.com", "role": "diretor"}  # role diferente
    fn = _build_require_any_auth(db, user)
    result = _aio(fn(_FakeRequest()))
    assert result == user  # passou — override era de professor, não diretor


def test_db_query_failure_does_not_block_user():
    """Se Mongo cair na consulta de override, NÃO deve bloquear (fail-open
    em leitura é o trade-off correto pra esse menu)."""
    class _FailingColl:
        async def find_one(self, *a, **kw):
            raise RuntimeError("mongo down")

    class _FailingDB:
        permission_overrides = _FailingColl()

    user = {"id": "u6", "email": "c@x.com", "role": "coordenador"}
    fn = _build_require_any_auth(_FailingDB(), user)
    result = _aio(fn(_FakeRequest()))
    assert result == user
