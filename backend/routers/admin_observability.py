"""
Router de Observabilidade — SIGESC.

Endpoints de telemetria operacional para super_admins. Restritos, auditados,
no-cache e com rate limit dedicado (apenas super_admin acessa, mas mesmo assim).

Diretriz: /app/docs/SEARCH_ARCHITECTURE.md (seção "Observabilidade").
"""
from __future__ import annotations

import time
import logging
from collections import defaultdict
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from auth_middleware import AuthMiddleware
from utils.students_search import get_observability_snapshot
from utils.observability import diary_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/observability", tags=["Observabilidade (admin)"])

# Rate limit dedicado (5 req/min por super_admin)
_admin_rate_buckets: dict[str, list[float]] = defaultdict(list)
_ADMIN_RATE_MAX = 5
_ADMIN_RATE_WINDOW = 60


def _check_admin_rate(user_id: str) -> None:
    now = time.monotonic()
    bucket = _admin_rate_buckets[user_id]
    cutoff = now - _ADMIN_RATE_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _ADMIN_RATE_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {_ADMIN_RATE_MAX} chamadas/min excedido para este endpoint."
        )
    bucket.append(now)


def _no_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def setup_admin_observability_router(audit_service: object | None = None) -> APIRouter:
    """Configura o router de observabilidade.

    `audit_service` é injetado pelo server.py (mesmo padrão dos demais routers).
    Caso None (testes), os endpoints continuam funcionando — apenas sem audit log.
    """

    @router.get("/autocomplete")
    async def autocomplete_observability(request: Request, response: Response):
        """Snapshot de observabilidade do autocomplete de alunos.

        Acesso restrito a super_admin. Cada chamada é registrada no audit log.
        Retorna métricas agregadas dos últimos 15 min em buckets de 1 min.
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # 1) Authz — só super_admin
        if current_user.get("role") != "super_admin":
            raise HTTPException(
                status_code=403,
                detail="Apenas super_admin pode acessar dados de observabilidade."
            )

        # 2) Rate limit dedicado
        user_key = current_user.get("id") or current_user.get("email") or "unknown"
        _check_admin_rate(user_key)

        # 3) No-cache headers (dado é dinâmico e sensível operacionalmente)
        _no_cache_headers(response)

        # 4) Snapshot
        snapshot = get_observability_snapshot()

        # 5) Audit log (best-effort — não bloqueia se falhar)
        if audit_service is not None:
            try:
                await audit_service.log(  # type: ignore[attr-defined]
                    action="export",
                    collection="observability_metrics",
                    user=current_user,
                    request=request,
                    description=(
                        f"Acesso a /admin/observability/autocomplete "
                        f"(window={snapshot['window']}, requests={snapshot['requests_total']})"
                    ),
                    extra_data={
                        "endpoint": "autocomplete",
                        "requests_total": snapshot["requests_total"],
                        "fallback_pct": snapshot["fallback_contains_pct"],
                        "cache_hit_pct": snapshot["cache_hit_pct"],
                    },
                )
            except Exception as e:
                logger.warning("[observability] falha ao gravar audit log: %s", e)

        return snapshot

    @router.get("/diary")
    async def diary_observability(request: Request, response: Response):
        """Snapshot do canal `diary` (alimentado pela Fase 2).

        Mesmo padrão do autocomplete: super_admin only, no-cache, rate limit, audit log.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Apenas super_admin pode acessar dados de observabilidade.")
        user_key = current_user.get("id") or current_user.get("email") or "unknown"
        _check_admin_rate(user_key)
        _no_cache_headers(response)
        snap = diary_metrics.snapshot()
        if audit_service is not None:
            try:
                await audit_service.log(  # type: ignore[attr-defined]
                    action="export", collection="observability_metrics",
                    user=current_user, request=request,
                    description=f"Acesso a /admin/observability/diary (requests={snap['requests_total']})",
                    extra_data={"endpoint": "diary", "requests_total": snap["requests_total"]},
                )
            except Exception as e:
                logger.warning("[observability:diary] audit log falhou: %s", e)
        return snap

    return router
