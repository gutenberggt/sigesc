"""S5.2 — Read adapter de Conteúdo para o Relatório Mensal Executivo.

Substitui somente a origem de ``aulas_lancadas_mes``. A métrica histórica é
contagem de registros de conteúdo por escola no mês; portanto este adaptador
preserva exatamente essa semântica usando S2 + S1.

Não altera frequência, cobertura curricular, alertas, snapshots, IA, PDFs ou
qualquer coleção. A leitura de conteúdo passa pelo boundary estrutural mínimo.
"""
from __future__ import annotations

import calendar
from typing import Any, Iterable

from services.content_reporting_cutover_resolver import resolve_content_reporting_cutover_scopes
from services.content_reporting_projection import list_reporting_content_shadow
from services.content_reporting_structural_db import structural_reporting_db


class ContentReportingMonthlyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    try:
        normalized_year = int(year)
        normalized_month = int(month)
    except (TypeError, ValueError) as exc:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_PERIOD_INVALID",
            "Ano/mês inválido para o reporting mensal de conteúdo.",
        ) from exc
    if normalized_year < 1900 or normalized_year > 2200 or normalized_month < 1 or normalized_month > 12:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_PERIOD_INVALID",
            "Ano/mês inválido para o reporting mensal de conteúdo.",
        )
    last_day = calendar.monthrange(normalized_year, normalized_month)[1]
    return (
        f"{normalized_year:04d}-{normalized_month:02d}-01",
        f"{normalized_year:04d}-{normalized_month:02d}-{last_day:02d}",
    )


async def get_monthly_content_record_counts_by_school(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    month: int,
    school_ids: Iterable[str],
) -> dict[str, int]:
    """Conta registros projetados por escola, preservando semântica legada.

    A projeção é executada por escola, o que mantém o agrupamento institucional
    explícito e reduz a superfície de cada leitura sem criar inferência de tenant.
    """
    tenant = _norm(tenant_id)
    if not tenant:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_TENANT_REQUIRED",
            "Mantenedora explícita é obrigatória no Relatório Mensal.",
        )
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_YEAR_INVALID",
            "Ano letivo inválido no Relatório Mensal.",
        ) from exc

    requested_schools = sorted({_norm(value) for value in school_ids if _norm(value)})
    result = {school_id: 0 for school_id in requested_schools}
    if not requested_schools:
        return result

    start_date, end_date = _month_bounds(year, month)
    reporting_db = structural_reporting_db(db)

    class_docs = await reporting_db.classes.find(
        {
            "mantenedora_id": tenant,
            "academic_year": {"$in": [year, str(year)]},
            "school_id": {"$in": requested_schools},
        },
        {"_id": 0, "id": 1, "school_id": 1},
    ).to_list(5000)

    classes_by_school: dict[str, list[str]] = {school_id: [] for school_id in requested_schools}
    for doc in class_docs:
        school_id = _norm(doc.get("school_id"))
        class_id = _norm(doc.get("id"))
        if school_id in classes_by_school and class_id:
            classes_by_school[school_id].append(class_id)

    for school_id in requested_schools:
        class_ids = sorted(set(classes_by_school.get(school_id) or []))
        if not class_ids:
            continue

        resolution = await resolve_content_reporting_cutover_scopes(
            reporting_db,
            mantenedora_id=tenant,
            academic_year=year,
            reference_date=end_date,
            class_ids=class_ids,
        )
        projection = await list_reporting_content_shadow(
            reporting_db,
            mantenedora_id=tenant,
            academic_year=year,
            cutover_scopes=resolution.scopes,
            class_ids=class_ids,
            start_date=start_date,
            end_date=end_date,
        )
        metrics = ((projection.get("source_metrics") or {}).get("projected") or {})
        result[school_id] = int(metrics.get("record_count") or 0)

    return result
