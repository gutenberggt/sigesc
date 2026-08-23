"""Fase 6.5B — PDF Individual do Plano AEE pela Fonte Efetiva.

Envolve somente ``GET /aee/planos/{plano_id}/pdf`` sem editar o router legado
nem o gerador ReportLab. A Fonte Efetiva é resolvida antes da geração:

- ``legacy``: o Plano legado continua sendo a própria fonte efetiva;
- ``sidecar_active``: o snapshot V2 vigente é projetado, em memória, para os
  campos que o PDF atual representa;
- erro de integridade ou projeção não representável: o PDF legado é preservado.

O adapter usa ``ContextVar`` para não haver vazamento entre requisições
concorrentes. Nenhuma coleção MongoDB é escrita nesta fase.
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

from .effective_source import resolve_effective_dossier
from .repository import AEEV2RepositoryError


logger = logging.getLogger(__name__)

Resolver = Callable[[Any, str], Awaitable[Any]]

_PDF_EFFECTIVE_CONTEXT: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "aee_v2_plano_pdf_effective",
    default=None,
)

_V2_TO_LEGACY_STATUS = {
    "draft": "rascunho",
    "active": "ativo",
    "review": "revisao",
    "closed": "encerrado",
    "cancelled": "cancelado",
}


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
            f"AEE v2 Plano PDF Effective esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _version_payload(resolved) -> Optional[dict[str, Any]]:
    if resolved.source != "sidecar_active":
        return None
    return {
        "active_snapshot_id": resolved.active_snapshot_id,
        "document_version": resolved.document_version,
        "revision": resolved.revision,
    }


def _blocked(code: str, message: str, **extra) -> dict[str, Any]:
    blocker = {"code": code, "message": message, **extra}
    return {
        "phase": "6.5B",
        "mode": "effective_source_cutover",
        "status": "blocked",
        "plan_source": "legacy",
        "effective_source": None,
        "effective_version": None,
        "dossier": None,
        "blockers": [blocker],
    }


async def build_plano_pdf_effective_context(
    db,
    plano_id: str,
    *,
    resolver: Optional[Resolver] = None,
) -> dict[str, Any]:
    """Resolve a Fonte Efetiva antes da geração do PDF, sem persistência."""

    resolve = resolver or resolve_effective_dossier

    try:
        resolved = await resolve(db, str(plano_id))
    except AEEV2RepositoryError as exc:
        context = _blocked(
            getattr(exc, "code", "AEE_V2_REPOSITORY_ERROR"),
            str(exc),
        )
        context["legacy_plano_id"] = str(plano_id)
        return context
    except Exception:
        logger.exception(
            "AEE v2 plano PDF 6.5B: falha inesperada ao resolver plano %s",
            plano_id,
        )
        context = _blocked(
            "AEE_V2_PLANO_PDF_EFFECTIVE_RESOLUTION_ERROR",
            "Falha inesperada ao resolver a Fonte Efetiva do Plano AEE.",
        )
        context["legacy_plano_id"] = str(plano_id)
        return context

    if resolved.source == "legacy":
        return {
            "phase": "6.5B",
            "mode": "effective_source_cutover",
            "status": "legacy",
            "plan_source": "legacy",
            "legacy_plano_id": str(plano_id),
            "effective_source": "legacy",
            "effective_version": None,
            "dossier": None,
            "blockers": [],
        }

    if resolved.source != "sidecar_active":
        context = _blocked(
            "AEE_V2_PLANO_PDF_EFFECTIVE_SOURCE_INVALID",
            "Fonte Efetiva do Plano AEE não é reconhecida para o PDF.",
            source=resolved.source,
        )
        context["legacy_plano_id"] = str(plano_id)
        return context

    return {
        "phase": "6.5B",
        "mode": "effective_source_cutover",
        "status": "effective",
        "plan_source": "sidecar_active",
        "legacy_plano_id": str(plano_id),
        "effective_source": "sidecar_active",
        "effective_version": _version_payload(resolved),
        "dossier": resolved.dossier.model_dump(mode="json"),
        "blockers": [],
    }


def _flatten_schedule(dossier: Mapping[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    schedule = dossier.get("schedule")
    if not isinstance(schedule, Mapping):
        return None, {
            "code": "AEE_V2_PLANO_PDF_SCHEDULE_INVALID",
            "message": "Dossiê V2 sem estrutura válida de cronograma.",
        }

    sessions = schedule.get("sessions")
    if not isinstance(sessions, list):
        return None, {
            "code": "AEE_V2_PLANO_PDF_SESSIONS_INVALID",
            "message": "Sessões do Dossiê V2 não formam uma lista válida.",
        }

    normalized: list[dict[str, Optional[str]]] = []
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            return None, {
                "code": "AEE_V2_PLANO_PDF_SESSION_INVALID",
                "session_index": index,
                "message": "Sessão V2 possui formato inválido.",
            }
        weekday = _text(session.get("weekday"))
        if not weekday:
            return None, {
                "code": "AEE_V2_PLANO_PDF_WEEKDAY_MISSING",
                "session_index": index,
                "message": "Sessão V2 sem dia da semana; PDF efetivo bloqueado.",
            }
        normalized.append(
            {
                "weekday": weekday,
                "start": _text(session.get("start")),
                "end": _text(session.get("end")),
                "local": _text(session.get("local")),
                "modalidade": _text(session.get("modalidade")),
            }
        )

    for field in ("start", "end", "local", "modalidade"):
        values = {session.get(field) for session in normalized}
        if len(values) > 1:
            return None, {
                "code": "AEE_V2_PLANO_PDF_NOT_FLATTENABLE",
                "field": field,
                "message": (
                    "O cronograma V2 possui valores diferentes entre sessões e não pode "
                    "ser representado sem perda pelo PDF individual atual."
                ),
            }

    first = normalized[0] if normalized else {}
    return {
        "dias_atendimento": [item["weekday"] for item in normalized],
        "horario_inicio": first.get("start"),
        "horario_fim": first.get("end"),
        "local_atendimento": first.get("local"),
        "modalidade": first.get("modalidade"),
        "carga_horaria_semanal": _text(schedule.get("carga_horaria_semanal")),
    }, None


def _descriptions(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            desc = _text(item.get("descricao"))
            if desc:
                result.append(dict(item))
        else:
            desc = _text(item)
            if desc:
                result.append({"descricao": desc})
    return result


def _objectives(items: Any) -> list[dict[str, Any]]:
    return _descriptions(items)


def _combine_accessibility(pei: Mapping[str, Any]) -> Optional[str]:
    curricular = _text(pei.get("acessibilidade_curricular"))
    didatico = _text(pei.get("acessibilidade_didatico_pedagogica"))
    avaliativa = _text(pei.get("acessibilidade_avaliativa"))

    # Compatibilidade semântica com o PDF legado: quando o snapshot ativo só
    # possui o campo curricular, não introduzir um rótulo que não existia no
    # conteúdo original e que criaria divergência artificial no Shadow Mode.
    if curricular and not didatico and not avaliativa:
        return curricular

    parts: list[str] = []
    for label, value in (
        ("Curricular", curricular),
        ("Didático-pedagógica", didatico),
        ("Avaliativa", avaliativa),
    ):
        if value:
            parts.append(f"{label}: {value}")
    return "\n".join(parts) or None


def _periodo_vigencia(lifecycle: Mapping[str, Any]) -> Optional[str]:
    legacy = _text(lifecycle.get("periodo_vigencia_legacy"))
    if legacy:
        return legacy
    start = _text(lifecycle.get("effective_from"))
    end = _text(lifecycle.get("effective_to"))
    if start and end:
        return f"{start} a {end}"
    return start or end


def project_effective_pdf_plan(
    legacy_plan: Any,
    context: Any,
) -> tuple[Any, dict[str, Any]]:
    """Projeta o snapshot ativo para o contrato atual do gerador ReportLab.

    A função valida toda a projeção antes de copiar/substituir o Plano. Em
    qualquer bloqueador, devolve exatamente o objeto legado recebido.
    """

    if not isinstance(context, Mapping):
        return legacy_plan, {
            "phase": "6.5B",
            "status": "blocked",
            "plan_source": "legacy",
            "blockers": [
                {
                    "code": "AEE_V2_PLANO_PDF_CONTEXT_MISSING",
                    "message": "Contexto da Fonte Efetiva não está disponível.",
                }
            ],
        }

    if context.get("status") == "legacy":
        return legacy_plan, {
            "phase": "6.5B",
            "status": "legacy",
            "plan_source": "legacy",
            "effective_source": "legacy",
            "blockers": [],
        }

    if context.get("status") != "effective":
        return legacy_plan, {
            "phase": "6.5B",
            "status": "blocked",
            "plan_source": "legacy",
            "effective_source": context.get("effective_source"),
            "blockers": deepcopy(context.get("blockers") or []),
        }

    if not isinstance(legacy_plan, Mapping):
        return legacy_plan, {
            "phase": "6.5B",
            "status": "blocked",
            "plan_source": "legacy",
            "blockers": [
                {
                    "code": "AEE_V2_PLANO_PDF_LEGACY_PAYLOAD_INVALID",
                    "message": "Plano legado recebido pelo gerador possui formato inválido.",
                }
            ],
        }

    dossier = context.get("dossier")
    if not isinstance(dossier, Mapping):
        return legacy_plan, {
            "phase": "6.5B",
            "status": "blocked",
            "plan_source": "legacy",
            "blockers": [
                {
                    "code": "AEE_V2_PLANO_PDF_DOSSIER_MISSING",
                    "message": "Contexto efetivo sem Dossiê V2 serializado.",
                }
            ],
        }

    blockers: list[dict[str, Any]] = []
    for field in ("student_id", "school_id", "academic_year"):
        legacy_value = legacy_plan.get(field)
        effective_value = dossier.get(field)
        if str(legacy_value) != str(effective_value):
            blockers.append(
                {
                    "code": "AEE_V2_PLANO_PDF_IDENTITY_MISMATCH",
                    "field": field,
                    "message": "Identidade do snapshot V2 diverge da âncora legado do PDF.",
                }
            )

    schedule_fields, schedule_blocker = _flatten_schedule(dossier)
    if schedule_blocker:
        blockers.append(schedule_blocker)

    if blockers:
        return legacy_plan, {
            "phase": "6.5B",
            "status": "blocked",
            "plan_source": "legacy",
            "effective_source": "sidecar_active",
            "blockers": blockers,
        }

    study_case = dossier.get("study_case") if isinstance(dossier.get("study_case"), Mapping) else {}
    paee = dossier.get("paee") if isinstance(dossier.get("paee"), Mapping) else {}
    pei = dossier.get("pei") if isinstance(dossier.get("pei"), Mapping) else {}
    lifecycle = dossier.get("lifecycle") if isinstance(dossier.get("lifecycle"), Mapping) else {}

    effective = deepcopy(dict(legacy_plan))
    effective.update(
        {
            "academic_year": dossier.get("academic_year"),
            "status": _V2_TO_LEGACY_STATUS.get(_text(lifecycle.get("status")) or "", legacy_plan.get("status")),
            "data_elaboracao": _text(lifecycle.get("elaborated_at")),
            "periodo_vigencia": _periodo_vigencia(lifecycle),
            "publico_alvo": _text(dossier.get("publico_alvo")),
            "criterio_elegibilidade": _text(study_case.get("fundamentacao_pedagogica_identificacao")),
            "escola_origem_nome": _text(dossier.get("escola_origem_nome")),
            "turma_origem_nome": _text(dossier.get("turma_origem_nome")),
            "professor_regente_nome": _text(dossier.get("professor_regente_nome")),
            "professor_aee_nome": _text(dossier.get("professor_aee_responsavel_nome")),
            "orientacoes_sala_comum": _text(pei.get("articulacao_sala_comum")),
            "combinados_professor_regente": _text(pei.get("combinados_professor_regente")),
            "adequacoes_curriculares": _combine_accessibility(pei),
            "adaptacoes_por_componente": _text(pei.get("adaptacoes_por_componente")),
            "linha_base_situacao_atual": _text(study_case.get("demanda_inicial_contexto")),
            "linha_base_potencialidades": _text(study_case.get("potencialidades")),
            "linha_base_dificuldades": _text(study_case.get("demandas_apoio")),
            "linha_base_comunicacao": _text(study_case.get("comunicacao_participacao")),
            "barreiras": _descriptions(paee.get("barreiras_prioritarias") or study_case.get("barreiras_contexto")),
            "objetivos": _objectives(paee.get("objetivos")),
            "recursos_acessibilidade": _descriptions(paee.get("materiais_recursos")),
            "indicadores_progresso": _text(paee.get("indicadores_progresso")),
            "frequencia_revisao": _text(paee.get("frequencia_revisao")),
            "criterios_ajuste": _text(paee.get("criterios_ajuste")),
            "data_revisao": _text(lifecycle.get("review_at")),
            **(schedule_fields or {}),
        }
    )

    return effective, {
        "phase": "6.5B",
        "status": "effective",
        "plan_source": "sidecar_active",
        "effective_source": "sidecar_active",
        "effective_version": deepcopy(context.get("effective_version")),
        "sessions_total": len((dossier.get("schedule") or {}).get("sessions") or []),
        "blockers": [],
    }


def install_plano_pdf_generator_effective(generator_module: ModuleType):
    """Instala adapter ContextVar no gerador individual sem editar ReportLab."""

    if getattr(generator_module, "_aee_v2_plano_pdf_effective_installed", False):
        return generator_module

    original = generator_module.generate_plano_aee_pdf
    signature = inspect.signature(original)

    @wraps(original)
    def effective_generator(*args, **kwargs):
        context = _PDF_EFFECTIVE_CONTEXT.get()
        if not isinstance(context, dict):
            return original(*args, **kwargs)

        try:
            bound = signature.bind_partial(*args, **kwargs)
            legacy_plan = bound.arguments.get("plano")
            projected, metadata = project_effective_pdf_plan(legacy_plan, context)
            context["applied"] = metadata
            if metadata.get("status") == "effective":
                bound.arguments["plano"] = projected
            return original(*bound.args, **bound.kwargs)
        except Exception:
            logger.exception(
                "AEE v2 plano PDF 6.5B: adapter falhou; usando Plano legado"
            )
            context["applied"] = {
                "phase": "6.5B",
                "status": "blocked",
                "plan_source": "legacy",
                "blockers": [
                    {
                        "code": "AEE_V2_PLANO_PDF_ADAPTER_ERROR",
                        "message": "Falha inesperada no adapter; PDF legado preservado.",
                    }
                ],
            }
            return original(*args, **kwargs)

    generator_module.generate_plano_aee_pdf = effective_generator
    generator_module._aee_v2_plano_pdf_effective_installed = True
    return generator_module


def _log_cutover(context: Mapping[str, Any]) -> None:
    applied = context.get("applied") if isinstance(context.get("applied"), Mapping) else {}
    payload = {
        "phase": "6.5B",
        "status": applied.get("status") or context.get("status"),
        "plan_source": applied.get("plan_source") or context.get("plan_source"),
        "effective_source": context.get("effective_source"),
        "legacy_plano_id": context.get("legacy_plano_id"),
        "document_version": (context.get("effective_version") or {}).get("document_version")
        if isinstance(context.get("effective_version"), Mapping)
        else None,
        "revision": (context.get("effective_version") or {}).get("revision")
        if isinstance(context.get("effective_version"), Mapping)
        else None,
        "sessions_total": applied.get("sessions_total"),
        "blockers": len(applied.get("blockers") or context.get("blockers") or []),
    }
    level = (
        logging.WARNING
        if payload["effective_source"] == "sidecar_active" or payload["blockers"] > 0
        else logging.INFO
    )
    logger.log(
        level,
        "AEE_V2_PLANO_PDF_EFFECTIVE %s",
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
    )


def install_aee_v2_plano_pdf_effective(
    base_router,
    db,
    *,
    generator_module: ModuleType,
    resolver: Optional[Resolver] = None,
):
    """Envolve GET /aee/planos/{plano_id}/pdf com cutover efetivo fail-closed."""

    if getattr(base_router, "_aee_v2_plano_pdf_effective_installed", False):
        return base_router

    install_plano_pdf_generator_effective(generator_module)

    target = _route_for(base_router, "/aee/planos/{plano_id}/pdf", "GET")
    current_endpoint = target.endpoint
    signature = inspect.signature(current_endpoint)

    @wraps(current_endpoint)
    async def effective_pdf_endpoint(*args, **kwargs):
        context = _blocked(
            "AEE_V2_PLANO_PDF_PREFLIGHT_UNAVAILABLE",
            "Preflight da Fonte Efetiva não foi concluído.",
        )

        try:
            bound = signature.bind_partial(*args, **kwargs)
            plano_id = bound.arguments.get("plano_id")
            if plano_id is None:
                raise RuntimeError("plano_id indisponível no preflight 6.5B")
            context = await build_plano_pdf_effective_context(
                db,
                str(plano_id),
                resolver=resolver,
            )
        except Exception:
            logger.exception(
                "AEE v2 plano PDF 6.5B: preflight falhou; mantendo PDF legado"
            )

        token = _PDF_EFFECTIVE_CONTEXT.set(context)
        try:
            response = await current_endpoint(*args, **kwargs)
        finally:
            _PDF_EFFECTIVE_CONTEXT.reset(token)

        _log_cutover(context)
        return response

    target.endpoint = effective_pdf_endpoint
    target.dependant.call = effective_pdf_endpoint

    setattr(base_router, "_aee_v2_plano_pdf_effective_installed", True)
    return base_router


def install_aee_v2_plano_pdf_effective_setup(aee_module):
    """Instala a 6.5B sem editar o router AEE ou o gerador individual."""

    if getattr(aee_module, "_aee_v2_plano_pdf_effective_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        from pdf import plano_aee as generator_module

        return install_aee_v2_plano_pdf_effective(
            configured,
            db,
            generator_module=generator_module,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plano_pdf_effective_setup_installed = True
