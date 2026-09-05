"""R2.0d — pareamento ordinal read-only por sessão para 9º B → 9º A.

Overlay executado após R2.0c.1. A fonte continua sendo o conteúdo institucional
legado/canônico da turma-espelho. Nesta fase cada registro-fonte é expandido
somente em memória pela sua capacidade declarada em ``number_of_classes``.
O destino é a sequência real de documentos/sessões de frequência atribuíveis
a Luiz, sem jamais projetar ``attendance.records``.

Nenhuma escrita acadêmica é realizada. O resultado é sanitizado, determinístico
e fail-closed.
"""

# ruff: noqa: F821

SESSION_SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_SESSION_ORDINAL_V1"
SESSION_SOURCE_CLASS = "9º ANO B"
SESSION_TARGET_CLASS = "9º ANO A"
MAX_DECLARED_CLASSES_PER_SOURCE = 10

SESSION_ATTENDANCE_PROJECTION = {
    "_id": 0,
    "class_id": 1,
    "course_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
    "number_of_classes": 1,
    "period": 1,
    "aula_numero": 1,
    "version": 1,
}


def _session_norm(value):
    raw = _sid(value)
    return raw.casefold() if raw else None


def _session_aula(value):
    raw = _sid(value)
    return raw or None


def _session_aula_sort(value):
    raw = _session_aula(value)
    if raw is None:
        return (0, 0, "")
    try:
        return (1, int(raw), "")
    except (TypeError, ValueError):
        return (2, 0, raw.casefold())


def _safe_positive_int(value, *, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1 or parsed > maximum:
        return None
    return parsed


def _expand_source_slots(source_items):
    """Expande capacidade declarada da fonte apenas para o manifesto read-only."""
    slots = []
    invalid = []
    for source_ordinal, item in enumerate(source_items, 1):
        count = _safe_positive_int(
            item.get("number_of_classes") or 1,
            maximum=MAX_DECLARED_CLASSES_PER_SOURCE,
        )
        if count is None:
            invalid.append({
                "source_ordinal": source_ordinal,
                "source_date": item.get("source_date"),
            })
            continue
        for source_slot in range(1, count + 1):
            slots.append({
                "source_record_ordinal": source_ordinal,
                "source_slot": source_slot,
                "source_slot_count": count,
                "source_date": item["source_date"],
                "source_month": item["source_date"][:7],
                "source_kind": item["source_kind"],
                "source_attribution": item.get("source_attribution"),
                "payload_fingerprint": item["payload_fingerprint"],
            })
    return slots, invalid


def _target_session_rows(
    db,
    *,
    class_id,
    math_ids,
    actor_ids,
    assignment_ids,
    start_date,
    end_date,
):
    rows = list(db.attendance.find(
        {
            "class_id": class_id,
            "course_id": {"$in": sorted(math_ids)},
            "date": {"$gte": start_date, "$lt": end_date},
        },
        SESSION_ATTENDANCE_PROJECTION,
    ))
    rows = [
        row for row in rows
        if _teacher_attributed(row, actor_ids, assignment_ids)
        and start_date <= (_iso_day(row.get("date")) or "") < end_date
    ]
    return rows


def _session_key_payload(row):
    return {
        "date": _iso_day(row.get("date")),
        "period": _session_norm(row.get("period")),
        "aula_numero": _session_aula(row.get("aula_numero")),
    }


def _session_sort_key(row):
    key = _session_key_payload(row)
    return (
        key["date"] or "",
        key["period"] or "",
        _session_aula_sort(key["aula_numero"]),
    )


def _safe_session_meta(row):
    key = _session_key_payload(row)
    declared = _safe_positive_int(row.get("number_of_classes") or 1, maximum=100)
    return {
        "target_date": key["date"],
        "target_month": (key["date"] or "")[:7],
        "period": key["period"],
        "aula_numero": key["aula_numero"],
        "number_of_classes_diagnostic": declared,
        "session_key_hash": _canonical_hash(key),
        "assignment_present": bool(_sid(row.get("assignment_id"))),
        "actor_fingerprint": _canonical_hash({
            field: _fp(row.get(field), 16) if _sid(row.get(field)) else None
            for field in ACTOR_COMPARE_FIELDS
        }),
        "assignment_fingerprint": (
            _fp(row.get("assignment_id"), 16)
            if _sid(row.get("assignment_id")) else None
        ),
    }


def _index_target_sessions(rows):
    """Ordena sessões e detecta chaves indistinguíveis/metadata parcial no dia."""
    by_day = defaultdict(list)
    for row in rows:
        day = _iso_day(row.get("date"))
        if day:
            by_day[day].append(row)

    collision_days = []
    partial_metadata_days = []
    for day, day_rows in sorted(by_day.items()):
        keys = [
            (
                _session_norm(row.get("period")),
                _session_aula(row.get("aula_numero")),
            )
            for row in day_rows
        ]
        if len(keys) != len(set(keys)):
            collision_days.append(day)
        if len(day_rows) > 1:
            patterns = {
                (
                    _session_norm(row.get("period")) is not None,
                    _session_aula(row.get("aula_numero")) is not None,
                )
                for row in day_rows
            }
            # No mesmo dia, uma mistura de documentos com/sem discriminadores
            # é estruturalmente ambígua para ordenação ordinal segura.
            if len(patterns) > 1:
                partial_metadata_days.append(day)

    ordered = sorted(rows, key=_session_sort_key)
    safe = [_safe_session_meta(row) for row in ordered]
    return {
        "sessions": safe,
        "distinct_dates": sorted(by_day),
        "collision_days": collision_days,
        "partial_metadata_days": partial_metadata_days,
        "aula_numero_present_count": sum(
            1 for row in rows if _session_aula(row.get("aula_numero")) is not None
        ),
        "period_present_count": sum(
            1 for row in rows if _session_norm(row.get("period")) is not None
        ),
        "attendance_number_of_classes_sum_diagnostic": sum(
            _safe_positive_int(row.get("number_of_classes") or 1, maximum=100) or 0
            for row in rows
        ),
    }


def _session_pair_plan(
    *,
    source,
    target,
    occupied_dates,
    assignment_by_date,
    structural_classification,
):
    source_items = sorted(
        list(source.get("items") or []),
        key=lambda item: (
            item.get("source_date") or "",
            item.get("payload_fingerprint") or "",
            item.get("source_kind") or "",
        ),
    )
    source_slots, invalid_source = _expand_source_slots(source_items)
    target_sessions = list(target.get("sessions") or [])
    target_dates = list(target.get("distinct_dates") or [])

    hard_blockers = list(source.get("blockers") or [])
    if structural_classification != "ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED":
        hard_blockers.append("R2C1_TWO_SESSION_PRECONDITION_NOT_MET")
    if invalid_source:
        hard_blockers.append("SOURCE_NUMBER_OF_CLASSES_INVALID")
    if target.get("collision_days"):
        hard_blockers.append("TARGET_SESSION_KEY_COLLISION")
    if target.get("partial_metadata_days"):
        hard_blockers.append("TARGET_SAME_DAY_SESSION_METADATA_PARTIAL")

    occupied_targets = sorted(set(target_dates) & set(occupied_dates))
    if occupied_targets:
        hard_blockers.append("TARGET_DATE_ALREADY_HAS_CONTENT")

    unresolved_dates = [
        day for day in target_dates
        if (assignment_by_date.get(day) or {}).get("status") != "RESOLVED"
    ]
    if unresolved_dates:
        hard_blockers.append("TARGET_BINDING_NOT_UNIQUE")

    count_mismatch = len(source_slots) != len(target_sessions)
    all_blockers = list(hard_blockers)
    if count_mismatch:
        all_blockers.append("SESSION_GLOBAL_COUNT_MISMATCH")

    diagnostic_pairing_allowed = not hard_blockers
    paired_limit = (
        min(len(source_slots), len(target_sessions))
        if diagnostic_pairing_allowed else 0
    )

    items = []
    source_target_dates = defaultdict(set)
    cross_month = 0
    for index in range(paired_limit):
        src = source_slots[index]
        tgt = target_sessions[index]
        day = tgt["target_date"]
        binding = assignment_by_date[day]
        if src["source_month"] != tgt["target_month"]:
            cross_month += 1
        source_target_dates[src["source_record_ordinal"]].add(day)
        items.append({
            "session_ordinal": index + 1,
            "source_record_ordinal": src["source_record_ordinal"],
            "source_slot": src["source_slot"],
            "source_slot_count": src["source_slot_count"],
            "source_date": src["source_date"],
            "source_month": src["source_month"],
            "source_kind": src["source_kind"],
            "source_attribution": src.get("source_attribution"),
            "payload_fingerprint": src["payload_fingerprint"],
            "target_date": day,
            "target_month": tgt["target_month"],
            "target_period": tgt.get("period"),
            "target_aula_numero": tgt.get("aula_numero"),
            "target_session_key_hash": tgt["session_key_hash"],
            "target_attendance_number_of_classes_diagnostic": tgt.get(
                "number_of_classes_diagnostic"
            ),
            "target_binding_fingerprint": binding.get("assignment_fingerprint"),
            "target_write_mode": binding.get("write_mode"),
            "historical_backfill": bool(binding.get("historical_backfill")),
        })

    unpaired_source = [
        {
            "session_ordinal": idx,
            "source_record_ordinal": src["source_record_ordinal"],
            "source_slot": src["source_slot"],
            "source_slot_count": src["source_slot_count"],
            "source_date": src["source_date"],
            "payload_fingerprint": src["payload_fingerprint"],
        }
        for idx, src in enumerate(
            source_slots[paired_limit:], paired_limit + 1
        )
    ]
    unpaired_target = [
        {
            "session_ordinal": idx,
            "target_date": tgt["target_date"],
            "target_period": tgt.get("period"),
            "target_aula_numero": tgt.get("aula_numero"),
            "target_session_key_hash": tgt["session_key_hash"],
        }
        for idx, tgt in enumerate(
            target_sessions[paired_limit:], paired_limit + 1
        )
    ]

    split_source_records = sorted(
        ordinal for ordinal, days in source_target_dates.items() if len(days) > 1
    )
    status = "READY_TO_APPLY" if not all_blockers else "BLOCKED_REVIEW_REQUIRED"
    plan = {
        "status": status,
        "blockers": sorted(set(all_blockers)),
        "source_record_total": len(source_items),
        "source_slot_total": len(source_slots),
        "source_invalid_number_of_classes_count": len(invalid_source),
        "source_invalid_number_of_classes_items": invalid_source,
        "source_month_counts": source.get("monthly_counts") or {},
        "target_session_total": len(target_sessions),
        "target_distinct_date_total": len(target_dates),
        "target_aula_numero_present_count": int(
            target.get("aula_numero_present_count") or 0
        ),
        "target_period_present_count": int(target.get("period_present_count") or 0),
        "target_attendance_number_of_classes_sum_diagnostic": int(
            target.get("attendance_number_of_classes_sum_diagnostic") or 0
        ),
        "target_session_collision_day_count": len(target.get("collision_days") or []),
        "target_partial_session_metadata_day_count": len(
            target.get("partial_metadata_days") or []
        ),
        "target_existing_content_on_session_dates": len(occupied_targets),
        "target_unresolved_binding_date_count": len(unresolved_dates),
        "paired_session_count": len(items),
        "unpaired_source_slot_count": len(source_slots) - len(items),
        "unpaired_target_session_count": len(target_sessions) - len(items),
        "calendar_cross_month_session_pair_count": cross_month,
        "source_record_spans_multiple_target_dates_count": len(split_source_records),
        "source_record_spans_multiple_target_dates_ordinals": split_source_records,
        "items": items,
        "unpaired_source_slots": unpaired_source,
        "unpaired_target_sessions": unpaired_target,
    }
    plan["pair_manifest_hash"] = _canonical_hash(plan)
    return plan


def run_session_ordinal_preflight(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("R2D_GLOBAL_STRATEGY_REQUIRED")

    # Revalida a premissa que motivou esta fase antes de ler o período inteiro.
    structural = run_orphan_structural_discrimination(case)

    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        context = _resolve_context(db, case)
        start_date = _sid(case["start_date"])
        end_date = _sid(case["end_date"])
        months = _months_between(start_date, end_date)

        pair = next(
            p for p in case["pairs"]
            if _sid(p["source_class"]) == SESSION_SOURCE_CLASS
            and _sid(p["target_class"]) == SESSION_TARGET_CLASS
        )
        source_id = context["class_ids"][_sid(pair["source_class"])]
        target_id = context["class_ids"][_sid(pair["target_class"])]
        target_component = context["target_component"][SESSION_TARGET_CLASS]

        source_canonical, source_legacy = _find_rows_for_class(
            db,
            class_id=source_id,
            math_ids=context["math_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        source_months = _source_items_by_month(
            source_canonical,
            source_legacy,
            actor_ids=context["actor_ids"],
            assignment_ids=context["assignment_ids"],
            months=months,
        )
        source = _flatten_source_months(source_months, months)

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

        target_canonical, target_legacy = _find_rows_for_class(
            db,
            class_id=target_id,
            math_ids=context["math_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        occupied = _occupied_dates(target_canonical, target_legacy)
        assignment_by_date = {
            day: _assignment_for_date(
                context["dvd_assignments"],
                class_id=target_id,
                component_id=target_component,
                teacher_id=context["teacher_id"],
                target_date=day,
            )
            for day in target["distinct_dates"]
        }

        plan = _session_pair_plan(
            source=source,
            target=target,
            occupied_dates=occupied,
            assignment_by_date=assignment_by_date,
            structural_classification=structural.get("classification"),
        )
        manifest = {
            "schema": SESSION_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "strategy": "GLOBAL_ORDINAL_BY_ATTENDANCE_SESSION",
            "source_class": SESSION_SOURCE_CLASS,
            "target_class": SESSION_TARGET_CLASS,
            "teacher_name": _sid(case["teacher_name"]),
            "school_name": _sid(case["school_name"]),
            "component_name": _sid(case["component_name"]),
            "academic_year": int(case["academic_year"]),
            "start_date": start_date,
            "end_date": end_date,
            "r2c1_structural_hash": structural.get("structural_discrimination_hash"),
            "r2c1_classification": structural.get("classification"),
            "session_plan": plan,
            "summary": {
                "overall_status": plan["status"],
                "recommended_action": (
                    "FREEZE_R2D_MANIFEST_FOR_R2_1"
                    if plan["status"] == "READY_TO_APPLY"
                    else "BLOCK_9A_APPLY_AND_REVIEW_SESSION_MODEL"
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
                "source_expansion_in_memory_only": True,
                "target_attendance_number_of_classes_expanded": False,
                "automatic_source_drop_or_repeat": False,
                "fail_closed_on_session_ambiguity": True,
                "deploy_performed": False,
            },
        }
        manifest["manifest_hash"] = _canonical_hash(manifest)
        return manifest
    finally:
        client.close()
