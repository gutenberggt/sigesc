from pathlib import Path

from scripts.inventory_initial_years_schedule_normalization import (
    ACADEMIC_YEAR,
    SCHEDULE_POLICY,
    TARGET_GRADES,
    assert_script_read_only,
    class_grade_evidence,
    classify_target,
    grade_numbers_from_value,
    proposed_slot_times,
    schedule_shape,
)


def test_policy_is_exactly_pinned_for_morning_and_afternoon():
    assert ACADEMIC_YEAR == 2026
    assert TARGET_GRADES == {1, 2, 3, 4, 5}
    assert SCHEDULE_POLICY == {
        "morning": {
            1: {"start": "07:00", "end": "07:55"},
            2: {"start": "07:55", "end": "08:50"},
            3: {"start": "09:10", "end": "10:05"},
            4: {"start": "10:05", "end": "11:00"},
        },
        "afternoon": {
            1: {"start": "13:00", "end": "13:55"},
            2: {"start": "13:55", "end": "14:50"},
            3: {"start": "15:10", "end": "16:05"},
            4: {"start": "16:05", "end": "17:00"},
        },
    }


def test_grade_parser_accepts_sigesc_values_and_labels():
    assert grade_numbers_from_value("1ano") == {1}
    assert grade_numbers_from_value("2º Ano") == {2}
    assert grade_numbers_from_value("3º ANO A") == {3}
    assert grade_numbers_from_value("4° ANO B") == {4}
    assert grade_numbers_from_value("5 ANO") == {5}
    assert grade_numbers_from_value("1º/2º ANO") == {1, 2}


def test_regular_initial_year_class_is_target():
    cls = {
        "name": "3º ANO A",
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3ano",
        "is_multi_grade": False,
    }
    evidence = class_grade_evidence(cls)
    assert evidence["is_target"] is True
    assert evidence["target_grades"] == [3]
    assert evidence["cross_boundary_multi"] is False


def test_multigrade_inside_1_to_5_is_target_and_not_blocked_by_grade():
    cls = {
        "name": "1º/2º ANO",
        "education_level": "fundamental_anos_iniciais",
        "is_multi_grade": True,
        "series": ["1ano", "2ano"],
        "shift": "morning",
    }
    evidence = class_grade_evidence(cls)
    assert evidence["is_target"] is True
    assert evidence["series_numbers"] == [1, 2]
    assert evidence["cross_boundary_multi"] is False
    status, blockers = classify_target(cls, evidence, [])
    assert status == "READY_NORMALIZE"
    assert blockers == []


def test_cross_boundary_multigrade_is_fail_closed():
    cls = {
        "name": "5º/6º ANO",
        "is_multi_grade": True,
        "series": ["5ano", "6ano"],
        "shift": "morning",
    }
    evidence = class_grade_evidence(cls)
    assert evidence["is_target"] is True
    assert evidence["cross_boundary_multi"] is True
    status, blockers = classify_target(cls, evidence, [])
    assert status == "BLOCKED_REQUIRES_REVIEW"
    assert "MULTI_GRADE_CROSSES_1_TO_5_BOUNDARY" in blockers


def test_morning_and_afternoon_proposals_are_exact():
    assert proposed_slot_times("morning") == {
        "1": {"start": "07:00", "end": "07:55"},
        "2": {"start": "07:55", "end": "08:50"},
        "3": {"start": "09:10", "end": "10:05"},
        "4": {"start": "10:05", "end": "11:00"},
    }
    assert proposed_slot_times("afternoon") == {
        "1": {"start": "13:00", "end": "13:55"},
        "2": {"start": "13:55", "end": "14:50"},
        "3": {"start": "15:10", "end": "16:05"},
        "4": {"start": "16:05", "end": "17:00"},
    }


def test_full_time_or_unknown_shift_requires_review():
    cls = {
        "name": "4º ANO A",
        "grade_level": "4ano",
        "shift": "full_time",
    }
    evidence = class_grade_evidence(cls)
    status, blockers = classify_target(cls, evidence, [])
    assert status == "BLOCKED_REQUIRES_REVIEW"
    assert "SHIFT_WITHOUT_POLICY:full_time" in blockers


def test_extra_slots_above_four_are_never_silently_removed():
    schedule = {
        "id": "schedule-1",
        "shift": "morning",
        "slots_per_day": 5,
        "slot_times": {
            "1": {"start": "07:00", "end": "08:00"},
            "5": {"start": "11:00", "end": "12:00"},
        },
        "schedule_slots": [
            {"day": "segunda", "slot_number": 5, "course_id": "course-x"},
        ],
    }
    shape = schedule_shape(schedule)
    assert shape["extra_slot_numbers"] == [5]

    cls = {
        "name": "5º ANO A",
        "grade_level": "5ano",
        "shift": "morning",
    }
    evidence = class_grade_evidence(cls)
    status, blockers = classify_target(cls, evidence, [schedule])
    assert status == "BLOCKED_REQUIRES_REVIEW"
    assert "EXTRA_SLOTS_ABOVE_4:5" in blockers


def test_multiple_schedules_for_same_class_are_fail_closed():
    cls = {
        "name": "2º ANO A",
        "grade_level": "2ano",
        "shift": "afternoon",
    }
    evidence = class_grade_evidence(cls)
    status, blockers = classify_target(
        cls,
        evidence,
        [{"id": "a"}, {"id": "b"}],
    )
    assert status == "BLOCKED_REQUIRES_REVIEW"
    assert "MULTIPLE_CLASS_SCHEDULES:2" in blockers


def test_script_is_strictly_read_only():
    assert_script_read_only()
    src = Path("scripts/inventory_initial_years_schedule_normalization.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    )
    assert not any(token in src for token in forbidden)
