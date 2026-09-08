"""S5.4 — Proxy de Conteúdo para Analytics.

O módulo Analytics legado é grande e mistura muitos indicadores. Este proxy
substitui somente as três agregações conhecidas de ``learning_objects`` usadas
para reporting de Conteúdo:

1. ranking de escolas: soma ``number_of_classes`` por turma;
2. desempenho docente/regência: conjunto de datas por turma;
3. desempenho docente/por componente: conjunto de datas por turma+componente.

Todos os demais acessos ao DB são delegados sem alteração. Um pipeline de
``learning_objects.aggregate`` fora desses contratos falha fechado.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Awaitable, Iterable, Mapping, Optional

from services.content_reporting_cutover_resolver import resolve_content_reporting_cutover_scopes
from services.content_reporting_projection import list_reporting_content_shadow
from services.content_reporting_structural_db import structural_reporting_db


class ContentReportingAnalyticsError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _year_from_match(match: Mapping[str, Any]) -> int:
    raw = match.get("academic_year")
    candidates = raw.get("$in") if isinstance(raw, Mapping) and "$in" in raw else [raw]
    years = set()
    for candidate in candidates or []:
        try:
            year = int(candidate)
        except (TypeError, ValueError):
            continue
        if 1900 <= year <= 2200:
            years.add(year)
    if len(years) != 1:
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_YEAR_AMBIGUOUS",
            "Pipeline do Analytics deve resolver exatamente um ano letivo.",
        )
    return next(iter(years))


def _class_ids_from_match(match: Mapping[str, Any]) -> list[str]:
    raw = match.get("class_id")
    values = raw.get("$in") if isinstance(raw, Mapping) and "$in" in raw else [raw]
    class_ids = sorted({_norm(value) for value in (values or []) if _norm(value)})
    if not class_ids:
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_CLASS_SCOPE_REQUIRED",
            "Pipeline do Analytics exige class_ids explícitos.",
        )
    return class_ids


def _reference_date(year: int, match: Mapping[str, Any], now: Optional[datetime] = None) -> str:
    date_filter = match.get("date")
    if isinstance(date_filter, Mapping) and _norm(date_filter.get("$lte")):
        raw = _norm(date_filter.get("$lte"))[:10]
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ContentReportingAnalyticsError(
                "CONTENT_REPORTING_ANALYTICS_END_DATE_INVALID",
                "Data final inválida no pipeline do Analytics.",
            ) from exc
        if parsed.year != year:
            raise ContentReportingAnalyticsError(
                "CONTENT_REPORTING_ANALYTICS_END_YEAR_MISMATCH",
                "Data final do pipeline deve pertencer ao ano letivo consultado.",
            )
        return parsed.isoformat()

    current = now or datetime.now(timezone.utc)
    if year < current.year:
        return date(year, 12, 31).isoformat()
    if year > current.year:
        return date(year, 1, 1).isoformat()
    return current.date().isoformat()


def _pipeline_kind(pipeline: list[Mapping[str, Any]]) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(pipeline, list) or len(pipeline) != 2:
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_PIPELINE_UNSUPPORTED",
            "Somente os três pipelines de Conteúdo homologados do Analytics são aceitos.",
        )
    match = pipeline[0].get("$match") if isinstance(pipeline[0], Mapping) else None
    group = pipeline[1].get("$group") if isinstance(pipeline[1], Mapping) else None
    if not isinstance(match, Mapping) or not isinstance(group, Mapping):
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_PIPELINE_UNSUPPORTED",
            "Pipeline de Conteúdo do Analytics fora do contrato homologado.",
        )

    if (
        group.get("_id") == "$class_id"
        and isinstance(group.get("count"), Mapping)
        and group["count"].get("$sum") == "$number_of_classes"
        and set(group) == {"_id", "count"}
    ):
        return "workload_by_class", match, group

    if (
        group.get("_id") == "$class_id"
        and isinstance(group.get("dates"), Mapping)
        and group["dates"].get("$addToSet") == "$date"
        and set(group) == {"_id", "dates"}
    ):
        return "dates_by_class", match, group

    group_id = group.get("_id")
    if (
        isinstance(group_id, Mapping)
        and group_id.get("c") == "$class_id"
        and group_id.get("k") == "$course_id"
        and isinstance(group.get("dates"), Mapping)
        and group["dates"].get("$addToSet") == "$date"
        and set(group) == {"_id", "dates"}
    ):
        return "dates_by_component", match, group

    raise ContentReportingAnalyticsError(
        "CONTENT_REPORTING_ANALYTICS_PIPELINE_UNSUPPORTED",
        "Pipeline de Conteúdo do Analytics fora dos três formatos homologados.",
    )


async def _resolve_tenant(db, *, class_ids: list[str], year: int) -> str:
    docs = await db.classes.find(
        {
            "id": {"$in": class_ids},
            "academic_year": {"$in": [year, str(year)]},
        },
        {"_id": 0, "id": 1, "mantenedora_id": 1},
    ).to_list(10000)
    found_ids = {_norm(doc.get("id")) for doc in docs if _norm(doc.get("id"))}
    if found_ids != set(class_ids):
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_CLASS_OUT_OF_SCOPE",
            "Uma ou mais turmas do pipeline não pertencem ao ano consultado.",
        )
    tenants = {_norm(doc.get("mantenedora_id")) for doc in docs if _norm(doc.get("mantenedora_id"))}
    if len(tenants) != 1:
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_TENANT_AMBIGUOUS",
            "As turmas do pipeline não resolvem uma única mantenedora.",
        )
    return next(iter(tenants))


async def execute_analytics_content_pipeline(
    db,
    pipeline: list[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Executa um dos três contratos legados sobre S1/S2 e devolve linhas compatíveis."""
    kind, match, _group = _pipeline_kind(pipeline)
    year = _year_from_match(match)
    class_ids = _class_ids_from_match(match)
    end_date = _reference_date(year, match, now=now)
    tenant = await _resolve_tenant(db, class_ids=class_ids, year=year)
    reporting_db = structural_reporting_db(db)

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
        start_date=f"{year:04d}-01-01",
        end_date=end_date,
    )
    items = list(projection.get("items") or [])

    if kind == "workload_by_class":
        totals: dict[str, float] = {}
        for item in items:
            class_id = _norm(item.get("class_id"))
            if not class_id:
                continue
            try:
                amount = float(item.get("number_of_classes") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            totals[class_id] = totals.get(class_id, 0.0) + amount
        rows = []
        for class_id in sorted(totals):
            value = totals[class_id]
            rows.append({"_id": class_id, "count": int(value) if value.is_integer() else value})
        return rows

    if kind == "dates_by_class":
        dates: dict[str, set[str]] = {}
        for item in items:
            class_id = _norm(item.get("class_id"))
            day = _norm(item.get("date"))[:10]
            if class_id and day:
                dates.setdefault(class_id, set()).add(day)
        return [
            {"_id": class_id, "dates": sorted(values)}
            for class_id, values in sorted(dates.items())
        ]

    dates_by_component: dict[tuple[str, str], set[str]] = {}
    for item in items:
        class_id = _norm(item.get("class_id"))
        component_id = _norm(item.get("component_id") or item.get("course_id"))
        day = _norm(item.get("date"))[:10]
        if class_id and component_id and day:
            dates_by_component.setdefault((class_id, component_id), set()).add(day)
    return [
        {"_id": {"c": class_id, "k": component_id}, "dates": sorted(values)}
        for (class_id, component_id), values in sorted(dates_by_component.items())
    ]


class _LazyAsyncRows:
    def __init__(self, loader: Awaitable[list[dict[str, Any]]]):
        self._loader = loader
        self._rows: Optional[list[dict[str, Any]]] = None
        self._index = 0

    async def _ensure(self) -> list[dict[str, Any]]:
        if self._rows is None:
            self._rows = list(await self._loader)
        return self._rows

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        rows = await self._ensure()
        if self._index >= len(rows):
            raise StopAsyncIteration
        row = rows[self._index]
        self._index += 1
        return dict(row)

    async def to_list(self, length: Optional[int] = None):
        rows = await self._ensure()
        if length is None:
            return [dict(row) for row in rows]
        return [dict(row) for row in rows[:length]]


class _AnalyticsLearningObjectsCollection:
    def __init__(self, db):
        self._db = db

    def aggregate(self, pipeline):
        return _LazyAsyncRows(execute_analytics_content_pipeline(self._db, pipeline))

    def __getattr__(self, name: str):
        raise ContentReportingAnalyticsError(
            "CONTENT_REPORTING_ANALYTICS_LEGACY_ACCESS_BLOCKED",
            f"Analytics não pode usar learning_objects.{name} fora do adapter S5.4.",
        )


class ContentReportingAnalyticsDb:
    def __init__(self, inner):
        self._inner = inner
        self.learning_objects = _AnalyticsLearningObjectsCollection(inner)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def __getitem__(self, name: str):
        if name == "learning_objects":
            return self.learning_objects
        return self._inner[name]


def content_reporting_analytics_db(db):
    if db is None or isinstance(db, ContentReportingAnalyticsDb):
        return db
    return ContentReportingAnalyticsDb(db)


def install_content_reporting_analytics_setup(legacy_setup):
    """Envolve somente a instalação do Analytics; demais routers mantêm o DB original."""
    def setup(db, audit_service=None, sandbox_db=None):
        return legacy_setup(
            content_reporting_analytics_db(db),
            audit_service,
            content_reporting_analytics_db(sandbox_db),
        )
    return setup
