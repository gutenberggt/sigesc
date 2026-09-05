"""R2.0e — calibração semântica read-only no próprio 9º B.

Overlay executado após R2.0d. Compara os conteúdos institucionais de Matemática
do 9º B com os próprios documentos/sessões de frequência da turma-fonte para
inferir empiricamente a granularidade histórica de ``number_of_classes``.

A fase não transforma nem escreve dados. ``attendance.records`` nunca é lido.
"""

# ruff: noqa: F821

CALIBRATION_SCHEMA = "SIBLING_CLASS_SOURCE_SEMANTIC_CALIBRATION_V1"
CALIBRATION_SOURCE_CLASS = "9º ANO B"


def _calibration_attendance_rows(db, *, class_id, math_ids, start_date, end_date):
    rows = list(db.attendance.find(
        {
            "class_id": class_id,
            "course_id": {"$in": sorted(math_ids)},
            "date": {"$gte": start_date, "$lt": end_date},
        },
        SESSION_ATTENDANCE_PROJECTION,
    ))
    return [
        row for row in rows
        if start_date <= (_iso_day(row.get("date")) or "") < end_date
    ]


def _content_day_index(source_items):
    by_day = defaultdict(list)
    invalid = []
    for ordinal, item in enumerate(source_items, 1):
        day = item.get("source_date")
        declared = _safe_positive_int(
            item.get("number_of_classes") or 1,
            maximum=MAX_DECLARED_CLASSES_PER_SOURCE,
        )
        if declared is None:
            invalid.append({"source_ordinal": ordinal, "source_date": day})
            continue
        by_day[day].append({
            "source_ordinal": ordinal,
            "declared_classes": declared,
            "payload_fingerprint": item.get("payload_fingerprint"),
            "source_kind": item.get("source_kind"),
            "source_attribution": item.get("source_attribution"),
        })
    return by_day, invalid


def _attendance_day_index(target_index):
    by_day = defaultdict(list)
    for session in target_index.get("sessions") or []:
        by_day[session.get("target_date")].append(session)
    return by_day


def _day_profile(day, contents, sessions):
    content_load = sum(int(item.get("declared_classes") or 0) for item in contents)
    attendance_load = sum(
        int(item.get("number_of_classes_diagnostic") or 0) for item in sessions
    )
    attendance_all_unit = bool(sessions) and all(
        int(item.get("number_of_classes_diagnostic") or 0) == 1
        for item in sessions
    )
    content_all_unit = bool(contents) and all(
        int(item.get("declared_classes") or 0) == 1 for item in contents
    )
    return {
        "date": day,
        "month": day[:7],
        "content_count": len(contents),
        "attendance_document_count": len(sessions),
        "content_declared_load_sum": content_load,
        "attendance_declared_load_sum": attendance_load,
        "content_all_declared_one": content_all_unit,
        "attendance_all_declared_one": attendance_all_unit,
        "single_content_date": len(contents) == 1,
        "content_count_equals_attendance_documents": len(contents) == len(sessions),
        "declared_load_equal": bool(contents and sessions and content_load == attendance_load),
        "single_content_load_equals_attendance_documents": bool(
            len(contents) == 1 and content_load == len(sessions)
        ),
        "single_content_load_equals_attendance_load": bool(
            len(contents) == 1 and content_load == attendance_load
        ),
        "content_fingerprints": [
            item.get("payload_fingerprint") for item in contents
        ],
        "session_key_hashes": [item.get("session_key_hash") for item in sessions],
    }


def _classify_source_semantics(profiles, *, structural_blockers=None):
    blockers = list(structural_blockers or [])
    if not profiles:
        return {
            "classification": "INSUFFICIENT_OR_CONFLICTING_EVIDENCE",
            "recommended_action": "BLOCK_9A_APPLY",
            "blockers": sorted(set(blockers + ["SOURCE_CALIBRATION_EMPTY"])),
        }

    content_only = [p["date"] for p in profiles if p["content_count"] and not p["attendance_document_count"]]
    attendance_only = [p["date"] for p in profiles if p["attendance_document_count"] and not p["content_count"]]
    multiple_content = [p["date"] for p in profiles if p["content_count"] > 1]
    aligned = [p for p in profiles if p["content_count"] and p["attendance_document_count"]]

    if content_only:
        blockers.append("SOURCE_CONTENT_DATE_WITHOUT_ATTENDANCE")
    if attendance_only:
        blockers.append("SOURCE_ATTENDANCE_DATE_WITHOUT_CONTENT")
    if multiple_content:
        blockers.append("SOURCE_MULTIPLE_CONTENTS_SAME_DATE")

    full_coverage = bool(aligned) and len(aligned) == len(profiles) and not blockers
    date_load = full_coverage and all(
        p["single_content_load_equals_attendance_load"] for p in aligned
    )
    date_docs = full_coverage and all(
        p["single_content_load_equals_attendance_documents"] for p in aligned
    )
    per_session = full_coverage and all(
        p["content_count_equals_attendance_documents"]
        and p["declared_load_equal"]
        and p["content_all_declared_one"]
        and p["attendance_all_declared_one"]
        for p in aligned
    )

    if per_session:
        classification = "ONE_CONTENT_PER_SESSION_SUPPORTED"
        action = "REMODEL_9A_USING_SOURCE_SESSION_GRANULARITY"
    elif date_load:
        if date_docs:
            classification = "ONE_CONTENT_PER_DATE_COVERS_SESSION_DOCUMENTS_SUPPORTED"
        else:
            classification = "ONE_CONTENT_PER_DATE_COVERS_DECLARED_LOAD_SUPPORTED"
        action = "REMODEL_9A_BY_DATE_LOAD_NOT_SOURCE_SLOT_EXPANSION"
    else:
        pattern_set = {
            (
                p["single_content_load_equals_attendance_documents"],
                p["single_content_load_equals_attendance_load"],
                p["content_count_equals_attendance_documents"],
            )
            for p in aligned
        }
        if len(pattern_set) > 1 and aligned:
            classification = "MIXED_HISTORICAL_GRANULARITY"
            action = "BLOCK_9A_APPLY_AND_REVIEW_MIXED_SOURCE_GRANULARITY"
        else:
            classification = "INSUFFICIENT_OR_CONFLICTING_EVIDENCE"
            action = "BLOCK_9A_APPLY"

    return {
        "classification": classification,
        "recommended_action": action,
        "blockers": sorted(set(blockers)),
        "content_only_dates": content_only,
        "attendance_only_dates": attendance_only,
        "multiple_content_dates": multiple_content,
    }


def run_source_semantic_calibration(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("R2E_GLOBAL_STRATEGY_REQUIRED")

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
            if _sid(p["source_class"]) == CALIBRATION_SOURCE_CLASS
            and _sid(p["target_class"]) == SESSION_TARGET_CLASS
        )
        source_id = context["class_ids"][_sid(pair["source_class"])]

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
        source_items = sorted(
            list(source.get("items") or []),
            key=lambda item: (
                item.get("source_date") or "",
                item.get("payload_fingerprint") or "",
            ),
        )
        content_by_day, invalid_content = _content_day_index(source_items)

        attendance_rows = _calibration_attendance_rows(
            db,
            class_id=source_id,
            math_ids=context["math_ids"],
            start_date=start_date,
            end_date=end_date,
        )
        attendance_index = _index_target_sessions(attendance_rows)
        attendance_by_day = _attendance_day_index(attendance_index)

        all_days = sorted(set(content_by_day) | set(attendance_by_day))
        profiles = [
            _day_profile(
                day,
                content_by_day.get(day, []),
                attendance_by_day.get(day, []),
            )
            for day in all_days
        ]

        structural_blockers = list(source.get("blockers") or [])
        if invalid_content:
            structural_blockers.append("SOURCE_NUMBER_OF_CLASSES_INVALID")
        if attendance_index.get("collision_days"):
            structural_blockers.append("SOURCE_ATTENDANCE_SESSION_KEY_COLLISION")
        if attendance_index.get("partial_metadata_days"):
            structural_blockers.append("SOURCE_ATTENDANCE_SESSION_METADATA_PARTIAL")

        decision = _classify_source_semantics(
            profiles,
            structural_blockers=structural_blockers,
        )

        month_summary = {}
        for month in months:
            month_profiles = [p for p in profiles if p["month"] == month]
            month_summary[month] = {
                "date_total": len(month_profiles),
                "content_record_total": sum(p["content_count"] for p in month_profiles),
                "attendance_document_total": sum(
                    p["attendance_document_count"] for p in month_profiles
                ),
                "content_declared_load_total": sum(
                    p["content_declared_load_sum"] for p in month_profiles
                ),
                "attendance_declared_load_total": sum(
                    p["attendance_declared_load_sum"] for p in month_profiles
                ),
                "single_content_load_matches_attendance_load_dates": sum(
                    1 for p in month_profiles
                    if p["single_content_load_equals_attendance_load"]
                ),
                "single_content_load_matches_attendance_documents_dates": sum(
                    1 for p in month_profiles
                    if p["single_content_load_equals_attendance_documents"]
                ),
            }

        summary = {
            "content_record_total": len(source_items),
            "content_distinct_date_total": len(content_by_day),
            "content_declared_load_total": sum(
                p["content_declared_load_sum"] for p in profiles
            ),
            "attendance_document_total": len(attendance_rows),
            "attendance_distinct_date_total": len(attendance_by_day),
            "attendance_declared_load_total": sum(
                p["attendance_declared_load_sum"] for p in profiles
            ),
            "attendance_aula_numero_present_count": int(
                attendance_index.get("aula_numero_present_count") or 0
            ),
            "attendance_period_present_count": int(
                attendance_index.get("period_present_count") or 0
            ),
            "session_collision_day_count": len(attendance_index.get("collision_days") or []),
            "partial_session_metadata_day_count": len(
                attendance_index.get("partial_metadata_days") or []
            ),
            "aligned_date_count": sum(
                1 for p in profiles if p["content_count"] and p["attendance_document_count"]
            ),
            "single_content_date_count": sum(1 for p in profiles if p["single_content_date"]),
            "single_content_load_matches_attendance_load_date_count": sum(
                1 for p in profiles if p["single_content_load_equals_attendance_load"]
            ),
            "single_content_load_matches_attendance_documents_date_count": sum(
                1 for p in profiles if p["single_content_load_equals_attendance_documents"]
            ),
            "classification": decision["classification"],
            "recommended_action": decision["recommended_action"],
            "blockers": decision["blockers"],
        }

        result = {
            "schema": CALIBRATION_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "source_class": CALIBRATION_SOURCE_CLASS,
            "component_name": _sid(case["component_name"]),
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
            "monthly": month_summary,
            "date_profiles": profiles,
            "content_only_dates": decision.get("content_only_dates", []),
            "attendance_only_dates": decision.get("attendance_only_dates", []),
            "multiple_content_dates": decision.get("multiple_content_dates", []),
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
                "automatic_semantic_rule_application": False,
                "deploy_performed": False,
                "fail_closed_on_mixed_or_inconclusive": True,
            },
        }
        result["calibration_hash"] = _canonical_hash(result)
        return result
    finally:
        client.close()
