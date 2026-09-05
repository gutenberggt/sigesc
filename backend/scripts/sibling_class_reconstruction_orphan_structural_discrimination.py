"""R2.0c.1 — discriminação estrutural read-only dos 2 attendance de 30/04.

Overlay executado após R2.0c. Lê somente metadados explicitamente projetados da
coleção ``attendance``. ``records`` nunca é projetado. O resultado publica apenas
presença/equivalência, hashes de assinaturas sanitizadas e classificações; IDs
brutos e plaintext de observações nunca são emitidos.
"""

# ruff: noqa: F821

from datetime import datetime

STRUCTURAL_SCHEMA = "SIBLING_CLASS_ORPHAN_STRUCTURAL_DISCRIMINATION_V1"
STRUCTURAL_TARGET_CLASS = "9º ANO A"
STRUCTURAL_DATE = "2026-04-30"

STRUCTURAL_ATTENDANCE_PROJECTION = {
    "_id": 0,
    "id": 1,
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
    "observations": 1,
    "created_at": 1,
    "updated_at": 1,
    "attendance_mode": 1,
    "attendance_purpose": 1,
    "historical_backfill": 1,
    "historical_backfill_source": 1,
    "historical_backfill_last_authorized_assignment_id": 1,
    "historical_backfill_last_authorized_at": 1,
    "legacy_historical_record": 1,
    "source": 1,
    "migrated": 1,
    "migrated_from": 1,
    "legacy": 1,
}

ACTOR_COMPARE_FIELDS = (
    "recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"
)
PROVENANCE_MARKER_FIELDS = (
    "historical_backfill",
    "historical_backfill_source",
    "historical_backfill_last_authorized_assignment_id",
    "historical_backfill_last_authorized_at",
    "legacy_historical_record",
    "source",
    "migrated",
    "migrated_from",
    "legacy",
)


def _norm_optional(value):
    raw = _sid(value)
    return raw.casefold() if raw else None


def _int_or_default(value, default=1):
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _timestamp(value):
    if isinstance(value, datetime):
        return value
    raw = _sid(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _observation_fingerprint(row):
    raw = _sid(row.get("observations"))
    return _fp(raw, 24) if raw else None


def _actor_vector(row):
    return tuple(_sid(row.get(field)) or None for field in ACTOR_COMPARE_FIELDS)


def _business_signature_payload(row):
    """Assinatura sem IDs de documento, timestamps ou versão.

    ``assignment_id`` e atores ficam fora daqui de propósito: são proveniência,
    não prova de que duas sessões pedagógicas são semanticamente diferentes.
    """
    return {
        "class": _sid(row.get("class_id")),
        "course": _sid(row.get("course_id")),
        "date": _iso_day(row.get("date")),
        "academic_year": _int_or_default(row.get("academic_year"), 0),
        "number_of_classes": _int_or_default(row.get("number_of_classes"), 1),
        "period": _norm_optional(row.get("period")),
        "aula_numero": _sid(row.get("aula_numero")) or None,
        "observations_fp": _observation_fingerprint(row),
    }


def _session_signature_payload(row):
    return {
        "number_of_classes": _int_or_default(row.get("number_of_classes"), 1),
        "period": _norm_optional(row.get("period")),
        "aula_numero": _sid(row.get("aula_numero")) or None,
    }


def _provenance_signature_payload(row):
    return {
        "actor_vector": _actor_vector(row),
        "assignment": _sid(row.get("assignment_id")) or None,
        "attendance_mode": _norm_optional(row.get("attendance_mode")),
        "attendance_purpose": _norm_optional(row.get("attendance_purpose")),
        "markers": {
            field: bool(row.get(field))
            for field in PROVENANCE_MARKER_FIELDS
        },
    }


def _legacy_evidence(row):
    markers = {
        field: bool(row.get(field))
        for field in PROVENANCE_MARKER_FIELDS
    }
    explicit = any(markers.values())
    historical_authorization = bool(
        row.get("historical_backfill_last_authorized_assignment_id")
        or row.get("historical_backfill_last_authorized_at")
    )
    return {
        "assignment_present": bool(_sid(row.get("assignment_id"))),
        "explicit_legacy_or_migration_marker": explicit,
        "historical_authorization_marker": historical_authorization,
    }


def _safe_document_meta(row):
    business = _business_signature_payload(row)
    session = _session_signature_payload(row)
    provenance = _provenance_signature_payload(row)
    legacy = _legacy_evidence(row)
    return {
        "business_signature": _canonical_hash(business),
        "session_signature": _canonical_hash(session),
        "provenance_signature": _canonical_hash(provenance),
        "number_of_classes": business["number_of_classes"],
        "period_present": business["period"] is not None,
        "aula_numero_present": business["aula_numero"] is not None,
        "observations_present": business["observations_fp"] is not None,
        "version": _int_or_default(row.get("version"), 1),
        "assignment_present": legacy["assignment_present"],
        "explicit_legacy_or_migration_marker": legacy[
            "explicit_legacy_or_migration_marker"
        ],
        "historical_authorization_marker": legacy[
            "historical_authorization_marker"
        ],
        "created_at_day": _iso_day(row.get("created_at")),
        "updated_at_day": _iso_day(row.get("updated_at")),
    }


def _gap_seconds(left, right, field):
    a = _timestamp(left.get(field))
    b = _timestamp(right.get(field))
    if not a or not b:
        return None
    try:
        return int(abs((a - b).total_seconds()))
    except TypeError:
        return None


def _same_or_both_absent(left, right, field):
    a = _sid(left.get(field)) or None
    b = _sid(right.get(field)) or None
    return a == b


def _structural_comparison(left, right):
    left_business = _business_signature_payload(left)
    right_business = _business_signature_payload(right)
    left_session = _session_signature_payload(left)
    right_session = _session_signature_payload(right)
    left_provenance = _provenance_signature_payload(left)
    right_provenance = _provenance_signature_payload(right)

    period_left, period_right = left_session["period"], right_session["period"]
    aula_left, aula_right = left_session["aula_numero"], right_session["aula_numero"]

    period_distinct = bool(
        period_left is not None
        and period_right is not None
        and period_left != period_right
    )
    aula_distinct = bool(
        aula_left is not None
        and aula_right is not None
        and aula_left != aula_right
    )
    session_presence_asymmetry = bool(
        (period_left is None) != (period_right is None)
        or (aula_left is None) != (aula_right is None)
    )
    class_count_diff = (
        left_session["number_of_classes"] != right_session["number_of_classes"]
    )

    legacy_left = _legacy_evidence(left)
    legacy_right = _legacy_evidence(right)
    assignment_asymmetry = (
        legacy_left["assignment_present"] != legacy_right["assignment_present"]
    )
    legacy_marker_asymmetry = (
        legacy_left["explicit_legacy_or_migration_marker"]
        != legacy_right["explicit_legacy_or_migration_marker"]
        or legacy_left["historical_authorization_marker"]
        != legacy_right["historical_authorization_marker"]
    )

    same_academic_identity = all(
        left_business[key] == right_business[key]
        for key in ("class", "course", "date", "academic_year")
    )
    business_equal = left_business == right_business
    session_equal = left_session == right_session
    provenance_equal = left_provenance == right_provenance
    actor_vector_equal = _actor_vector(left) == _actor_vector(right)
    assignment_equal = _same_or_both_absent(left, right, "assignment_id")
    observation_equal = (
        left_business["observations_fp"] == right_business["observations_fp"]
    )

    strong_distinct_session = bool(
        same_academic_identity
        and (period_distinct or aula_distinct)
        and not session_presence_asymmetry
    )

    strong_legacy_canonical_overlap = bool(
        same_academic_identity
        and business_equal
        and actor_vector_equal
        and assignment_asymmetry
        and legacy_marker_asymmetry
        and (
            legacy_left["explicit_legacy_or_migration_marker"]
            or legacy_right["explicit_legacy_or_migration_marker"]
            or legacy_left["historical_authorization_marker"]
            or legacy_right["historical_authorization_marker"]
        )
    )

    duplicate_supported = bool(
        same_academic_identity
        and business_equal
        and session_equal
        and provenance_equal
        and actor_vector_equal
        and assignment_equal
        and not strong_distinct_session
    )

    structural_conflict = bool(
        not same_academic_identity
        or class_count_diff
        or session_presence_asymmetry
        or (
            not actor_vector_equal
            and not strong_legacy_canonical_overlap
        )
    )

    return {
        "same_academic_identity": same_academic_identity,
        "business_signature_equal": business_equal,
        "session_signature_equal": session_equal,
        "provenance_signature_equal": provenance_equal,
        "actor_vector_equal": actor_vector_equal,
        "assignment_equal": assignment_equal,
        "assignment_presence_asymmetry": assignment_asymmetry,
        "legacy_marker_asymmetry": legacy_marker_asymmetry,
        "observations_fingerprint_equal": observation_equal,
        "period_distinct_with_both_present": period_distinct,
        "aula_numero_distinct_with_both_present": aula_distinct,
        "session_presence_asymmetry": session_presence_asymmetry,
        "number_of_classes_different": class_count_diff,
        "created_at_equal": _sid(left.get("created_at")) == _sid(right.get("created_at")),
        "updated_at_equal": _sid(left.get("updated_at")) == _sid(right.get("updated_at")),
        "created_at_gap_seconds_abs": _gap_seconds(left, right, "created_at"),
        "updated_at_gap_seconds_abs": _gap_seconds(left, right, "updated_at"),
        "strong_distinct_session_evidence": strong_distinct_session,
        "strong_legacy_canonical_overlap_evidence": strong_legacy_canonical_overlap,
        "duplicate_supported_evidence": duplicate_supported,
        "structural_conflict_evidence": structural_conflict,
    }


def run_orphan_structural_discrimination(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("R2C1_GLOBAL_STRATEGY_REQUIRED")

    # Reexecuta R2.0c para provar que o estado adjudicado não mudou.
    adjudication = run_orphan_adjudication(case)
    evidence = adjudication.get("evidence") or {}
    state_expected = bool(
        adjudication.get("orphan_still_exact") is True
        and adjudication.get("classification")
        == "ORPHAN_ATTENDANCE_DUPLICATE_OR_AMBIGUOUS"
        and evidence.get("orphan_attendance_document_count") == 2
    )

    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        context = _resolve_context(db, case)
        target_id = context["class_ids"][STRUCTURAL_TARGET_CLASS]
        rows = list(db.attendance.find(
            {
                "class_id": target_id,
                "course_id": {"$in": sorted(context["math_ids"])},
                "date": STRUCTURAL_DATE,
            },
            STRUCTURAL_ATTENDANCE_PROJECTION,
        ))
        rows = [
            row for row in rows
            if _teacher_attributed(
                row, context["actor_ids"], context["assignment_ids"]
            )
        ]

        exact_two = len(rows) == 2
        if exact_two:
            comparison = _structural_comparison(rows[0], rows[1])
            documents = sorted(
                [_safe_document_meta(rows[0]), _safe_document_meta(rows[1])],
                key=lambda item: _canonical_hash(item),
            )
        else:
            comparison = None
            documents = []

        if not state_expected or not exact_two:
            classification = "ORPHAN_STATE_CHANGED_REVIEW_REQUIRED"
            recommended_action = "BLOCK_APPLY_AND_REPREFLIGHT"
        elif comparison["strong_distinct_session_evidence"]:
            classification = "ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED"
            recommended_action = "REMODEL_9A_PAIRING_BY_SESSION_BEFORE_APPLY"
        elif comparison["strong_legacy_canonical_overlap_evidence"]:
            classification = "ORPHAN_LEGACY_CANONICAL_OVERLAP_SUPPORTED"
            recommended_action = "PREPARE_SEPARATE_ATTENDANCE_SANITIZATION_PHASE"
        elif comparison["duplicate_supported_evidence"]:
            classification = "ORPHAN_DUPLICATE_ATTENDANCE_SUPPORTED"
            recommended_action = "PREPARE_SEPARATE_ATTENDANCE_DUPLICATE_REVIEW_PHASE"
        elif comparison["structural_conflict_evidence"]:
            classification = "ORPHAN_STRUCTURAL_CONFLICT"
            recommended_action = "BLOCK_9A_APPLY_AND_INVESTIGATE_PROVENANCE"
        else:
            classification = "ORPHAN_STRUCTURAL_DISCRIMINATION_INCONCLUSIVE"
            recommended_action = "BLOCK_9A_APPLY"

        result = {
            "schema": STRUCTURAL_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "target_class": STRUCTURAL_TARGET_CLASS,
            "target_date": STRUCTURAL_DATE,
            "r2c_adjudication_hash": adjudication.get("adjudication_hash"),
            "r2b_manifest_hash": adjudication.get("r2b_manifest_hash"),
            "state_expected": state_expected,
            "attendance_document_count": len(rows),
            "classification": classification,
            "recommended_action": recommended_action,
            "documents": documents,
            "comparison": comparison,
            "boundaries": {
                "mongo_reads_only": True,
                "production_writes": False,
                "attendance_records_read": False,
                "students_read": False,
                "enrollments_read": False,
                "grades_read": False,
                "attendance_written": False,
                "content_written": False,
                "observation_plaintext_emitted": False,
                "technical_ids_emitted": False,
                "raw_timestamps_emitted": False,
                "audit_logs_read": False,
                "fail_closed_on_ambiguity": True,
                "automatic_attendance_sanitization": False,
            },
        }
        result["structural_discrimination_hash"] = _canonical_hash(result)
        return result
    finally:
        client.close()
