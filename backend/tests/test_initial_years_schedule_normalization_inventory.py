from pathlib import Path

import pytest

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
from scripts.inventory_initial_years_schedule_normalization_v2 import (
    EXCLUSION_AEE,
    EXCLUSION_EJA,
    assert_script_read_only as assert_v2_read_only,
    build_scope_v2,
    exclusion_reason,
    review_group,
)
from scripts.prepare_initial_years_schedule_normalization_phase1 import (
    EXPECTED_SCOPE_V2_SHA256,
    Phase1PreflightError,
    assert_script_read_only as assert_phase1_read_only,
    build_manifest,
    deterministic_schedule_id,
    validate_persistent_backup_path,
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


def test_v2_excludes_aee_even_when_series_are_1_to_5():
    row = {
        "class_name": "AEE-A",
        "atendimento_programa": "aee",
        "grade_evidence": {
            "education_level": "fundamental_anos_iniciais",
            "combined_numbers": [1, 2],
        },
    }
    assert exclusion_reason(row) == EXCLUSION_AEE


def test_v2_excludes_eja_and_etapa_by_level_or_legacy_name():
    assert exclusion_reason({
        "class_name": "EJA 1º E 2º ETAPA",
        "grade_evidence": {"education_level": "eja", "combined_numbers": [1, 2]},
    }) == EXCLUSION_EJA
    assert exclusion_reason({
        "class_name": "MULTI 3º E 4º ETAPA",
        "grade_evidence": {"education_level": None, "combined_numbers": [3, 4]},
    }) == EXCLUSION_EJA


def test_v2_keeps_regular_multigrade_and_groups_real_blockers():
    regular = {
        "class_name": "3º, 4º E 5º ANO MULTI",
        "atendimento_programa": "regular",
        "grade_evidence": {
            "education_level": "fundamental_anos_iniciais",
            "combined_numbers": [3, 4, 5],
        },
        "blockers": [],
    }
    assert exclusion_reason(regular) is None
    assert review_group({"blockers": ["SHIFT_WITHOUT_POLICY:full_time"]}) == "FULL_TIME_POLICY_REQUIRED"
    assert review_group({"blockers": ["EXTRA_SLOTS_ABOVE_4:5"]}) == "EXTRA_SLOTS_REVIEW"
    assert review_group({"blockers": ["CLASS_SCHEDULE_SHIFT_MISMATCH:morning!=afternoon"]}) == "SHIFT_MISMATCH_REVIEW"


def test_v2_recalculates_scope_without_silently_dropping_exclusions():
    source = {
        "meta": {"mutates_database": False},
        "inventory_sha256": "source-hash",
        "inventory": {
            "policy": SCHEDULE_POLICY,
            "rows": [
                {
                    "class_id": "regular-1",
                    "class_name": "1º ANO A",
                    "school_id": "s1",
                    "school_name": "Escola",
                    "shift": "morning",
                    "atendimento_programa": "regular",
                    "grade_evidence": {"education_level": "fundamental_anos_iniciais", "combined_numbers": [1], "is_multi_grade": False},
                    "schedule_count": 0,
                    "schedule_shape": {"extra_slot_numbers": []},
                    "status": "READY_NORMALIZE",
                    "blockers": [],
                },
                {
                    "class_id": "aee-1",
                    "class_name": "AEE-A",
                    "school_id": "s1",
                    "school_name": "Escola",
                    "shift": "morning",
                    "atendimento_programa": "aee",
                    "grade_evidence": {"education_level": "fundamental_anos_iniciais", "combined_numbers": [1, 2], "is_multi_grade": True},
                    "schedule_count": 0,
                    "status": "READY_NORMALIZE",
                    "blockers": [],
                },
                {
                    "class_id": "eja-1",
                    "class_name": "EJA 1º E 2º ETAPA",
                    "school_id": "s1",
                    "school_name": "Escola",
                    "shift": "evening",
                    "atendimento_programa": "regular",
                    "grade_evidence": {"education_level": "eja", "combined_numbers": [1, 2], "is_multi_grade": True},
                    "schedule_count": 0,
                    "status": "BLOCKED_REQUIRES_REVIEW",
                    "blockers": ["SHIFT_WITHOUT_POLICY:evening"],
                },
                {
                    "class_id": "full-1",
                    "class_name": "4º ANO",
                    "school_id": "s1",
                    "school_name": "Escola",
                    "shift": "full_time",
                    "atendimento_programa": "regular",
                    "grade_evidence": {"education_level": "fundamental_anos_iniciais", "combined_numbers": [4], "is_multi_grade": False},
                    "schedule_count": 0,
                    "status": "BLOCKED_REQUIRES_REVIEW",
                    "blockers": ["SHIFT_WITHOUT_POLICY:full_time"],
                },
            ],
        },
    }
    report = build_scope_v2(source)
    scope = report["scope"]
    assert scope["regular_target_count"] == 2
    assert scope["excluded_non_regular_count"] == 2
    assert scope["excluded_counts"] == {EXCLUSION_AEE: 1, EXCLUSION_EJA: 1}
    assert scope["summary"]["status"] == {
        "BLOCKED_REQUIRES_REVIEW": 1,
        "READY_NORMALIZE": 1,
    }
    assert scope["summary"]["review_groups"] == {"FULL_TIME_POLICY_REQUIRED": 1}


def test_phase1_scope_hash_is_pinned_to_homologated_v2():
    assert EXPECTED_SCOPE_V2_SHA256 == "1815d025770d24f2bb109cb5598bc990f2f0ca4ce361095dc1446cbbb2de9b7d"


def test_phase1_deterministic_create_id_is_stable_and_per_class():
    a1 = deterministic_schedule_id("class-a")
    a2 = deterministic_schedule_id("class-a")
    b = deterministic_schedule_id("class-b")
    assert a1 == a2
    assert a1 != b


def test_phase1_manifest_creates_missing_and_preserves_existing_schedule_slots():
    morning = proposed_slot_times("morning")
    afternoon = proposed_slot_times("afternoon")
    ready = [
        {
            "class_id": "class-create",
            "class_name": "1º ANO A",
            "school_id": "school-1",
            "school_name": "Escola",
            "shift": "morning",
            "grade_evidence": {"combined_numbers": [1], "is_multi_grade": False},
            "schedule_count": 0,
            "schedule_shape": {"schedule_id": None},
            "proposed_slot_times": morning,
        },
        {
            "class_id": "class-update",
            "class_name": "4º E 5º ANO",
            "school_id": "school-1",
            "school_name": "Escola",
            "shift": "afternoon",
            "grade_evidence": {"combined_numbers": [4, 5], "is_multi_grade": True},
            "schedule_count": 1,
            "schedule_shape": {"schedule_id": "schedule-existing"},
            "proposed_slot_times": afternoon,
        },
    ]
    schedule_slots = [
        {"day": "segunda", "slot_number": 1, "course_id": "course-a"},
        {"day": "segunda", "slot_number": 2, "course_id": "course-b"},
    ]
    existing = [{
        "id": "schedule-existing",
        "class_id": "class-update",
        "school_id": "school-1",
        "academic_year": 2026,
        "shift": "afternoon",
        "slots_per_day": 4,
        "slot_times": {"1": {"start": "13:00", "end": "14:00"}},
        "schedule_slots": schedule_slots,
        "updated_at": "2026-01-01T00:00:00+00:00",
    }]
    result = build_manifest(ready, existing, [])
    manifest = result["manifest"]
    assert manifest["target_count"] == 2
    assert manifest["create_target_count"] == 1
    assert manifest["existing_target_count"] == 1
    create = next(row for row in manifest["targets"] if row["mode"] == "CREATE_TIME_GRID")
    update = next(row for row in manifest["targets"] if row["mode"] == "UPDATE_TIME_GRID")
    assert create["proposed_schedule_slots"] == []
    assert create["write_required"] is True
    assert update["preserve_schedule_slots"] is True
    assert update["schedule_slots_count"] == 2
    assert update["write_required"] is True
    assert update["proposed_slot_times"] == afternoon


def test_phase1_manifest_fails_on_deterministic_id_collision():
    morning = proposed_slot_times("morning")
    ready = [{
        "class_id": "class-create",
        "class_name": "1º ANO A",
        "school_id": "school-1",
        "school_name": "Escola",
        "shift": "morning",
        "grade_evidence": {"combined_numbers": [1], "is_multi_grade": False},
        "schedule_count": 0,
        "schedule_shape": {"schedule_id": None},
        "proposed_slot_times": morning,
    }]
    proposed_id = deterministic_schedule_id("class-create")
    with pytest.raises(Phase1PreflightError, match="DETERMINISTIC_ID_COLLISION"):
        build_manifest(
            ready,
            [],
            [{"id": proposed_id, "class_id": "other-class"}],
        )


def test_phase1_backup_path_must_be_persistent_data_volume():
    assert validate_persistent_backup_path(Path("/data/sigesc-schedule-backups/test")) == Path(
        "/data/sigesc-schedule-backups/test"
    )
    with pytest.raises(Phase1PreflightError, match="BACKUP_PATH_MUST_BE_UNDER_DATA"):
        validate_persistent_backup_path(Path("/tmp/not-persistent"))


def test_script_is_strictly_read_only():
    assert_script_read_only()
    assert_v2_read_only()
    assert_phase1_read_only()
    for path in (
        "scripts/inventory_initial_years_schedule_normalization.py",
        "scripts/inventory_initial_years_schedule_normalization_v2.py",
        "scripts/prepare_initial_years_schedule_normalization_phase1.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        forbidden = (
            ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
            ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
        )
        assert not any(token in src for token in forbidden)


def test_v2_direct_entrypoint_bootstraps_backend_parent_on_sys_path():
    src = Path("scripts/inventory_initial_years_schedule_normalization_v2.py").read_text(
        encoding="utf-8"
    )
    assert "import sys" in src
    assert "SCRIPT_DIR = Path(__file__).resolve().parent" in src
    assert "BACKEND_DIR = SCRIPT_DIR.parent" in src
    assert "sys.path.insert(0, str(BACKEND_DIR))" in src
    assert src.index("sys.path.insert(0, str(BACKEND_DIR))") < src.index(
        "from scripts import inventory_initial_years_schedule_normalization as base"
    )


def test_phase1_direct_entrypoint_bootstraps_backend_parent_on_sys_path():
    src = Path("scripts/prepare_initial_years_schedule_normalization_phase1.py").read_text(
        encoding="utf-8"
    )
    assert "SCRIPT_DIR = Path(__file__).resolve().parent" in src
    assert "BACKEND_DIR = SCRIPT_DIR.parent" in src
    assert "sys.path.insert(0, str(BACKEND_DIR))" in src
    assert src.index("sys.path.insert(0, str(BACKEND_DIR))") < src.index(
        "from scripts import inventory_initial_years_schedule_normalization as inventory_v1"
    )
