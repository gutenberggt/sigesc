from pathlib import Path

from scripts.audit_dvd_schedule_blockers import (
    choose_schedule_document,
    diagnose_component_schedule,
    recovery_bucket,
)


def test_exact_current_year_is_the_only_auto_eligible_schedule():
    state, doc = choose_schedule_document(
        [
            {"id": "old", "academic_year": 2025},
            {"id": "current", "academic_year": 2026},
        ],
        2026,
    )
    assert state == "schedule_exact_year"
    assert doc["id"] == "current"


def test_other_year_is_never_used_as_automatic_fallback():
    state, doc = choose_schedule_document(
        [{"id": "old", "academic_year": 2025}],
        2026,
    )
    assert state == "schedule_other_year_only"
    assert doc is None


def test_duplicate_current_year_fails_closed():
    state, doc = choose_schedule_document(
        [
            {"id": "a", "academic_year": 2026},
            {"id": "b", "academic_year": "2026"},
        ],
        2026,
    )
    assert state == "schedule_duplicate_current_year"
    assert doc is None


def test_missing_year_requires_review_even_when_document_exists():
    state, doc = choose_schedule_document([{"id": "legacy-no-year"}], 2026)
    assert state == "schedule_year_missing"
    assert doc["id"] == "legacy-no-year"


def test_exact_component_with_canonical_times_is_ready():
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
    result = diagnose_component_schedule(schedule, course_id="course-1", course_name="Matemática")
    assert result["code"] == "schedule_ready"
    assert result["complete_slots"] == 2


def test_course_name_match_with_different_id_is_only_mapping_review():
    schedule = {
        "schedule_slots": [
            {
                "day": "segunda",
                "slot_number": 1,
                "course_id": "legacy-alias",
                "course_name": "Língua Portuguesa",
            }
        ],
        "slot_times": {"1": {"start": "07:00", "end": "07:45"}},
    }
    result = diagnose_component_schedule(
        schedule,
        course_id="canonical-id",
        course_name="Lingua Portuguesa",
    )
    assert result["code"] == "component_id_mismatch_name_match"
    assert result["schedule_course_ids"] == ["legacy-alias"]
    assert recovery_bucket("schedule_exact_year", result["code"]) == "component_mapping_review"


def test_alternate_slot_time_keys_are_parser_gap_not_data_loss():
    schedule = {
        "schedule_slots": [
            {"day": "terça", "slot_number": 3, "course_id": "course-1"}
        ],
        "slot_times": {
            "3": {"start_time": "08:30", "end_time": "09:15"}
        },
    }
    result = diagnose_component_schedule(schedule, course_id="course-1")
    assert result["code"] == "parser_gap_alt_time_keys"
    assert result["complete_slots"] == 1
    assert recovery_bucket("schedule_exact_year", result["code"]) == "code_only"


def test_missing_time_remains_real_data_fix():
    schedule = {
        "schedule_slots": [
            {"day": "segunda", "slot_number": 1, "course_id": "course-1"}
        ],
        "slot_times": {},
    }
    result = diagnose_component_schedule(schedule, course_id="course-1")
    assert result["code"] == "slot_time_missing"
    assert recovery_bucket("schedule_exact_year", result["code"]) == "schedule_data_fix_needed"


def test_invalid_weekday_is_not_guessed():
    schedule = {
        "schedule_slots": [
            {"day": "dia-qualquer", "slot_number": 1, "course_id": "course-1"}
        ],
        "slot_times": {"1": {"start": "07:00", "end": "07:45"}},
    }
    result = diagnose_component_schedule(schedule, course_id="course-1")
    assert result["code"] == "slot_weekday_invalid"


def test_phase38c_source_contains_no_mongodb_mutators():
    backend = Path(__file__).resolve().parents[1]
    path = backend / "scripts" / "audit_dvd_schedule_blockers.py"
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
        assert token not in text, f"Diagnóstico 38C read-only contém mutador {token}"
