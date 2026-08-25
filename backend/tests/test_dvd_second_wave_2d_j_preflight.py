from pathlib import Path

import pytest

from scripts.prepare_dvd_second_wave_2d_j import (
    ACADEMIC_YEAR,
    APPROVED_READY_COUNT,
    APPROVED_TARGETS,
    CLASS_ID,
    PERSISTENT_BACKUP_ROOT,
    PreflightGateError,
    REQUIRED_PEER_PROFILE_MIN_COUNT,
    REQUIRED_SLOTS_PER_DAY,
    SCHOOL_ID,
    STAFF_ID,
    TEACHER_USER_ID,
    assert_script_read_only,
    deterministic_assignment_id,
    resolve_peer_profile,
    validate_exact_schedule_result,
    validate_persistent_backup_path,
)


def _peer(component_id: str, *, profile: str = "integrator", scope: str = "all"):
    return {
        "id": f"peer-{component_id}-{profile}",
        "teacher_id": "peer-teacher",
        "class_id": "peer-class",
        "component_id": component_id,
        "valid_from": "2026-08-18",
        "valid_until": None,
        "is_substitute": False,
        "deleted": False,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": profile,
            "student_scope": scope,
        },
    }


def test_scope_constants_are_pinned_to_juliana_2d_j():
    assert ACADEMIC_YEAR == 2026
    assert TEACHER_USER_ID == "2e5004ac-dad2-4d07-a6aa-372ff49bb54a"
    assert STAFF_ID == "a2dfe7d1-b135-46f8-b347-0b21b8bc906c"
    assert CLASS_ID == "a76ccc2c-317c-4bd6-8b39-ed5fa806d67c"
    assert SCHOOL_ID == "1279c538-94c9-4c6b-a0de-994ed73c9f6f"
    assert APPROVED_READY_COUNT == 2
    assert REQUIRED_SLOTS_PER_DAY == 7
    assert REQUIRED_PEER_PROFILE_MIN_COUNT == 2
    assert set(APPROVED_TARGETS) == {
        "1f08bfe3-b486-4266-81bc-2f03fe72a3a4",
        "7d62a0df-c601-4288-b4ef-18093d3c37cf",
    }


def test_exact_schedule_targets_are_pinned_to_production_audit():
    contacao = APPROVED_TARGETS["1f08bfe3-b486-4266-81bc-2f03fe72a3a4"]
    higiene = APPROVED_TARGETS["7d62a0df-c601-4288-b4ef-18093d3c37cf"]

    assert contacao["component_id"] == "e90107dc-3276-4480-852b-91f617eefc67"
    assert contacao["workload"] == 5
    assert len(contacao["weekly_slots"]) == 5
    assert contacao["weekly_slots"][0] == {
        "weekday": 1,
        "aula_numero": 5,
        "start_time": "13:00",
        "end_time": "13:40",
    }

    assert higiene["component_id"] == "7cce8ff9-9cd1-4737-a4ed-a61554a711dc"
    assert higiene["workload"] == 3
    assert len(higiene["weekly_slots"]) == 3
    assert higiene["weekly_slots"][0] == {
        "weekday": 1,
        "aula_numero": 7,
        "start_time": "14:50",
        "end_time": "15:55",
    }


def test_no_residue_is_the_only_accepted_p0_blocker_for_2d_j():
    legacy_id = "7d62a0df-c601-4288-b4ef-18093d3c37cf"
    expected = APPROVED_TARGETS[legacy_id]
    weekly = expected["weekly_slots"]

    result = {
        "ready": False,
        "blockers": ["no_out_of_range_residue"],
        "weekly_slots": weekly,
        "stale_slots": [],
        "slots_per_day": 7,
    }
    assert validate_exact_schedule_result(legacy_id, result) == weekly

    bad = dict(result)
    bad["blockers"] = ["no_out_of_range_residue", "slot_time_invalid_in_range"]
    with pytest.raises(PreflightGateError, match="SCHEDULE_GATE_MISMATCH"):
        validate_exact_schedule_result(legacy_id, bad)


def test_schedule_drift_is_fail_closed():
    legacy_id = "1f08bfe3-b486-4266-81bc-2f03fe72a3a4"
    weekly = [dict(row) for row in APPROVED_TARGETS[legacy_id]["weekly_slots"]]
    weekly[0]["start_time"] = "13:01"
    with pytest.raises(PreflightGateError, match="WEEKLY_SLOTS_DRIFT"):
        validate_exact_schedule_result(
            legacy_id,
            {
                "ready": False,
                "blockers": ["no_out_of_range_residue"],
                "weekly_slots": weekly,
                "stale_slots": [],
                "slots_per_day": 7,
            },
        )


def test_peer_profile_requires_two_matching_active_peers():
    component = APPROVED_TARGETS["1f08bfe3-b486-4266-81bc-2f03fe72a3a4"]["component_id"]
    peers = [_peer(component), _peer(component)]
    evidence = resolve_peer_profile(component, peers)
    assert evidence["profile"] == "integrator"
    assert evidence["student_scope"] == "all"
    assert evidence["peer_count"] == 2

    with pytest.raises(PreflightGateError, match="PEER_PROFILE_EVIDENCE_INSUFFICIENT"):
        resolve_peer_profile(component, peers[:1])


def test_peer_profile_ambiguity_is_fail_closed():
    component = APPROVED_TARGETS["7d62a0df-c601-4288-b4ef-18093d3c37cf"]["component_id"]
    peers = [
        _peer(component, profile="regular"),
        _peer(component, profile="integrator"),
    ]
    with pytest.raises(PreflightGateError, match="PEER_PROFILE_AMBIGUOUS"):
        resolve_peer_profile(component, peers)


def test_shared_profile_and_group_scope_are_not_accepted():
    component = APPROVED_TARGETS["7d62a0df-c601-4288-b4ef-18093d3c37cf"]["component_id"]
    shared = [_peer(component, profile="shared", scope="group") for _ in range(2)]
    with pytest.raises(PreflightGateError, match="PEER_PROFILE_NOT_ALLOWED"):
        resolve_peer_profile(component, shared)

    mixed_scope = [
        _peer(component, profile="integrator", scope="all"),
        _peer(component, profile="integrator", scope="group"),
    ]
    with pytest.raises(PreflightGateError, match="PEER_STUDENT_SCOPE_AMBIGUOUS"):
        resolve_peer_profile(component, mixed_scope)


def test_deterministic_id_is_stable_and_changes_with_source():
    component = APPROVED_TARGETS["1f08bfe3-b486-4266-81bc-2f03fe72a3a4"]["component_id"]
    first = deterministic_assignment_id(
        source_legacy_assignment_id="1f08bfe3-b486-4266-81bc-2f03fe72a3a4",
        component_id=component,
        valid_from="2026-08-18",
    )
    second = deterministic_assignment_id(
        source_legacy_assignment_id="1f08bfe3-b486-4266-81bc-2f03fe72a3a4",
        component_id=component,
        valid_from="2026-08-18",
    )
    different = deterministic_assignment_id(
        source_legacy_assignment_id="other",
        component_id=component,
        valid_from="2026-08-18",
    )
    assert first == second
    assert first != different


def test_backup_path_must_be_persistent_child():
    validate_persistent_backup_path(PERSISTENT_BACKUP_ROOT / "dvd-second-wave-2d-j-preflight-v1")
    with pytest.raises(PreflightGateError, match="BACKUP_PATH_NOT_ABSOLUTE"):
        validate_persistent_backup_path(Path("relative"))
    with pytest.raises(PreflightGateError, match="BACKUP_PATH_NOT_PERSISTENT"):
        validate_persistent_backup_path(Path("/tmp/unsafe"))
    with pytest.raises(PreflightGateError, match="BACKUP_PATH_MUST_BE_CHILD_DIRECTORY"):
        validate_persistent_backup_path(PERSISTENT_BACKUP_ROOT)


def test_script_has_no_mongo_mutators_or_apply_mode():
    assert_script_read_only()
    src = Path("scripts/prepare_dvd_second_wave_2d_j.py").read_text(encoding="utf-8")
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
