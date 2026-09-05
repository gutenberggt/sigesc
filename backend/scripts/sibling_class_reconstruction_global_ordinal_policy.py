"""Policy R2.0b para pareamento ordinal contínuo no período inteiro.

Este overlay é executado após:
1. ``sibling_class_reconstruction_preflight_readonly.py``;
2. ``sibling_class_reconstruction_mirror_policy.py``.

A policy mantém a turma B como espelho curricular institucional e o binding
DVD/legado da R2.0a, mas substitui o pareamento mensal por uma sequência única
cronológica no período. Divergência total permanece fail-closed.
"""

# Este módulo é deliberadamente um overlay executado no MESMO namespace dos
# motores anteriores. Os símbolos abaixo são providos antes deste arquivo.
# ruff: noqa: F821

GLOBAL_STRATEGY = "GLOBAL_ORDINAL_CONTINUOUS_PERIOD"
GLOBAL_SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_GLOBAL_PREFLIGHT_V1"
_R2_GLOBAL_BASE_VALIDATE_CASE = _validate_case


def _validate_case(case):
    """Aceita a estratégia global sem enfraquecer o contrato do caso V1."""
    if case.get("strategy") != GLOBAL_STRATEGY:
        return _R2_GLOBAL_BASE_VALIDATE_CASE(case)
    shadow = dict(case)
    shadow["strategy"] = SUPPORTED_STRATEGY
    _R2_GLOBAL_BASE_VALIDATE_CASE(shadow)


def _flatten_source_months(source_months, months):
    items = []
    blockers = []
    monthly = {}
    attribution = Counter()
    canonical_total = 0
    legacy_total = 0
    for month in months:
        bucket = source_months[month]
        blockers.extend(bucket.get("blockers") or [])
        bucket_items = list(bucket.get("items") or [])
        items.extend(bucket_items)
        canonical_total += int(bucket.get("canonical_row_count") or 0)
        legacy_total += int(bucket.get("legacy_row_count") or 0)
        attribution["TARGET_TEACHER"] += int(
            bucket.get("target_teacher_row_count") or 0
        )
        attribution["OTHER_ACTOR"] += int(bucket.get("foreign_row_count") or 0)
        attribution["UNATTRIBUTED_LEGACY"] += int(
            bucket.get("unattributed_legacy_row_count") or 0
        )
        monthly[month] = len(bucket_items)
    items.sort(key=lambda item: item["source_date"])
    return {
        "items": items,
        "blockers": sorted(set(blockers)),
        "monthly_counts": monthly,
        "canonical_total": canonical_total,
        "legacy_total": legacy_total,
        "attribution_counts": dict(sorted(attribution.items())),
    }


def _flatten_target_months(target_months, months):
    dates = []
    conflict_dates = []
    monthly = {}
    document_count = 0
    foreign_document_count = 0
    for month in months:
        bucket = target_months[month]
        bucket_dates = list(bucket.get("dates") or [])
        dates.extend(bucket_dates)
        conflict_dates.extend(bucket.get("actor_conflict_dates") or [])
        monthly[month] = len(bucket_dates)
        document_count += int(bucket.get("document_count") or 0)
        foreign_document_count += int(bucket.get("foreign_document_count") or 0)
    return {
        "dates": sorted(set(dates)),
        "conflict_dates": sorted(set(conflict_dates)),
        "monthly_counts": monthly,
        "document_count": document_count,
        "foreign_document_count": foreign_document_count,
    }


def _global_pair_plan(
    *,
    source,
    target,
    occupied_dates,
    assignment_by_date,
):
    blockers = list(source.get("blockers") or [])
    source_items = list(source.get("items") or [])
    target_dates = list(target.get("dates") or [])

    hard_blockers = []
    if blockers:
        hard_blockers.extend(blockers)
    if target.get("conflict_dates"):
        hard_blockers.append("TARGET_ATTENDANCE_ACTOR_CONFLICT")

    occupied_targets = sorted(set(target_dates) & occupied_dates)
    if occupied_targets:
        hard_blockers.append("TARGET_DATE_ALREADY_HAS_CONTENT")

    unresolved = [
        day
        for day in target_dates
        if (assignment_by_date.get(day) or {}).get("status") != "RESOLVED"
    ]
    if unresolved:
        hard_blockers.append("TARGET_BINDING_NOT_UNIQUE")

    count_mismatch = len(source_items) != len(target_dates)
    all_blockers = list(hard_blockers)
    if count_mismatch:
        all_blockers.append("GLOBAL_COUNT_MISMATCH")

    diagnostic_pairing_allowed = not hard_blockers
    paired_limit = min(len(source_items), len(target_dates)) if diagnostic_pairing_allowed else 0

    items = []
    shift_days = []
    cross_month = 0
    for index in range(paired_limit):
        src = source_items[index]
        target_date = target_dates[index]
        binding = assignment_by_date[target_date]
        source_date = src["source_date"]
        source_month = source_date[:7]
        target_month = target_date[:7]
        if source_month != target_month:
            cross_month += 1
        shift_days.append(
            (date.fromisoformat(target_date) - date.fromisoformat(source_date)).days
        )
        items.append({
            "global_ordinal": index + 1,
            "source_date": source_date,
            "source_month": source_month,
            "target_date": target_date,
            "target_month": target_month,
            "source_kind": src["source_kind"],
            "source_attribution": src.get("source_attribution"),
            "payload_fingerprint": src["payload_fingerprint"],
            "number_of_classes": int(src.get("number_of_classes") or 1),
            "target_binding_fingerprint": binding.get("assignment_fingerprint"),
            "target_write_mode": binding.get("write_mode"),
            "historical_backfill": bool(binding.get("historical_backfill")),
        })

    unpaired_source = []
    for index, src in enumerate(source_items[paired_limit:], paired_limit + 1):
        unpaired_source.append({
            "global_ordinal": index,
            "source_date": src["source_date"],
            "source_month": src["source_date"][:7],
            "source_kind": src["source_kind"],
            "source_attribution": src.get("source_attribution"),
            "payload_fingerprint": src["payload_fingerprint"],
            "number_of_classes": int(src.get("number_of_classes") or 1),
        })

    unpaired_target = []
    for index, target_date in enumerate(target_dates[paired_limit:], paired_limit + 1):
        binding = assignment_by_date[target_date]
        unpaired_target.append({
            "global_ordinal": index,
            "target_date": target_date,
            "target_month": target_date[:7],
            "target_binding_fingerprint": binding.get("assignment_fingerprint"),
            "target_write_mode": binding.get("write_mode"),
            "historical_backfill": bool(binding.get("historical_backfill")),
        })

    write_modes = Counter(
        (assignment_by_date.get(day) or {}).get("write_mode") or "UNRESOLVED"
        for day in target_dates
    )
    status = "READY_TO_APPLY" if not all_blockers else "BLOCKED_REVIEW_REQUIRED"
    plan = {
        "status": status,
        "blockers": sorted(set(all_blockers)),
        "source_total": len(source_items),
        "source_number_of_classes_total": sum(
            int(item.get("number_of_classes") or 1) for item in source_items
        ),
        "source_canonical_total": int(source.get("canonical_total") or 0),
        "source_legacy_total": int(source.get("legacy_total") or 0),
        "source_attribution_counts": source.get("attribution_counts") or {},
        "source_month_counts": source.get("monthly_counts") or {},
        "target_total": len(target_dates),
        "target_month_counts": target.get("monthly_counts") or {},
        "target_attendance_document_count": int(target.get("document_count") or 0),
        "target_foreign_document_count": int(
            target.get("foreign_document_count") or 0
        ),
        "target_existing_content_on_anchor_dates": len(occupied_targets),
        "target_unresolved_binding_date_count": len(unresolved),
        "target_write_mode_counts": dict(sorted(write_modes.items())),
        "paired_count": len(items),
        "unpaired_source_count": len(source_items) - len(items),
        "unpaired_target_count": len(target_dates) - len(items),
        "calendar_cross_month_pair_count": cross_month,
        "calendar_shift_days_min": min(shift_days) if shift_days else None,
        "calendar_shift_days_max": max(shift_days) if shift_days else None,
        "items": items,
        "unpaired_source_items": unpaired_source,
        "unpaired_target_dates": unpaired_target,
    }
    plan["pair_manifest_hash"] = _canonical_hash(plan)
    return plan


def run_live_preflight(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("GLOBAL_STRATEGY_REQUIRED")

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

        pair_results = []
        for pair in case["pairs"]:
            source_name = _sid(pair["source_class"])
            target_name = _sid(pair["target_class"])
            source_id = context["class_ids"][source_name]
            target_id = context["class_ids"][target_name]
            target_component = context["target_component"][target_name]

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

            target_months = _attendance_by_month(
                db,
                class_id=target_id,
                math_ids=context["math_ids"],
                actor_ids=context["actor_ids"],
                assignment_ids=context["assignment_ids"],
                start_date=start_date,
                end_date=end_date,
                months=months,
            )
            target = _flatten_target_months(target_months, months)

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
                for day in target["dates"]
            }

            plan = _global_pair_plan(
                source=source,
                target=target,
                occupied_dates=occupied,
                assignment_by_date=assignment_by_date,
            )
            pair_results.append({
                "source_class": source_name,
                "target_class": target_name,
                "global_plan": plan,
            })

        plans = [pair["global_plan"] for pair in pair_results]
        ready_count = sum(1 for plan in plans if plan["status"] == "READY_TO_APPLY")
        blocked_count = len(plans) - ready_count
        manifest = {
            "schema": GLOBAL_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "strategy": GLOBAL_STRATEGY,
            "teacher_name": _sid(case["teacher_name"]),
            "school_name": _sid(case["school_name"]),
            "component_name": _sid(case["component_name"]),
            "academic_year": int(case["academic_year"]),
            "start_date": start_date,
            "end_date": end_date,
            "pairs": pair_results,
            "summary": {
                "pair_total": len(plans),
                "ready_to_apply": ready_count,
                "blocked_review_required": blocked_count,
                "overall_status": (
                    "READY_TO_APPLY" if blocked_count == 0
                    else "BLOCKED_REVIEW_REQUIRED"
                ),
            },
            "boundaries": {
                "mongo_reads_only": True,
                "production_writes": False,
                "attendance_records_read": False,
                "student_data_read": False,
                "enrollment_data_read": False,
                "grades_read": False,
                "source_payload_plaintext_read_for_fingerprint": True,
                "source_payload_plaintext_emitted": False,
                "technical_ids_emitted": False,
                "learning_objects_written": False,
                "content_entries_written": False,
                "attendance_written": False,
                "monthly_count_equality_required": False,
                "global_order_preserved": True,
                "automatic_source_expansion_by_number_of_classes": False,
                "automatic_source_drop_or_repeat": False,
            },
        }
        manifest["manifest_hash"] = _canonical_hash(manifest)
        return manifest
    finally:
        client.close()
