from pathlib import Path

from scripts.audit_dvd_second_wave_2d_a_forensics import (
    ACADEMIC_YEAR,
    CLASS_ID,
    EXPECTED_CLASS_NAME,
    EXPECTED_SHIFT,
    EXPECTED_SLOTS_PER_DAY,
    SCHOOL_ID,
    STAFF_ID,
    TARGETS,
    TEACHER_USER_ID,
    analyze_schedule_snapshot,
    assert_script_read_only,
    classify_forensic_evidence,
    group_donor_patterns,
    reconstruct_audit_snapshots,
)
from scripts.audit_dvd_schedule_recovery import schedule_time_consensus


def _target_schedule(slot3=None):
    slots = [
        {"day": "segunda", "slot_number": 1, "course_id": "component", "start_time": "07:08", "end_time": "08:00"},
        {"day": "terca", "slot_number": 2, "course_id": "component", "start_time": "08:00", "end_time": "09:00"},
        {"day": "quarta", "slot_number": 4, "course_id": "component", "start_time": "10:30", "end_time": "11:15"},
    ]
    if slot3:
        slots.append(
            {"day": "quinta", "slot_number": 3, "course_id": "component", "start_time": slot3[0], "end_time": slot3[1]}
        )
    return {
        "id": "schedule-target",
        "class_id": CLASS_ID,
        "school_id": SCHOOL_ID,
        "academic_year": ACADEMIC_YEAR,
        "shift": EXPECTED_SHIFT,
        "slots_per_day": 4,
        "schedule_slots": slots,
    }


def test_scope_is_pinned_to_abadia_2d_a():
    assert ACADEMIC_YEAR == 2026
    assert TEACHER_USER_ID == "3d7b951f-0430-49d3-b090-9eda9fd730d7"
    assert STAFF_ID == "90877172-bf65-4e63-a8d2-431dee5b63dd"
    assert SCHOOL_ID == "736ea4a8-60ff-4fe0-9dcd-fa9ab6b76d29"
    assert CLASS_ID == "5a0fe91e-1d61-4787-adf7-b9bc1ffb07a3"
    assert EXPECTED_CLASS_NAME == "5º ANO A"
    assert EXPECTED_SHIFT == "morning"
    assert EXPECTED_SLOTS_PER_DAY == 4
    assert set(TARGETS) == {
        "62235d46-558f-4be0-8e48-397b4fbe5ed5",
        "14939b59-9571-4a16-8ed1-14798876c454",
    }


def test_reconstruct_update_before_after_from_audit_log():
    before = _target_schedule(slot3=("09:30", "10:30"))
    logs = [
        {
            "action": "update",
            "timestamp": "2026-03-01T12:00:00+00:00",
            "document_id": "schedule-target",
            "user_id": "admin-1",
            "old_value": before,
            "new_value": {
                "schedule_slots": [
                    {"day": "segunda", "slot_number": 1, "course_id": "component", "start_time": "07:08", "end_time": "08:00"},
                    {"day": "terca", "slot_number": 2, "course_id": "component", "start_time": "08:00", "end_time": "09:00"},
                    {"day": "quarta", "slot_number": 4, "course_id": "component", "start_time": "10:30", "end_time": "11:15"},
                ]
            },
        }
    ]
    snapshots = reconstruct_audit_snapshots(logs, current_schedule_id="schedule-target")
    assert len(snapshots) == 2
    assert {row["side"] for row in snapshots} == {"update_before", "update_after"}
    before_snapshot = next(row for row in snapshots if row["side"] == "update_before")
    after_snapshot = next(row for row in snapshots if row["side"] == "update_after")
    assert len(before_snapshot["schedule"]["schedule_slots"]) == 4
    assert len(after_snapshot["schedule"]["schedule_slots"]) == 3


def test_historical_complete_pattern_can_be_current_consistent():
    current = _target_schedule(slot3=None)
    consensus = schedule_time_consensus(current)
    historical = _target_schedule(slot3=("09:30", "10:30"))
    analysis = analyze_schedule_snapshot(
        historical,
        component_id="component",
        current_consensus=consensus,
    )
    assert analysis["complete"] is True
    assert analysis["conflicts"] == []
    assert analysis["matching_overlap_slots"] == [1, 2, 4]


def test_conflicting_historical_pattern_is_not_current_consistent():
    current = _target_schedule(slot3=None)
    consensus = schedule_time_consensus(current)
    historical = _target_schedule(slot3=("09:30", "10:30"))
    historical["schedule_slots"][0]["start_time"] = "07:00"
    analysis = analyze_schedule_snapshot(
        historical,
        component_id="component",
        current_consensus=consensus,
    )
    assert analysis["complete"] is True
    assert len(analysis["conflicts"]) == 1
    assert analysis["conflicts"][0]["slot"] == 1


def test_donor_patterns_preserve_ambiguity_and_zero_conflict_count():
    current = _target_schedule(slot3=None)
    consensus = schedule_time_consensus(current)

    donor_1 = _target_schedule(slot3=("09:30", "10:30"))
    donor_1["class_id"] = "donor-1"

    donor_2 = _target_schedule(slot3=("09:20", "10:20"))
    donor_2["class_id"] = "donor-2"

    groups = group_donor_patterns(
        [donor_1, donor_2],
        component_id="component",
        current_consensus=consensus,
        class_by_id={
            "donor-1": {"name": "4º A"},
            "donor-2": {"name": "5º B"},
        },
    )
    assert len(groups) == 2
    assert sum(group["zero_conflict_donors"] for group in groups) == 2


def test_forensic_classification_prefers_unique_consistent_history_but_never_auto_actions():
    historical = [
        {
            "analysis": {
                "complete": True,
                "signature": [[1, "07:08", "08:00"], [2, "08:00", "09:00"], [3, "09:30", "10:30"], [4, "10:30", "11:15"]],
                "conflicts": [],
            }
        }
    ]
    result = classify_forensic_evidence(historical, donor_patterns=[])
    assert result["classification"] == "HISTORICAL_SOURCE_CANDIDATE_REQUIRES_REVIEW"
    assert result["automatic_action"] is False


def test_forensic_classification_keeps_ambiguous_donors_blocked():
    result = classify_forensic_evidence(
        historical_analyses=[],
        donor_patterns=[
            {"zero_conflict_donors": 0},
            {"zero_conflict_donors": 0},
        ],
    )
    assert result["classification"] == "BLOCKED_SOURCE_SCHEDULE_REQUIRES_VALIDATION"
    assert result["automatic_action"] is False


def test_script_is_strictly_read_only():
    assert_script_read_only()
    src = Path("scripts/audit_dvd_second_wave_2d_a_forensics.py").read_text(encoding="utf-8")
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
    )
    executable = "\n".join(
        line
        for line in src.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    )
    assert not any(token in executable for token in forbidden)
    assert "--apply" not in src
    assert "--rollback" not in src
