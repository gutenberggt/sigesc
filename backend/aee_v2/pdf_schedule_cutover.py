"""Fase 6.3B — cutover controlado da agenda efetiva no PDF do Diário AEE.

A Fase 6.3A observa o endpoint legado e produz um diagnóstico de paridade entre
agenda legada e fonte efetiva. Esta camada usa esse diagnóstico *antes* da
geração do PDF e só ativa a agenda efetiva quando toda a resposta é segura:

- status global ``parity``;
- zero erros e zero divergências;
- todas as fichas possuem item correspondente e agenda válida;
- a agenda efetiva pode ser representada sem perda pelo cronograma achatado do
  PDF atual (um mesmo horário/local/modalidade para os dias listados).

O cutover é atômico por requisição. Qualquer bloqueador mantém integralmente a
agenda legada. Nenhuma escrita é feita no MongoDB. O gerador ReportLab original
permanece intacto: um adapter ContextVar troca somente ``fichas`` e
``grade_horarios`` no momento da chamada, sem monkeypatch por requisição e sem
vazamento entre requisições concorrentes.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import inspect
import json
import logging
from types import ModuleType
from typing import Any, Awaitable, Callable, Optional

from .pdf_shadow import build_pdf_schedule_shadow


logger = logging.getLogger(__name__)

DiagnosticsBuilder = Callable[..., Awaitable[dict]]
UserGetter = Callable[[Any], Awaitable[dict]]

_PDF_CUTOVER_CONTEXT: ContextVar[Optional[dict]] = ContextVar(
    "aee_v2_pdf_schedule_cutover",
    default=None,
)


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
            f"AEE v2 PDF Schedule Cutover esperava exatamente uma rota "
            f"{method} {path}; encontrou {len(matches)}."
        )
    return matches[0]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_pdf_cutover_context(diagnostic: Any) -> dict:
    """Converte o diagnóstico 6.3A em decisão fail-closed para a 6.3B."""

    blockers: list[dict] = []

    if not isinstance(diagnostic, Mapping):
        blockers.append(
            {
                "code": "AEE_V2_PDF_CUTOVER_DIAGNOSTIC_INVALID",
                "message": "Diagnóstico do PDF Shadow possui formato inválido.",
            }
        )
        return {
            "phase": "6.3B",
            "mode": "controlled_cutover",
            "status": "blocked",
            "grade_source": "legacy",
            "diagnostic": diagnostic,
            "items": {},
            "blockers": blockers,
        }

    status = diagnostic.get("status")
    if status != "parity":
        blockers.append(
            {
                "code": "AEE_V2_PDF_CUTOVER_SHADOW_NOT_PARITY",
                "shadow_status": status,
                "message": "Cutover bloqueado porque o PDF Shadow não está em paridade global.",
            }
        )

    if int(diagnostic.get("error_plans") or 0) != 0:
        blockers.append(
            {
                "code": "AEE_V2_PDF_CUTOVER_SHADOW_ERRORS",
                "error_plans": int(diagnostic.get("error_plans") or 0),
                "message": "Cutover bloqueado por erro de resolução no PDF Shadow.",
            }
        )

    if int(diagnostic.get("divergent_plans") or 0) != 0:
        blockers.append(
            {
                "code": "AEE_V2_PDF_CUTOVER_SHADOW_DIVERGENCE",
                "divergent_plans": int(diagnostic.get("divergent_plans") or 0),
                "message": "Cutover bloqueado por divergência entre agenda legada e efetiva.",
            }
        )

    indexed: dict[str, dict] = {}
    raw_items = diagnostic.get("items")
    if not isinstance(raw_items, list):
        blockers.append(
            {
                "code": "AEE_V2_PDF_CUTOVER_ITEMS_INVALID",
                "message": "Diagnóstico não possui lista válida de planos.",
            }
        )
    else:
        for index, item in enumerate(raw_items):
            if not isinstance(item, Mapping):
                blockers.append(
                    {
                        "code": "AEE_V2_PDF_CUTOVER_ITEM_INVALID",
                        "item_index": index,
                        "message": "Item do diagnóstico possui formato inválido.",
                    }
                )
                continue

            plano_id = _text(item.get("legacy_plano_id"))
            if not plano_id:
                blockers.append(
                    {
                        "code": "AEE_V2_PDF_CUTOVER_PLAN_ID_MISSING",
                        "item_index": index,
                        "message": "Item do diagnóstico sem identificador de Plano AEE.",
                    }
                )
                continue

            if item.get("status") != "parity" or item.get("parity") is not True:
                blockers.append(
                    {
                        "code": "AEE_V2_PDF_CUTOVER_ITEM_NOT_PARITY",
                        "plano_id": plano_id,
                        "message": "Plano sem paridade individual para o cutover do PDF.",
                    }
                )
                continue

            sessions = item.get("effective_sessions")
            if not isinstance(sessions, list):
                blockers.append(
                    {
                        "code": "AEE_V2_PDF_CUTOVER_SCHEDULE_INVALID",
                        "plano_id": plano_id,
                        "message": "Agenda efetiva do plano não é uma lista válida.",
                    }
                )
                continue

            indexed[plano_id] = dict(item)

    return {
        "phase": "6.3B",
        "mode": "controlled_cutover",
        "status": "blocked" if blockers else "effective",
        "grade_source": "legacy" if blockers else "effective",
        "diagnostic": diagnostic,
        "items": indexed,
        "blockers": blockers,
    }


def _flattenability_blocker(plano_id: str, sessions: list) -> Optional[dict]:
    """Impede perda de informação no cronograma achatado do PDF atual."""

    if not sessions:
        return None

    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping) or not _text(session.get("weekday")):
            return {
                "code": "AEE_V2_PDF_CUTOVER_SESSION_INVALID",
                "plano_id": plano_id,
                "session_index": index,
                "message": "Sessão efetiva sem dia válido; cutover do PDF bloqueado.",
            }

    for field in ("start", "end", "local", "modalidade"):
        values = {_text(session.get(field)) for session in sessions}
        if len(values) > 1:
            return {
                "code": "AEE_V2_PDF_CUTOVER_NOT_FLATTENABLE",
                "plano_id": plano_id,
                "field": field,
                "message": (
                    "Agenda efetiva possui valores diferentes entre sessões e não pode "
                    "ser representada sem perda no cronograma atual do PDF."
                ),
            }

    return None


def apply_pdf_schedule_cutover(
    fichas: Any,
    grade_horarios: Any,
    context: Any,
) -> tuple[Any, Any, dict]:
    """Prepara cópias efetivas para o gerador ou preserva o legado integralmente."""

    if not isinstance(context, Mapping) or context.get("status") != "effective":
        metadata = {
            "phase": "6.3B",
            "status": "blocked",
            "grade_source": "legacy",
            "blockers": deepcopy((context or {}).get("blockers", []))
            if isinstance(context, Mapping)
            else [
                {
                    "code": "AEE_V2_PDF_CUTOVER_CONTEXT_MISSING",
                    "message": "Contexto do cutover não disponível.",
                }
            ],
        }
        return fichas, grade_horarios, metadata

    if not isinstance(fichas, list) or not isinstance(grade_horarios, dict):
        return fichas, grade_horarios, {
            "phase": "6.3B",
            "status": "blocked",
            "grade_source": "legacy",
            "blockers": [
                {
                    "code": "AEE_V2_PDF_CUTOVER_PAYLOAD_INVALID",
                    "message": "Fichas ou grade do PDF possuem formato inválido.",
                }
            ],
        }

    items = context.get("items")
    if not isinstance(items, Mapping):
        return fichas, grade_horarios, {
            "phase": "6.3B",
            "status": "blocked",
            "grade_source": "legacy",
            "blockers": [
                {
                    "code": "AEE_V2_PDF_CUTOVER_ITEMS_MISSING",
                    "message": "Contexto efetivo sem índice de planos.",
                }
            ],
        }

    blockers: list[dict] = []
    sessions_by_plan: dict[str, list] = {}

    # Primeira passagem: valida tudo antes de produzir qualquer substituição.
    for index, ficha in enumerate(fichas):
        if not isinstance(ficha, Mapping):
            blockers.append(
                {
                    "code": "AEE_V2_PDF_CUTOVER_FICHA_INVALID",
                    "ficha_index": index,
                    "message": "Ficha do PDF possui formato inválido.",
                }
            )
            continue

        plano = ficha.get("plano")
        plano_id = _text(plano.get("id")) if isinstance(plano, Mapping) else None
        if not plano_id:
            blockers.append(
                {
                    "code": "AEE_V2_PDF_CUTOVER_FICHA_PLAN_ID_MISSING",
                    "ficha_index": index,
                    "message": "Ficha do PDF sem identificador do Plano AEE.",
                }
            )
            continue

        item = items.get(plano_id)
        if not isinstance(item, Mapping):
            blockers.append(
                {
                    "code": "AEE_V2_PDF_CUTOVER_DIAGNOSTIC_ITEM_MISSING",
                    "plano_id": plano_id,
                    "message": "Plano da ficha não possui item correspondente no diagnóstico.",
                }
            )
            continue

        sessions = item.get("effective_sessions")
        if not isinstance(sessions, list):
            blockers.append(
                {
                    "code": "AEE_V2_PDF_CUTOVER_SCHEDULE_INVALID",
                    "plano_id": plano_id,
                    "message": "Agenda efetiva da ficha não é uma lista válida.",
                }
            )
            continue

        blocker = _flattenability_blocker(plano_id, sessions)
        if blocker:
            blockers.append(blocker)
            continue

        sessions_by_plan[plano_id] = deepcopy(sessions)

    if blockers:
        return fichas, grade_horarios, {
            "phase": "6.3B",
            "status": "blocked",
            "grade_source": "legacy",
            "fichas_total": len(fichas),
            "blockers": blockers,
        }

    effective_fichas = deepcopy(fichas)
    effective_grade: dict[str, list[dict]] = {}
    sessions_total = 0

    for ficha in effective_fichas:
        plano = ficha["plano"]
        plano_id = str(plano["id"])
        sessions = sessions_by_plan[plano_id]

        # O cronograma legado aceita uma lista de dias e um único conjunto de
        # horário/local/modalidade. A validação acima garante que a projeção é lossless.
        plano["dias_atendimento"] = [
            _text(session.get("weekday"))
            for session in sessions
            if _text(session.get("weekday"))
        ]

        if sessions:
            first = sessions[0]
            plano["horario_inicio"] = _text(first.get("start"))
            plano["horario_fim"] = _text(first.get("end"))
            plano["local_atendimento"] = _text(first.get("local"))
            plano["modalidade"] = _text(first.get("modalidade"))

        student = ficha.get("student") if isinstance(ficha.get("student"), Mapping) else {}
        student_name = _text(student.get("full_name")) or "N/A"

        for session in sessions:
            weekday = _text(session.get("weekday"))
            effective_grade.setdefault(weekday, []).append(
                {
                    "student_name": student_name,
                    "horario_inicio": _text(session.get("start")),
                    "horario_fim": _text(session.get("end")),
                }
            )
            sessions_total += 1

    for entries in effective_grade.values():
        entries.sort(
            key=lambda item: (
                item.get("horario_inicio") or "00:00",
                item.get("student_name") or "",
            )
        )

    diagnostic = context.get("diagnostic") if isinstance(context, Mapping) else {}
    return effective_fichas, effective_grade, {
        "phase": "6.3B",
        "status": "effective",
        "grade_source": "effective",
        "fichas_total": len(effective_fichas),
        "sessions_total": sessions_total,
        "sidecar_active_plans": (diagnostic or {}).get("sidecar_active_plans"),
        "legacy_plans": (diagnostic or {}).get("legacy_plans"),
        "blockers": [],
    }


def install_pdf_generator_schedule_cutover(generator_module: ModuleType):
    """Instala adapter ContextVar no gerador sem alterar o módulo ReportLab."""

    if getattr(generator_module, "_aee_v2_pdf_schedule_cutover_installed", False):
        return generator_module

    original = generator_module.generate_diario_aee_pdf
    signature = inspect.signature(original)

    @wraps(original)
    def effective_generator(*args, **kwargs):
        context = _PDF_CUTOVER_CONTEXT.get()
        if not isinstance(context, dict):
            return original(*args, **kwargs)

        try:
            bound = signature.bind_partial(*args, **kwargs)
            fichas = bound.arguments.get("fichas")
            grade = bound.arguments.get("grade_horarios")
            effective_fichas, effective_grade, metadata = apply_pdf_schedule_cutover(
                fichas,
                grade,
                context,
            )
            context["applied"] = metadata

            if metadata.get("status") == "effective":
                bound.arguments["fichas"] = effective_fichas
                bound.arguments["grade_horarios"] = effective_grade

            return original(*bound.args, **bound.kwargs)
        except Exception:
            # A falha da camada de cutover nunca derruba o PDF legado.
            logger.exception("AEE v2 PDF 6.3B: falha no adapter; usando agenda legada")
            context["applied"] = {
                "phase": "6.3B",
                "status": "blocked",
                "grade_source": "legacy",
                "blockers": [
                    {
                        "code": "AEE_V2_PDF_CUTOVER_ADAPTER_ERROR",
                        "message": "Falha inesperada no adapter; agenda legada preservada.",
                    }
                ],
            }
            return original(*args, **kwargs)

    generator_module.generate_diario_aee_pdf = effective_generator
    generator_module._aee_v2_pdf_schedule_cutover_installed = True
    return generator_module


def _log_cutover(context: Mapping[str, Any]) -> None:
    applied = context.get("applied") if isinstance(context.get("applied"), Mapping) else {}
    diagnostic = context.get("diagnostic") if isinstance(context.get("diagnostic"), Mapping) else {}
    payload = {
        "phase": "6.3B",
        "status": applied.get("status") or context.get("status"),
        "grade_source": applied.get("grade_source") or context.get("grade_source"),
        "plans_total": diagnostic.get("plans_total"),
        "sidecar_active_plans": diagnostic.get("sidecar_active_plans"),
        "legacy_plans": diagnostic.get("legacy_plans"),
        "sessions_total": applied.get("sessions_total"),
        "blockers": len(applied.get("blockers") or context.get("blockers") or []),
    }
    logger.info(
        "AEE_V2_PDF_SCHEDULE_CUTOVER %s",
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
    )


def install_aee_v2_pdf_schedule_cutover(
    base_router,
    db,
    *,
    user_getter: UserGetter,
    generator_module: ModuleType,
    diagnostics_builder: Optional[DiagnosticsBuilder] = None,
):
    """Envolve GET /aee/diario/pdf externamente ao Shadow 6.3A."""

    if getattr(base_router, "_aee_v2_pdf_schedule_cutover_installed", False):
        return base_router

    install_pdf_generator_schedule_cutover(generator_module)

    target = _route_for(base_router, "/aee/diario/pdf", "GET")
    current_endpoint = target.endpoint
    signature = inspect.signature(current_endpoint)
    builder = diagnostics_builder or build_pdf_schedule_shadow

    @wraps(current_endpoint)
    async def cutover_endpoint(*args, **kwargs):
        context: dict = {
            "phase": "6.3B",
            "mode": "controlled_cutover",
            "status": "blocked",
            "grade_source": "legacy",
            "items": {},
            "blockers": [
                {
                    "code": "AEE_V2_PDF_CUTOVER_PREFLIGHT_UNAVAILABLE",
                    "message": "Preflight do cutover não foi concluído.",
                }
            ],
        }

        try:
            bound = signature.bind_partial(*args, **kwargs)
            params = bound.arguments
            request = params.get("request")
            school_id = params.get("school_id")
            academic_year = params.get("academic_year")

            if request is None or school_id is None or academic_year is None:
                raise RuntimeError("Parâmetros essenciais do PDF indisponíveis no preflight 6.3B.")

            user = await user_getter(request)
            diagnostic = await builder(
                db,
                school_id=school_id,
                academic_year=academic_year,
                user=user,
                student_id=params.get("student_id"),
                professor_aee_id=params.get("professor_aee_id"),
            )
            context = build_pdf_cutover_context(diagnostic)
        except Exception:
            # O endpoint original mantém sua autenticação/erros e agenda legado.
            logger.exception("AEE v2 PDF 6.3B: preflight falhou; mantendo agenda legada")

        token = _PDF_CUTOVER_CONTEXT.set(context)
        try:
            response = await current_endpoint(*args, **kwargs)
        finally:
            _PDF_CUTOVER_CONTEXT.reset(token)

        _log_cutover(context)
        return response

    target.endpoint = cutover_endpoint
    target.dependant.call = cutover_endpoint

    setattr(base_router, "_aee_v2_pdf_schedule_cutover_installed", True)
    return base_router


def install_aee_v2_pdf_schedule_cutover_setup(aee_module):
    """Encadeia 6.3B depois do PDF Shadow 6.3A sem editar o router legado."""

    if getattr(aee_module, "_aee_v2_pdf_schedule_cutover_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router
    user_getter = aee_module.AuthMiddleware.get_current_user

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        from pdf import diario_aee as generator_module

        return install_aee_v2_pdf_schedule_cutover(
            configured,
            db,
            user_getter=user_getter,
            generator_module=generator_module,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_pdf_schedule_cutover_setup_installed = True
