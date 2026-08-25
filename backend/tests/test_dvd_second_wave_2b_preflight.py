from pathlib import Path

import pytest

from scripts.prepare_dvd_second_wave_2b import (
    ALLOWED_RECOVERY_STATES,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    BACKUP_MODE,
    PERSISTENT_BACKUP_ROOT,
    PreflightGateError,
    assert_script_read_only,
    select_second_wave_2b,
    validate_manifest_gate,
    validate_persistent_backup_path,
    write_backup_directory,
)


def _proposed(doc_id, legacy_id, schedule_source, recovery_state):
    return {
        "id": doc_id,
        "teacher_id": "teacher-1",
        "teacher_name": "Professora",
        "class_id": f"class-{doc_id}",
        "class_name": f"Turma {doc_id}",
        "school_id": "school-1",
        "component_id": f"component-{doc_id}",
        "component_name": f"Componente {doc_id}",
        "weekly_slots": [
            {
                "weekday": 1,
                "aula_numero": 1,
                "start_time": "07:00",
                "end_time": "08:00",
            }
        ],
        "valid_from": "2026-08-18",
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "cutover_provenance": {
            "source_legacy_assignment_id": legacy_id,
            "schedule_source": schedule_source,
            "recovery_state": recovery_state,
        },
    }


def test_selector_inclui_somente_ready_da_recuperacao_2b_aprovada():
    source = {
        "meta": {
            "mode": "READ_ONLY_FIRST_WAVE_MANIFEST",
            "academic_year": 2026,
            "reference_date": "2026-08-18",
        },
        "summary": {
            "first_wave_ready": 2,
            "manifest_sha256": "source-sha",
        },
        "details": [
            {
                "legacy_assignment_id": "legacy-exact",
                "first_wave_state": "ready",
                "schedule_source": "existing_exact_schedule",
                "recovery_state": "schedule_ready",
            },
            {
                "legacy_assignment_id": "legacy-2b",
                "first_wave_state": "ready",
                "schedule_source": "deterministic_recovery",
                "recovery_state": "time_recoverable_unique_school_shift",
            },
        ],
        "manifest": [
            _proposed(
                "dvd-exact",
                "legacy-exact",
                "existing_exact_schedule",
                "schedule_ready",
            ),
            _proposed(
                "dvd-2b",
                "legacy-2b",
                "deterministic_recovery",
                "time_recoverable_unique_school_shift",
            ),
        ],
    }

    report = select_second_wave_2b(source)

    assert report["summary"]["second_wave_2b_ready"] == 1
    assert report["summary"]["source_38e_ready"] == 2
    assert report["summary"]["source_38e_manifest_sha256"] == "source-sha"
    assert report["summary"]["recovery_states"] == {
        "time_recoverable_unique_school_shift": 1
    }
    assert [row["id"] for row in report["manifest"]] == ["dvd-2b"]


def test_selector_falha_se_estado_de_recuperacao_mudar():
    source = {
        "meta": {},
        "summary": {},
        "details": [
            {
                "legacy_assignment_id": "legacy-other",
                "first_wave_state": "ready",
                "schedule_source": "deterministic_recovery",
                "recovery_state": "time_recoverable_same_schedule",
            }
        ],
        "manifest": [
            _proposed(
                "dvd-other",
                "legacy-other",
                "deterministic_recovery",
                "time_recoverable_same_schedule",
            )
        ],
    }

    with pytest.raises(PreflightGateError, match="READY_RECOVERY_STATE_NOT_ALLOWED"):
        select_second_wave_2b(source)


def test_selector_falha_se_detail_ready_nao_estiver_no_manifesto():
    source = {
        "meta": {},
        "summary": {},
        "details": [
            {
                "legacy_assignment_id": "legacy-2b",
                "first_wave_state": "ready",
                "schedule_source": "deterministic_recovery",
                "recovery_state": "time_recoverable_unique_school_shift",
            }
        ],
        "manifest": [],
    }

    with pytest.raises(PreflightGateError, match="READY_DETAIL_MANIFEST_MISMATCH"):
        select_second_wave_2b(source)


def test_selector_falha_com_weekly_slots_vazio():
    row = _proposed(
        "dvd-2b",
        "legacy-2b",
        "deterministic_recovery",
        "time_recoverable_unique_school_shift",
    )
    row["weekly_slots"] = []
    source = {
        "meta": {},
        "summary": {"first_wave_ready": 1},
        "details": [
            {
                "legacy_assignment_id": "legacy-2b",
                "first_wave_state": "ready",
                "schedule_source": "deterministic_recovery",
                "recovery_state": "time_recoverable_unique_school_shift",
            }
        ],
        "manifest": [row],
    }

    with pytest.raises(PreflightGateError, match="MANIFEST_WEEKLY_SLOTS_EMPTY"):
        select_second_wave_2b(source)


def test_manifest_gate_aceita_apenas_snapshot_aprovado():
    validate_manifest_gate(
        {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "second_wave_2b_ready": APPROVED_READY_COUNT,
        },
        expected_sha256=APPROVED_MANIFEST_SHA256,
        expected_count=APPROVED_READY_COUNT,
    )


def test_manifest_gate_rejeita_hash_drift():
    with pytest.raises(PreflightGateError, match="MANIFEST_SHA256_MISMATCH"):
        validate_manifest_gate(
            {
                "manifest_sha256": "0" * 64,
                "second_wave_2b_ready": APPROVED_READY_COUNT,
            },
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_manifest_gate_rejeita_count_drift():
    with pytest.raises(PreflightGateError, match="MANIFEST_COUNT_MISMATCH"):
        validate_manifest_gate(
            {
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "second_wave_2b_ready": APPROVED_READY_COUNT - 1,
            },
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_snapshot_aprovado_corresponde_a_auditoria_de_producao():
    assert APPROVED_READY_COUNT == 13
    assert APPROVED_MANIFEST_SHA256 == (
        "4d84e76b7236d2e6c5e0b8199165aa1e034d6d2529ceed05d248226ff9af72fc"
    )
    assert ALLOWED_RECOVERY_STATES == frozenset(
        {"time_recoverable_unique_school_shift"}
    )


def test_backup_e_selado_com_metadados_2b(tmp_path: Path):
    target = tmp_path / "backup"
    manifest_report = {
        "summary": {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "second_wave_2b_ready": APPROVED_READY_COUNT,
            "source_38e_manifest_sha256": APPROVED_MANIFEST_SHA256,
            "recovery_states": {"time_recoverable_unique_school_shift": 13},
            "weekly_slots_counts": {"5": 13},
        },
        "manifest": [{"id": "dvd-1", "class_id": "c1"}],
    }
    bundle = {
        "scope": {"academic_year": 2026, "class_ids": ["c1"]},
        "collections": {
            "teacher_class_assignments_before": [
                {"id": "old-1", "class_id": "c1"}
            ],
            "teacher_assignments_source": [
                {"id": "legacy-1", "class_id": "c1"}
            ],
        },
    }

    result = write_backup_directory(
        target,
        manifest_report=manifest_report,
        bundle=bundle,
    )

    assert (target / "manifest.json").is_file()
    assert (target / "teacher_class_assignments_before.json").is_file()
    assert (target / "backup-metadata.json").is_file()
    assert (target / "BACKUP-SEAL.json").is_file()
    assert len(result["backup_bundle_sha256"]) == 64
    assert result["mode"] == BACKUP_MODE
    assert result["mutates_database"] is False
    assert result["recovery_states"] == {
        "time_recoverable_unique_school_shift": 13
    }


def test_backup_nunca_sobrescreve_diretorio_existente(tmp_path: Path):
    target = tmp_path / "backup"
    target.mkdir()

    with pytest.raises(FileExistsError):
        write_backup_directory(
            target,
            manifest_report={"summary": {}, "manifest": []},
            bundle={"scope": {}, "collections": {}},
        )


def test_cli_exige_caminho_no_volume_persistente():
    validate_persistent_backup_path(
        PERSISTENT_BACKUP_ROOT / "dvd-second-wave-2b-preflight"
    )

    with pytest.raises(PreflightGateError, match="BACKUP_PATH_NOT_PERSISTENT"):
        validate_persistent_backup_path(Path("/tmp/dvd-second-wave-2b"))

    with pytest.raises(PreflightGateError, match="BACKUP_PATH_MUST_BE_CHILD_DIRECTORY"):
        validate_persistent_backup_path(PERSISTENT_BACKUP_ROOT)


def test_preflight_contem_zero_mutadores_mongo_e_zero_apply_cli():
    assert_script_read_only()
    src = Path("scripts/prepare_dvd_second_wave_2b.py").read_text(encoding="utf-8")
    assert "APPLY_CONFIRMATION" not in src
    assert "ROLLBACK_CONFIRMATION" not in src
    assert "--apply" not in src
    assert "--rollback" not in src
