"""Read model institucional de Conteúdo para relatórios e KPIs.

Fundação de shadow para o cutover dos consumidores que ainda leem
``learning_objects`` diretamente. Esta camada é deliberadamente READ-ONLY e não
altera nenhum consumidor operacional nesta fase.

Princípios:
- ``content_entries`` é a fonte canônica de novas escritas;
- ``learning_objects`` permanece apenas como histórico/fallback compatível;
- o corte legado→canônico NÃO é inferido de ``diary_settings.enabled``;
- os escopos de corte são entrada explícita e devem vir do resolver canônico S2;
- após o corte de um escopo, ``learning_objects`` posterior ao ``valid_from`` não
  entra na projeção;
- no histórico sobreposto, o canônico prevalece sobre o legado pela mesma chave
  semântica usada pelo ``content_history_bridge``;
- o tenant é ancorado por ``classes`` e qualquer tenant explicitamente divergente
  em um registro histórico é rejeitado da projeção.

Nenhuma função deste módulo executa insert/update/replace/delete/bulk_write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional


class ContentReportingProjectionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _component_id(item: Mapping[str, Any]) -> str:
    return _norm(item.get("component_id") or item.get("course_id"))


def _tenant_compatible(item: Mapping[str, Any], tenant_id: str) -> bool:
    """Ausência histórica é tolerada só depois de a turma ancorar o tenant."""
    item_tenant = _norm(item.get("mantenedora_id"))
    return not item_tenant or item_tenant == tenant_id


def _semantic_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(item.get("class_id")),
        _component_id(item),
        _norm(item.get("teacher_id") or item.get("recorded_by")),
        _norm(item.get("date"))[:10],
    )


def _number_of_classes(item: Mapping[str, Any]) -> float:
    value = item.get("number_of_classes")
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _month_key(item: Mapping[str, Any]) -> str:
    raw = _norm(item.get("date"))[:10]
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return "UNKNOWN"
    return parsed.strftime("%Y-%m")


def _delay_days(item: Mapping[str, Any]) -> Optional[int]:
    """Replica a semântica atual do PMPI: data criada - data da aula, >= 0."""
    raw_date = _norm(item.get("date"))[:10]
    created = item.get("created_at")
    if not raw_date or created in (None, ""):
        return None
    try:
        lesson = datetime.fromisoformat(raw_date)
        if isinstance(created, datetime):
            created_dt = created
        else:
            created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        if created_dt.tzinfo:
            created_dt = created_dt.replace(tzinfo=None)
        delta = (created_dt - lesson).days
    except (TypeError, ValueError):
        return None
    return delta if delta >= 0 else None


def summarize_reporting_items(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Agrega métricas puras usadas pelo executor S3, sem I/O ou side effects."""
    rows = [dict(item) for item in items]
    monthly_records: dict[str, int] = {}
    monthly_classes: dict[str, float] = {}
    classes_sum = 0.0
    delay_values: list[int] = []
    delay_incomparable = 0

    for item in rows:
        month = _month_key(item)
        monthly_records[month] = monthly_records.get(month, 0) + 1
        classes = _number_of_classes(item)
        classes_sum += classes
        monthly_classes[month] = monthly_classes.get(month, 0.0) + classes
        delay = _delay_days(item)
        if delay is None:
            delay_incomparable += 1
        else:
            delay_values.append(delay)

    def _clean_number(value: float) -> int | float:
        return int(value) if value.is_integer() else value

    clean_monthly_classes = {
        key: _clean_number(value)
        for key, value in sorted(monthly_classes.items())
    }
    avg_delay = None
    if delay_values:
        avg_delay = round(sum(delay_values) / len(delay_values), 4)

    return {
        "record_count": len(rows),
        "number_of_classes_sum": _clean_number(classes_sum),
        "monthly_record_count": dict(sorted(monthly_records.items())),
        "monthly_number_of_classes_sum": clean_monthly_classes,
        "average_delay_days": avg_delay,
        "delay_sample_count": len(delay_values),
        "delay_incomparable_count": delay_incomparable,
        "delay_fully_comparable": delay_incomparable == 0,
    }


@dataclass(frozen=True)
class ContentReportingCutoverScope:
    """Escopo de corte já resolvido/validado por uma camada canônica externa."""

    class_id: str
    valid_from: str
    component_id: Optional[str] = None

    def normalized(self) -> "ContentReportingCutoverScope":
        class_id = _norm(self.class_id)
        component_id = _norm(self.component_id) or None
        valid_from = _norm(self.valid_from)[:10]
        if not class_id:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_CLASS_REQUIRED",
                "Escopo de reporting exige class_id.",
            )
        try:
            date.fromisoformat(valid_from)
        except ValueError as exc:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_VALID_FROM_INVALID",
                "Escopo de reporting exige valid_from ISO YYYY-MM-DD.",
            ) from exc
        return ContentReportingCutoverScope(
            class_id=class_id,
            component_id=component_id,
            valid_from=valid_from,
        )


def normalize_cutover_scopes(
    scopes: Iterable[ContentReportingCutoverScope],
) -> dict[tuple[str, Optional[str]], str]:
    """Normaliza cortes e falha fechado em escopos contraditórios."""
    result: dict[tuple[str, Optional[str]], str] = {}
    for raw in scopes:
        scope = raw.normalized()
        key = (scope.class_id, scope.component_id)
        current = result.get(key)
        if current and current != scope.valid_from:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_CUTOVER_AMBIGUOUS",
                "Há mais de uma data de corte para o mesmo escopo de conteúdo.",
            )
        result[key] = scope.valid_from
    return result


def _cutover_for(
    item: Mapping[str, Any],
    cutovers: Mapping[tuple[str, Optional[str]], str],
) -> Optional[str]:
    class_id = _norm(item.get("class_id"))
    component_id = _component_id(item)
    if not class_id:
        return None
    exact = cutovers.get((class_id, component_id or None))
    if exact:
        return exact
    return cutovers.get((class_id, None))


def _canonical_public(item: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out.pop("_id", None)
    component_id = _component_id(out)
    out["component_id"] = component_id or None
    out["course_id"] = component_id or None
    out["source"] = "content_entries"
    out["legacy"] = False
    return out


def _legacy_public(item: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out.pop("_id", None)
    component_id = _component_id(out)
    out["component_id"] = component_id or None
    out["course_id"] = component_id or None
    out["source"] = "learning_objects"
    out["legacy"] = True
    out["read_only"] = True
    return out


def merge_reporting_content(
    canonical_items: Iterable[Mapping[str, Any]],
    legacy_items: Iterable[Mapping[str, Any]],
    *,
    tenant_id: str,
    cutover_scopes: Iterable[ContentReportingCutoverScope] = (),
) -> dict[str, Any]:
    """Compõe uma projeção única sem alterar origem alguma."""
    tenant = _norm(tenant_id)
    if not tenant:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_TENANT_REQUIRED",
            "A projeção institucional exige mantenedora_id explícito.",
        )

    cutovers = normalize_cutover_scopes(cutover_scopes)
    canonical: list[dict[str, Any]] = []
    rejected_tenant = 0
    for raw in canonical_items:
        if not _tenant_compatible(raw, tenant):
            rejected_tenant += 1
            continue
        canonical.append(_canonical_public(raw))

    canonical_keys = {_semantic_key(item) for item in canonical}
    legacy_kept: list[dict[str, Any]] = []
    excluded_post_cutover = 0
    duplicate_suppressed = 0
    legacy_seen = 0

    for raw in legacy_items:
        legacy_seen += 1
        if not _tenant_compatible(raw, tenant):
            rejected_tenant += 1
            continue
        item = _legacy_public(raw)
        cutover = _cutover_for(item, cutovers)
        item_date = _norm(item.get("date"))[:10]
        if cutover and item_date and item_date > cutover:
            excluded_post_cutover += 1
            continue
        if _semantic_key(item) in canonical_keys:
            duplicate_suppressed += 1
            continue
        legacy_kept.append(item)

    merged = [*canonical, *legacy_kept]
    merged.sort(
        key=lambda item: (
            item.get("aula_numero") is None,
            item.get("aula_numero") if item.get("aula_numero") is not None else 0,
        )
    )
    merged.sort(key=lambda item: _norm(item.get("date")), reverse=True)

    return {
        "items": merged,
        "total": len(merged),
        "shadow": {
            "canonical_count": len(canonical),
            "legacy_input_count": legacy_seen,
            "legacy_kept_count": len(legacy_kept),
            "legacy_excluded_post_cutover": excluded_post_cutover,
            "legacy_duplicate_suppressed": duplicate_suppressed,
            "tenant_mismatch_rejected": rejected_tenant,
            "cutover_scope_count": len(cutovers),
        },
    }


def _iso_date(value: Optional[str], *, code: str, label: str) -> Optional[str]:
    if not value:
        return None
    normalized = _norm(value)[:10]
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ContentReportingProjectionError(code, f"{label} deve usar ISO YYYY-MM-DD.") from exc
    return normalized


def _date_filter(start_date: Optional[str], end_date: Optional[str]) -> Optional[dict[str, str]]:
    start = _iso_date(
        start_date,
        code="CONTENT_REPORTING_START_DATE_INVALID",
        label="start_date",
    )
    end = _iso_date(
        end_date,
        code="CONTENT_REPORTING_END_DATE_INVALID",
        label="end_date",
    )
    if start and end and start > end:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_DATE_RANGE_INVALID",
            "start_date não pode ser posterior a end_date.",
        )
    if not start and not end:
        return None
    result: dict[str, str] = {}
    if start:
        result["$gte"] = start
    if end:
        result["$lte"] = end
    return result


def _empty_metrics() -> dict[str, Any]:
    return summarize_reporting_items([])


async def list_reporting_content_shadow(
    db,
    *,
    mantenedora_id: str,
    academic_year: int,
    cutover_scopes: Iterable[ContentReportingCutoverScope] = (),
    class_ids: Optional[Iterable[str]] = None,
    component_ids: Optional[Iterable[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Carrega as duas fontes e aplica o merge read-only para observação."""
    tenant = _norm(mantenedora_id)
    if not tenant:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_TENANT_REQUIRED",
            "A projeção institucional exige mantenedora_id explícito.",
        )
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_YEAR_INVALID",
            "A projeção institucional exige academic_year válido.",
        ) from exc

    scopes = list(cutover_scopes)
    normalized_cutovers = normalize_cutover_scopes(scopes)
    requested_classes = {_norm(value) for value in (class_ids or []) if _norm(value)}
    year_filter = {"$in": [year, str(year)]}
    class_query: dict[str, Any] = {
        "mantenedora_id": tenant,
        "academic_year": year_filter,
    }
    if requested_classes:
        class_query["id"] = {"$in": sorted(requested_classes)}
    class_docs = await db.classes.find(
        class_query, {"_id": 0, "id": 1, "mantenedora_id": 1, "academic_year": 1}
    ).to_list(5000)
    allowed_classes = {_norm(doc.get("id")) for doc in class_docs if _norm(doc.get("id"))}
    if requested_classes and allowed_classes != requested_classes:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_CLASS_OUT_OF_SCOPE",
            "Uma ou mais turmas não pertencem à mantenedora/ano consultados.",
        )

    cutover_classes = {class_id for class_id, _component in normalized_cutovers}
    if not cutover_classes.issubset(allowed_classes):
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_CUTOVER_OUT_OF_SCOPE",
            "Há escopo de corte fora das turmas autorizadas para o relatório.",
        )

    components = {_norm(value) for value in (component_ids or []) if _norm(value)}
    normalized_start = _iso_date(
        start_date,
        code="CONTENT_REPORTING_START_DATE_INVALID",
        label="start_date",
    )
    normalized_end = _iso_date(
        end_date,
        code="CONTENT_REPORTING_END_DATE_INVALID",
        label="end_date",
    )
    date_filter = _date_filter(start_date, end_date)
    scope_payload = {
        "mantenedora_id": tenant,
        "academic_year": year,
        "class_ids": sorted(allowed_classes),
        "component_ids": sorted(components),
        "start_date": normalized_start,
        "end_date": normalized_end,
    }

    if not allowed_classes:
        empty = _empty_metrics()
        return {
            "items": [],
            "total": 0,
            "shadow": {
                "canonical_count": 0,
                "legacy_input_count": 0,
                "legacy_kept_count": 0,
                "legacy_excluded_post_cutover": 0,
                "legacy_duplicate_suppressed": 0,
                "tenant_mismatch_rejected": 0,
                "cutover_scope_count": len(normalized_cutovers),
            },
            "source_metrics": {
                "legacy": dict(empty),
                "canonical": dict(empty),
                "projected": dict(empty),
            },
            "scope": scope_payload,
        }

    canonical_query: dict[str, Any] = {
        "mantenedora_id": tenant,
        "academic_year": year_filter,
        "class_id": {"$in": sorted(allowed_classes)},
        "deleted": {"$ne": True},
    }
    if components:
        canonical_query["$or"] = [
            {"component_id": {"$in": sorted(components)}},
            {"course_id": {"$in": sorted(components)}},
        ]
    if date_filter:
        canonical_query["date"] = date_filter

    legacy_query: dict[str, Any] = {
        "academic_year": year_filter,
        "class_id": {"$in": sorted(allowed_classes)},
    }
    if components:
        legacy_query["course_id"] = {"$in": sorted(components)}
    if date_filter:
        legacy_query["date"] = date_filter

    canonical = await db.content_entries.find(canonical_query, {"_id": 0}).to_list(50000)
    legacy = await db.learning_objects.find(legacy_query, {"_id": 0}).to_list(50000)
    result = merge_reporting_content(
        canonical,
        legacy,
        tenant_id=tenant,
        cutover_scopes=scopes,
    )
    result["source_metrics"] = {
        "legacy": summarize_reporting_items(legacy),
        "canonical": summarize_reporting_items(canonical),
        "projected": summarize_reporting_items(result["items"]),
    }
    result["scope"] = scope_payload
    return result
