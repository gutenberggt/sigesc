from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_dvd_second_wave_2d_a_forensics as forensic
from scripts.prepare_dvd_second_wave_2d_a1_source_validation import (
    CANDIDATE_PAIR,
    CANDIDATE_SLOT,
    CURRENT_INVALID_PAIR,
    HISTORICAL_CONSISTENT_PAIR,
    QUESTION,
    RESPONSE_OPTIONS,
    SourceValidationGateError,
    VALIDATION_ID,
    assert_script_read_only,
    build_validation_packet,
)


def _target(component_id: str, component_name: str, workload: int):
    return {
        "component_id": component_id,
        "component_name": component_name,
        "workload": workload,
        "current_schedule_analysis": {
            "complete": False,
            "required_slots": [1, 2, 3, 4],
            "missing_slots": [3],
        },
        "recovery_state_38d": "time_pattern_ambiguous_school_shift",
        "historical_snapshots": [
            {
                "timestamp": "2026-05-27T17:16:27.780032+00:00",
                "analysis": {
                    "complete": True,
                    "conflicts": [{"slot": 4}],
                    "signature": [
                        [1, "07:08", "08:00"],
                        [2, "08:00", "09:00"],
                        [3, "09:15", "10:15"],
                        [4, "10:15", "11:15"],
                    ],
                },
                "changes": None,
            },
            {
                "timestamp": "2026-05-27T17:42:56.207437+00:00",
                "analysis": {
                    "complete": True,
                    "conflicts": [],
                    "signature": [
                        [1, "07:08", "08:00"],
                        [2, "08:00", "09:00"],
                        [3, "09:15", "09:30"],
                        [4, "10:30", "11:15"],
                    ],
                },
                "changes": {
                    "slot_times": {
                        "new": {"3": {"start": "09:15", "end": "09:30"}}
                    }
                },
            },
            {
                "timestamp": "2026-05-27T17:48:52.253835+00:00",
                "analysis": {
                    "complete": False,
                    "conflicts": [],
                    "signature": None,
                },
                "changes": {
                    "slot_times": {
                        "new": {"3": {"start": "09:30", "end": "09:30"}}
                    }
                },
            },
        ],
        "donor_patterns": [
            {
                "pattern": {
                    "1": {"start": "07:00", "end": "08:00"},
                    "2": {"start": "08:00", "end": "09:00"},
                    "3": {"start": "09:30", "end": "10:30"},
                    "4": {"start": "10:30", "end": "11:15"},
                },
                "donors": [
                    {"class_id": "c3", "class_name": "3º ANO A", "program": "atendimento_integral"},
                    {"class_id": "c4a", "class_name": "4º ANO A", "program": "atendimento_integral"},
                    {"class_id": "c4b", "class_name": "4º ANO B", "program": "atendimento_integral"},
                ],
            },
            {
                "pattern": {
                    "1": {"start": "07:00", "end": "08:00"},
                    "2": {"start": "08:00", "end": "09:15"},
                    "3": {"start": "09:30", "end": "10:30"},
                    "4": {"start": "10:30", "end": "11:15"},
                },
                "donors": [
                    {"class_id": "c5b", "class_name": "5ºANO B", "program": None},
                ],
            },
        ],
        "forensic_classification": {
            "classification": "HISTORICAL_SOURCE_CANDIDATE_REQUIRES_REVIEW",
            "automatic_action": False,
        },
    }


def _report():
    targets = {}
    for legacy_id, spec in forensic.TARGETS.items():
        targets[legacy_id] = _target(
            spec["component_id"],
            spec["component_name"],
            spec["workload"],
        )
    return {
        "meta": {
            "mode": "SECOND_WAVE_2D_A_FORENSICS_READ_ONLY",
            "mutates_database": False,
            "generated_at": "2026-08-26T00:00:00+00:00",
            "academic_year": 2026,
        },
        "scope": {
            "teacher_user_id": forensic.TEACHER_USER_ID,
            "staff_id": forensic.STAFF_ID,
            "teacher_name": "Abadia Alves Martins",
            "school_id": forensic.SCHOOL_ID,
            "class_id": forensic.CLASS_ID,
            "class_name": forensic.EXPECTED_CLASS_NAME,
            "shift": forensic.EXPECTED_SHIFT,
            "program": None,
            "schedule_id": "69b5c732-249b-45fc-bf16-c5e4ae7104a3",
            "slots_per_day": forensic.EXPECTED_SLOTS_PER_DAY,
            "current_schedule_created_at": "2026-05-27T17:16:27.778926+00:00",
            "current_schedule_updated_at": "2026-05-27T17:48:52.251738+00:00",
        },
        "current_schedule_consensus": {
            "1": {"start": "07:08", "end": "08:00"},
            "2": {"start": "08:00", "end": "09:00"},
            "4": {"start": "10:30", "end": "11:15"},
        },
        "audit_log_count": 3,
        "audit_snapshot_count": 3,
        "donor_schedule_count": 9,
        "existing_target_dvd_count": 0,
        "existing_target_dvd": [],
        "targets": targets,
    }


def test_scope_and_question_are_pinned():
    assert VALIDATION_ID == "DVD-SECOND-WAVE-2D-A1-5A-SLOT3-2026"
    assert CANDIDATE_SLOT == 3
    assert CANDIDATE_PAIR == ("09:30", "10:30")
    assert HISTORICAL_CONSISTENT_PAIR == ("09:15", "09:30")
    assert CURRENT_INVALID_PAIR == ("09:30", "09:30")
    assert "5º ANO A" in QUESTION
    assert "09:30 às 10:30" in QUESTION
    assert RESPONSE_OPTIONS == (
        "CONFIRMADO_09_30_10_30",
        "NEGADO",
        "OUTRO_HORARIO",
    )


def test_build_packet_seals_dual_target_evidence_without_decision():
    packet = build_validation_packet(_report())
    evidence = packet["evidence"]

    assert packet["meta"]["mutates_database"] is False
    assert len(packet["evidence_sha256"]) == 64
    assert evidence["candidate"] == {
        "slot": 3,
        "start": "09:30",
        "end": "10:30",
        "status": "REQUIRES_INSTITUTIONAL_CONFIRMATION",
    }
    assert evidence["automatic_action"] is False
    assert set(evidence["targets"]) == set(forensic.TARGETS)
    for target in evidence["targets"].values():
        assert target["donor_slot3_consensus"]["complete_schedule_count"] == 4
        assert target["donor_slot3_consensus"]["full_pattern_count"] == 2
        assert target["historical_conflict_free_slot3"]["start"] == "09:15"
        assert target["historical_conflict_free_slot3"]["end"] == "09:30"
        assert target["latest_invalid_slot3"] == {"start": "09:30", "end": "09:30"}


def test_evidence_hash_is_stable_for_same_source_snapshot():
    first = build_validation_packet(_report())
    second = build_validation_packet(_report())
    assert first["evidence_sha256"] == second["evidence_sha256"]
    assert first["meta"]["generated_at"] != ""
    assert second["meta"]["generated_at"] != ""


def test_donor_slot3_disagreement_fails_closed():
    report = _report()
    legacy_id = next(iter(report["targets"]))
    report["targets"][legacy_id]["donor_patterns"][1]["pattern"]["3"] = {
        "start": "09:20",
        "end": "10:20",
    }
    with pytest.raises(SourceValidationGateError, match="DONOR_SLOT3_NOT_UNANIMOUS"):
        build_validation_packet(report)


def test_existing_target_dvd_fails_closed():
    report = _report()
    report["existing_target_dvd_count"] = 1
    with pytest.raises(SourceValidationGateError, match="EXISTING_TARGET_DVD_PRESENT"):
        build_validation_packet(report)


def test_historical_pair_drift_fails_closed():
    report = _report()
    legacy_id = next(iter(report["targets"]))
    report["targets"][legacy_id]["historical_snapshots"][1]["analysis"]["signature"][2] = [
        3,
        "09:30",
        "10:30",
    ]
    with pytest.raises(SourceValidationGateError, match="HISTORICAL_CONSISTENT_PAIR_DRIFT"):
        build_validation_packet(report)


def test_source_snapshot_change_changes_evidence_hash():
    first = build_validation_packet(_report())
    changed = _report()
    changed["scope"]["current_schedule_updated_at"] = "2026-08-26T01:00:00+00:00"
    second = build_validation_packet(changed)
    assert first["evidence_sha256"] != second["evidence_sha256"]


def test_script_is_strictly_mongo_read_only_and_has_no_decision_mode():
    assert_script_read_only()
    src = Path("scripts/prepare_dvd_second_wave_2d_a1_source_validation.py").read_text(
        encoding="utf-8"
    )
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
    assert not any(token in src for token in forbidden)
    assert 'add_argument("--confirm"' not in src
    assert 'add_argument("--decision"' not in src
    assert 'add_argument("--response"' not in src
