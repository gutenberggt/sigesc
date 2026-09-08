#!/usr/bin/env python3
"""S4 — Shadow real, read-only, do Reporting de Conteúdo.

Executa S3 contra dados reais por mantenedora/ano sem alterar consumidores,
HTTP, runtime ou MongoDB. O artefato público é sanitizado: não emite IDs
brutos, nomes, estudantes, texto pedagógico ou valores de frequência/notas.

Boundary:
- MongoDB somente leitura;
- content_entries/learning_objects usam projeção estrutural mínima;
- nenhum HTTP/login;
- nenhum dado de estudante/matrícula;
- nenhum texto pedagógico;
- nenhum ID técnico bruto no artefato público;
- nenhum cutover automático.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
import os
import re
from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorClient

from services.content_reporting_cutover_resolver import (
    ContentReportingCutoverResolutionError,
    resolve_content_reporting_cutover_scopes,
)
from services.content_reporting_parity import execute_content_reporting_parity


SCHEMA = "CONTENT_REPORTING_SHADOW_S4_V1"
CONSUMERS = (
    "DIARY_DASHBOARD_CONTENT",
    "MONTHLY_REPORT",
    "PMPI_LESSONS",
    "PMPI_WORKLOAD",
    "PMPI_DELAY",
    "ANALYTICS_CONTENT",
)
BLOCKING_CLASSIFICATIONS = {"UNEXPECTED_DIFFERENCE", "SCOPE_ERROR", "ERROR"}
SAMPLE_LIMIT_PER_TENANT = 20

STRUCTURAL_CONTENT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "mantenedora_id": 1,
    "academic_year": 1,
    "class_id": 1,
    "component_id": 1,
    "course_id": 1,
    "teacher_id": 1,
    "recorded_by": 1,
    "date": 1,
    "number_of_classes": 1,
    "created_at": 1,
    "aula_numero": 1,
    "deleted": 1,
}


class StructuralCollection:
    """Força projeção estrutural mínima em coleções com texto pedagógico."""

    def __init__(self, inner):
        self._inner = inner

    def find(self, query, _projection=None):
        return self._inner.find(query, STRUCTURAL_CONTENT_PROJECTION)


class ReadOnlyDbView:
    def __init__(self, inner):
        self._inner = inner
        self.content_entries = StructuralCollection(inner.content_entries)
        self.learning_objects = StructuralCollection(inner.learning_objects)
        self.classes = inner.classes
        self.teacher_class_assignments = inner.teacher_class_assignments


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _fp(value: Any) -> str | None:
    raw = _norm(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _full_sha(value: Any) -> str:
    raw = _norm(value).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", raw):
        raise RuntimeError("CONTENT_SHADOW_S4_CODE_SHA_INVALID")
    return raw


def _iso_day(value: Any, *, label: str) -> str:
    raw = _norm(value)[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise RuntimeError(f"CONTENT_SHADOW_S4_{label}_INVALID") from exc


def _generated_at(value: Any) -> str:
    raw = _norm(value)
    if not raw:
        raise RuntimeError("CONTENT_SHADOW_S4_GENERATED_AT_REQUIRED")
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("CONTENT_SHADOW_S4_GENERATED_AT_INVALID") from exc
    return raw


def _windows(reference_date: str) -> dict[str, dict[str, str]]:
    ref = date.fromisoformat(reference_date)
    ytd = f"{ref.year:04d}-01-01"
    month = ref.replace(day=1).isoformat()
    rolling_30 = (ref - timedelta(days=29)).isoformat()
    return {
        "DIARY_DASHBOARD_CONTENT": {"start_date": ytd, "end_date": reference_date},
        "MONTHLY_REPORT": {"start_date": month, "end_date": reference_date},
        "PMPI_LESSONS": {"start_date": rolling_30, "end_date": reference_date},
        "PMPI_WORKLOAD": {"start_date": ytd, "end_date": reference_date},
        "PMPI_DELAY": {"start_date": rolling_30, "end_date": reference_date},
        "ANALYTICS_CONTENT": {"start_date": ytd, "end_date": reference_date},
    }


def _sanitize_metric(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metric": row.get("metric"),
        "legacy": row.get("legacy"),
        "projected": row.get("projected"),
        "delta": row.get("delta"),
        "classification": row.get("classification"),
        "explanation": row.get("explanation"),
        "reconciliation": dict(row.get("reconciliation") or {}),
    }


def _sanitize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    scope = report.get("scope") or {}
    filters = report.get("filters") or {}
    cutover = report.get("cutover") or {}
    sanitized_cutovers = []
    for item in cutover.get("scopes") or []:
        sanitized_cutovers.append(
            {
                "class_fp": _fp(item.get("class_id")),
                "component_fp": _fp(item.get("component_id")),
                "valid_from": item.get("valid_from"),
            }
        )
    return {
        "consumer": report.get("consumer"),
        "code_sha": report.get("code_sha"),
        "generated_at": report.get("generated_at"),
        "report_sha256": report.get("report_sha256"),
        "tenant_fp": _fp(scope.get("mantenedora_id")),
        "scope": {
            "academic_year": scope.get("academic_year"),
            "class_count": len(scope.get("class_ids") or []),
            "component_filter_count": len(scope.get("component_ids") or []),
            "start_date": scope.get("start_date"),
            "end_date": scope.get("end_date"),
            "reference_date": filters.get("reference_date"),
        },
        "cutover": {
            "scope_count": cutover.get("scope_count", 0),
            "sha256": cutover.get("sha256"),
            "scopes": sanitized_cutovers,
        },
        "metrics": [_sanitize_metric(row) for row in report.get("metrics") or []],
        "classifications": list(report.get("classifications") or []),
        "shadow": dict(report.get("shadow") or {}),
        "resolver_diagnostics": dict(report.get("resolver_diagnostics") or {}),
        "errors": [
            {
                "code": err.get("code"),
                "message": err.get("message"),
                "classification": err.get("classification"),
            }
            for err in report.get("errors") or []
        ],
    }


def _classification_counts(reports: list[Mapping[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for report in reports:
        metrics = report.get("metrics") or []
        if metrics:
            for metric in metrics:
                classification = _norm(metric.get("classification"))
                if classification:
                    counts[classification] += 1
        else:
            for classification in report.get("classifications") or []:
                if _norm(classification):
                    counts[_norm(classification)] += 1
    return counts


def _tenant_mismatch_total(reports: list[Mapping[str, Any]]) -> int:
    return sum(int((report.get("shadow") or {}).get("tenant_mismatch_rejected") or 0) for report in reports)


async def _tenant_ids(db, *, academic_year: int) -> list[str]:
    values = await db.classes.distinct(
        "mantenedora_id",
        {"academic_year": {"$in": [academic_year, str(academic_year)]}},
    )
    return sorted({_norm(value) for value in values if _norm(value)})


async def _aggregate_reports(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    reference_date: str,
    generated_at: str,
    code_sha: str,
) -> list[dict[str, Any]]:
    windows = _windows(reference_date)
    reports = []
    for consumer in CONSUMERS:
        window = windows[consumer]
        report = await execute_content_reporting_parity(
            db,
            consumer=consumer,
            mantenedora_id=tenant_id,
            academic_year=academic_year,
            reference_date=reference_date,
            generated_at=generated_at,
            code_sha=code_sha,
            start_date=window["start_date"],
            end_date=window["end_date"],
        )
        reports.append(_sanitize_report(report))
    return reports


async def _critical_samples(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    reference_date: str,
    generated_at: str,
    code_sha: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        resolution = await resolve_content_reporting_cutover_scopes(
            db,
            mantenedora_id=tenant_id,
            academic_year=academic_year,
            reference_date=reference_date,
        )
    except ContentReportingCutoverResolutionError as exc:
        return [], {"error": exc.code, "classification": "SCOPE_ERROR"}

    scopes = list(resolution.scopes)[:SAMPLE_LIMIT_PER_TENANT]
    samples = []
    for scope in scopes:
        report = await execute_content_reporting_parity(
            db,
            consumer="DIARY_DASHBOARD_CONTENT",
            mantenedora_id=tenant_id,
            academic_year=academic_year,
            reference_date=reference_date,
            generated_at=generated_at,
            code_sha=code_sha,
            class_ids=[scope.class_id],
            component_ids=[scope.component_id] if scope.component_id else None,
            start_date=f"{academic_year:04d}-01-01",
            end_date=reference_date,
        )
        sanitized = _sanitize_report(report)
        sanitized["sample_scope"] = {
            "class_fp": _fp(scope.class_id),
            "component_fp": _fp(scope.component_id),
            "valid_from": scope.valid_from,
        }
        samples.append(sanitized)
    return samples, {
        "available_cutover_scopes": len(resolution.scopes),
        "sampled_cutover_scopes": len(scopes),
        "resolver_diagnostics": dict(resolution.diagnostics),
    }


async def run_live_shadow() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise RuntimeError("CONTENT_SHADOW_S4_MONGO_URL_MISSING")

    try:
        academic_year = int(os.environ.get("CONTENT_SHADOW_S4_ACADEMIC_YEAR", "2026"))
    except ValueError as exc:
        raise RuntimeError("CONTENT_SHADOW_S4_ACADEMIC_YEAR_INVALID") from exc
    reference_date = _iso_day(
        os.environ.get("CONTENT_SHADOW_S4_REFERENCE_DATE", ""),
        label="REFERENCE_DATE",
    )
    if int(reference_date[:4]) != academic_year:
        raise RuntimeError("CONTENT_SHADOW_S4_REFERENCE_YEAR_MISMATCH")
    code_sha = _full_sha(os.environ.get("CONTENT_SHADOW_S4_CODE_SHA", ""))
    generated_at = _generated_at(os.environ.get("CONTENT_SHADOW_S4_GENERATED_AT", ""))

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
    real_db = client[db_name]
    db = ReadOnlyDbView(real_db)
    try:
        tenants = await _tenant_ids(real_db, academic_year=academic_year)
        if not tenants:
            raise RuntimeError("CONTENT_SHADOW_S4_NO_TENANTS_FOR_YEAR")

        tenant_results = []
        all_reports: list[Mapping[str, Any]] = []
        sample_preflight_errors = 0
        for tenant_id in tenants:
            aggregate = await _aggregate_reports(
                db,
                tenant_id=tenant_id,
                academic_year=academic_year,
                reference_date=reference_date,
                generated_at=generated_at,
                code_sha=code_sha,
            )
            samples, sample_meta = await _critical_samples(
                db,
                tenant_id=tenant_id,
                academic_year=academic_year,
                reference_date=reference_date,
                generated_at=generated_at,
                code_sha=code_sha,
            )
            if sample_meta.get("classification") == "SCOPE_ERROR":
                sample_preflight_errors += 1
            tenant_reports = [*aggregate, *samples]
            counts = _classification_counts(tenant_reports)
            all_reports.extend(tenant_reports)
            tenant_results.append(
                {
                    "tenant_fp": _fp(tenant_id),
                    "aggregate_reports": aggregate,
                    "critical_samples": samples,
                    "sample_meta": sample_meta,
                    "classification_counts": dict(sorted(counts.items())),
                    "tenant_mismatch_rejected": _tenant_mismatch_total(tenant_reports),
                }
            )

        counts = _classification_counts(list(all_reports))
        tenant_mismatch = _tenant_mismatch_total(list(all_reports))
        blockers = {
            key: int(counts.get(key, 0))
            for key in sorted(BLOCKING_CLASSIFICATIONS)
        }
        gate_pass = (
            all(value == 0 for value in blockers.values())
            and tenant_mismatch == 0
            and sample_preflight_errors == 0
        )

        return {
            "schema": SCHEMA,
            "status": "PASS" if gate_pass else "BLOCKED",
            "classification": (
                "S4_CLEAR_FOR_S5_CONSIDERATION"
                if gate_pass
                else "S4_BLOCKED_REQUIRES_REVIEW"
            ),
            "generated_at": generated_at,
            "code_sha": code_sha,
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_count": len(tenants),
            "classification_counts": dict(sorted(counts.items())),
            "blocking_counts": blockers,
            "tenant_mismatch_rejected": tenant_mismatch,
            "sample_preflight_errors": sample_preflight_errors,
            "tenants": tenant_results,
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "login_endpoint_used": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "grade_values_read": False,
            "attendance_values_read": False,
            "pedagogical_text_read": False,
            "technical_ids_emitted": False,
            "technical_id_fingerprints_emitted": True,
            "automatic_cutover_authorized": False,
            "s5_authorized_by_collector": False,
        }
    finally:
        client.close()


def main() -> None:
    payload = asyncio.run(run_live_shadow())
    print(
        "CONTENT_SHADOW_S4_PUBLIC_JSON="
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
