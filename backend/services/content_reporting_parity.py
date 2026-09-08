"""S3 — Executor read-only de paridade do Reporting de Conteúdo.

Compara a leitura legada atualmente usada por consumidores institucionais com a
projeção canônica S1, usando os escopos de cutover resolvidos pela S2. O módulo
não altera resposta HTTP, não persiste relatórios e não executa qualquer escrita.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Optional

from services.content_reporting_cutover_resolver import (
    ContentReportingCutoverResolutionError,
    resolve_content_reporting_cutover_scopes,
)
from services.content_reporting_projection import (
    ContentReportingProjectionError,
    ContentReportingCutoverScope,
    list_reporting_content_shadow,
)


class ContentReportingParityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


CONSUMER_METRICS: dict[str, tuple[str, ...]] = {
    "DIARY_DASHBOARD_CONTENT": ("record_count", "monthly_record_count"),
    "MONTHLY_REPORT": ("record_count", "monthly_record_count"),
    "PMPI_LESSONS": ("record_count",),
    "PMPI_WORKLOAD": ("number_of_classes_sum",),
    "PMPI_DELAY": ("average_delay_days",),
    "ANALYTICS_CONTENT": (
        "record_count",
        "number_of_classes_sum",
        "monthly_record_count",
        "monthly_number_of_classes_sum",
    ),
}

CLASSIFICATIONS = {
    "MATCH",
    "EXPECTED_CANONICAL_GAIN",
    "EXPECTED_POST_CUTOVER_LEGACY_EXCLUSION",
    "HISTORICAL_OVERLAP_SUPPRESSED",
    "PROVENANCE_INCOMPARABLE",
    "SCOPE_ERROR",
    "UNEXPECTED_DIFFERENCE",
    "ERROR",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _consumer(value: str) -> str:
    consumer = _norm(value).upper()
    if consumer not in CONSUMER_METRICS:
        raise ContentReportingParityError(
            "CONTENT_REPORTING_PARITY_CONSUMER_INVALID",
            f"Consumidor shadow não reconhecido: {consumer or '<vazio>'}.",
        )
    return consumer


def _code_sha(value: str) -> str:
    sha = _norm(value).lower()
    if not re.fullmatch(r"[0-9a-f]{7,64}", sha):
        raise ContentReportingParityError(
            "CONTENT_REPORTING_PARITY_CODE_SHA_INVALID",
            "code_sha deve ser um SHA hexadecimal explícito.",
        )
    return sha


def _generated_at(value: str) -> str:
    timestamp = _norm(value)
    if not timestamp:
        raise ContentReportingParityError(
            "CONTENT_REPORTING_PARITY_GENERATED_AT_REQUIRED",
            "generated_at explícito é obrigatório para relatório reproduzível.",
        )
    return timestamp


def _scope_payload(scopes: Iterable[ContentReportingCutoverScope]) -> list[dict[str, Any]]:
    normalized = [scope.normalized() for scope in scopes]
    return sorted(
        [
            {
                "class_id": scope.class_id,
                "component_id": scope.component_id,
                "valid_from": scope.valid_from,
            }
            for scope in normalized
        ],
        key=lambda row: (row["class_id"], row["component_id"] is None, row["component_id"] or ""),
    )


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _delta(legacy: Any, projected: Any) -> Any:
    if isinstance(legacy, Mapping) and isinstance(projected, Mapping):
        keys = sorted(set(legacy) | set(projected))
        return {
            key: (projected.get(key, 0) or 0) - (legacy.get(key, 0) or 0)
            for key in keys
        }
    if legacy is None or projected is None:
        return None
    return projected - legacy


def _equal(metric: str, legacy: Any, projected: Any) -> bool:
    if metric == "average_delay_days":
        if legacy is None and projected is None:
            return True
        if legacy is None or projected is None:
            return False
        return abs(float(projected) - float(legacy)) <= 0.01
    return legacy == projected


def _structural_classification(
    *,
    metric: str,
    legacy: Any,
    projected: Any,
    shadow: Mapping[str, Any],
    legacy_metrics: Mapping[str, Any],
    projected_metrics: Mapping[str, Any],
) -> tuple[str, str]:
    tenant_rejected = int(shadow.get("tenant_mismatch_rejected") or 0)
    canonical = int(shadow.get("canonical_count") or 0)
    excluded = int(shadow.get("legacy_excluded_post_cutover") or 0)
    duplicates = int(shadow.get("legacy_duplicate_suppressed") or 0)

    if tenant_rejected:
        return (
            "SCOPE_ERROR",
            f"{tenant_rejected} registro(s) com tenant explícito incompatível foram rejeitados.",
        )

    if metric == "average_delay_days":
        if not legacy_metrics.get("delay_fully_comparable", False) or not projected_metrics.get(
            "delay_fully_comparable", False
        ):
            return (
                "PROVENANCE_INCOMPARABLE",
                "Atraso possui registros sem date/created_at comparáveis; não há paridade segura.",
            )

    if _equal(metric, legacy, projected):
        if duplicates and canonical == duplicates and not excluded:
            return (
                "HISTORICAL_OVERLAP_SUPPRESSED",
                "O valor líquido coincide porque sobreposição histórica foi substituída pelo canônico.",
            )
        return "MATCH", "Valor legado e valor projetado são equivalentes dentro da tolerância."

    drivers = sum(bool(value) for value in (canonical, excluded, duplicates))
    scalar_delta = _delta(legacy, projected)
    delta_sign = 0
    if isinstance(scalar_delta, (int, float)):
        delta_sign = 1 if scalar_delta > 0 else -1 if scalar_delta < 0 else 0

    if canonical and not excluded and not duplicates:
        return (
            "EXPECTED_CANONICAL_GAIN",
            "A projeção contém lançamentos canônicos que a fonte legada não pode conter.",
        )
    if excluded and not canonical and not duplicates:
        return (
            "EXPECTED_POST_CUTOVER_LEGACY_EXCLUSION",
            "A projeção excluiu legado posterior ao cutover explícito.",
        )
    if duplicates and not excluded and canonical == duplicates and delta_sign <= 0:
        return (
            "HISTORICAL_OVERLAP_SUPPRESSED",
            "A diferença é compatível com sobreposição histórica suprimida pelo canônico.",
        )
    if canonical and not excluded and delta_sign > 0:
        return (
            "EXPECTED_CANONICAL_GAIN",
            "A divergência positiva é explicável por novos lançamentos canônicos.",
        )
    if excluded and delta_sign < 0:
        return (
            "EXPECTED_POST_CUTOVER_LEGACY_EXCLUSION",
            "A divergência negativa é compatível com exclusão de legado pós-cutover.",
        )
    if duplicates and drivers == 1:
        return (
            "HISTORICAL_OVERLAP_SUPPRESSED",
            "A divergência é explicável por duplicidade histórica suprimida.",
        )
    return (
        "UNEXPECTED_DIFFERENCE",
        "A divergência não é explicada de forma determinística pelos drivers shadow conhecidos.",
    )


def _metric_row(
    metric: str,
    *,
    legacy_metrics: Mapping[str, Any],
    projected_metrics: Mapping[str, Any],
    shadow: Mapping[str, Any],
) -> dict[str, Any]:
    legacy = legacy_metrics.get(metric)
    projected = projected_metrics.get(metric)
    classification, explanation = _structural_classification(
        metric=metric,
        legacy=legacy,
        projected=projected,
        shadow=shadow,
        legacy_metrics=legacy_metrics,
        projected_metrics=projected_metrics,
    )
    assert classification in CLASSIFICATIONS
    return {
        "metric": metric,
        "legacy": legacy,
        "projected": projected,
        "delta": _delta(legacy, projected),
        "classification": classification,
        "explanation": explanation,
    }


def _error_report(
    *,
    consumer: str,
    generated_at: str,
    code_sha: str,
    mantenedora_id: str,
    academic_year: int,
    filters: Mapping[str, Any],
    classification: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "code_sha": code_sha,
        "consumer": consumer,
        "scope": {
            "mantenedora_id": mantenedora_id,
            "academic_year": academic_year,
            **dict(filters),
        },
        "cutover": {"scopes": [], "scope_count": 0, "sha256": _stable_hash([])},
        "metrics": [],
        "classifications": [classification],
        "shadow": {},
        "errors": [{"code": code, "message": message, "classification": classification}],
    }
    payload["report_sha256"] = _stable_hash(payload)
    return payload


async def execute_content_reporting_parity(
    db,
    *,
    consumer: str,
    mantenedora_id: str,
    academic_year: int,
    reference_date: str,
    generated_at: str,
    code_sha: str,
    class_ids: Optional[Iterable[str]] = None,
    component_ids: Optional[Iterable[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Executa uma comparação reproduzível, sem publicar nem persistir resultado."""
    consumer_id = _consumer(consumer)
    timestamp = _generated_at(generated_at)
    sha = _code_sha(code_sha)
    tenant = _norm(mantenedora_id)
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise ContentReportingParityError(
            "CONTENT_REPORTING_PARITY_YEAR_INVALID",
            "academic_year deve ser inteiro válido.",
        ) from exc

    classes = sorted({_norm(value) for value in (class_ids or []) if _norm(value)})
    components = sorted({_norm(value) for value in (component_ids or []) if _norm(value)})
    filters = {
        "reference_date": _norm(reference_date),
        "class_ids": classes,
        "component_ids": components,
        "start_date": _norm(start_date) or None,
        "end_date": _norm(end_date) or None,
    }

    try:
        resolution = await resolve_content_reporting_cutover_scopes(
            db,
            mantenedora_id=tenant,
            academic_year=year,
            reference_date=reference_date,
            class_ids=classes or None,
        )
        scopes = list(resolution.scopes)
        if components:
            component_set = set(components)
            scopes = [
                scope
                for scope in scopes
                if scope.component_id is None or scope.component_id in component_set
            ]
        projection = await list_reporting_content_shadow(
            db,
            mantenedora_id=tenant,
            academic_year=year,
            cutover_scopes=scopes,
            class_ids=classes or None,
            component_ids=components or None,
            start_date=start_date,
            end_date=end_date,
        )
    except (ContentReportingCutoverResolutionError, ContentReportingProjectionError) as exc:
        return _error_report(
            consumer=consumer_id,
            generated_at=timestamp,
            code_sha=sha,
            mantenedora_id=tenant,
            academic_year=year,
            filters=filters,
            classification="SCOPE_ERROR",
            code=exc.code,
            message=exc.message,
        )
    except Exception as exc:  # pragma: no cover - guarda operacional, sem side effect
        return _error_report(
            consumer=consumer_id,
            generated_at=timestamp,
            code_sha=sha,
            mantenedora_id=tenant,
            academic_year=year,
            filters=filters,
            classification="ERROR",
            code="CONTENT_REPORTING_PARITY_EXECUTION_ERROR",
            message=str(exc),
        )

    source_metrics = projection.get("source_metrics") or {}
    legacy_metrics = source_metrics.get("legacy") or {}
    projected_metrics = source_metrics.get("projected") or {}
    shadow = dict(projection.get("shadow") or {})
    metrics = [
        _metric_row(
            metric,
            legacy_metrics=legacy_metrics,
            projected_metrics=projected_metrics,
            shadow=shadow,
        )
        for metric in CONSUMER_METRICS[consumer_id]
    ]
    cutover_scopes = _scope_payload(scopes)
    classifications = sorted({row["classification"] for row in metrics})

    report = {
        "schema_version": 1,
        "generated_at": timestamp,
        "code_sha": sha,
        "consumer": consumer_id,
        "scope": dict(projection.get("scope") or {}),
        "filters": filters,
        "cutover": {
            "scopes": cutover_scopes,
            "scope_count": len(cutover_scopes),
            "sha256": _stable_hash(cutover_scopes),
        },
        "metrics": metrics,
        "classifications": classifications,
        "source_metrics": {
            "legacy": legacy_metrics,
            "projected": projected_metrics,
        },
        "shadow": shadow,
        "resolver_diagnostics": dict(resolution.diagnostics),
        "errors": [],
    }
    report["report_sha256"] = _stable_hash(report)
    return report
