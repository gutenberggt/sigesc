from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f1_readonly_audit.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f1", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_authorized_target_has_exactly_6_pairs():
    assert len(mod.TARGET_PAIRS) == 6
    assert len(set(mod.TARGET_PAIRS)) == 6
    assert ("6º ANO A", "Matemática") in mod.TARGET_PAIRS
    assert ("9º ANO A", "Matemática") in mod.TARGET_PAIRS
    assert all(course == "Matemática" for _class, course in mod.TARGET_PAIRS)


def test_name_normalization_handles_accents_and_ordinals():
    assert mod._norm("Matemática") == mod._norm("MATEMATICA")
    assert mod._norm("6º ANO A") == mod._norm("6o ano a")
    assert mod._norm("9º ANO A") == mod._norm("9o ano a")


def test_content_partition_separates_current_historical_and_assignmentless():
    rows = [
        {"date": "2026-03-01", "assignment_id": "current"},
        {"date": "2026-04-01", "assignment_id": "old"},
        {"date": "2026-05-01", "assignment_id": None},
        {"date": "2026-06-01", "assignment_id": "other"},
    ]
    result = mod._partition_content_entries(
        rows,
        current_assignment_ids={"current"},
        target_teacher_assignment_ids={"current", "old"},
        target_teacher_id="teacher-1",
        assignment_owner_by_id={"current": "teacher-1", "old": "teacher-1", "other": "teacher-2"},
    )
    assert result["current_assignment"]["documents"] == 1
    assert result["historical_same_teacher_assignment"]["documents"] == 1
    assert result["without_assignment_id"]["documents"] == 1
    assert result["foreign_or_unknown_assignment"]["documents"] == 1
    assert "current" not in result["current_assignment"]["assignment_fingerprints"]


def test_attendance_partition_does_not_read_student_records_and_marks_class_daily():
    rows = [
        {
            "date": "2026-03-01",
            "academic_year": 2026,
            "course_id": "course-1",
            "assignment_id": "current",
            "teacher_id": "teacher-1",
            "class_id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-1",
            "assignment_profile_at_record": "regular",
            "assignment_schema_version_at_record": 1,
        },
        {
            "date": "2026-03-02",
            "academic_year": "2026",
            "course_id": None,
            "assignment_id": None,
        },
    ]
    result = mod._partition_attendance(
        rows,
        current_assignment_ids={"current"},
        target_teacher_assignment_ids={"current"},
        target_teacher_id="teacher-1",
        assignment_owner_by_id={"current": "teacher-1"},
        target_course_id="course-1",
    )
    assert result["current_assignment"]["documents"] == 1
    assert result["current_assignment"]["snapshot_complete"] == 1
    assert result["legacy_class_daily_unattributed"]["documents"] == 1
    assert result["legacy_class_daily_unattributed"]["academic_year_types"] == {"str": 1}


def test_root_causes_identify_historical_assignment_drift():
    causes = mod._root_causes(
        current_diaries=[{"assignment_id": "new"}],
        content_legacy=[],
        content_partition={
            "current_assignment": {"documents": 0},
            "historical_same_teacher_assignment": {"documents": 3},
            "other_same_teacher_assignment": {"documents": 0},
            "without_assignment_id": {"documents": 0},
            "foreign_or_unknown_assignment": {"documents": 0},
        },
        legacy_visible_count=0,
        legacy_after_cutover_count=0,
        attendance_partition={
            "current_assignment": {"documents": 0, "snapshot_incomplete": 0, "academic_year_types": {}},
            "historical_same_teacher_assignment": {"documents": 2},
            "other_same_teacher_assignment": {"documents": 0},
            "legacy_same_course_without_assignment": {"documents": 0},
            "foreign_or_unknown_assignment": {"documents": 0},
            "legacy_class_daily_unattributed": {"documents": 0},
        },
    )
    assert "CONTENT_ON_HISTORICAL_ASSIGNMENT" in causes
    assert "ATTENDANCE_ON_HISTORICAL_ASSIGNMENT" in causes
    assert "NO_CURRENT_CANONICAL_DIARY" not in causes


def test_fingerprint_never_emits_raw_identifier():
    raw = "assignment-sensitive-id"
    fingerprint = mod._fp(raw)
    assert fingerprint
    assert fingerprint != raw
    assert len(fingerprint) == 12
