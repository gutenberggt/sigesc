from pathlib import Path
import os
import subprocess
import sys

import pytest

from scripts import apply_dvd_second_wave_2a as base
from scripts import prepare_dvd_second_wave_2c as preflight
from scripts.apply_dvd_second_wave_2c import (
    ACTOR,
    APPLY_CONFIRMATION,
    APPLY_PHASE,
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    CLASS_ID,
    EXPECTED_EXCLUDED_BLOCKERS,
    EXPECTED_RESIDUE_COUNTS,
    EXPECTED_SOURCE_BLOCKED,
    EXPECTED_SOURCE_MISSING_TOTAL,
    EXPECTED_WEEKLY_SLOTS_COUNTS,
    PERSISTENT_BACKUP_DIR,
    PERSISTENT_RECEIPT_DIR,
    ROLLBACK_CONFIRMATION,
    SCHOOL_ID,
    TEACHER_USER_ID,
    SecondWaveGateError,
    _configure_base,
    load_and_verify_backup,
)
from scripts.apply_dvd_second_wave_2c_persistent import (
    PersistentSealArgumentError,
    build_locked_argv,
    validate_runtime_args,
)
from scripts.remediate_dvd_out_of_range_schedule_p0 import manifest_digest


def _row(*, legacy_id: str, component_name: str, proposed_id: str, weekly: int, residue_slot: int):
    return {
        "id": proposed_id,
        "teacher_id": TEACHER_USER_ID,
        "teacher_name": "Juliana da Silva Leao",
        "class_id": CLASS_ID,
        "class_name": "Berçario II A",
        "school_id": SCHOOL_ID,
        "mantenedora_id": "tenant-1",
        "component_id": f"component-{legacy_id[-4:]}",
        "component_name": component_name,
        "weekly_slots": [
            {
                "weekday": n + 1,
                "aula_numero": 1,
                "start_time": "07:00",
                "end_time": "08:00",
            }
            for n in range(weekly)
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
            "phase": preflight.PROVENANCE_PHASE,
            "state": "DRY_RUN_ONLY",
            "source_legacy_assignment_id": legacy_id,
            "evidence": preflight.REQUIRED_EVIDENCE,
            "slots_per_day": preflight.REQUIRED_SLOTS_PER_DAY,
            "ignored_out_of_range_slots": [
                {
                    "day": day,
                    "slot_number": residue_slot,
                    "course_id": f"component-{legacy_id[-4:]}",
                }
                for day in ("segunda", "terca", "quarta", "quinta", "sexta")
            ],
        },
    }


def _manifest():
    return [
        _row(
            legacy_id="0f96bcb8-33e9-47ca-add4-e9d9f9b4635d",
            component_name="Linguagem Recreativa Com Práticas de Esporte e Lazer",
            proposed_id="b1ed1194-3118-5d32-9fce-cd4ef9cb4093",
            weekly=3,
            residue_slot=8,
        ),
        _row(
            legacy_id="8d48d5bd-418c-414a-88ce-015a8bd20fa6",
            component_name="Arte e Cultura",
            proposed_id="d3645603-7051-57c8-bcb2-f7326767e8e0",
            weekly=4,
            residue_slot=9,
        ),
    ]


def _sealed_backup(tmp_path: Path, monkeypatch):
    manifest = _manifest()
    manifest_sha = manifest_digest(manifest)
    monkeypatch.setattr(preflight, "APPROVED_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(preflight, "PERSISTENT_BACKUP_ROOT", tmp_path)

    report = {
        "summary": {
            "ready": 2,
            "manifest_sha256": manifest_sha,
            "missing_total": 4,
            "blocked": 2,
        },
        "manifest": manifest,
        "details": [
            {"state": "blocked", "blockers": ["no_out_of_range_residue"]},
            {"state": "blocked", "blockers": ["no_out_of_range_residue"]},
        ],
    }
    validated = preflight.validate_2c_report(report)
    bundle = {
        "scope": {"academic_year": 2026, "class_ids": [CLASS_ID]},
        "collections": {
            "teacher_class_assignments_before": [
                {"id": "existing-1", "class_id": CLASS_ID}
            ],
            "teacher_assignments_source": [
                {"id": "legacy-source", "class_id": CLASS_ID}
            ],
        },
    }
    backup_dir = tmp_path / "backup"
    sealed = preflight.write_backup_directory(
        backup_dir,
        validated=validated,
        bundle=bundle,
    )
    return backup_dir, manifest_sha, sealed["backup_bundle_sha256"]


def test_production_snapshot_constants_are_pinned():
    assert APPROVED_READY_COUNT == 2
    assert APPROVED_MANIFEST_SHA256 == (
        "09aa29dd9c535c1b83de8390a14c24d6cf44d77e7eb811530c87dc8222cc0223"
    )
    assert APPROVED_BACKUP_BUNDLE_SHA256 == (
        "02b0b0e64fa1d208dfd9a22a56c69c6028df9e3157b61beeb77e93bdb6430975"
    )
    assert PERSISTENT_BACKUP_DIR == Path(
        "/data/sigesc-dvd-backups/dvd-second-wave-2c-preflight-v1"
    )
    assert PERSISTENT_RECEIPT_DIR == Path(
        "/data/sigesc-dvd-backups/receipts/second-wave-2c"
    )
    assert EXPECTED_SOURCE_MISSING_TOTAL == 4
    assert EXPECTED_SOURCE_BLOCKED == 2
    assert EXPECTED_EXCLUDED_BLOCKERS == {"no_out_of_range_residue": 2}
    assert EXPECTED_WEEKLY_SLOTS_COUNTS == {"3": 1, "4": 1}
    assert EXPECTED_RESIDUE_COUNTS == {"5": 2}
    assert APPLY_PHASE == "SECOND_WAVE_2C"
    assert ACTOR == "dvd-second-wave-2c"
    assert APPLY_CONFIRMATION == "APPLY-DVD-SECOND-WAVE-2C-2"
    assert ROLLBACK_CONFIRMATION == "ROLLBACK-DVD-SECOND-WAVE-2C-2"


def test_backup_loader_accepts_matching_2c_seal(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, bundle_sha = _sealed_backup(tmp_path, monkeypatch)

    loaded = load_and_verify_backup(
        backup_dir,
        expected_manifest_sha256=manifest_sha,
        expected_count=2,
        expected_backup_sha256=bundle_sha,
    )

    assert loaded["manifest_sha256"] == manifest_sha
    assert loaded["backup_bundle_sha256"] == bundle_sha
    assert loaded["metadata"]["second_wave_2c_ready"] == 2
    assert loaded["metadata"]["excluded_blockers"] == EXPECTED_EXCLUDED_BLOCKERS


def test_backup_loader_rejects_unapproved_bundle(tmp_path: Path, monkeypatch):
    backup_dir, manifest_sha, _ = _sealed_backup(tmp_path, monkeypatch)

    with pytest.raises(SecondWaveGateError, match="BACKUP_BUNDLE_NOT_APPROVED"):
        load_and_verify_backup(
            backup_dir,
            expected_manifest_sha256=manifest_sha,
            expected_count=2,
            expected_backup_sha256="0" * 64,
        )


def test_shared_apply_helpers_receive_2c_provenance():
    old_phase = base.APPLY_PHASE
    old_actor = base.ACTOR
    try:
        _configure_base()
        assert base.APPLY_PHASE == APPLY_PHASE
        assert base.ACTOR == ACTOR

        docs = base.build_apply_documents(
            [_manifest()[0]],
            manifest_sha256="m" * 64,
            backup_bundle_sha256="b" * 64,
            run_id="run-2c",
            activated_at="2026-08-25T22:30:00+00:00",
        )
        provenance = docs[0]["cutover_provenance"]
        assert provenance["apply_phase"] == APPLY_PHASE
        assert provenance["evidence"] == preflight.REQUIRED_EVIDENCE
        assert provenance["slots_per_day"] == 7
        assert docs[0]["created_by"] == ACTOR
    finally:
        base.APPLY_PHASE = old_phase
        base.ACTOR = old_actor


def test_persistent_entrypoint_defaults_to_dry_run_and_forwards_only_mode():
    argv = build_locked_argv([])
    assert "--apply" not in argv
    assert "--rollback" not in argv

    assert validate_runtime_args(
        ["--apply", "--confirm", APPLY_CONFIRMATION]
    ) == ["--apply", "--confirm", APPLY_CONFIRMATION]
    assert validate_runtime_args(
        ["--rollback", f"--confirm={ROLLBACK_CONFIRMATION}"]
    )[0] == "--rollback"


def test_persistent_entrypoint_executes_as_production_script_without_pythonpath():
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/apply_dvd_second_wave_2c_persistent.py",
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


def test_confirmation_requires_value():
    with pytest.raises(PersistentSealArgumentError, match="CONFIRM_VALUE_REQUIRED"):
        validate_runtime_args(["--apply", "--confirm"])


def test_scripts_are_dry_run_by_default_and_delegate_mutation_to_shared_base():
    apply_src = Path("scripts/apply_dvd_second_wave_2c.py").read_text(encoding="utf-8")
    wrapper_src = Path("scripts/apply_dvd_second_wave_2c_persistent.py").read_text(
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
    assert not any(token in apply_src for token in forbidden)
    assert not any(token in wrapper_src for token in forbidden)
    assert "sys.path.insert(0, str(BACKEND_DIR))" in wrapper_src
    assert "await implementation.main()" in wrapper_src
