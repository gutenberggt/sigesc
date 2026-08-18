from pathlib import Path

from scripts.audit_dvd_first_wave_manifest import (
    build_manifest_weekly_slots,
    deterministic_proposed_id,
    first_wave_blocker,
)


def _plan(**overrides):
    row = {
        "teacher_user_id": "user-1",
        "is_substitution": False,
        "non_substitute_teachers_same_class_course": 1,
        "has_grade_evidence": True,
    }
    row.update(overrides)
    return row


def _recovery(state="schedule_ready", evidence=None):
    return {"recovery_state": state, "evidence": evidence}


def test_first_wave_requires_resolved_teacher():
    assert first_wave_blocker(_plan(teacher_user_id=None), _recovery()) == "teacher_identity_unresolved"


def test_first_wave_rejects_substitution_and_multi_teacher():
    assert first_wave_blocker(_plan(is_substitution=True), _recovery()) == "substitution_review"
    assert (
        first_wave_blocker(
            _plan(non_substitute_teachers_same_class_course=2), _recovery()
        )
        == "shared_or_multi_teacher_review"
    )


def test_first_wave_does_not_guess_regular_without_grade_evidence():
    assert (
        first_wave_blocker(_plan(has_grade_evidence=False), _recovery())
        == "regular_or_integrator_review"
    )


def test_first_wave_accepts_ready_or_deterministic_schedule_only():
    assert first_wave_blocker(_plan(), _recovery("schedule_ready")) is None
    assert (
        first_wave_blocker(
            _plan(), _recovery("time_recoverable_unique_school_shift")
        )
        is None
    )
    assert (
        first_wave_blocker(_plan(), _recovery("time_pattern_no_safe_evidence"))
        == "schedule:time_pattern_no_safe_evidence"
    )


def test_build_weekly_slots_from_existing_exact_schedule():
    schedule = {
        "schedule_slots": [
            {"day": "segunda", "slot_number": 1, "course_id": "course-1"},
            {"day": "quarta", "slot_number": 2, "course_id": "course-1"},
        ],
        "slot_times": {
            "1": {"start": "07:00", "end": "07:45"},
            "2": {"start": "07:45", "end": "08:30"},
        },
    }
    slots = build_manifest_weekly_slots(
        schedule,
        course_id="course-1",
        recovery_row=_recovery("schedule_ready"),
    )
    assert slots == [
        {"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:45"},
        {"weekday": 3, "aula_numero": 2, "start_time": "07:45", "end_time": "08:30"},
    ]


def test_build_weekly_slots_from_deterministic_recovery_evidence():
    schedule = {
        "schedule_slots": [
            {"day": "terca", "slot_number": 3, "course_id": "course-1"},
        ],
        "slot_times": {},
    }
    recovery = _recovery(
        "time_recoverable_unique_school_shift",
        {
            "required_slots": [3],
            "pattern": {"3": {"start": "08:30", "end": "09:15"}},
            "donor_classes": ["class-donor"],
        },
    )
    slots = build_manifest_weekly_slots(schedule, course_id="course-1", recovery_row=recovery)
    assert slots == [
        {"weekday": 2, "aula_numero": 3, "start_time": "08:30", "end_time": "09:15"}
    ]


def test_weekly_slots_fail_closed_if_day_or_time_missing():
    schedule = {
        "schedule_slots": [{"slot_number": 1, "course_id": "course-1"}],
        "slot_times": {"1": {"start": "07:00", "end": "07:45"}},
    }
    assert (
        build_manifest_weekly_slots(
            schedule,
            course_id="course-1",
            recovery_row=_recovery("schedule_ready"),
        )
        == []
    )


def test_proposed_id_is_deterministic_and_cutover_date_sensitive():
    kwargs = {
        "source_legacy_assignment_id": "legacy-1",
        "teacher_id": "teacher-1",
        "class_id": "class-1",
        "component_id": "course-1",
        "valid_from": "2026-08-18",
    }
    first = deterministic_proposed_id(**kwargs)
    second = deterministic_proposed_id(**kwargs)
    assert first == second
    assert first != deterministic_proposed_id(**{**kwargs, "valid_from": "2026-08-19"})


def test_phase38e_source_contains_no_mongodb_mutators():
    backend = Path(__file__).resolve().parents[1]
    path = backend / "scripts" / "audit_dvd_first_wave_manifest.py"
    text = path.read_text(encoding="utf-8")
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
    for token in forbidden:
        assert token not in text, f"Manifesto 38E read-only contém mutador {token}"
