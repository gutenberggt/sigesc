"""Projeção do nome do responsável no histórico de movimentações do estudante.

A coleção ``student_history`` possui registros legados em que ``user_name``
recebeu o e-mail do executor. Esta camada envolve apenas a leitura de
``GET /students/{student_id}/history`` e resolve o ``full_name`` atual a partir
de ``user_id`` (preferencial) ou do e-mail legado.

Invariantes:
- nenhuma migração/backfill ou escrita em ``student_history``;
- o endpoint canônico continua responsável por autenticação e autorização;
- quando o usuário não puder ser resolvido, o valor legado é preservado;
- a resolução é feita em lote, evitando N+1 queries.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from auth_middleware import AuthMiddleware


ROUTE_PATH = "/students/{student_id}/history"


def _remove_route(base_router: Any, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def _db_for_user(db, sandbox_db, current_user: dict):
    if current_user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


def install_student_history_responsible_name(base_router: Any, db, sandbox_db=None):
    """Substitui somente a projeção de leitura do histórico de movimentações."""
    if getattr(base_router, "_student_history_responsible_name_installed", False):
        return base_router

    current_history = _remove_route(base_router, ROUTE_PATH, "GET")
    if current_history is None:
        raise RuntimeError(
            "Histórico do Estudante não encontrou GET "
            "/students/{student_id}/history para envolver."
        )

    @base_router.get("/{student_id}/history")
    async def get_student_history_with_responsible_name(
        student_id: str,
        request: Request,
    ):
        history = await current_history(student_id=student_id, request=request)
        if not isinstance(history, list) or not history:
            return history

        user_ids = {
            item.get("user_id")
            for item in history
            if isinstance(item, dict) and item.get("user_id")
        }
        legacy_emails = {
            str(item.get("user_name") or "").strip()
            for item in history
            if isinstance(item, dict)
            and "@" in str(item.get("user_name") or "")
        }
        if not user_ids and not legacy_emails:
            return history

        current_user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, current_user)

        filters = []
        if user_ids:
            filters.append({"id": {"$in": list(user_ids)}})
        if legacy_emails:
            filters.append({"email": {"$in": list(legacy_emails)}})
        user_query = filters[0] if len(filters) == 1 else {"$or": filters}

        users = await current_db.users.find(
            user_query,
            {"_id": 0, "id": 1, "full_name": 1, "email": 1},
        ).to_list(None)

        names_by_id: dict[str, str] = {}
        names_by_email: dict[str, str] = {}
        for user_doc in users:
            full_name = str(user_doc.get("full_name") or "").strip()
            if not full_name:
                continue
            user_id = user_doc.get("id")
            if user_id:
                names_by_id[str(user_id)] = full_name
            email = str(user_doc.get("email") or "").strip().lower()
            if email:
                names_by_email[email] = full_name

        for item in history:
            if not isinstance(item, dict):
                continue
            resolved_name = names_by_id.get(str(item.get("user_id") or ""))
            if not resolved_name:
                legacy_value = str(item.get("user_name") or "").strip()
                if "@" in legacy_value:
                    resolved_name = names_by_email.get(legacy_value.lower())
            if resolved_name:
                # Projeção somente em memória/resposta HTTP; não persiste no Mongo.
                item["user_name"] = resolved_name

        return history

    base_router._student_history_responsible_name_installed = True
    return base_router
