from pathlib import Path

import pytest

from scripts.prepare_dvd_cutover_phase38g import (
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    PreflightGateError,
    assert_script_read_only,
    validate_manifest_gate,
    write_backup_directory,
)


def test_manifest_gate_accepts_only_approved_baseline():
    validate_manifest_gate(
        {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "first_wave_ready": APPROVED_READY_COUNT,
        },
        expected_sha256=APPROVED_MANIFEST_SHA256,
        expected_count=APPROVED_READY_COUNT,
    )


def test_manifest_gate_rejects_hash_drift():
    with pytest.raises(PreflightGateError, match="MANIFEST_SHA256_MISMATCH"):
        validate_manifest_gate(
            {"manifest_sha256": "0" * 64, "first_wave_ready": APPROVED_READY_COUNT},
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_manifest_gate_rejects_count_drift_even_with_same_hash():
    with pytest.raises(PreflightGateError, match="MANIFEST_COUNT_MISMATCH"):
        validate_manifest_gate(
            {
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "first_wave_ready": APPROVED_READY_COUNT - 1,
            },
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_backup_directory_is_sealed_and_contains_pre_state(tmp_path: Path):
    target = tmp_path / "backup"
    manifest_report = {
        "summary": {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "first_wave_ready": APPROVED_READY_COUNT,
        },
        "manifest": [{"id": "dvd-1", "class_id": "c1"}],
    }
    bundle = {
        "scope": {"academic_year": 2026, "class_ids": ["c1"]},
        "collections": {
            "teacher_class_assignments_before": [{"id": "old-1", "class_id": "c1"}],
            "teacher_assignments_source": [{"id": "legacy-1", "class_id": "c1"}],
        },
    }

    result = write_backup_directory(target, manifest_report=manifest_report, bundle=bundle)

    assert (target / "manifest.json").is_file()
    assert (target / "teacher_class_assignments_before.json").is_file()
    assert (target / "BACKUP-SEAL.json").is_file()
    assert len(result["backup_bundle_sha256"]) == 64
    assert result["file_counts"]["manifest.json"] == 1


def test_backup_never_overwrites_existing_directory(tmp_path: Path):
    target = tmp_path / "backup"
    target.mkdir()
    with pytest.raises(FileExistsError):
        write_backup_directory(
            target,
            manifest_report={
                "summary": {
                    "manifest_sha256": APPROVED_MANIFEST_SHA256,
                    "first_wave_ready": APPROVED_READY_COUNT,
                },
                "manifest": [],
            },
            bundle={"scope": {}, "collections": {}},
        )


def test_preflight_script_contains_no_mongo_mutator_calls():
    assert_script_read_only()
