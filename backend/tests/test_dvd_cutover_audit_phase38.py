from pathlib import Path

from services.dvd_cutover_audit import (
    classify_legacy_binding,
    component_compatible,
    is_current_assignment,
    resolve_teacher_user_id,
    year_or_date_query,
)


def _dvd(
    *,
    id="dvd-1",
    teacher_id="user-1",
    class_id="class-1",
    component_id="course-1",
    valid_from="2026-01-01",
    valid_until=None,
    enabled=True,
    profile="regular",
    student_scope="all",
):
    return {
        "id": id,
        "teacher_id": teacher_id,
        "class_id": class_id,
        "component_id": component_id,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "deleted": False,
        "diary_settings": {
            "enabled": enabled,
            "schema_version": 1,
            "profile": profile,
            "student_scope": student_scope,
        },
    }


def test_component_classwide_is_compatible_but_foreign_component_is_not():
    assert component_compatible(None, "course-1") is True
    assert component_compatible("course-1", "course-1") is True
    assert component_compatible("course-2", "course-1") is False


def test_current_assignment_respects_validity_boundaries():
    assignment = _dvd(valid_from="2026-02-01", valid_until="2026-08-18")
    assert is_current_assignment(assignment, "2026-02-01") is True
    assert is_current_assignment(assignment, "2026-08-18") is True
    assert is_current_assignment(assignment, "2026-08-19") is False


def test_teacher_identity_prefers_user_id_and_falls_back_to_casefold_email():
    users = {"prof@example.com": {"id": "user-email"}}
    assert resolve_teacher_user_id({"user_id": "user-direct"}, users) == "user-direct"
    assert resolve_teacher_user_id({"email": "Prof@Example.COM"}, users) == "user-email"
    assert resolve_teacher_user_id({"email": "unknown@example.com"}, users) is None


def test_unresolved_teacher_identity_never_guesses_dvd():
    result = classify_legacy_binding(
        teacher_user_id=None,
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd()],
    )
    assert result.code == "teacher_identity_unresolved"


def test_missing_dvd_is_reported_as_legacy_gap():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[],
    )
    assert result.code == "dvd_missing"


def test_present_but_disabled_dvd_is_not_counted_as_cutover():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd(enabled=False)],
    )
    assert result.code == "dvd_present_disabled"


def test_expired_dvd_is_not_counted_as_current_cutover():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd(valid_until="2026-08-17")],
    )
    assert result.code == "dvd_present_not_current"


def test_multiple_enabled_compatible_dvds_fail_closed_as_ambiguous():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd(id="dvd-a"), _dvd(id="dvd-b", component_id=None)],
    )
    assert result.code == "dvd_active_ambiguous"
    assert result.active_enabled_dvd_ids == ("dvd-a", "dvd-b")


def test_shared_group_remains_unresolved_for_cutover():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd(profile="shared", student_scope="group")],
    )
    assert result.code == "dvd_active_group_unresolved"


def test_exact_single_enabled_dvd_is_safe_cutover_binding():
    result = classify_legacy_binding(
        teacher_user_id="user-1",
        class_id="class-1",
        course_id="course-1",
        reference_date="2026-08-18",
        dvd_assignments=[_dvd()],
    )
    assert result.code == "dvd_active_exact"
    assert result.active_enabled_dvd_ids == ("dvd-1",)


def test_year_query_covers_metadata_or_record_date():
    query = year_or_date_query(2026)
    assert query["$or"][0]["academic_year"]["$in"] == [2026, "2026"]
    assert query["$or"][1]["date"] == {
        "$gte": "2026-01-01",
        "$lte": "2026-12-31",
    }


def test_auditor_source_contains_no_mongodb_mutators():
    backend = Path(__file__).resolve().parents[1]
    sources = [
        backend / "services" / "dvd_cutover_audit.py",
        backend / "scripts" / "audit_dvd_cutover.py",
    ]
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".create_index(",
        ".drop_index(",
        ".find_one_and_update(",
        ".find_one_and_delete(",
        ".find_one_and_replace(",
    )
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"Auditor read-only contém mutador {token} em {path.name}"
