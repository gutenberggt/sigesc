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
from utils.academic_event_sla import compute_sla_days, compute_sla_status

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


def setup_admin_observability_router(audit_service: object | None = None, db=None) -> APIRouter:
    """Configura o router de observabilidade.

    `audit_service` é injetado pelo server.py (mesmo padrão dos demais routers).
    `db` é necessário para os endpoints de academic_events (Passo 2 — Fev/2026).
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
        # Enriquece com média móvel de dep_ratio (sem PII).
        counters = snap.get("counters") or {}
        ratio_sum = counters.get("dependency_ratio_sum_x100") or 0
        ratio_samples = counters.get("dependency_ratio_samples") or 0
        if ratio_samples:
            snap["avg_dependency_ratio_pct"] = round((ratio_sum / 100.0) / ratio_samples, 2)
        else:
            snap["avg_dependency_ratio_pct"] = None

        # P2 (Fev/2026) — separa métricas técnicas vs pedagógicas.
        # Counters como `dependency_by_course__<id>` e `dependency_by_stage__<x>`
        # vão para o bloco `pedagogical`. O resto fica em `technical`.
        technical: dict = {}
        pedagogical: dict = {
            "dependency_by_course": {},
            "dependency_by_school_stage": {},
            "regular_total": counters.get("regular_total", 0),
            "dependency_total": counters.get("dependency_total", 0),
            "excess_dep_loads": counters.get("excess_dep_loads", 0),
            "avg_dependency_ratio_pct": snap.get("avg_dependency_ratio_pct"),
        }
        for k, v in counters.items():
            if k.startswith("dependency_by_course__"):
                pedagogical["dependency_by_course"][k.split("__", 1)[1]] = v
            elif k.startswith("dependency_by_stage__"):
                pedagogical["dependency_by_school_stage"][k.split("__", 1)[1]] = v
            elif k in {"regular_total", "dependency_total", "excess_dep_loads",
                       "dependency_ratio_sum_x100", "dependency_ratio_samples",
                       "items_total"}:
                # já no bloco pedagogical OU intermediários ocultos
                continue
            else:
                technical[k] = v
        snap["technical"] = technical
        snap["pedagogical"] = pedagogical
        # Compat: mantém `excess_dep_loads` no root para clientes legados (depreciado).
        snap["excess_dep_loads"] = pedagogical["excess_dep_loads"]

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

    @router.get("/academic_events")
    async def academic_events_observability(request: Request, response: Response):
        """Snapshot do canal `academic_events` (Passo 2 — Fev/2026).

        Separa explicitamente 4 dimensões:
        - `technical`  — DevOps/SRE
        - `operational` — Diretor / coordenação / SEMED
        - `pedagogical` — Análise de rede
        - `legal` — Auditoria jurídica e compliance
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Apenas super_admin pode acessar dados de observabilidade.")
        user_key = current_user.get("id") or current_user.get("email") or "unknown"
        _check_admin_rate(user_key)
        _no_cache_headers(response)

        if db is None:
            raise HTTPException(status_code=503, detail="Observability academic_events indisponível: db não injetado.")

        from datetime import datetime, timedelta, timezone
        now_utc = datetime.now(timezone.utc)
        last24h = (now_utc - timedelta(hours=24)).isoformat()

        # === OPERATIONAL ===
        pending_total = await db.academic_events.count_documents({"approval_status": "pending"})
        approvals_24h = await db.academic_events.count_documents({"approval_status": "approved", "approved_at": {"$gte": last24h}})
        supersessions_total = await db.academic_events.count_documents({"approval_status": "superseded"})

        pending_critical = 0
        pending_warning = 0
        pending_healthy = 0
        # SLA p95 dos pendentes
        pending_ages: list[int] = []
        async for e in db.academic_events.find({"approval_status": "pending"}, {"_id": 0, "created_at": 1}):
            d = compute_sla_days(e.get("created_at"), now=now_utc)
            pending_ages.append(d)
            st = compute_sla_status(d)
            if st == "critical":
                pending_critical += 1
            elif st == "warning":
                pending_warning += 1
            else:
                pending_healthy += 1
        pending_ages.sort()
        if pending_ages:
            p95_idx = max(0, int(len(pending_ages) * 0.95) - 1)
            pending_age_p95 = pending_ages[p95_idx]
        else:
            pending_age_p95 = 0

        # === PEDAGOGICAL — distribuição por tipo ===
        events_by_type: dict[str, int] = {}
        cursor = db.academic_events.aggregate([
            {"$match": {"approval_status": {"$in": ["approved", "pending"]}}},
            {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
        ])
        async for row in cursor:
            events_by_type[row["_id"] or "unknown"] = row["n"]

        # === LEGAL ===
        # 1) blocked_post_effective_date_attempts
        blocked_post = await db.academic_event_audit.count_documents(
            {"reason_code": "AFTER_EFFECTIVE_DATE"}
        )
        # 2) blocked_pre_effective_date_attempts (destination read-only)
        blocked_pre = await db.academic_event_audit.count_documents(
            {"reason_code": "BEFORE_EFFECTIVE_DATE_DESTINATION"}
        )
        # 3) events_without_rationale (defensivo — contrato exige rationale ≥30; este é health check)
        events_without_rationale = await db.academic_events.count_documents({
            "$or": [{"rationale": {"$exists": False}}, {"rationale": None}, {"rationale": ""}],
        })
        # 4) supersession chain depth p95 (quantos eventos foram superseded sucessivamente)
        depths: list[int] = []
        async for ev in db.academic_events.find({"supersedes_event_id": {"$ne": None}}, {"_id": 0, "id": 1, "supersedes_event_id": 1}):
            depth = 1
            current = ev.get("supersedes_event_id")
            seen = set()
            while current and current not in seen:
                seen.add(current)
                prev = await db.academic_events.find_one({"id": current}, {"_id": 0, "supersedes_event_id": 1})
                if not prev or not prev.get("supersedes_event_id"):
                    break
                depth += 1
                current = prev["supersedes_event_id"]
            depths.append(depth)
        depths.sort()
        chain_p95 = depths[max(0, int(len(depths) * 0.95) - 1)] if depths else 0

        # === TECHNICAL ===
        lock_attempts_total = await db.academic_event_audit.count_documents({})
        # Contagem por reason_code
        lock_by_reason: dict[str, int] = {}
        cursor2 = db.academic_event_audit.aggregate([
            {"$group": {"_id": "$reason_code", "n": {"$sum": 1}}},
        ])
        async for row in cursor2:
            lock_by_reason[row["_id"] or "unknown"] = row["n"]

        snapshot = {
            "channel": "academic_events",
            "captured_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sla_version": "1",

            "technical": {
                "lock_attempts_total": lock_attempts_total,
                "lock_attempts_by_reason_code": lock_by_reason,
            },

            "operational": {
                "pending_total": pending_total,
                "pending_healthy": pending_healthy,
                "pending_warning": pending_warning,
                "pending_critical": pending_critical,
                "pending_age_p95_days": pending_age_p95,
                "supersessions_total": supersessions_total,
                "approvals_last_24h": approvals_24h,
            },

            "pedagogical": {
                "events_by_type": events_by_type,
            },

            "legal": {
                "blocked_post_effective_date_attempts": blocked_post,
                "blocked_pre_effective_date_attempts": blocked_pre,
                "events_without_rationale": events_without_rationale,
                "superseded_chain_depth_p95": chain_p95,
            },
        }

        if audit_service is not None:
            try:
                await audit_service.log(  # type: ignore[attr-defined]
                    action="export", collection="observability_metrics",
                    user=current_user, request=request,
                    description=f"Acesso a /admin/observability/academic_events (pending={pending_total})",
                    extra_data={"endpoint": "academic_events", "pending_total": pending_total},
                )
            except Exception as e:
                logger.warning("[observability:academic_events] audit log falhou: %s", e)
        return snapshot

    return router
