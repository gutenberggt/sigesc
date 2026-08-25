from pathlib import Path
import os
import subprocess
import sys

import pytest

from scripts import apply_dvd_second_wave_2a as apply_base
from scripts import prepare_dvd_second_wave_2d_j as preflight_base
from scripts import prepare_dvd_second_wave_2d_j_dual_profile_persistent as dual
from scripts.apply_dvd_second_wave_2d_j import (
    ACTOR,
    APPLY_CONFIRMATION,
    APPLY_PHASE,
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    CLASS_ID,
    EXPECTED_LEGACY_MIGRATION_ARTIFACTS,
    EXPECTED_PROFILE,
    EXPECTED_SCOPE,
    EXPECTED_SIBLING_COUNT,
    EXPECTED_SIBLING_IDS,
    EXPECTED_TARGETS,
    EXPECTED_VALID_FROM,
    PERSISTENT_BACKUP_DIR,
    PERSISTENT_RECEIPT_DIR,
    ROLLBACK_CONFIRMATION,
    SCHOOL_ID,
    STAFF_ID,
    TEACHER_USER_ID,
    SecondWaveGateError,
    _configure_base,
    load_and_verify_backup,
    validate_manifest_semantics,
    validate_peer_evidence,
)
from scripts.apply_dvd_second_wave_2d_j_persistent import (
    PersistentSealArgumentError,
    build_locked_argv,
    validate_runtime_args,
)


def _peer_evidence():
    sibling_ids = sorted(EXPECTED_SIBLING_IDS)
    result = {}
    for spec in EXPECTED_TARGETS.values():
        result[spec["legacy_id"]] = {
            "evidence_model": dual.DUAL_PROFILE_EVIDENCE,
            "peer_count": 1,
            "profile": EXPECTED_PROFILE,
            "profile_counts": {EXPECTED_PROFILE: 1},
            "same_component_ids": [spec["peer_id"]],
            "sibling_count": EXPECTED_SIBLING_COUNT,
            "sibling_ids": sibling_ids,
            "sibling_profile_counts": {EXPECTED_PROFILE: EXPECTED_SIBLING_COUNT},
            "student_scope": EXPECTED_SCOPE,
        }
    return result


def _manifest():
    rows = []
    for assignment_id, spec in EXPECTED_TARGETS.items():
        legacy_id = spec["legacy_id"]
        source_spec = preflight_base.APPROVED_TARGETS[legacy_id]
        rows.append(
            {
                "id": assignment_id,
                "teacher_id": TEACHER_USER_ID,
                "teacher_name": "Juliana da Silva Leao",
                "class_id": CLASS_ID,
                "class_name": "Berçario II A",
                "school_id": SCHOOL_ID,
                "mantenedora_id": "tenant-1",
                "component_id": spec["component_id"],
                "component_name": spec["component_name"],
                "weekly_slots": source_spec["weekly_slots"],
                "valid_from": EXPECTED_VALID_FROM,
                "valid_until": None,
                "is_substitute": False,
                "source": "import",
                "diary_settings": {
                    "enabled": True,
                    "schema_version": 1,
                    "profile": EXPECTED_PROFILE,
                    "student_scope": EXPECTED_SCOPE,
                },
                "cutover_provenance": {
                    "phase": preflight_base.PROVENANCE_PHASE,
                    "state": "DRY_RUN_ONLY",
                    "source_legacy_assignment_id": legacy_id,
                    "evidence": dual.REQUIRED_EVIDENCE,
                    "schedule_state": "schedule_ready",
                    "slots_per_day": preflight_base.REQUIRED_SLOTS_PER_DAY,
                    "workload": spec["workload"],
                    "peer_profile": EXPECTED_PROFILE,
                    "peer_profile_count": 1,
                    "profile_evidence": dual.DUAL_PROFILE_EVIDENCE,
                    "same_component_peer_count": 1,
                    "sibling_profile_count": EXPECTED_SIBLING_COUNT,
                },
            }
        )
    rows.sort(key=lambda row: (str(row.get("component_name") or "").casefold(), str(row["id"])))
    return rows


def _sealed_backup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preflight_base, "PERSISTENT_BACKUP_ROOT", tmp_path)
    manifest = _manifest()
    manifest_sha = preflight_base.manifest_digest(manifest)
    evidence = _peer_evidence()
    validated = {
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "peer_evidence": evidence,
        "valid_from": EXPECTED_VALID_FROM,
        "school_class_count": 2,
        "current_sibling_count": EXPECTED_SIBLING_COUNT,
    }
    bundle = {
        "scope": {
            "academic_year": 2026,
            "class_ids": [CLASS_ID],
            "second_wave_2d_j_legacy_migration_artifacts": [
                {"id": "legacy-a"},
                {"id": "legacy-b"},
            ],
            "second_wave_2d_j_profile_evidence": evidence,
        },
        "collections": {
            "teacher_class_assignments_before": [
                {"id": "baseline", "class_id": CLASS_ID}
            ],
            "teacher_assignments_source": [],
        },
    }
    backup_dir = tmp_path / "backup"
    sealed = preflight_base.write_backup_directory(
        backup_dir,
        validated=validated,
        bundle=bundle,
    )
    return backup_dir, manifest_sha, sealed["backup_bundle_sha256"]


def test_production_seal_constants_are_pinned():
    assert APPROVED_READY_COUNT == 2
    assert APPROVED_MANIFEST_SHA256 == (
        "d55cf98685e6025f2ef988cc7df1cdfb2c307a5565a1a612b996614e026889c9"
    )
    assert APPROVED_BACKUP_BUNDLE_SHA256 == (
        "8961e226b44dc760754c03a9ee41c545821249cc918a69b68dd2e6d9dbe094bd"
    )
    assert PERSISTENT_BACKUP_DIR == Path(
        "/data/sigesc-dvd-backups/dvd-second-wave-2d-j-preflight-v2"
    )
    assert PERSISTENT_RECEIPT_DIR == Path(
        "/data/sigesc-dvd-backups/receipts/second-wave-2d-j"
    )
    assert APPLY_PHASE == "SECOND_WAVE_2D_J"
    assert ACTOR == "dvd-second-wave-2d-j"
    assert APPLY_CONFIRMATION == "APPLY-DVD-SECOND-WAVE-2D-J-2"
    assert ROLLBACK_CONFIRMATION == "ROLLBACK-DVD-SECOND-WAVE-2D-J-2"
    assert EXPECTED_PROFILE == "regular"
    assert EXPECTED_SCOPE == "all"
    assert EXPECTED_VALID_FROM == "2026-08-18"
    assert EXPECTED_SIBLING_COUNT == 7
    assert EXPECTED_LEGACY_MIGRATION_ARTIFACTS == 2
    assert set(EXPECTED_TARGETS) == {
        "bd8273ec-2dfd-563a-80c7-38b7c32088f9",
        "332d4421-cb57-5a4b-bf2c-eb8878904373",
    }


def test_manifest_and_dual_profile_evidence_accept_exact_snapshot():
    validate_manifest_semantics(_manifest())
    validate_peer_evidence(_peer_evidence())


def test_manifest_profile_or_evidence_drift_fails_closed():
    manifest = _manifest()
    manifest[0]["diary_settings"]["profile"] = "integrator"
    with pytest.raises(SecondWaveGateError, match="MANIFEST_DIARY_PROFILE"):
        validate_manifest_semantics(manifest)

    evidence = _peer_evidence()
    first = sorted(evidence)[0]
    evidence[first]["sibling_count"] = 6
    with pytest.raises(SecondWaveGateError, match="PEER_EVIDENCE_SIBLING_COUNT"):
        validate_peer_evidence(evidence)


def test_manifest_id_set_is_exact_and_non_expandable():
    manifest = _manifest()
    manifest[0]["id"] = "other"
    with pytest.raises(SecondWaveGateError, match="SEALED_MANIFEST_ID_SET_MISMATCH"):
        validate_manifest_semantics(manifest)


def test_backup_loader_accepts_matching_dual_profile_seal(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, bundle_sha = _sealed_backup(tmp_path, monkeypatch)
    loaded = load_and_verify_backup(
        backup_dir,
        expected_manifest_sha256=manifest_sha,
        expected_count=2,
        expected_backup_sha256=bundle_sha,
    )
    assert loaded["manifest_sha256"] == manifest_sha
    assert loaded["backup_bundle_sha256"] == bundle_sha
    assert loaded["metadata"]["current_sibling_count"] == EXPECTED_SIBLING_COUNT


def test_backup_loader_rejects_unapproved_bundle(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, _ = _sealed_backup(tmp_path, monkeypatch)
    with pytest.raises(SecondWaveGateError, match="BACKUP_BUNDLE_NOT_APPROVED"):
        load_and_verify_backup(
            backup_dir,
            expected_manifest_sha256=manifest_sha,
            expected_count=2,
            expected_backup_sha256="0" * 64,
        )


def test_shared_apply_helpers_receive_2d_j_provenance():
    old_phase = apply_base.APPLY_PHASE
    old_actor = apply_base.ACTOR
    try:
        _configure_base()
        assert apply_base.APPLY_PHASE == APPLY_PHASE
        assert apply_base.ACTOR == ACTOR
        docs = apply_base.build_apply_documents(
            [_manifest()[0]],
            manifest_sha256="m" * 64,
            backup_bundle_sha256="b" * 64,
            run_id="run-2d-j",
            activated_at="2026-08-25T23:45:00+00:00",
        )
        provenance = docs[0]["cutover_provenance"]
        assert provenance["apply_phase"] == APPLY_PHASE
        assert provenance["evidence"] == dual.REQUIRED_EVIDENCE
        assert provenance["profile_evidence"] == dual.DUAL_PROFILE_EVIDENCE
        assert provenance["same_component_peer_count"] == 1
        assert provenance["sibling_profile_count"] == EXPECTED_SIBLING_COUNT
        assert docs[0]["created_by"] == ACTOR
    finally:
        apply_base.APPLY_PHASE = old_phase
        apply_base.ACTOR = old_actor


def test_persistent_entrypoint_is_locked_and_defaults_to_dry_run():
    argv = build_locked_argv([])
    assert "--apply" not in argv
    assert "--rollback" not in argv
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
        ["--expected-count", "3"],
        ["--academic-year", "2027"],
        ["--receipt-dir", "/tmp/receipts"],
        ["--teacher-user-id", "other"],
        ["--class-id", "other"],
    ],
)
def test_authoritative_scope_cannot_be_overridden(args):
    with pytest.raises(PersistentSealArgumentError, match="SEALED_ARGUMENT_OVERRIDE"):
        validate_runtime_args(args)


def test_apply_and_rollback_cannot_be_combined():
    with pytest.raises(PersistentSealArgumentError, match="MUTUALLY_EXCLUSIVE"):
        validate_runtime_args(["--apply", "--rollback"])


def test_persistent_entrypoint_executes_without_pythonpath():
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/apply_dvd_second_wave_2d_j_persistent.py",
            "--entrypoint-import-regression-probe",
        ],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in combined
    assert "SEALED_ARGUMENT_OVERRIDE_NOT_ALLOWED" in combined


def test_2d_j_apply_delegates_mutation_to_shared_base_and_is_dry_run_by_default():
    apply_src = Path("scripts/apply_dvd_second_wave_2d_j.py").read_text(encoding="utf-8")
    wrapper_src = Path("scripts/apply_dvd_second_wave_2d_j_persistent.py").read_text(encoding="utf-8")

    assert "if not args.apply:" in apply_src
    assert "APPLY_CONFIRMATION_REQUIRED" in apply_src
    assert "ROLLBACK_CONFIRMATION_REQUIRED" in apply_src
    assert "await apply_base.apply_second_wave(" in apply_src
    assert "await apply_base.rollback_second_wave(" in apply_src

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
    assert not any(token in apply_src for token in forbidden)
    assert not any(token in wrapper_src for token in forbidden)
    assert "sys.path.insert(0, str(BACKEND_DIR))" in wrapper_src
    assert "await implementation.main()" in wrapper_src
