#!/usr/bin/env python3
"""Auditoria populacional read-only da Fase AEE v2 6.6A.

Compara filtros de status legado x Fonte Efetiva sem alterar documentos, índices
ou ponteiros. Deve ser executado manualmente; não participa do request online.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
from typing import Any

from aee_v2.plan_list_effective import (
    V2_TO_LEGACY_STATUS,
    resolve_plan_list_effective_batch,
)


DEFAULT_MAX_PLANS = 2000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auditoria read-only da listagem AEE v2 6.6A")
    parser.add_argument("--academic-year", type=int, required=True)
    parser.add_argument("--school-id")
    parser.add_argument("--student-id")
    parser.add_argument("--professor-user-id")
    parser.add_argument("--max-plans", type=int, default=DEFAULT_MAX_PLANS)
    parser.add_argument(
        "--page-size",
        type=int,
        default=0,
        help="Quando >0, inclui simulação simples de quantidade de páginas por status.",
    )
    return parser


def _base_query(args: argparse.Namespace) -> dict[str, Any]:
    query: dict[str, Any] = {"academic_year": args.academic_year}
    if args.school_id:
        query["school_id"] = args.school_id
    if args.student_id:
        query["student_id"] = args.student_id
    if args.professor_user_id:
        query["$or"] = [
            {"professor_aee_id": args.professor_user_id},
            {"created_by": args.professor_user_id},
        ]
    return query


def _distribution(values) -> dict[str, int]:
    counter = Counter(str(value) for value in values if value is not None)
    return dict(sorted(counter.items()))


def _page_count(total: int, page_size: int) -> int:
    if page_size <= 0 or total <= 0:
        return 0
    return (total + page_size - 1) // page_size


def build_population_report(
    planos: list[dict[str, Any]],
    batch: dict[str, Any],
    *,
    page_size: int = 0,
) -> dict[str, Any]:
    summaries = batch.get("items") or []
    by_id = {
        str(item.get("legacy_plano_id")): item
        for item in summaries
        if isinstance(item, dict) and item.get("legacy_plano_id")
    }

    legacy_status_by_id: dict[str, Any] = {}
    effective_status_by_id: dict[str, Any] = {}
    transitions = Counter()

    for plano in planos:
        plano_id = str(plano.get("id") or "")
        if not plano_id:
            continue
        legacy_status = plano.get("status")
        summary = by_id.get(plano_id) or {}
        effective_status = summary.get("effective_legacy_status")
        legacy_status_by_id[plano_id] = legacy_status
        effective_status_by_id[plano_id] = effective_status
        if effective_status is not None:
            transitions[f"{legacy_status or 'null'}->{effective_status}"] += 1

    known_statuses = set(V2_TO_LEGACY_STATUS.values())
    known_statuses.update(value for value in legacy_status_by_id.values() if value)
    known_statuses.update(value for value in effective_status_by_id.values() if value)

    filter_compare: dict[str, Any] = {}
    for status in sorted(str(value) for value in known_statuses):
        legacy_set = {
            plano_id
            for plano_id, value in legacy_status_by_id.items()
            if value == status
        }
        effective_set = {
            plano_id
            for plano_id, value in effective_status_by_id.items()
            if value == status
        }
        entry: dict[str, Any] = {
            "legacy_total": len(legacy_set),
            "effective_total": len(effective_set),
            "total_delta": len(effective_set) - len(legacy_set),
            "false_positive_count": len(legacy_set - effective_set),
            "false_negative_count": len(effective_set - legacy_set),
        }
        if page_size > 0:
            entry["pagination"] = {
                "page_size": page_size,
                "legacy_pages": _page_count(len(legacy_set), page_size),
                "effective_pages": _page_count(len(effective_set), page_size),
            }
        filter_compare[status] = entry

    source_counts = Counter()
    integrity_codes = Counter()
    days_equal = days_divergent = heterogeneous = 0
    for item in summaries:
        if not isinstance(item, dict):
            continue
        state = item.get("management_state") or "unknown"
        source_counts[str(state)] += 1
        if item.get("days_parity") is True:
            days_equal += 1
        elif item.get("days_parity") is False:
            days_divergent += 1
        if item.get("schedule_shape") == "heterogeneous":
            heterogeneous += 1
        for field in ("integrity_error", "working_integrity_error"):
            error = item.get(field)
            if isinstance(error, dict) and error.get("code"):
                integrity_codes[str(error["code"])] += 1

    performance = batch.get("performance") or {}
    return {
        "phase": "6.6A",
        "mode": "population_audit_read_only",
        "plans_total": len(planos),
        "sources": dict(sorted(source_counts.items())),
        "legacy_status_distribution": _distribution(legacy_status_by_id.values()),
        "effective_status_distribution": _distribution(effective_status_by_id.values()),
        "transitions": dict(sorted(transitions.items())),
        "filter_compare": filter_compare,
        "schedule_compare": {
            "days_equal": days_equal,
            "days_divergent": days_divergent,
            "heterogeneous_v2": heterogeneous,
        },
        "integrity": {
            "errors": sum(integrity_codes.values()),
            "by_code": dict(sorted(integrity_codes.items())),
        },
        "performance": {
            "head_queries": int(performance.get("head_queries") or 0),
            "snapshot_queries": int(performance.get("snapshot_queries") or 0),
            "batch_ms": float(performance.get("batch_ms") or 0.0),
        },
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_plans < 1:
        raise SystemExit("--max-plans deve ser maior que zero")
    if args.page_size < 0:
        raise SystemExit("--page-size não pode ser negativo")

    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurado")
    db_name = os.environ.get("DB_NAME", "sigesc_db")

    # Import lazy: as funções puras do auditor permanecem testáveis no Contract
    # Guard isolado, que não precisa instalar o driver Motor.
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        query = _base_query(args)
        population_total = await db.planos_aee.count_documents(query)
        if population_total > args.max_plans:
            raise SystemExit(
                f"Auditoria abortada: população {population_total} excede --max-plans={args.max_plans}."
            )

        planos = await db.planos_aee.find(query, {"_id": 0}).to_list(length=args.max_plans)
        batch = await resolve_plan_list_effective_batch(db, planos)
        report = build_population_report(planos, batch, page_size=args.page_size)
        report["scope"] = {
            "academic_year": args.academic_year,
            "school_filter": bool(args.school_id),
            "student_filter": bool(args.student_id),
            "professor_scope": bool(args.professor_user_id),
            "max_plans": args.max_plans,
        }
        return report
    finally:
        client.close()


def main() -> None:
    args = _parser().parse_args()
    report = asyncio.run(_run(args))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
