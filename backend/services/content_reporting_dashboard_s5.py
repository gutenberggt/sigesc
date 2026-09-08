"""S5.1 — Cutover do Dashboard de Diários para o read model institucional.

Este adaptador preserva o contrato HTTP histórico do endpoint de conteúdo e
centraliza somente a troca de fonte: a projeção S1 (content_entries + legado
histórico elegível) passa a alimentar as métricas do dashboard.

Não executa escrita, backfill ou remoção de compatibilidade legada.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from services.content_reporting_cutover_resolver import resolve_content_reporting_cutover_scopes
from services.content_reporting_projection import list_reporting_content_shadow


class ContentReportingDashboardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _reference_date_for_year(academic_year: int, today: Optional[date] = None) -> str:
    """Resolve uma referência temporal sem projetar cutover futuro no ano corrente."""
    current = today or date.today()
    if academic_year < current.year:
        return date(academic_year, 12, 31).isoformat()
    if academic_year > current.year:
        return date(academic_year, 1, 1).isoformat()
    return current.isoformat()


def _empty_stats() -> dict[str, Any]:
    return {"completion_rate": 0, "total_records": 0, "by_month": []}


def _format_dashboard_stats(projected_metrics: dict[str, Any]) -> dict[str, Any]:
    total_records = int(projected_metrics.get("record_count") or 0)
    monthly_records = dict(projected_metrics.get("monthly_record_count") or {})
    monthly_classes = dict(projected_metrics.get("monthly_number_of_classes_sum") or {})

    month_names = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    by_month = []
    for key in sorted(monthly_records):
        try:
            month_num = int(str(key).split("-", 1)[1])
        except (IndexError, TypeError, ValueError):
            continue
        if month_num < 1 or month_num > 12:
            continue
        by_month.append(
            {
                "month": month_names[month_num],
                "registros": int(monthly_records.get(key) or 0),
                "aulas": monthly_classes.get(key, 0) or 0,
            }
        )

    expected_days = 200
    completion_rate = min(100, round((total_records / max(expected_days, 1)) * 100))
    return {
        "completion_rate": completion_rate,
        "total_records": total_records,
        "by_month": by_month,
    }


async def get_diary_dashboard_content_stats(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    school_id: Optional[str] = None,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> dict[str, Any]:
    """Retorna o payload histórico do dashboard usando o read model S1."""
    tenant = _norm(tenant_id)
    if not tenant:
        raise ContentReportingDashboardError(
            "CONTENT_REPORTING_DASHBOARD_TENANT_REQUIRED",
            "Escopo de mantenedora é obrigatório para o reporting de conteúdo.",
        )
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise ContentReportingDashboardError(
            "CONTENT_REPORTING_DASHBOARD_YEAR_INVALID",
            "Ano letivo inválido para o reporting de conteúdo.",
        ) from exc

    school = _norm(school_id)
    class_filter = _norm(class_id)
    component = _norm(course_id)
    requested_class_ids: Optional[list[str]] = None

    if school or class_filter:
        class_query: dict[str, Any] = {
            "mantenedora_id": tenant,
            "academic_year": {"$in": [year, str(year)]},
        }
        if school:
            class_query["school_id"] = school
        if class_filter:
            class_query["id"] = class_filter
        class_docs = await db.classes.find(class_query, {"_id": 0, "id": 1}).to_list(5000)
        requested_class_ids = sorted(
            {_norm(doc.get("id")) for doc in class_docs if _norm(doc.get("id"))}
        )
        if not requested_class_ids:
            return _empty_stats()

    ref = _norm(reference_date) or _reference_date_for_year(year)
    resolution = await resolve_content_reporting_cutover_scopes(
        db,
        mantenedora_id=tenant,
        academic_year=year,
        reference_date=ref,
        class_ids=requested_class_ids,
    )
    scopes = list(resolution.scopes)
    if component:
        scopes = [
            scope
            for scope in scopes
            if scope.component_id is None or scope.component_id == component
        ]

    projection = await list_reporting_content_shadow(
        db,
        mantenedora_id=tenant,
        academic_year=year,
        cutover_scopes=scopes,
        class_ids=requested_class_ids,
        component_ids=[component] if component else None,
        start_date=f"{year:04d}-01-01",
        end_date=f"{year:04d}-12-31",
    )
    projected_metrics = ((projection.get("source_metrics") or {}).get("projected") or {})
    return _format_dashboard_stats(projected_metrics)
