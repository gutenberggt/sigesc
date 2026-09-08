"""Domínio de continuidade histórica de Notas/Conceitos no DVD.

A prova canônica de cutover já pertence a
``services.dvd_cutover_legacy_provenance`` e é compartilhada por Frequência e
Notas. Este módulo NÃO cria uma segunda política de proveniência: apenas ancora
o contexto de Notas nessa SSoT e acrescenta as condições específicas para uma
escrita estritamente pré-cutover.

Esta camada não escreve em ``grades`` nem altera ``teacher_class_assignments``.
O ``valid_from`` persistido do DVD nunca é retrodatado.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from services.dvd_cutover_legacy_provenance import (
    resolve_validated_cutover_legacy_assignment,
)


LEGACY_HISTORY_FLAG = "legacy_grade_history_read"
LEGACY_SOURCE_FLAG = "legacy_grade_source_assignment_id"
LEGACY_YEAR_FLAG = "legacy_grade_history_academic_year"

HISTORICAL_WRITE_FLAG = "historical_grade_write"
HISTORICAL_WRITE_SOURCE = "validated_dvd_cutover_legacy_assignment"
HISTORICAL_WRITE_SOURCE_FLAG = "historical_grade_source_legacy_assignment_id"
HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG = "historical_grade_authorized_from"
HISTORICAL_WRITE_PERIOD_FLAG = "historical_grade_period"
HISTORICAL_WRITE_PERIOD_START_FLAG = "historical_grade_period_start"
HISTORICAL_WRITE_PERIOD_END_FLAG = "historical_grade_period_end"


async def safe_cutover_legacy_assignment(
    db,
    context,
    academic_year: int,
) -> Optional[dict[str, Any]]:
    """Ancora a SSoT genérica no contexto de Notas já autorizado.

    A lista de fases históricas aprovadas, a exigência de ``ACTIVATED``, a
    revalidação de ``source_legacy_assignment_id`` e a cadeia staff -> user ficam
    exclusivamente no serviço genérico compartilhado.
    """
    assignment = context.assignment
    return await resolve_validated_cutover_legacy_assignment(
        db,
        assignment,
        academic_year,
        expected_class_id=context.class_id,
        expected_component_id=context.course_id,
    )


async def decorate_context_with_legacy_history(
    db,
    context,
    academic_year: int,
):
    """Marca contexto de leitura quando a continuidade de cutover foi comprovada."""
    if context is None:
        return None

    legacy = await safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy:
        return context

    snapshot = dict(context.snapshot)
    snapshot[LEGACY_HISTORY_FLAG] = True
    snapshot[LEGACY_SOURCE_FLAG] = legacy.get("id")
    snapshot[LEGACY_YEAR_FLAG] = int(academic_year)
    return replace(context, snapshot=snapshot)


async def historical_grade_write_evidence(
    db,
    context,
    *,
    field: str,
    period_number: int,
    period: tuple[str, str],
) -> Optional[dict[str, Any]]:
    """Resolve evidência para uma escrita estritamente anterior ao cutover.

    Esta função não substitui RBAC, tenant, capability, shared owner nem escopo de
    estudante. Ela só pode ser chamada depois que o ``GradeAssignmentContext``
    vivo foi autorizado. Além disso:
    - exige propriedade pedagógica do assignment atual;
    - não usa a ponte para um intervalo de assignment inconsistente;
    - não libera período que encoste/intersecte o ``valid_from``;
    - revalida a origem legada no ano institucional do período pela SSoT
      ``resolve_validated_cutover_legacy_assignment``.
    """
    if not getattr(context.access, "is_owner", False):
        return None

    valid_from = str(context.assignment.get("valid_from") or "")[:10]
    valid_until = str(context.assignment.get("valid_until") or "")[:10] or None
    if not valid_from:
        return None
    if valid_until and valid_until < valid_from:
        return None

    start = str(period[0] or "")[:10]
    end = str(period[1] or "")[:10]
    if not start or not end or start > end:
        return None

    # Ponte estritamente retroativa. Falha causada por ``valid_until`` ou período
    # que já intersecta ``valid_from`` continua sob a regra normal do DVD.
    if end >= valid_from:
        return None

    if len(start) < 4 or len(end) < 4 or start[:4] != end[:4]:
        return None
    try:
        academic_year = int(start[:4])
    except ValueError:
        return None

    legacy = await safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy:
        return None

    return {
        HISTORICAL_WRITE_FLAG: True,
        "historical_grade_write_source": HISTORICAL_WRITE_SOURCE,
        HISTORICAL_WRITE_SOURCE_FLAG: legacy.get("id"),
        HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG: valid_from,
        HISTORICAL_WRITE_PERIOD_FLAG: int(period_number),
        HISTORICAL_WRITE_PERIOD_START_FLAG: start,
        HISTORICAL_WRITE_PERIOD_END_FLAG: end,
        LEGACY_YEAR_FLAG: academic_year,
    }
