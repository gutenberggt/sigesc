from pathlib import Path

import pytest

from scripts import apply_initial_years_schedule_normalization_phase2 as apply2
from scripts import inventory_initial_years_schedule_normalization as inventory_v1
from scripts import prepare_initial_years_schedule_normalization_phase1 as preflight


def _make_manifest():
    targets = []
    for index in range(apply2.EXPECTED_CREATES):
        class_id = f"create-class-{index:02d}"
        shift = "morning" if index % 2 == 0 else "afternoon"
        targets.append(
            {
                "class_id": class_id,
                "class_name": f"Turma C {index}",
                "school_id": f"school-{index % 4}",
                "school_name": "Escola",
                "academic_year": 2026,
                "shift": shift,
                "series": [1],
                "is_multi_grade": False,
                "proposed_slots_per_day": 4,
                "proposed_slot_times": inventory_v1.proposed_slot_times(shift),
                "mode": "CREATE_TIME_GRID",
                "schedule_id": preflight.deterministic_schedule_id(class_id),
                "current_document_sha256": None,
                "current_schedule_slots_sha256": None,
                "current_slots_per_day": None,
                "current_slot_times": None,
                "preserve_schedule_slots": False,
                "proposed_schedule_slots": [],
                "write_required": True,
            }
        )

    for index in range(apply2.EXPECTED_UPDATES):
        class_id = f"update-class-{index:02d}"
        shift = "morning" if index % 2 == 0 else "afternoon"
        targets.append(
            {
                "class_id": class_id,
                "class_name": f"Turma U {index}",
                "school_id": f"school-{index % 4}",
                "school_name": "Escola",
                "academic_year": 2026,
                "shift": shift,
                "series": [2],
                "is_multi_grade": False,
                "proposed_slots_per_day": 4,
                "proposed_slot_times": inventory_v1.proposed_slot_times(shift),
                "mode": "UPDATE_TIME_GRID",
                "schedule_id": f"existing-schedule-{index:02d}",
                "current_document_sha256": f"doc-hash-{index}",
                "current_schedule_slots_sha256": f"slots-hash-{index}",
                "current_slots_per_day": 4,
                "current_slot_times": {"1": {"start": "00:00", "end": "00:01"}},
                "current_updated_at": None,
                "preserve_schedule_slots": True,
                "schedule_slots_count": 1,
                "write_required": True,
            }
        )

    return {
        "phase_id": preflight.PHASE_ID,
        "academic_year": 2026,
        "source_inventory_sha256": apply2.APPROVED_SOURCE_INVENTORY_SHA256,
        "scope_v2_sha256": apply2.APPROVED_SCOPE_V2_SHA256,
        "policy": {
            shift: inventory_v1.proposed_slot_times(shift)
            for shift in ("morning", "afternoon")
        },
        "target_count": apply2.EXPECTED_TARGETS,
        "create_target_count": apply2.EXPECTED_CREATES,
        "existing_target_count": apply2.EXPECTED_UPDATES,
        "existing_write_required_count": apply2.EXPECTED_UPDATE_WRITES,
        "existing_already_compliant_count": 0,
        "blocked_outside_phase1_count": apply2.EXPECTED_BLOCKED_OUTSIDE,
        "targets": targets,
    }


def test_seals_are_exactly_pinned_to_production_preflight():
    assert apply2.APPROVED_SOURCE_INVENTORY_SHA256 == "891e6f8bc29929ba0a4d9ca59eb7d034f0ad1617f2758b3db9a00b4d3bdcc01a"
    assert apply2.APPROVED_SCOPE_V2_SHA256 == "1815d025770d24f2bb109cb5598bc990f2f0ca4ce361095dc1446cbbb2de9b7d"
    assert apply2.APPROVED_MANIFEST_SHA256 == "550812a8358a587f1dbbf56ae1ebe1999889d66fd0829de66d69b72062a4e554"
    assert apply2.APPROVED_BACKUP_BUNDLE_SHA256 == "7fbb0bcee57d7b81e67a5aaf35f0e75aec86ca6f44e2d96a8d96ef53ebfc512f"
    assert str(apply2.APPROVED_BACKUP_DIR) == "/data/sigesc-schedule-backups/initial-years-phase1-preflight-v1"


def test_apply_requires_all_three_explicit_confirmations():
    apply2.validate_confirmation(
        apply=False,
        confirm=None,
        confirm_manifest=None,
        confirm_backup=None,
    )

    with pytest.raises(apply2.Phase2ApplyError, match="APPLY_CONFIRMATION_INVALID"):
        apply2.validate_confirmation(
            apply=True,
            confirm="wrong",
            confirm_manifest=apply2.APPROVED_MANIFEST_SHA256,
            confirm_backup=apply2.APPROVED_BACKUP_BUNDLE_SHA256,
        )

    with pytest.raises(apply2.Phase2ApplyError, match="MANIFEST_CONFIRMATION_INVALID"):
        apply2.validate_confirmation(
            apply=True,
            confirm=apply2.APPLY_CONFIRMATION,
            confirm_manifest="wrong",
            confirm_backup=apply2.APPROVED_BACKUP_BUNDLE_SHA256,
        )

    with pytest.raises(apply2.Phase2ApplyError, match="BACKUP_CONFIRMATION_INVALID"):
        apply2.validate_confirmation(
            apply=True,
            confirm=apply2.APPLY_CONFIRMATION,
            confirm_manifest=apply2.APPROVED_MANIFEST_SHA256,
            confirm_backup="wrong",
        )

    apply2.validate_confirmation(
        apply=True,
        confirm=apply2.APPLY_CONFIRMATION,
        confirm_manifest=apply2.APPROVED_MANIFEST_SHA256,
        confirm_backup=apply2.APPROVED_BACKUP_BUNDLE_SHA256,
    )


def test_exact_manifest_shape_is_accepted_and_drift_fails_closed():
    manifest = _make_manifest()
    targets = apply2.validate_manifest_semantics(manifest)
    assert len(targets) == 69
    assert sum(t["mode"] == "CREATE_TIME_GRID" for t in targets) == 36
    assert sum(t["mode"] == "UPDATE_TIME_GRID" for t in targets) == 33

    drift = _make_manifest()
    drift["existing_already_compliant_count"] = 1
    with pytest.raises(apply2.Phase2ApplyError, match="SEALED_MANIFEST_FIELD_MISMATCH"):
        apply2.validate_manifest_semantics(drift)


def test_create_document_has_only_empty_weekly_grid_and_exact_time_policy():
    target = _make_manifest()["targets"][0]
    doc = apply2.build_create_document(target, timestamp="2026-08-26T00:00:00+00:00")
    assert doc == {
        "id": target["schedule_id"],
        "school_id": target["school_id"],
        "class_id": target["class_id"],
        "academic_year": 2026,
        "shift": target["shift"],
        "slots_per_day": 4,
        "slot_times": target["proposed_slot_times"],
        "schedule_slots": [],
        "created_at": "2026-08-26T00:00:00+00:00",
    }


def test_update_patch_cannot_replace_schedule_slots_or_other_schedule_fields():
    target = _make_manifest()["targets"][-1]
    current = {
        "id": target["schedule_id"],
        "class_id": target["class_id"],
        "school_id": target["school_id"],
        "academic_year": "2026",
        "shift": target["shift"],
        "slots_per_day": 5,
        "slot_times": {"1": {"start": "13:00", "end": "14:00"}},
        "schedule_slots": [{"day": "segunda", "slot_number": 1, "course_id": "course-x"}],
        "updated_at": "before",
        "other_field": "must-survive",
    }
    filter_doc, patch = apply2.build_update_filter_and_patch(
        target,
        current,
        timestamp="after",
    )
    assert filter_doc["schedule_slots"] == current["schedule_slots"]
    assert filter_doc["updated_at"] == "before"
    assert set(patch) == {"$set"}
    assert set(patch["$set"]) == {"slots_per_day", "slot_times", "updated_at"}
    assert "schedule_slots" not in patch["$set"]
    assert "other_field" not in patch["$set"]
    assert patch["$set"]["slots_per_day"] == 4
    assert patch["$set"]["slot_times"] == target["proposed_slot_times"]


def test_apply_source_has_no_destructive_collection_mutators():
    src = Path("scripts/apply_initial_years_schedule_normalization_phase2.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".find_one_and_update(",
        ".find_one_and_delete(",
        ".find_one_and_replace(",
    )
    assert not any(token in src for token in forbidden)
    assert src.count(".update_one(") == 2
    assert '"$setOnInsert": doc' in src
    assert '"schedule_slots": deepcopy(current.get("schedule_slots") or [])' in src


def test_scope_snapshot_bundle_changes_with_generated_at_without_scope_drift():
    scope_core = {
        "academic_year": 2026,
        "source_inventory_sha256": "source",
        "regular_target_count": 84,
    }
    scope_hash = preflight._sha256(scope_core)
    snapshot_a = {
        "meta": {"mode": "READ_ONLY", "mutates_database": False, "generated_at": "2026-08-26T01:00:00+00:00"},
        "scope_v2_sha256": scope_hash,
        "scope": scope_core,
    }
    snapshot_b = {
        "meta": {"mode": "READ_ONLY", "mutates_database": False, "generated_at": "2026-08-26T02:00:00+00:00"},
        "scope_v2_sha256": scope_hash,
        "scope": scope_core,
    }

    assert snapshot_a["scope_v2_sha256"] == snapshot_b["scope_v2_sha256"]
    assert snapshot_a["scope"] == snapshot_b["scope"]
    assert preflight._sha256(snapshot_a) != preflight._sha256(snapshot_b)


def test_persistent_reseal_changes_only_backup_bundle_authority():
    from scripts import apply_initial_years_schedule_normalization_phase2_persistent_reseal as reseal

    original_bundle = apply2.APPROVED_BACKUP_BUNDLE_SHA256
    original_manifest = apply2.APPROVED_MANIFEST_SHA256
    original_scope = apply2.APPROVED_SCOPE_V2_SHA256
    original_dir = apply2.APPROVED_BACKUP_DIR
    try:
        assert original_bundle == reseal.PREVIOUS_EPHEMERAL_BACKUP_BUNDLE_SHA256
        reseal.activate_reseal()
        assert apply2.APPROVED_BACKUP_BUNDLE_SHA256 == reseal.RESEALED_PERSISTENT_BACKUP_BUNDLE_SHA256
        assert apply2.APPROVED_MANIFEST_SHA256 == original_manifest
        assert apply2.APPROVED_SCOPE_V2_SHA256 == original_scope
        assert apply2.APPROVED_BACKUP_DIR == original_dir
        reseal.activate_reseal()
    finally:
        apply2.APPROVED_BACKUP_BUNDLE_SHA256 = original_bundle
