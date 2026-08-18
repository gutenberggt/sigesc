from pathlib import Path

from scripts.audit_dvd_cutover_plan import (
    classify_plan_binding,
    extract_weekly_slots,
    grade_has_real_evidence,
)


def test_empty_grade_document_is_not_regular_evidence():
    assert grade_has_real_evidence({"b1": None, "b2": "", "b3": None}) is False
    assert grade_has_real_evidence({"b1": "C"}) is True
    assert grade_has_real_evidence({"b2": 8.5}) is True


def test_unresolved_identity_blocks_before_profile_inference():
    code = classify_plan_binding(
        teacher_user_id=None,
        is_substitution=False,
        non_substitute_teacher_count=1,
        has_grade_evidence=True,
        schedule_state="schedule_ready",
    )
    assert code == "teacher_identity_unresolved"


def test_substitution_is_never_promoted_automatically():
    code = classify_plan_binding(
        teacher_user_id="user-1",
        is_substitution=True,
        non_substitute_teacher_count=1,
        has_grade_evidence=True,
        schedule_state="schedule_ready",
    )
    assert code == "substitution_review"


def test_multiple_teachers_same_component_requires_shared_review():
    code = classify_plan_binding(
        teacher_user_id="user-1",
        is_substitution=False,
        non_substitute_teacher_count=2,
        has_grade_evidence=True,
        schedule_state="schedule_ready",
    )
    assert code == "shared_review"


def test_unique_teacher_with_real_grade_and_schedule_is_regular_ready():
    code = classify_plan_binding(
        teacher_user_id="user-1",
        is_substitution=False,
        non_substitute_teacher_count=1,
        has_grade_evidence=True,
        schedule_state="schedule_ready",
    )
    assert code == "regular_ready"


def test_unique_teacher_without_grade_evidence_is_not_guessed_integrator_or_regular():
    code = classify_plan_binding(
        teacher_user_id="user-1",
        is_substitution=False,
        non_substitute_teacher_count=1,
        has_grade_evidence=False,
        schedule_state="schedule_ready",
    )
    assert code == "regular_or_integrator_review"


def test_schedule_gap_blocks_even_when_grade_exists():
    code = classify_plan_binding(
        teacher_user_id="user-1",
        is_substitution=False,
        non_substitute_teacher_count=1,
        has_grade_evidence=True,
        schedule_state="schedule_missing",
    )
    assert code == "schedule_missing"


def test_extract_weekly_slots_uses_legacy_schedule_without_inventing_times():
    schedule = {
        "schedule_slots": [
            {"day": "segunda", "slot_number": 2, "course_id": "course-1"},
            {"day": "quarta", "slot_number": 1, "course_id": "course-1"},
        ],
        "slot_times": {
            "1": {"start": "07:30", "end": "08:20"},
            "2": {"start": "08:20", "end": "09:10"},
        },
    }
    state, slots = extract_weekly_slots(schedule, "course-1")
    assert state == "schedule_ready"
    assert slots == [
        {"weekday": 1, "aula_numero": 2, "start_time": "08:20", "end_time": "09:10"},
        {"weekday": 3, "aula_numero": 1, "start_time": "07:30", "end_time": "08:20"},
    ]


def test_extract_weekly_slots_fails_closed_on_missing_time():
    schedule = {
        "schedule_slots": [{"day": "segunda", "slot_number": 1, "course_id": "course-1"}],
        "slot_times": {},
    }
    state, slots = extract_weekly_slots(schedule, "course-1")
    assert state == "schedule_incomplete"
    assert slots == []


def test_phase38b_source_contains_no_mongodb_mutators():
    backend = Path(__file__).resolve().parents[1]
    path = backend / "scripts" / "audit_dvd_cutover_plan.py"
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
        assert token not in text, f"Plano 38B read-only contém mutador {token}"
