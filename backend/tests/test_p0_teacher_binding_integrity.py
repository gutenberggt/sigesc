from scripts.audit_teacher_binding_integrity_p0 import (
    assert_read_only,
    binding_state,
    build_identity_indexes,
    resolve_staff_identity,
)
from services.course_reference_integrity import (
    COURSE_REFERENCE_SPECS,
    extract_reference_ids,
)


def test_p0_auditor_is_statically_read_only():
    assert_read_only()


def test_course_reference_registry_covers_critical_pedagogical_surfaces():
    pairs = {(spec.collection, spec.field) for spec in COURSE_REFERENCE_SPECS}
    expected = {
        ("teacher_assignments", "course_id"),
        ("teacher_allocations", "course_id"),
        ("teacher_class_assignments", "component_id"),
        ("class_schedules", "schedule_slots.course_id"),
        ("grades", "course_id"),
        ("attendance", "course_id"),
        ("content_entries", "component_id"),
        ("learning_objects", "course_id"),
        ("student_dependencies", "course_id"),
    }
    assert expected <= pairs


def test_extract_reference_ids_handles_nested_schedule_slots():
    document = {
        "schedule_slots": [
            {"course_id": "course-a"},
            {"course_id": "course-b"},
            {"course_id": None},
        ]
    }
    assert extract_reference_ids(document, "schedule_slots.course_id") == ["course-a", "course-b"]


def test_binding_state_matrix_is_explicit():
    assert binding_state({"legacy", "allocation", "dvd"}) == "ALL_THREE_OK"
    assert binding_state({"legacy", "allocation"}) == "LEGACY_AND_ALLOCATION_MISSING_DVD"
    assert binding_state({"legacy", "dvd"}) == "LEGACY_AND_DVD_MISSING_ALLOCATION"
    assert binding_state({"allocation", "dvd"}) == "ALLOCATION_AND_DVD_MISSING_LEGACY"
    assert binding_state({"legacy"}) == "LEGACY_ONLY"
    assert binding_state({"allocation"}) == "ALLOCATION_ONLY"
    assert binding_state({"dvd"}) == "DVD_ONLY"


def test_identity_resolution_prefers_staff_user_id():
    staff = [
        {"id": "staff-1", "user_id": "user-1", "email": "old@example.com"},
        {"id": "staff-2", "user_id": "user-2", "email": "teacher@example.com"},
    ]
    by_uid, by_email = build_identity_indexes(staff)
    resolved, mode = resolve_staff_identity(
        "user-1",
        user_by_id={"user-1": {"email": "teacher@example.com"}},
        staff_by_user_id=by_uid,
        staff_by_email=by_email,
    )
    assert resolved == "staff-1"
    assert mode == "USER_ID"


def test_identity_resolution_uses_unique_email_only_as_legacy_fallback():
    staff = [{"id": "staff-1", "email": "Teacher@Example.com"}]
    by_uid, by_email = build_identity_indexes(staff)
    resolved, mode = resolve_staff_identity(
        "user-1",
        user_by_id={"user-1": {"email": "teacher@example.com"}},
        staff_by_user_id=by_uid,
        staff_by_email=by_email,
    )
    assert resolved == "staff-1"
    assert mode == "EMAIL_FALLBACK"


def test_identity_resolution_fails_closed_on_ambiguous_email():
    staff = [
        {"id": "staff-1", "email": "teacher@example.com"},
        {"id": "staff-2", "email": "TEACHER@example.com"},
    ]
    by_uid, by_email = build_identity_indexes(staff)
    resolved, mode = resolve_staff_identity(
        "user-1",
        user_by_id={"user-1": {"email": "teacher@example.com"}},
        staff_by_user_id=by_uid,
        staff_by_email=by_email,
    )
    assert resolved is None
    assert mode == "AMBIGUOUS_EMAIL"
