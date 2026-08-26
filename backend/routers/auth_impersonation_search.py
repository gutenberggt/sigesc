"""Busca global e segura de usuários para o Modo de Teste do Super Administrador."""

from __future__ import annotations

import re
from typing import Any, Mapping

from fastapi import HTTPException, Request, status

from auth_middleware import AuthMiddleware
from role_context import get_authorized_roles


SEARCH_MIN_CHARS = 2
SEARCH_DEFAULT_LIMIT = 20
SEARCH_MAX_LIMIT = 25


def _assert_search_access(current_user: Mapping[str, Any]) -> None:
    if current_user.get("impersonation"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Encerre o modo de teste antes de pesquisar outro usuário",
        )
    if current_user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o Super Administrador pode pesquisar usuários para o modo de teste",
        )


def _build_global_user_query(current_user_id: str, term: str) -> dict[str, Any]:
    """Monta consulta global sem escopo de tenant e sem regex fornecida pelo cliente."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return {
        "status": "active",
        "id": {"$ne": current_user_id},
        "role": {"$ne": "super_admin"},
        "roles": {"$ne": "super_admin"},
        "$or": [
            {"full_name": pattern},
            {"name": pattern},
            {"email": pattern},
        ],
    }


def _public_candidate(user_doc: Mapping[str, Any]) -> dict[str, Any] | None:
    roles = [role for role in get_authorized_roles(dict(user_doc)) if role != "super_admin"]
    raw_roles = set([user_doc.get("role"), *(user_doc.get("roles") or [])])
    if "super_admin" in raw_roles or not roles:
        return None

    return {
        "id": user_doc.get("id"),
        "full_name": user_doc.get("full_name") or user_doc.get("name") or user_doc.get("email"),
        "email": user_doc.get("email"),
        "role": user_doc.get("role"),
        "roles": roles,
        "mantenedora_id": user_doc.get("mantenedora_id"),
    }


async def search_global_test_users(
    db,
    *,
    current_user: Mapping[str, Any],
    query: str,
    limit: int = SEARCH_DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Pesquisa contas ativas em `users`, sem limitar a professor ou tenant ativo."""
    _assert_search_access(current_user)

    term = str(query or "").strip()
    if len(term) < SEARCH_MIN_CHARS:
        return []

    safe_limit = max(1, min(int(limit or SEARCH_DEFAULT_LIMIT), SEARCH_MAX_LIMIT))
    mongo_query = _build_global_user_query(str(current_user.get("id") or ""), term)
    projection = {
        "_id": 0,
        "id": 1,
        "full_name": 1,
        "name": 1,
        "email": 1,
        "role": 1,
        "roles": 1,
        "status": 1,
        "mantenedora_id": 1,
    }

    cursor = db.users.find(mongo_query, projection).sort(
        [("full_name", 1), ("email", 1)]
    ).limit(safe_limit)
    docs = await cursor.to_list(length=safe_limit)

    candidates = []
    for doc in docs:
        candidate = _public_candidate(doc)
        if candidate:
            candidates.append(candidate)
    return candidates


def install_auth_impersonation_search(router, db):
    """Instala busca global de candidatos no router Auth já configurado."""
    if getattr(router, "_super_admin_test_user_search_installed", False):
        return router

    @router.get("/impersonation/users/search")
    async def search_impersonation_users(
        request: Request,
        q: str = "",
        limit: int = SEARCH_DEFAULT_LIMIT,
    ):
        current_user = await AuthMiddleware.get_current_user(request)
        items = await search_global_test_users(
            db,
            current_user=current_user,
            query=q,
            limit=limit,
        )
        return {"items": items, "count": len(items)}

    router._super_admin_test_user_search_installed = True
    return router
