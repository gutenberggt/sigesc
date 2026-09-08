"""S5.3 — fatos canônicos de Conteúdo para KPIs PMPI.

Substitui somente a fonte dos KPIs dependentes de conteúdo:
- aulas lançadas (contagem de registros na janela);
- atraso médio (somente quando toda a proveniência é comparável);
- carga horária executada (soma de ``number_of_classes`` no ano).

Frequência, notas, thresholds e regras do PMPI permanecem fora deste módulo.
A leitura é estritamente read-only e passa pelo boundary estrutural mínimo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from services.content_reporting_cutover_resolver import resolve_content_reporting_cutover_scopes
from services.content_reporting_projection import (
    list_reporting_content_shadow,
    summarize_reporting_items,
)
from services.content_reporting_structural_db import structural_reporting_db


class ContentReportingPmpiError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_year(value: Any) -> Optional[int]:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2200 else None


async def _resolve_tenant_for_school(db, *, school_id: str, tenant_id: Optional[str]) -> str:
    school = _norm(school_id)
    if not school:
        raise ContentReportingPmpiError(
            "CONTENT_REPORTING_PMPI_SCHOOL_REQUIRED",
            "school_id é obrigatório para o PMPI.",
        )

    explicit = _norm(tenant_id)
    if explicit:
        doc = await db.schools.find_one(
            {"id": school, "mantenedora_id": explicit},
            {"_id": 0, "id": 1, "mantenedora_id": 1},
        )
        if not doc:
            raise ContentReportingPmpiError(
                "CONTENT_REPORTING_PMPI_SCHOOL_OUT_OF_SCOPE",
                "A escola não pertence à mantenedora informada.",
            )
        return explicit

    docs = await db.schools.find(
        {"id": school},
        {"_id": 0, "mantenedora_id": 1},
    ).to_list(3)
    tenants = {_norm(doc.get("mantenedora_id")) for doc in docs if _norm(doc.get("mantenedora_id"))}
    if len(tenants) != 1:
        raise ContentReportingPmpiError(
            "CONTENT_REPORTING_PMPI_TENANT_AMBIGUOUS",
            "Não foi possível resolver uma única mantenedora para a escola.",
        )
    return next(iter(tenants))


async def get_pmpi_content_facts(
    db,
    *,
    school_id: str,
    days_window: int = 30,
    tenant_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Retorna fatos estruturais projetados para os três KPIs de Conteúdo."""
    current = now or datetime.now(timezone.utc)
    try:
        window_days = int(days_window)
    except (TypeError, ValueError) as exc:
        raise ContentReportingPmpiError(
            "CONTENT_REPORTING_PMPI_WINDOW_INVALID",
            "days_window deve ser inteiro positivo.",
        ) from exc
    if window_days < 1 or window_days > 366:
        raise ContentReportingPmpiError(
            "CONTENT_REPORTING_PMPI_WINDOW_INVALID",
            "days_window deve estar entre 1 e 366.",
        )

    reporting_db = structural_reporting_db(db)
    tenant = await _resolve_tenant_for_school(
        reporting_db,
        school_id=school_id,
        tenant_id=tenant_id,
    )

    class_docs = await reporting_db.classes.find(
        {
            "mantenedora_id": tenant,
            "school_id": _norm(school_id),
        },
        {"_id": 0, "id": 1, "academic_year": 1},
    ).to_list(10000)

    years = sorted(
        {year for year in (_as_year(doc.get("academic_year")) for doc in class_docs) if year is not None},
        reverse=True,
    )
    academic_year = years[0] if years else current.year
    class_ids = sorted(
        {
            _norm(doc.get("id"))
            for doc in class_docs
            if _norm(doc.get("id")) and _as_year(doc.get("academic_year")) == academic_year
        }
    )

    if not class_ids:
        return {
            "tenant_id": tenant,
            "academic_year": academic_year,
            "class_ids": [],
            "record_count_window": 0,
            "number_of_classes_sum_year": 0,
            "delay_average_days": None,
            "delay_sample_count": 0,
            "delay_fully_comparable": True,
            "delay_incomparable_count": 0,
        }

    if academic_year < current.year:
        reference_day = date(academic_year, 12, 31)
    elif academic_year > current.year:
        reference_day = date(academic_year, 1, 1)
    else:
        reference_day = current.date()

    resolution = await resolve_content_reporting_cutover_scopes(
        reporting_db,
        mantenedora_id=tenant,
        academic_year=academic_year,
        reference_date=reference_day.isoformat(),
        class_ids=class_ids,
    )

    year_start = date(academic_year, 1, 1)
    year_end = reference_day if academic_year == current.year else date(academic_year, 12, 31)
    projection = await list_reporting_content_shadow(
        reporting_db,
        mantenedora_id=tenant,
        academic_year=academic_year,
        cutover_scopes=resolution.scopes,
        class_ids=class_ids,
        start_date=year_start.isoformat(),
        end_date=year_end.isoformat(),
    )

    items = list(projection.get("items") or [])
    projected = ((projection.get("source_metrics") or {}).get("projected") or {})
    window_start = (current.date() - timedelta(days=window_days)).isoformat()
    window_end = current.date().isoformat()
    window_items = [
        item
        for item in items
        if window_start <= _norm(item.get("date"))[:10] <= window_end
    ]
    delay_metrics = summarize_reporting_items(window_items)

    return {
        "tenant_id": tenant,
        "academic_year": academic_year,
        "class_ids": class_ids,
        "record_count_window": len(window_items),
        "number_of_classes_sum_year": projected.get("number_of_classes_sum") or 0,
        "delay_average_days": delay_metrics.get("average_delay_days"),
        "delay_sample_count": int(delay_metrics.get("delay_sample_count") or 0),
        "delay_fully_comparable": bool(delay_metrics.get("delay_fully_comparable")),
        "delay_incomparable_count": int(delay_metrics.get("delay_incomparable_count") or 0),
    }
