"""Fase 6.5A — Shadow Mode do PDF Individual do Plano AEE.

O endpoint legado ``GET /aee/planos/{plano_id}/pdf`` continua sendo a única
fonte do PDF devolvido ao usuário. Depois que o PDF legado já foi construído,
esta camada calcula, somente em memória, como a Fonte Efetiva seria projetada
para o contrato atual do gerador ReportLab e registra paridade/divergências.

Importante: o PR que preparou a 6.5B permanece no repositório, porém seu
instalador runtime deve ficar DESARMADO enquanto esta fase não for homologada.
As funções puras de projeção da 6.5B são reutilizadas aqui apenas como candidato
de comparação; o generator adapter/cutover da 6.5B não é instalado.

Nenhum texto pedagógico é registrado em log: somente nomes de campos divergentes,
metadados de versão e blockers. Nenhum dado é persistido e nenhum byte do PDF
legado é substituído.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from .plano_pdf_effective import (
    build_plano_pdf_effective_context,
    project_effective_pdf_plan,
)


logger = logging.getLogger(__name__)

ContextBuilder = Callable[..., Awaitable[dict[str, Any]]]
Projector = Callable[[Any, Any], tuple[Any, dict[str, Any]]]
DiagnosticsBuilder = Callable[..., Awaitable[dict[str, Any]]]


# Campos do ``plano`` efetivamente consumidos por backend/pdf/plano_aee.py.
# Dados de student/school/mantenedora permanecem nas mesmas consultas legadas e
# não fazem parte do cutover do Dossiê V2.
PDF_PLAN_FIELDS: tuple[str, ...] = (
    "academic_year",
    "status",
    "data_elaboracao",
    "periodo_vigencia",
    "publico_alvo",
    "criterio_elegibilidade",
    "escola_origem_nome",
    "turma_origem_nome",
    "professor_regente_nome",
    "professor_aee_nome",
    "orientacoes_sala_comum",
    "combinados_professor_regente",
    "adequacoes_curriculares",
    "adaptacoes_por_componente",
    "linha_base_situacao_atual",
    "linha_base_potencialidades",
    "linha_base_dificuldades",
    "linha_base_comunicacao",
    "modalidade",
    "carga_horaria_semanal",
    "dias_atendimento",
    "horario_inicio",
    "horario_fim",
    "local_atendimento",
    "barreiras",
    "objetivos",
    "recursos_acessibilidade",
    "indicadores_progresso",
    "frequencia_revisao",
    "criterios_ajuste",
    "data_revisao",
)

_DESCRIPTION_LIST_FIELDS = {
    "barreiras",
    "objetivos",
    "recursos_acessibilidade",
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
            f"AEE v2 Plano PDF Shadow esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _description_list(value: Any) -> list[Optional[str]]:
    if not isinstance(value, list):
        return []
    result: list[Optional[str]] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(_text(item.get("descricao")))
        else:
            result.append(_text(item))
    return result


def _normalise_pdf_value(field: str, value: Any) -> Any:
    """Normaliza conforme a semântica visível no PDF, sem carregar textos em log."""

    if field in _DESCRIPTION_LIST_FIELDS:
        return _description_list(value)

    if field == "dias_atendimento":
        if not isinstance(value, list):
            return []
        return [_text(item) for item in value if _text(item)]

    if isinstance(value, str) or value is None:
        return _text(value)

    return value


def compare_pdf_plan_fields(
    legacy_plan: Mapping[str, Any],
    candidate_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Compara somente campos renderizados e retorna nomes, nunca conteúdos."""

    equal_fields: list[str] = []
    divergent_fields: list[str] = []

    for field in PDF_PLAN_FIELDS:
        legacy_value = _normalise_pdf_value(field, legacy_plan.get(field))
        candidate_value = _normalise_pdf_value(field, candidate_plan.get(field))
        if legacy_value == candidate_value:
            equal_fields.append(field)
        else:
            divergent_fields.append(field)

    return {
        "fields_total": len(PDF_PLAN_FIELDS),
        "equal_fields": equal_fields,
        "divergent_fields": divergent_fields,
        "equal_count": len(equal_fields),
        "divergent_count": len(divergent_fields),
        "parity": not divergent_fields,
    }


async def build_plano_pdf_shadow(
    db,
    plano_id: str,
    *,
    context_builder: Optional[ContextBuilder] = None,
    projector: Optional[Projector] = None,
) -> dict[str, Any]:
    """Calcula diagnóstico 6.5A sem gerar PDF e sem qualquer persistência."""

    legacy_plan = await db.planos_aee.find_one(
        {"id": str(plano_id)},
        {"_id": 0},
    )

    base = {
        "phase": "6.5A",
        "mode": "shadow_read_only",
        "legacy_plano_id": str(plano_id),
        "status": "error",
        "effective_source": None,
        "effective_version": None,
        "fields_total": len(PDF_PLAN_FIELDS),
        "equal_count": 0,
        "divergent_count": 0,
        "divergent_fields": [],
        "parity": None,
        "blockers": [],
        "error": None,
    }

    if not isinstance(legacy_plan, Mapping):
        base["error"] = {
            "code": "AEE_V2_PLANO_PDF_SHADOW_LEGACY_NOT_FOUND",
            "message": "Plano AEE legado não encontrado para o diagnóstico do PDF.",
        }
        return base

    build_context = context_builder or build_plano_pdf_effective_context
    project = projector or project_effective_pdf_plan

    try:
        context = await build_context(db, str(plano_id))
        base["effective_source"] = context.get("effective_source")
        base["effective_version"] = context.get("effective_version")

        candidate_plan, projection = project(legacy_plan, context)
        blockers = list(projection.get("blockers") or [])
        base["blockers"] = blockers

        if projection.get("status") == "blocked":
            base["status"] = "blocked"
            return base

        if not isinstance(candidate_plan, Mapping):
            base["error"] = {
                "code": "AEE_V2_PLANO_PDF_SHADOW_CANDIDATE_INVALID",
                "message": "Projeção candidata do PDF possui formato inválido.",
            }
            return base

        comparison = compare_pdf_plan_fields(legacy_plan, candidate_plan)
        base.update(
            {
                "status": "parity" if comparison["parity"] else "divergent",
                "fields_total": comparison["fields_total"],
                "equal_count": comparison["equal_count"],
                "divergent_count": comparison["divergent_count"],
                "divergent_fields": comparison["divergent_fields"],
                "parity": comparison["parity"],
            }
        )
        return base
    except Exception:
        logger.exception(
            "AEE v2 plano PDF 6.5A: falha inesperada no diagnóstico do plano %s",
            plano_id,
        )
        base["error"] = {
            "code": "AEE_V2_PLANO_PDF_SHADOW_ERROR",
            "message": "Falha inesperada ao calcular o Shadow Mode do PDF individual.",
        }
        return base


def _log_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    # Não logar valores dos campos pedagógicos; apenas nomes divergentes.
    payload = {
        key: diagnostic.get(key)
        for key in (
            "phase",
            "mode",
            "legacy_plano_id",
            "status",
            "effective_source",
            "effective_version",
            "fields_total",
            "equal_count",
            "divergent_count",
            "divergent_fields",
            "parity",
            "blockers",
            "error",
        )
    }
    level = logging.WARNING if diagnostic.get("error") or diagnostic.get("status") in {
        "blocked",
        "divergent",
    } else logging.INFO
    logger.log(
        level,
        "AEE_V2_PLANO_PDF_SHADOW %s",
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
    )


def install_aee_v2_plano_pdf_shadow(
    base_router,
    db,
    *,
    diagnostics_builder: Optional[DiagnosticsBuilder] = None,
):
    """Envolve somente o GET individual e preserva exatamente seu PDF legado."""

    if getattr(base_router, "_aee_v2_plano_pdf_shadow_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/planos/{plano_id}/pdf", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)
    builder = diagnostics_builder or build_plano_pdf_shadow

    @wraps(original_endpoint)
    async def shadow_pdf_endpoint(*args, **kwargs):
        # Regra central da 6.5A: o PDF legado é produzido e devolvido sem troca.
        response = await original_endpoint(*args, **kwargs)

        try:
            bound = signature.bind_partial(*args, **kwargs)
            plano_id = bound.arguments.get("plano_id")
            if plano_id is None:
                raise RuntimeError("plano_id indisponível no Shadow Mode 6.5A")
            diagnostic = await builder(db, str(plano_id))
            _log_diagnostic(diagnostic)
        except Exception:
            logger.exception(
                "AEE v2 plano PDF 6.5A: diagnóstico falhou após gerar PDF legado"
            )

        return response

    target.endpoint = shadow_pdf_endpoint
    target.dependant.call = shadow_pdf_endpoint
    setattr(base_router, "_aee_v2_plano_pdf_shadow_installed", True)
    return base_router


def install_aee_v2_plano_pdf_shadow_setup(aee_module):
    """Instala a 6.5A no setup sem editar o router AEE bloqueado."""

    if getattr(aee_module, "_aee_v2_plano_pdf_shadow_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plano_pdf_shadow(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plano_pdf_shadow_setup_installed = True
