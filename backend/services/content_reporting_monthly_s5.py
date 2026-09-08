"""S5.2 — Read adapter de Conteúdo para o Relatório Mensal Executivo.

Substitui somente a origem de ``aulas_lancadas_mes``. A métrica histórica é
contagem de registros de conteúdo por escola no mês; portanto este adaptador
preserva exatamente essa semântica usando S2 + S1.

Não altera frequência, cobertura curricular, alertas, snapshots, IA, PDFs ou
qualquer coleção. A leitura de conteúdo passa pelo boundary estrutural mínimo.
"""
from __future__ import annotations

import calendar
from typing import Any, Iterable, Mapping, Optional

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


def _pipeline_school_ids(pipeline: Iterable[Mapping[str, Any]]) -> list[str]:
    """Extrai o escopo por escola do pipeline legado conhecido do G3.

    Se o contrato do consumidor mudar, falha fechado em vez de executar uma
    agregação canônica com escopo mais amplo do que o solicitado.
    """
    schools: list[str] = []
    has_school_group = False
    for stage in pipeline:
        match = stage.get("$match") if isinstance(stage, Mapping) else None
        if isinstance(match, Mapping):
            school_match = match.get("_class.school_id")
            if isinstance(school_match, Mapping):
                values = school_match.get("$in")
                if isinstance(values, list):
                    schools = sorted({_norm(value) for value in values if _norm(value)})
        group = stage.get("$group") if isinstance(stage, Mapping) else None
        if isinstance(group, Mapping) and group.get("_id") == "$_class.school_id":
            has_school_group = True
    if not has_school_group:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_PIPELINE_UNEXPECTED",
            "O contrato de agregação de conteúdo do Relatório Mensal mudou.",
        )
    return schools


class _ProjectedMonthlyContentCursor:
    def __init__(self, db, *, tenant_id: str, year: int, month: int, pipeline):
        self._db = db
        self._tenant_id = tenant_id
        self._year = year
        self._month = month
        self._pipeline = list(pipeline or [])

    async def to_list(self, length: int = 2000):
        school_ids = _pipeline_school_ids(self._pipeline)
        if not school_ids:
            return []
        counts = await get_monthly_content_record_counts_by_school(
            self._db,
            tenant_id=self._tenant_id,
            academic_year=self._year,
            month=self._month,
            school_ids=school_ids,
        )
        rows = [
            {"_id": school_id, "n": count}
            for school_id, count in sorted(counts.items())
            if count
        ]
        return rows[: max(0, int(length))]


class _ProjectedMonthlyLearningObjects:
    """Compatibilidade local: intercepta somente o aggregate legado conhecido."""

    def __init__(self, db, *, tenant_id: str, year: int, month: int):
        self._db = db
        self._tenant_id = tenant_id
        self._year = year
        self._month = month

    def aggregate(self, pipeline):
        return _ProjectedMonthlyContentCursor(
            self._db,
            tenant_id=self._tenant_id,
            year=self._year,
            month=self._month,
            pipeline=pipeline,
        )


class MonthlyReportS5Db:
    """Proxy do DB usado somente durante a geração G3 da S5.2."""

    def __init__(self, inner, *, tenant_id: str, year: int, month: int):
        self._inner = inner
        self.learning_objects = _ProjectedMonthlyLearningObjects(
            inner,
            tenant_id=tenant_id,
            year=year,
            month=month,
        )

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def monthly_report_s5_db(db, *, tenant_id: str, year: int, month: int) -> MonthlyReportS5Db:
    tenant = _norm(tenant_id)
    if not tenant:
        raise ContentReportingMonthlyError(
            "CONTENT_REPORTING_MONTHLY_TENANT_REQUIRED",
            "Mantenedora explícita é obrigatória no Relatório Mensal.",
        )
    return MonthlyReportS5Db(db, tenant_id=tenant, year=int(year), month=int(month))


async def generate_monthly_report_s5(
    db,
    *,
    mantenedora_id: str,
    year: int,
    month: int,
    user: dict,
    force: bool = False,
) -> dict:
    """Executa o gerador G3 existente com a fonte de conteúdo cortada para S1."""
    from services import monthly_report_service as mr_svc

    tenant = _norm(mantenedora_id)
    proxy = monthly_report_s5_db(db, tenant_id=tenant, year=year, month=month)
    return await mr_svc.generate_monthly_report(
        proxy,
        mantenedora_id=tenant,
        year=year,
        month=month,
        user=user,
        force=force,
    )
