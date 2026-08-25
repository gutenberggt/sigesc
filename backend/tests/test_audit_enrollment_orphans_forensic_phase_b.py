from scripts.audit_enrollment_orphans_forensic_phase_b import (
    SAFE_STUDENT_FIELDS,
    _latest_snapshot,
    _safe_event,
    classify_missing_class,
    classify_missing_student,
)


def test_missing_student_academic_and_delete_labels():
    labels = classify_missing_student(
        grades=5,
        attendance=94,
        history_docs=1,
        audit_events=7,
        delete_events=1,
        same_number_candidates=0,
        same_name_candidates=0,
    )
    assert "ACADEMIC_DATA_PRESENT" in labels
    assert "STUDENT_DELETE_AUDITED" in labels
    assert "NO_TRACE" not in labels


def test_missing_student_audit_only_label():
    labels = classify_missing_student(
        grades=0,
        attendance=0,
        history_docs=0,
        audit_events=2,
        delete_events=0,
        same_number_candidates=0,
        same_name_candidates=0,
    )
    assert labels == ["AUDIT_TRACE_ONLY"]


def test_candidate_labels_are_explicit_not_auto_repair():
    labels = classify_missing_student(
        grades=0,
        attendance=0,
        history_docs=1,
        audit_events=2,
        delete_events=1,
        same_number_candidates=1,
        same_name_candidates=2,
    )
    assert "CURRENT_STUDENT_SAME_ENROLLMENT_NUMBER" in labels
    assert "CURRENT_STUDENT_SAME_NAME" in labels


def test_missing_class_inactive_unassigned_no_references():
    labels = classify_missing_class(
        student_status="inactive",
        student_class_id="",
        active_other_enrollments=0,
        class_delete_events=0,
        class_evidence_total=0,
    )
    assert "STUDENT_CURRENTLY_INACTIVE_UNASSIGNED" in labels
    assert "NO_CLASS_REFERENCES_REMAIN" in labels


def test_latest_snapshot_prefers_delete_old_value_and_safe_fields():
    events = [
        {
            "action": "update",
            "timestamp": "2026-03-01T10:00:00+00:00",
            "new_value": {"full_name": "Aluno A", "status": "active", "cpf": "should-not-leak"},
        },
        {
            "action": "delete",
            "timestamp": "2026-04-01T10:00:00+00:00",
            "old_value": {"full_name": "Aluno A", "status": "inactive", "cpf": "should-not-leak"},
        },
    ]
    snapshot = _latest_snapshot(events, SAFE_STUDENT_FIELDS)
    assert snapshot["full_name"] == "Aluno A"
    assert snapshot["status"] == "inactive"
    assert snapshot["_snapshot_from_action"] == "delete"
    assert "cpf" not in snapshot


def test_safe_event_does_not_expose_unlisted_fields():
    event = {
        "action": "delete",
        "collection": "students",
        "timestamp": "2026-04-01T10:00:00+00:00",
        "old_value": {"full_name": "Aluno A", "cpf": "hidden"},
        "new_value": None,
        "changes": None,
    }
    safe = _safe_event(event, SAFE_STUDENT_FIELDS)
    assert safe["old_value"]["full_name"] == "Aluno A"
    assert "cpf" not in safe["old_value"]
