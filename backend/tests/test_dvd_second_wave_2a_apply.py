from pathlib import Path

import pytest

from scripts.apply_dvd_second_wave_2a import (
    ACTOR,
    APPLY_CONFIRMATION,
    APPLY_PHASE,
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    BACKUP_MODE,
    ROLLBACK_CONFIRMATION,
    SecondWaveGateError,
    _assert_baseline_unchanged,
    _core,
    _verify_applied_docs,
    build_apply_documents,
    load_and_verify_backup,
)
from scripts.audit_dvd_first_wave_manifest import manifest_digest
from scripts.prepare_dvd_second_wave_2a import write_backup_directory


def _manifest_row():
    return {
        "id": "dvd-2a-1",
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
                "weekday": 1,
                "aula_numero": 1,
                "start_time": "07:00",
                "end_time": "08:00",
            }
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
            "schedule_source": "existing_exact_schedule",
            "recovery_state": "schedule_ready",
        },
    }


def _sealed_backup(tmp_path: Path):
    manifest = [_manifest_row()]
    manifest_sha = manifest_digest(manifest)
    report = {
        "summary": {
            "manifest_sha256": manifest_sha,
            "second_wave_2a_ready": 1,
            "source_38e_manifest_sha256": "source-sha",
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
    sealed = write_backup_directory(
        backup_dir,
        manifest_report=report,
        bundle=bundle,
    )
    return backup_dir, manifest_sha, sealed["backup_bundle_sha256"]


def test_production_snapshot_constants_are_pinned():
    assert APPROVED_READY_COUNT == 27
    assert APPROVED_MANIFEST_SHA256 == (
        "7ab088f1705c28894adadd4b9d294440cf07d77030ed6ae2d8af7435b043b546"
    )
    assert APPROVED_BACKUP_BUNDLE_SHA256 == (
        "ecfd6fa75d141e37561b48d82a7a6485213ef43735b08f0c0cd271e2bf0ef180"
    )
    assert BACKUP_MODE == "SECOND_WAVE_2A_PREFLIGHT_READ_ONLY"
    assert APPLY_PHASE == "SECOND_WAVE_2A-B"
    assert APPLY_CONFIRMATION == "APPLY-DVD-SECOND-WAVE-2A-27"
    assert ROLLBACK_CONFIRMATION == "ROLLBACK-DVD-SECOND-WAVE-2A-27"


def test_backup_loader_accepts_only_matching_seal(tmp_path: Path):
    backup_dir, manifest_sha, bundle_sha = _sealed_backup(tmp_path)

    loaded = load_and_verify_backup(
        backup_dir,
        expected_manifest_sha256=manifest_sha,
        expected_count=1,
        expected_backup_sha256=bundle_sha,
    )

    assert loaded["manifest_sha256"] == manifest_sha
    assert loaded["backup_bundle_sha256"] == bundle_sha
    assert loaded["metadata"]["mode"] == BACKUP_MODE
    assert loaded["metadata"]["mutates_database"] is False


def test_backup_loader_rejects_unapproved_bundle(tmp_path: Path):
    backup_dir, manifest_sha, _ = _sealed_backup(tmp_path)

    with pytest.raises(SecondWaveGateError, match="BACKUP_BUNDLE_NOT_APPROVED"):
        load_and_verify_backup(
            backup_dir,
            expected_manifest_sha256=manifest_sha,
            expected_count=1,
            expected_backup_sha256="0" * 64,
        )


def test_apply_documents_preserve_core_and_add_sealed_provenance():
    proposed = _manifest_row()
    docs = build_apply_documents(
        [proposed],
        manifest_sha256="m" * 64,
        backup_bundle_sha256="b" * 64,
        run_id="run-1",
        activated_at="2026-08-25T14:00:00+00:00",
    )

    assert len(docs) == 1
    doc = docs[0]
    assert _core(doc) == _core(proposed)
    assert doc["deleted"] is False
    assert doc["created_by"] == ACTOR
    assert doc["updated_by"] == ACTOR
    provenance = doc["cutover_provenance"]
    assert provenance["phase"] == "38E"
    assert provenance["schedule_source"] == "existing_exact_schedule"
    assert provenance["apply_phase"] == APPLY_PHASE
    assert provenance["apply_state"] == "ACTIVATED"
    assert provenance["manifest_sha256"] == "m" * 64
    assert provenance["backup_bundle_sha256"] == "b" * 64
    assert provenance["apply_run_id"] == "run-1"


def test_applied_doc_verification_rejects_core_drift():
    proposed = _manifest_row()
    actual = build_apply_documents(
        [proposed],
        manifest_sha256="m" * 64,
        backup_bundle_sha256="b" * 64,
        run_id="run-1",
        activated_at="2026-08-25T14:00:00+00:00",
    )[0]

    _verify_applied_docs(
        {actual["id"]: actual},
        [proposed],
        expected_manifest_sha256="m" * 64,
        expected_backup_sha256="b" * 64,
    )

    bad = dict(actual)
    bad["component_id"] = "component-alterado"
    with pytest.raises(SecondWaveGateError, match="APPLIED_DOC_CORE_MISMATCH"):
        _verify_applied_docs(
            {bad["id"]: bad},
            [proposed],
            expected_manifest_sha256="m" * 64,
            expected_backup_sha256="b" * 64,
        )


def test_baseline_guard_is_fail_closed():
    baseline = [{"id": "a", "class_id": "c1"}]
    _assert_baseline_unchanged(baseline, baseline)

    with pytest.raises(SecondWaveGateError, match="PRE_APPLY_BASELINE_DRIFT"):
        _assert_baseline_unchanged(
            [{"id": "a", "class_id": "c1"}, {"id": "b", "class_id": "c1"}],
            baseline,
        )


def test_apply_script_defaults_to_dry_run_and_has_no_update_mutators():
    src = Path("scripts/apply_dvd_second_wave_2a.py").read_text(encoding="utf-8")
    assert "if not args.apply:" in src
    assert "APPLY_CONFIRMATION_REQUIRED" in src
    assert "ROLLBACK_CONFIRMATION_REQUIRED" in src
    assert ".insert_many(" in src
    assert ".delete_many(" in src
    assert ".update_one(" not in src
    assert ".update_many(" not in src
    assert ".replace_one(" not in src
