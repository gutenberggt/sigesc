"""R2.0f — pareamento ordinal read-only por data + carga para 9º B → 9º A.

Overlay executado após a calibração R2.0e. Mantém cada conteúdo-fonte como
uma unidade indivisível por data e agrega as sessões reais do destino por dia.
O pareamento monotônico por carga é apenas diagnóstico: nenhuma fonte ou data
é descartada, repetida, fracionada ou inventada para fechar contagens.

Nenhuma escrita acadêmica é realizada. ``attendance.records`` nunca é lido.
"""

# ruff: noqa: F821

from collections import Counter, defaultdict
import hashlib
import json

DATE_LOAD_SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_DATE_LOAD_ORDINAL_V1"
DATE_LOAD_SOURCE_CLASS = "9º ANO B"
DATE_LOAD_TARGET_CLASS = "9º ANO A"
EXPECTED_R2E_CALIBRATION_HASH = (
    "cbe9f21d5a9d9e76c508c6bea9f924cc10ac086546b9e9cb065aa7a77006af88"
)
EXPECTED_R2E_CLASSIFICATION = (
    "ONE_CONTENT_PER_DATE_COVERS_SESSION_DOCUMENTS_SUPPORTED"
)


def _date_load_hash(value):
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source_date_units(canonical, legacy, *, actor_ids, assignment_ids):
    items, blockers = _calibration_source_items(
        canonical,
        legacy,
        actor_ids=actor_ids,
        assignment_ids=assignment_ids,
    )
    by_day = defaultdict(list)
    for item in items:
        by_day[item["source_date"]].append(item)

    multiple_days = sorted(day for day, rows in by_day.items() if len(rows) != 1)
    if multiple_days:
        blockers = list(blockers) + ["SOURCE_NOT_ONE_CONTENT_PER_DATE"]

    units = []
    for day in sorted(by_day):
        rows = by_day[day]
        if len(rows) != 1:
            continue
        row = rows[0]
        declared = _safe_positive_int(
            row.get("number_of_classes") or 1,
            maximum=MAX_DECLARED_CLASSES_PER_SOURCE,
        )
        if declared is None:
            blockers = list(blockers) + ["SOURCE_NUMBER_OF_CLASSES_INVALID"]
            continue
        units.append({
            "source_ordinal": len(units) + 1,
            "source_date": day,
            "source_month": day[:7],
            "source_declared_load": declared,
            "source_kind": row.get("source_kind"),
            "source_attribution": row.get("source_attribution"),
            "payload_fingerprint": row.get("payload_fingerprint"),
        })
    return units, sorted(set(blockers)), multiple_days


def _target_date_loads(target_index):
    by_day = defaultdict(list)
    for session in target_index.get("sessions") or []:
        by_day[session.get("target_date")].append(session)

    days = []
    invalid_days = []
    for ordinal, day in enumerate(sorted(by_day), 1):
        sessions = by_day[day]
        declared_values = [
            _safe_positive_int(
                session.get("number_of_classes_diagnostic") or 1,
                maximum=100,
            )
            for session in sessions
        ]
        valid = all(value is not None for value in declared_values)
        declared_sum = sum(value or 0 for value in declared_values)
        document_count = len(sessions)
        load_consistent = bool(valid and declared_sum == document_count)
        if not load_consistent:
            invalid_days.append(day)
        signature = {
            "date": day,
            "document_count": document_count,
            "declared_load": declared_sum,
            "session_key_hashes": sorted(
                session.get("session_key_hash") for session in sessions
            ),
        }
        days.append({
            "target_ordinal": ordinal,
            "target_date": day,
            "target_month": day[:7],
            "target_document_count": document_count,
            "target_declared_load": declared_sum,
            "target_load_consistent": load_consistent,
            "target_load_fingerprint": _date_load_hash(signature),
            "session_key_hashes": signature["session_key_hashes"],
        })
    return days, invalid_days


def _max_monotonic_load_pairs(source_units, target_days):
    """LCS por carga, preservando ordem; resultado estritamente diagnóstico."""
    n = len(source_units)
    m = len(target_days)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        source_load = source_units[i]["source_declared_load"]
        for j in range(m - 1, -1, -1):
            target_load = target_days[j]["target_declared_load"]
            match = -1
            if (
                target_days[j].get("target_load_consistent")
                and source_load == target_load
            ):
                match = 1 + dp[i + 1][j + 1]
            dp[i][j] = max(match, dp[i + 1][j], dp[i][j + 1])

    pairs = []
    i = 0
    j = 0
    while i < n and j < m:
        source_load = source_units[i]["source_declared_load"]
        target_load = target_days[j]["target_declared_load"]
        if (
            target_days[j].get("target_load_consistent")
            and source_load == target_load
            and 1 + dp[i + 1][j + 1] == dp[i][j]
        ):
            pairs.append((i, j))
            i += 1
            j += 1
            continue
        skip_source = dp[i + 1][j]
        skip_target = dp[i][j + 1]
        if skip_source > skip_target:
            i += 1
        else:
            # Em empate, avança o destino para manter a fonte mais antiga
            # disponível para uma data futura compatível.
            j += 1
    return pairs


def _load_distribution(values):
    counts = Counter(int(value) for value in values)
    return {str(key): counts[key] for key in sorted(counts)}


def _date_load_plan(
    *,
    source_units,
    source_blockers,
    source_multiple_days,
    target,
    target_days,
    target_invalid_load_days,
    occupied_dates,
    assignment_by_date,
    calibration_hash,
    calibration_classification,
):
    hard_blockers = list(source_blockers or [])
    if calibration_hash != EXPECTED_R2E_CALIBRATION_HASH:
        hard_blockers.append("R2E_CALIBRATION_HASH_CHANGED")
    if calibration_classification != EXPECTED_R2E_CLASSIFICATION:
        hard_blockers.append("R2E_CALIBRATION_CLASSIFICATION_CHANGED")
    if source_multiple_days:
        hard_blockers.append("SOURCE_NOT_ONE_CONTENT_PER_DATE")
    if target.get("collision_days"):
        hard_blockers.append("TARGET_SESSION_KEY_COLLISION")
    if target.get("partial_metadata_days"):
        hard_blockers.append("TARGET_SAME_DAY_SESSION_METADATA_PARTIAL")
    if target_invalid_load_days:
        hard_blockers.append("TARGET_DAILY_LOAD_INCONSISTENT")

    target_dates = [item["target_date"] for item in target_days]
    occupied_targets = sorted(set(target_dates) & set(occupied_dates))
    if occupied_targets:
        hard_blockers.append("TARGET_DATE_ALREADY_HAS_CONTENT")

    unresolved_dates = [
        day for day in target_dates
        if (assignment_by_date.get(day) or {}).get("status") != "RESOLVED"
    ]
    if unresolved_dates:
        hard_blockers.append("TARGET_BINDING_NOT_UNIQUE")

    source_total_load = sum(item["source_declared_load"] for item in source_units)
    target_total_load = sum(item["target_declared_load"] for item in target_days)

    blockers = list(hard_blockers)
    if len(source_units) != len(target_days):
        blockers.append("DATE_GLOBAL_COUNT_MISMATCH")
    if source_total_load != target_total_load:
        blockers.append("DAILY_LOAD_TOTAL_MISMATCH")

    diagnostic_pairs = (
        _max_monotonic_load_pairs(source_units, target_days)
        if not hard_blockers
        else []
    )
    matched_source = {i for i, _ in diagnostic_pairs}
    matched_target = {j for _, j in diagnostic_pairs}

    if (
        len(diagnostic_pairs) != len(source_units)
        or len(diagnostic_pairs) != len(target_days)
    ):
        blockers.append("DAILY_LOAD_SEQUENCE_MISMATCH")

    items = []
    cross_month = 0
    for pair_ordinal, (source_index, target_index) in enumerate(diagnostic_pairs, 1):
        src = source_units[source_index]
        tgt = target_days[target_index]
        binding = assignment_by_date[tgt["target_date"]]
        if src["source_month"] != tgt["target_month"]:
            cross_month += 1
        items.append({
            "pair_ordinal": pair_ordinal,
            "source_ordinal": src["source_ordinal"],
            "source_date": src["source_date"],
            "source_month": src["source_month"],
            "source_declared_load": src["source_declared_load"],
            "source_kind": src.get("source_kind"),
            "source_attribution": src.get("source_attribution"),
            "payload_fingerprint": src.get("payload_fingerprint"),
            "target_ordinal": tgt["target_ordinal"],
            "target_date": tgt["target_date"],
            "target_month": tgt["target_month"],
            "target_document_count": tgt["target_document_count"],
            "target_declared_load": tgt["target_declared_load"],
            "target_load_fingerprint": tgt["target_load_fingerprint"],
            "target_binding_fingerprint": binding.get("assignment_fingerprint"),
            "target_write_mode": binding.get("write_mode"),
            "historical_backfill": bool(binding.get("historical_backfill")),
        })

    unpaired_source = [
        {
            "source_ordinal": item["source_ordinal"],
            "source_date": item["source_date"],
            "source_declared_load": item["source_declared_load"],
            "payload_fingerprint": item.get("payload_fingerprint"),
        }
        for index, item in enumerate(source_units)
        if index not in matched_source
    ]
    unpaired_target = [
        {
            "target_ordinal": item["target_ordinal"],
            "target_date": item["target_date"],
            "target_document_count": item["target_document_count"],
            "target_declared_load": item["target_declared_load"],
            "target_load_fingerprint": item["target_load_fingerprint"],
        }
        for index, item in enumerate(target_days)
        if index not in matched_target
    ]

    ordinal_zip = list(zip(source_units, target_days))
    ordinal_load_match_count = sum(
        1 for src, tgt in ordinal_zip
        if tgt.get("target_load_consistent")
        and src["source_declared_load"] == tgt["target_declared_load"]
    )

    status = "READY_TO_APPLY" if not blockers else "BLOCKED_REVIEW_REQUIRED"
    plan = {
        "status": status,
        "blockers": sorted(set(blockers)),
        "source_content_total": len(source_units),
        "source_distinct_date_total": len(source_units),
        "source_total_declared_load": source_total_load,
        "source_load_distribution": _load_distribution(
            item["source_declared_load"] for item in source_units
        ),
        "source_multiple_content_date_count": len(source_multiple_days),
        "target_distinct_date_total": len(target_days),
        "target_session_document_total": sum(
            item["target_document_count"] for item in target_days
        ),
        "target_total_declared_load": target_total_load,
        "target_load_distribution": _load_distribution(
            item["target_declared_load"] for item in target_days
        ),
        "target_invalid_load_day_count": len(target_invalid_load_days),
        "target_session_collision_day_count": len(target.get("collision_days") or []),
        "target_partial_session_metadata_day_count": len(
            target.get("partial_metadata_days") or []
        ),
        "target_existing_content_date_count": len(occupied_targets),
        "target_unresolved_binding_date_count": len(unresolved_dates),
        "ordinal_zip_compared_count": len(ordinal_zip),
        "ordinal_zip_load_match_count": ordinal_load_match_count,
        "ordinal_zip_load_mismatch_count": len(ordinal_zip) - ordinal_load_match_count,
        "monotonic_load_compatible_pair_count": len(items),
        "unpaired_source_content_count": len(unpaired_source),
        "unpaired_target_date_count": len(unpaired_target),
        "calendar_cross_month_pair_count": cross_month,
        "items": items,
        "unpaired_source_contents": unpaired_source,
        "unpaired_target_dates": unpaired_target,
    }
    plan["pair_manifest_hash"] = _date_load_hash(plan)
    return plan


def run_date_load_ordinal_preflight(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("R2F_GLOBAL_STRATEGY_REQUIRED")

    # Recalibra a fonte primeiro. O hash congelado da R2.0e é um prerequisito
    # explícito: qualquer drift bloqueia esta fase antes de reutilizar a regra.
    calibration = run_source_semantic_calibration(case)
    calibration_summary = calibration.get("summary") or {}

    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        context = _resolve_context(db, case)
        start_date = _sid(case["start_date"])
        end_date = _sid(case["end_date"])

        pair = next(
            p for p in case["pairs"]
            if _sid(p["source_class"]) == DATE_LOAD_SOURCE_CLASS
            and _sid(p["target_class"]) == DATE_LOAD_TARGET_CLASS
        )
        source_id = context["class_ids"][_sid(pair["source_class"])]
        target_id = context["class_ids"][_sid(pair["target_class"])]
        target_component = context["target_component"][DATE_LOAD_TARGET_CLASS]

        source_canonical, source_legacy = _find_rows_for_class(
            db,
            class_id=source_id,
            math_ids=context["math_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        source_units, source_blockers, source_multiple_days = _source_date_units(
            source_canonical,
            source_legacy,
            actor_ids=context["actor_ids"],
            assignment_ids=context["assignment_ids"],
        )

        attendance_rows = _target_session_rows(
            db,
            class_id=target_id,
            math_ids=context["math_ids"],
            actor_ids=context["actor_ids"],
            assignment_ids=context["assignment_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        target = _index_target_sessions(attendance_rows)
        target_days, target_invalid_load_days = _target_date_loads(target)

        target_canonical, target_legacy = _find_rows_for_class(
            db,
            class_id=target_id,
            math_ids=context["math_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        occupied = _occupied_dates(target_canonical, target_legacy)
        assignment_by_date = {
            item["target_date"]: _assignment_for_date(
                context["dvd_assignments"],
                class_id=target_id,
                component_id=target_component,
                teacher_id=context["teacher_id"],
                target_date=item["target_date"],
            )
            for item in target_days
        }

        plan = _date_load_plan(
            source_units=source_units,
            source_blockers=source_blockers,
            source_multiple_days=source_multiple_days,
            target=target,
            target_days=target_days,
            target_invalid_load_days=target_invalid_load_days,
            occupied_dates=occupied,
            assignment_by_date=assignment_by_date,
            calibration_hash=calibration.get("calibration_hash"),
            calibration_classification=calibration_summary.get("classification"),
        )

        manifest = {
            "schema": DATE_LOAD_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "strategy": "GLOBAL_ORDINAL_BY_DATE_AND_CALIBRATED_LOAD",
            "source_class": DATE_LOAD_SOURCE_CLASS,
            "target_class": DATE_LOAD_TARGET_CLASS,
            "teacher_name": _sid(case["teacher_name"]),
            "school_name": _sid(case["school_name"]),
            "component_name": _sid(case["component_name"]),
            "academic_year": int(case["academic_year"]),
            "start_date": start_date,
            "end_date": end_date,
            "r2e_calibration_hash": calibration.get("calibration_hash"),
            "r2e_classification": calibration_summary.get("classification"),
            "date_load_plan": plan,
            "summary": {
                "overall_status": plan["status"],
                "recommended_action": (
                    "FREEZE_R2F_MANIFEST_FOR_R2_1"
                    if plan["status"] == "READY_TO_APPLY"
                    else "BLOCK_9A_APPLY_AND_REVIEW_DAILY_LOAD_GAP"
                ),
            },
            "boundaries": {
                "mongo_reads_only": True,
                "production_writes": False,
                "attendance_records_read": False,
                "students_read": False,
                "enrollments_read": False,
                "grades_read": False,
                "audit_logs_read": False,
                "attendance_written": False,
                "content_written": False,
                "source_payload_plaintext_read_for_fingerprint": True,
                "source_payload_plaintext_emitted": False,
                "technical_ids_emitted": False,
                "source_content_expanded": False,
                "source_content_split": False,
                "source_content_repeated": False,
                "source_content_dropped_automatically": False,
                "target_date_dropped_automatically": False,
                "monotonic_load_pairing_diagnostic_only": True,
                "automatic_semantic_rule_application": False,
                "deploy_performed": False,
                "fail_closed_on_count_or_load_mismatch": True,
            },
        }
        manifest["manifest_hash"] = _date_load_hash(manifest)
        return manifest
    finally:
        client.close()
