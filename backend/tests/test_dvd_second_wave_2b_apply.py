from pathlib import Path

import pytest

from scripts import apply_dvd_second_wave_2a as base
from scripts import prepare_dvd_second_wave_2b as preflight
from scripts.apply_dvd_second_wave_2b import (
    ACTOR,
    APPLY_CONFIRMATION,
    APPLY_PHASE,
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    PERSISTENT_BACKUP_DIR,
    REQUIRED_RECOVERY_STATE,
    REQUIRED_WEEKLY_SLOTS,
    ROLLBACK_CONFIRMATION,
    SCHEDULE_SOURCE,
    SecondWaveGateError,
    _configure_base,
    load_and_verify_backup,
)
from scripts.apply_dvd_second_wave_2b_persistent import (
    ACADEMIC_YEAR,
    PERSISTENT_RECEIPT_DIR,
    REFERENCE_DATE,
    PersistentSealArgumentError,
    build_locked_argv,
    validate_runtime_args,
)
from scripts.audit_dvd_first_wave_manifest import manifest_digest


def _manifest_row(*, recovery_state=REQUIRED_RECOVERY_STATE):
    return {
        "id": "dvd-2b-1",
        "teacher_id": "teacher-1",
        "teacher_name": "Professora",
        "class_id": "class-1",
        "class_name": "Turma 1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "component_id": "component-1",
        "component_name": "Componente 1",
        "weekly_slots": [
            {
                "weekday": n,
                "aula_numero": 1,
                "start_time": "07:00",
                "end_time": "08:00",
            }
            for n in range(1, 6)
        ],
        "valid_from": "2026-08-18",
        "valid_until": None,
        "is_substitute": False,
        "source": "import",
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "cutover_provenance": {
            "phase": "38E",
            "state": "DRY_RUN_ONLY",
            "source_legacy_assignment_id": "legacy-1",
            "schedule_source": SCHEDULE_SOURCE,
            "recovery_state": recovery_state,
        },
    }


def _sealed_backup(tmp_path: Path, *, recovery_state=REQUIRED_RECOVERY_STATE):
    manifest = [_manifest_row(recovery_state=recovery_state)]
    manifest_sha = manifest_digest(manifest)
    report = {
        "summary": {
            "manifest_sha256": manifest_sha,
            "second_wave_2b_ready": 1,
            "source_38e_manifest_sha256": "source-sha",
            "recovery_states": {recovery_state: 1},
            "weekly_slots_counts": {"5": 1},
        },
        "manifest": manifest,
    }
    bundle = {
        "scope": {"academic_year": 2026, "class_ids": ["class-1"]},
        "collections": {
            "teacher_class_assignments_before": [
                {"id": "existing-1", "class_id": "class-1"}
            ],
            "teacher_assignments_source": [
                {"id": "legacy-1", "class_id": "class-1"}
            ],
        },
    }
    backup_dir = tmp_path / "backup"
    sealed = preflight.write_backup_directory(
        backup_dir,
        manifest_report=report,
        bundle=bundle,
    )
    return backup_dir, manifest_sha, sealed["backup_bundle_sha256"]


def test_production_snapshot_constants_are_pinned():
    assert APPROVED_READY_COUNT == 13
    assert APPROVED_MANIFEST_SHA256 == (
        "4d84e76b7236d2e6c5e0b8199165aa1e034d6d2529ceed05d248226ff9af72fc"
    )
    assert APPROVED_BACKUP_BUNDLE_SHA256 == (
        "b481670bb416429254d1efb066ef614a50c2bf053957bd078fe5eba3ea8f81f6"
    )
    assert PERSISTENT_BACKUP_DIR == Path(
        "/data/sigesc-dvd-backups/dvd-second-wave-2b-preflight-v1"
    )
    assert SCHEDULE_SOURCE == "deterministic_recovery"
    assert REQUIRED_RECOVERY_STATE == "time_recoverable_unique_school_shift"
    assert REQUIRED_WEEKLY_SLOTS == 5
    assert APPLY_PHASE == "SECOND_WAVE_2B"
    assert ACTOR == "dvd-second-wave-2b"
    assert APPLY_CONFIRMATION == "APPLY-DVD-SECOND-WAVE-2B-13"
    assert ROLLBACK_CONFIRMATION == "ROLLBACK-DVD-SECOND-WAVE-2B-13"


def test_backup_loader_accepts_only_matching_2b_seal(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, bundle_sha = _sealed_backup(tmp_path)
    monkeypatch.setattr(preflight, "PERSISTENT_BACKUP_ROOT", tmp_path)

    loaded = load_and_verify_backup(
        backup_dir,
        expected_manifest_sha256=manifest_sha,
        expected_count=1,
        expected_backup_sha256=bundle_sha,
    )

    assert loaded["manifest_sha256"] == manifest_sha
    assert loaded["backup_bundle_sha256"] == bundle_sha
    assert loaded["metadata"]["mode"] == preflight.BACKUP_MODE
    assert loaded["metadata"]["mutates_database"] is False


def test_backup_loader_rejects_unapproved_bundle(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, _ = _sealed_backup(tmp_path)
    monkeypatch.setattr(preflight, "PERSISTENT_BACKUP_ROOT", tmp_path)

    with pytest.raises(SecondWaveGateError, match="BACKUP_BUNDLE_NOT_APPROVED"):
        load_and_verify_backup(
            backup_dir,
            expected_manifest_sha256=manifest_sha,
            expected_count=1,
            expected_backup_sha256="0" * 64,
        )


def test_backup_loader_rejects_disallowed_recovery_state(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, bundle_sha = _sealed_backup(
        tmp_path,
        recovery_state="time_recoverable_same_schedule",
    )
    monkeypatch.setattr(preflight, "PERSISTENT_BACKUP_ROOT", tmp_path)

    with pytest.raises(SecondWaveGateError, match="RECOVERY_STATES_INVALID"):
        load_and_verify_backup(
            backup_dir,
            expected_manifest_sha256=manifest_sha,
            expected_count=1,
            expected_backup_sha256=bundle_sha,
        )


def test_shared_apply_helpers_receive_2b_provenance():
    old_phase = base.APPLY_PHASE
    old_actor = base.ACTOR
    try:
        _configure_base()
        assert base.APPLY_PHASE == APPLY_PHASE
        assert base.ACTOR == ACTOR

        docs = base.build_apply_documents(
            [_manifest_row()],
            manifest_sha256="m" * 64,
            backup_bundle_sha256="b" * 64,
            run_id="run-2b",
            activated_at="2026-08-25T22:00:00+00:00",
        )
        provenance = docs[0]["cutover_provenance"]
        assert provenance["apply_phase"] == APPLY_PHASE
        assert provenance["schedule_source"] == SCHEDULE_SOURCE
        assert provenance["recovery_state"] == REQUIRED_RECOVERY_STATE
        assert docs[0]["created_by"] == ACTOR
    finally:
        base.APPLY_PHASE = old_phase
        base.ACTOR = old_actor


def test_persistent_entrypoint_is_fully_pinned_and_defaults_dry_run():
    assert ACADEMIC_YEAR == 2026
    assert REFERENCE_DATE == "2026-08-18"
    argv = build_locked_argv([])
    joined = " ".join(argv)
    assert "--academic-year 2026" in joined
    assert "--reference-date 2026-08-18" in joined
    assert f"--expected-count {APPROVED_READY_COUNT}" in joined
    assert f"--expected-manifest-sha256 {APPROVED_MANIFEST_SHA256}" in joined
    assert f"--expected-backup-sha256 {APPROVED_BACKUP_BUNDLE_SHA256}" in joined
    assert f"--backup-dir {PERSISTENT_BACKUP_DIR}" in joined
    assert f"--receipt-dir {PERSISTENT_RECEIPT_DIR}" in joined
    assert "--apply" not in argv
    assert "--rollback" not in argv


def test_only_mode_and_confirmation_can_be_forwarded():
    assert validate_runtime_args(
        ["--apply", "--confirm", APPLY_CONFIRMATION]
    ) == ["--apply", "--confirm", APPLY_CONFIRMATION]
    assert validate_runtime_args(
        ["--rollback", f"--confirm={ROLLBACK_CONFIRMATION}"]
    )[0] == "--rollback"


@pytest.mark.parametrize(
    "args",
    [
        ["--backup-dir", "/tmp/unsafe"],
        ["--expected-backup-sha256", "0" * 64],
        ["--expected-manifest-sha256", "0" * 64],
        ["--expected-count", "14"],
        ["--academic-year", "2027"],
        ["--reference-date", "2026-08-19"],
        ["--receipt-dir", "/tmp/receipts"],
        ["--tenant-id", "other"],
    ],
)
def test_authoritative_scope_cannot_be_overridden(args):
    with pytest.raises(PersistentSealArgumentError, match="SEALED_ARGUMENT_OVERRIDE"):
        validate_runtime_args(args)


def test_apply_and_rollback_cannot_be_combined():
    with pytest.raises(PersistentSealArgumentError, match="MUTUALLY_EXCLUSIVE"):
        validate_runtime_args(["--apply", "--rollback"])


def test_scripts_are_dry_run_by_default_and_wrapper_has_no_mutators():
    apply_src = Path("scripts/apply_dvd_second_wave_2b.py").read_text(encoding="utf-8")
    wrapper_src = Path("scripts/apply_dvd_second_wave_2b_persistent.py").read_text(
        encoding="utf-8"
    )

    assert "if not args.apply:" in apply_src
    assert "APPLY_CONFIRMATION_REQUIRED" in apply_src
    assert "ROLLBACK_CONFIRMATION_REQUIRED" in apply_src
    assert "await base.apply_second_wave(" in apply_src
    assert "await base.rollback_second_wave(" in apply_src

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
    assert not any(token in wrapper_src for token in forbidden)
    assert "await implementation.main()" in wrapper_src
