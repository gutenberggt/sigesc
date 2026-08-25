from scripts.remediate_dvd_out_of_range_schedule_p0 import (
    build_in_range_weekly_slots,
    deterministic_assignment_id,
)


def _schedule():
    return {
        "slots_per_day": 4,
        "schedule_slots": [
            {"day": "terca", "slot_number": 3, "course_id": "math"},
            {"day": "terca", "slot_number": 4, "course_id": "math"},
            {"day": "quinta", "slot_number": 1, "course_id": "math"},
            {"day": "quinta", "slot_number": 2, "course_id": "math"},
            # Resíduos que ficaram persistidos após a grade ser reduzida para 4 aulas.
            {"day": "quarta", "slot_number": 5, "course_id": "math"},
            {"day": "quinta", "slot_number": 5, "course_id": "math"},
            {"day": "sexta", "slot_number": 3, "course_id": "arte"},
            {"day": "terca", "slot_number": 5, "course_id": "arte"},
            {"day": "sexta", "slot_number": 4, "course_id": "religiao"},
            {"day": "segunda", "slot_number": 5, "course_id": "religiao"},
        ],
        "slot_times": {
            "1": {"start": "07:00", "end": "08:00"},
            "2": {"start": "08:00", "end": "09:00"},
            "3": {"start": "09:30", "end": "10:30"},
            "4": {"start": "10:30", "end": "11:15"},
            "5": {"start": None, "end": "11:00"},
        },
    }


def test_math_uses_only_declared_grid_and_matches_workload():
    result = build_in_range_weekly_slots(
        _schedule(), course_id="math", expected_workload=4
    )

    assert result["ready"] is True
    assert result["blockers"] == []
    assert len(result["weekly_slots"]) == 4
    assert {row["aula_numero"] for row in result["weekly_slots"]} == {1, 2, 3, 4}
    assert len(result["stale_slots"]) == 2
    assert all(row["slot_number"] == 5 for row in result["stale_slots"])


def test_single_weekly_lesson_is_recovered_when_only_extra_slot_is_stale():
    arte = build_in_range_weekly_slots(
        _schedule(), course_id="arte", expected_workload=1
    )
    religiao = build_in_range_weekly_slots(
        _schedule(), course_id="religiao", expected_workload=1
    )

    assert arte["ready"] is True
    assert arte["weekly_slots"] == [
        {"weekday": 5, "aula_numero": 3, "start_time": "09:30", "end_time": "10:30"}
    ]
    assert religiao["ready"] is True
    assert religiao["weekly_slots"] == [
        {"weekday": 5, "aula_numero": 4, "start_time": "10:30", "end_time": "11:15"}
    ]


def test_workload_mismatch_remains_fail_closed():
    result = build_in_range_weekly_slots(
        _schedule(), course_id="math", expected_workload=5
    )

    assert result["ready"] is False
    assert "workload_mismatch:expected=5:valid_slots=4" in result["blockers"]


def test_invalid_time_inside_declared_grid_is_never_ignored():
    schedule = _schedule()
    schedule["slot_times"]["3"] = {"start": None, "end": "10:30"}

    result = build_in_range_weekly_slots(
        schedule, course_id="arte", expected_workload=1
    )

    assert result["ready"] is False
    assert "slot_time_invalid_in_range" in result["blockers"]


def test_scope_requires_actual_out_of_range_residue():
    schedule = _schedule()
    schedule["schedule_slots"] = [
        row for row in schedule["schedule_slots"]
        if not (row["course_id"] == "arte" and row["slot_number"] == 5)
    ]

    result = build_in_range_weekly_slots(
        schedule, course_id="arte", expected_workload=1
    )

    assert result["ready"] is False
    assert "no_out_of_range_residue" in result["blockers"]


def test_assignment_id_is_deterministic():
    args = dict(
        source_legacy_assignment_id="legacy-1",
        teacher_id="teacher-1",
        class_id="class-1",
        component_id="component-1",
        valid_from="2026-08-18",
    )
    assert deterministic_assignment_id(**args) == deterministic_assignment_id(**args)
