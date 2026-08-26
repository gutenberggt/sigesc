from scripts.audit_enrollment_orphans_repair_plan_phase_e import (
    _assert_report_safe,
    compare_attendance_docs,
    compare_grade_docs,
    classify_repair_plan,
    norm_cpf,
)


def test_norm_cpf_accepts_formatted_and_rejects_invalid_length():
    assert norm_cpf("123.456.789-01") == "12345678901"
    assert norm_cpf("123") == ""
    assert norm_cpf(None) == ""


def test_compare_grade_docs_detects_mergeable_overlap_and_conflict():
    old_docs = [
        {"class_id": "c1", "course_id": "p", "academic_year": 2026, "b1": 8, "b2": 9},
        {"class_id": "c1", "course_id": "m", "academic_year": 2026, "b1": 7},
    ]
    target_docs = [
        {"class_id": "c1", "course_id": "p", "academic_year": 2026, "b1": 8, "b2": None},
        {"class_id": "c1", "course_id": "m", "academic_year": 2026, "b1": 6},
    ]
    result = compare_grade_docs(old_docs, target_docs)
    assert result["overlap_keys"] == 2
    assert result["mergeable_overlap_keys"] == 1
    assert result["conflicting_overlap_keys"] == 1


def test_compare_attendance_docs_detects_same_document_status_conflict():
    old_docs = [{
        "id": "a1", "date": "2026-03-10", "records": [{"student_id": "old", "status": "present"}]
    }]
    target_docs = [{
        "id": "a1", "date": "2026-03-10", "records": [{"student_id": "new", "status": "absent"}]
    }]
    result = compare_attendance_docs(old_docs, target_docs, "old", "new")
    assert result["old_attendance_rows"] == 1
    assert result["target_attendance_rows"] == 1
    assert result["overlap_rows"] == 1
    assert result["conflicting_overlap_rows"] == 1


def test_classify_repair_plan_prioritizes_identity_shared_and_collisions():
    assert classify_repair_plan(
        verified=False, shared_target=False, target_regular_active=1,
        grade_conflicts=0, attendance_conflicts=0, old_reference_total=0,
    ) == "IDENTITY_REVIEW_REQUIRED"
    assert classify_repair_plan(
        verified=True, shared_target=True, target_regular_active=1,
        grade_conflicts=0, attendance_conflicts=0, old_reference_total=0,
    ) == "SHARED_TARGET_CONSOLIDATION_REQUIRED"
    assert classify_repair_plan(
        verified=True, shared_target=False, target_regular_active=2,
        grade_conflicts=0, attendance_conflicts=0, old_reference_total=0,
    ) == "TARGET_CANONICAL_ENROLLMENT_REVIEW_REQUIRED"
    assert classify_repair_plan(
        verified=True, shared_target=False, target_regular_active=1,
        grade_conflicts=1, attendance_conflicts=0, old_reference_total=2,
    ) == "ACADEMIC_COLLISION_REQUIRES_REVIEW"
    assert classify_repair_plan(
        verified=True, shared_target=False, target_regular_active=1,
        grade_conflicts=0, attendance_conflicts=0, old_reference_total=3,
    ) == "MIGRATE_REFERENCES_THEN_CLOSE_ORPHAN"
    assert classify_repair_plan(
        verified=True, shared_target=False, target_regular_active=1,
        grade_conflicts=0, attendance_conflicts=0, old_reference_total=0,
    ) == "CLOSE_ORPHAN_NO_REFERENCES"


def test_privacy_guard_rejects_sensitive_keys_recursively():
    _assert_report_safe({"case": {"cpf_match_count": 1, "target": {"id": "x"}}})
    try:
        _assert_report_safe({"case": {"cpf": "12345678901"}})
    except RuntimeError as exc:
        assert "Campo sensível" in str(exc)
    else:
        raise AssertionError("privacy guard deveria rejeitar chave cpf")
