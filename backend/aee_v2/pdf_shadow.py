"""Fase 6.3A — Shadow Mode read-only do PDF do Diário AEE.

O PDF legado continua sendo produzido exatamente pelo endpoint e pelo gerador
existentes. Esta camada executa, somente depois de o PDF ter sido construído,
um diagnóstico de paridade entre a agenda que o PDF legado consulta em
``planos_aee`` e a agenda efetiva do Resolver Central da Fase 6.1A.

Nenhum dado do diagnóstico é injetado no PDF, na resposta HTTP ou no MongoDB.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from .effective_source import resolve_effective_dossier
from .repository import AEEV2RepositoryError


logger = logging.getLogger(__name__)

Resolver = Callable[[Any, str], Awaitable[Any]]
UserGetter = Callable[[Any], Awaitable[dict]]
DiagnosticsBuilder = Callable[..., Awaitable[dict]]

DAY_ORDER = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
}
DEFAULT_LOCAL = "Sala de Recursos Multifuncionais"


def _route_for(base_router, path: str, method: str):
    method = method.upper()
    matches = [
        route
        for route in base_router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"AEE v2 PDF Shadow esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise_session(session: Mapping[str, Any]) -> dict:
    """Normaliza somente os campos de agenda efetivamente exibidos no PDF."""

    return {
        "weekday": _text(session.get("weekday")),
        "start": _text(session.get("start")),
        "end": _text(session.get("end")),
        "local": _text(session.get("local")) or DEFAULT_LOCAL,
        "modalidade": _text(session.get("modalidade")),
    }


def _sort_sessions(sessions: list[dict]) -> list[dict]:
    return sorted(
        sessions,
        key=lambda item: (
            DAY_ORDER.get(item.get("weekday"), 99),
            item.get("weekday") or "",
            item.get("start") or "00:00",
            item.get("end") or "00:00",
            item.get("local") or "",
            item.get("modalidade") or "",
        ),
    )


def legacy_pdf_sessions(plano: Mapping[str, Any]) -> list[dict]:
    """Agenda que o endpoint legado usa para grade + cronograma do PDF."""

    days = plano.get("dias_atendimento")
    if not isinstance(days, list):
        days = []

    sessions = []
    for day in days:
        weekday = _text(day)
        if not weekday:
            continue
        sessions.append(
            _normalise_session(
                {
                    "weekday": weekday,
                    "start": plano.get("horario_inicio"),
                    "end": plano.get("horario_fim"),
                    "local": plano.get("local_atendimento"),
                    "modalidade": plano.get("modalidade"),
                }
            )
        )
    return _sort_sessions(sessions)


def effective_pdf_sessions(resolved: Any) -> list[dict]:
    """Agenda efetiva canônica reduzida ao conjunto de campos exibido no PDF."""

    schedule = getattr(getattr(resolved, "dossier", None), "schedule", None)
    raw_sessions = getattr(schedule, "sessions", None) or []

    sessions: list[dict] = []
    for raw in raw_sessions:
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json")
        if not isinstance(raw, Mapping):
            continue
        sessions.append(_normalise_session(raw))
    return _sort_sessions(sessions)


def _version_payload(resolved: Any) -> Optional[dict]:
    if getattr(resolved, "source", None) != "sidecar_active":
        return None
    return {
        "active_snapshot_id": getattr(resolved, "active_snapshot_id", None),
        "document_version": getattr(resolved, "document_version", None),
        "revision": getattr(resolved, "revision", None),
    }


def _pdf_plan_filter(
    *,
    school_id: str,
    academic_year: int,
    user: Mapping[str, Any],
    student_id: Optional[str] = None,
    professor_aee_id: Optional[str] = None,
) -> dict:
    """Replica apenas o escopo de leitura do endpoint legado de PDF."""

    query: dict[str, Any] = {
        "school_id": school_id,
        "academic_year": academic_year,
        "status": {"$in": ["ativo", "rascunho"]},
    }
    if student_id:
        query["student_id"] = student_id
    if professor_aee_id:
        query["professor_aee_id"] = professor_aee_id

    if user.get("role") == "professor":
        uid = user.get("id")
        query.setdefault("$or", []).extend(
            [
                {"professor_aee_id": uid},
                {"created_by": uid},
            ]
        )

    return query


async def build_pdf_schedule_shadow(
    db,
    *,
    school_id: str,
    academic_year: int,
    user: Mapping[str, Any],
    student_id: Optional[str] = None,
    professor_aee_id: Optional[str] = None,
    resolver: Optional[Resolver] = None,
    limit: int = 100,
) -> dict:
    """Calcula diagnóstico read-only da agenda do PDF, sem gerar/substituir PDF."""

    query = _pdf_plan_filter(
        school_id=school_id,
        academic_year=academic_year,
        user=user,
        student_id=student_id,
        professor_aee_id=professor_aee_id,
    )
    planos = await db.planos_aee.find(query, {"_id": 0}).to_list(limit)
    resolve = resolver or resolve_effective_dossier

    items: list[dict] = []
    sidecar_active_plans = 0
    legacy_plans = 0
    parity_plans = 0
    divergent_plans = 0
    error_plans = 0

    for plano in planos:
        plano_id = plano.get("id")
        legacy_sessions = legacy_pdf_sessions(plano)

        if not plano_id:
            error_plans += 1
            items.append(
                {
                    "legacy_plano_id": None,
                    "status": "error",
                    "effective_source": None,
                    "effective_version": None,
                    "legacy_sessions": legacy_sessions,
                    "effective_sessions": None,
                    "parity": None,
                    "error": {
                        "code": "AEE_V2_PDF_SHADOW_PLAN_ID_MISSING",
                        "message": "Plano AEE sem identificador no escopo do PDF.",
                    },
                }
            )
            continue

        try:
            resolved = await resolve(db, str(plano_id))
            effective_sessions = effective_pdf_sessions(resolved)
            parity = legacy_sessions == effective_sessions
            source = getattr(resolved, "source", None)

            if source == "sidecar_active":
                sidecar_active_plans += 1
            elif source == "legacy":
                legacy_plans += 1

            if parity:
                parity_plans += 1
                item_status = "parity"
            else:
                divergent_plans += 1
                item_status = "divergent"

            items.append(
                {
                    "legacy_plano_id": str(plano_id),
                    "status": item_status,
                    "effective_source": source,
                    "effective_version": _version_payload(resolved),
                    "legacy_sessions": legacy_sessions,
                    "effective_sessions": effective_sessions,
                    "parity": parity,
                    "error": None,
                }
            )
        except AEEV2RepositoryError as exc:
            error_plans += 1
            items.append(
                {
                    "legacy_plano_id": str(plano_id),
                    "status": "error",
                    "effective_source": None,
                    "effective_version": None,
                    "legacy_sessions": legacy_sessions,
                    "effective_sessions": None,
                    "parity": None,
                    "error": {
                        "code": getattr(exc, "code", "AEE_V2_REPOSITORY_ERROR"),
                        "message": str(exc),
                    },
                }
            )
        except Exception:
            error_plans += 1
            logger.exception(
                "AEE v2 PDF shadow: falha inesperada ao resolver plano %s",
                plano_id,
            )
            items.append(
                {
                    "legacy_plano_id": str(plano_id),
                    "status": "error",
                    "effective_source": None,
                    "effective_version": None,
                    "legacy_sessions": legacy_sessions,
                    "effective_sessions": None,
                    "parity": None,
                    "error": {
                        "code": "AEE_V2_PDF_SHADOW_RESOLUTION_ERROR",
                        "message": "Falha inesperada ao calcular a agenda efetiva do PDF.",
                    },
                }
            )

    if error_plans:
        status = "partial_error"
    elif divergent_plans:
        status = "divergent"
    else:
        status = "parity"

    return {
        "phase": "6.3A",
        "mode": "shadow_read_only",
        "status": status,
        "scope": {
            "school_id": school_id,
            "academic_year": academic_year,
            "student_id": student_id,
            "professor_aee_id": professor_aee_id,
            "role": user.get("role"),
        },
        "plans_total": len(planos),
        "sidecar_active_plans": sidecar_active_plans,
        "legacy_plans": legacy_plans,
        "parity_plans": parity_plans,
        "divergent_plans": divergent_plans,
        "error_plans": error_plans,
        "items": items,
    }


def _log_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    summary = {
        key: diagnostic.get(key)
        for key in (
            "phase",
            "mode",
            "status",
            "scope",
            "plans_total",
            "sidecar_active_plans",
            "legacy_plans",
            "parity_plans",
            "divergent_plans",
            "error_plans",
        )
    }
    logger.info(
        "AEE_V2_PDF_SHADOW %s",
        json.dumps(summary, ensure_ascii=False, default=str, sort_keys=True),
    )

    for item in diagnostic.get("items") or []:
        if item.get("status") == "parity":
            continue
        logger.warning(
            "AEE_V2_PDF_SHADOW_ITEM %s",
            json.dumps(item, ensure_ascii=False, default=str, sort_keys=True),
        )


def install_aee_v2_pdf_shadow(
    base_router,
    db,
    *,
    user_getter: UserGetter,
    diagnostics_builder: Optional[DiagnosticsBuilder] = None,
):
    """Envolve somente ``GET /aee/diario/pdf`` sem tocar na resposta gerada."""

    if getattr(base_router, "_aee_v2_pdf_shadow_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/diario/pdf", "GET")
    original_endpoint = target.endpoint
    original_signature = inspect.signature(original_endpoint)
    builder = diagnostics_builder or build_pdf_schedule_shadow

    @wraps(original_endpoint)
    async def shadow_endpoint(*args, **kwargs):
        # O PDF legado é construído primeiro. O retorno abaixo jamais é trocado.
        response = await original_endpoint(*args, **kwargs)

        try:
            bound = original_signature.bind_partial(*args, **kwargs)
            params = bound.arguments
            request = params.get("request")
            school_id = params.get("school_id")
            academic_year = params.get("academic_year")

            if request is None or school_id is None or academic_year is None:
                raise RuntimeError("Parâmetros essenciais do PDF não disponíveis no Shadow Mode.")

            user = await user_getter(request)
            diagnostic = await builder(
                db,
                school_id=school_id,
                academic_year=academic_year,
                user=user,
                student_id=params.get("student_id"),
                professor_aee_id=params.get("professor_aee_id"),
            )
            _log_diagnostic(diagnostic)
        except Exception:
            # Shadow Mode nunca pode derrubar ou substituir o PDF legado.
            logger.exception("AEE v2 PDF shadow: diagnóstico falhou após geração do PDF legado")

        return response

    # FastAPI 0.110.1 clona APIRoute em include_router() a partir de endpoint.
    target.endpoint = shadow_endpoint
    target.dependant.call = shadow_endpoint

    setattr(base_router, "_aee_v2_pdf_shadow_installed", True)
    return base_router


def install_aee_v2_pdf_shadow_setup(aee_module):
    """Instala o Shadow do PDF após os adapters AEE já encadeados."""

    if getattr(aee_module, "_aee_v2_pdf_shadow_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router
    user_getter = aee_module.AuthMiddleware.get_current_user

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_pdf_shadow(
            configured,
            db,
            user_getter=user_getter,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_pdf_shadow_setup_installed = True
