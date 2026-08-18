from pathlib import Path

from scripts.audit_dvd_schedule_recovery import (
    classify_time_recovery,
    pattern_signature,
    schedule_time_consensus,
)


def test_schedule_time_consensus_accepts_canonical_and_inline_without_conflict():
    schedule = {
        "slot_times": {"1": {"start": "07:00", "end": "07:45"}},
        "schedule_slots": [
            {"slot_number": 1, "start_time": "07:00", "end_time": "07:45"},
            {"slot_number": 2, "start_time": "07:45", "end_time": "08:30"},
        ],
    }
    assert schedule_time_consensus(schedule) == {
        1: ("07:00", "07:45"),
        2: ("07:45", "08:30"),
    }


def test_schedule_time_consensus_drops_conflicting_slot_number():
    schedule = {
        "schedule_slots": [
            {"slot_number": 1, "start_time": "07:00", "end_time": "07:45"},
            {"slot_number": 1, "start_time": "07:10", "end_time": "07:55"},
        ]
    }
    assert schedule_time_consensus(schedule) == {}


def test_pattern_signature_requires_all_needed_slots():
    pattern = {1: ("07:00", "07:45")}
    assert pattern_signature(pattern, {1}) is not None
    assert pattern_signature(pattern, {1, 2}) is None


def test_same_schedule_evidence_has_priority():
    target = {
        "schedule_slots": [
            {"course_id": "c1", "slot_number": 1},
            {"course_id": "other", "slot_number": 1, "start_time": "07:00", "end_time": "07:45"},
        ]
    }
    code, evidence = classify_time_recovery(
        target_schedule=target,
        course_id="c1",
        donor_schedules=[],
    )
    assert code == "time_recoverable_same_schedule"
    assert evidence["pattern"]["1"] == {"start": "07:00", "end": "07:45"}


def test_unique_school_shift_pattern_is_candidate():
    target = {"schedule_slots": [{"course_id": "c1", "slot_number": 2}]}
    donors = [
        {"class_id": "d1", "slot_times": {"2": {"start": "08:00", "end": "08:45"}}},
        {"class_id": "d2", "slot_times": {"2": {"start": "08:00", "end": "08:45"}}},
    ]
    code, evidence = classify_time_recovery(
        target_schedule=target,
        course_id="c1",
        donor_schedules=donors,
    )
    assert code == "time_recoverable_unique_school_shift"
    assert evidence["donor_classes"] == ["d1", "d2"]


def test_conflicting_school_shift_patterns_remain_ambiguous():
    target = {"schedule_slots": [{"course_id": "c1", "slot_number": 2}]}
    donors = [
        {"class_id": "d1", "slot_times": {"2": {"start": "08:00", "end": "08:45"}}},
        {"class_id": "d2", "slot_times": {"2": {"start": "08:10", "end": "08:55"}}},
    ]
    code, evidence = classify_time_recovery(
        target_schedule=target,
        course_id="c1",
        donor_schedules=donors,
    )
    assert code == "time_pattern_ambiguous_school_shift"
    assert evidence["pattern_count"] == 2


def test_phase38d_source_contains_no_mongodb_mutators():
    backend = Path(__file__).resolve().parents[1]
    text = (backend / "scripts" / "audit_dvd_schedule_recovery.py").read_text(encoding="utf-8")
    forbidden = (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
        ".create_index(", ".drop_index(", ".find_one_and_update(",
        ".find_one_and_delete(", ".find_one_and_replace(",
    )
    for token in forbidden:
        assert token not in text, f"38D read-only contém mutador {token}"
