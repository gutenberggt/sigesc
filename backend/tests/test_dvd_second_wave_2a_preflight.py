from pathlib import Path

import pytest

from scripts.prepare_dvd_second_wave_2a import (
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    PreflightGateError,
    assert_script_read_only,
    select_second_wave_2a,
    validate_manifest_gate,
    write_backup_directory,
)


def _proposed(doc_id, legacy_id, schedule_source):
    return {
        "id": doc_id,
        "teacher_id": "teacher-1",
        "teacher_name": "Professora",
        "class_id": f"class-{doc_id}",
        "class_name": f"Turma {doc_id}",
        "school_id": "school-1",
        "component_id": f"component-{doc_id}",
        "component_name": f"Componente {doc_id}",
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
        },
    }


def test_selector_inclui_somente_ready_com_horario_exato():
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
            },
            {
                "legacy_assignment_id": "legacy-recovered",
                "first_wave_state": "ready",
                "schedule_source": "deterministic_recovery",
            },
            {
                "legacy_assignment_id": "legacy-blocked",
                "first_wave_state": "blocked",
                "schedule_source": None,
            },
        ],
        "manifest": [
            _proposed("dvd-exact", "legacy-exact", "existing_exact_schedule"),
            _proposed("dvd-recovered", "legacy-recovered", "deterministic_recovery"),
        ],
    }

    report = select_second_wave_2a(source)

    assert report["summary"]["second_wave_2a_ready"] == 1
    assert report["summary"]["source_38e_ready"] == 2
    assert report["summary"]["source_38e_manifest_sha256"] == "source-sha"
    assert [row["id"] for row in report["manifest"]] == ["dvd-exact"]
    assert report["manifest"][0]["cutover_provenance"]["schedule_source"] == "existing_exact_schedule"


def test_selector_falha_se_detail_ready_nao_estiver_no_manifesto():
    source = {
        "meta": {},
        "summary": {},
        "details": [
            {
                "legacy_assignment_id": "legacy-exact",
                "first_wave_state": "ready",
                "schedule_source": "existing_exact_schedule",
            }
        ],
        "manifest": [],
    }

    with pytest.raises(PreflightGateError, match="READY_DETAIL_MANIFEST_MISMATCH"):
        select_second_wave_2a(source)


def test_manifest_gate_aceita_apenas_snapshot_aprovado():
    validate_manifest_gate(
        {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "second_wave_2a_ready": APPROVED_READY_COUNT,
        },
        expected_sha256=APPROVED_MANIFEST_SHA256,
        expected_count=APPROVED_READY_COUNT,
    )


def test_manifest_gate_rejeita_hash_drift():
    with pytest.raises(PreflightGateError, match="MANIFEST_SHA256_MISMATCH"):
        validate_manifest_gate(
            {
                "manifest_sha256": "0" * 64,
                "second_wave_2a_ready": APPROVED_READY_COUNT,
            },
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_manifest_gate_rejeita_count_drift():
    with pytest.raises(PreflightGateError, match="MANIFEST_COUNT_MISMATCH"):
        validate_manifest_gate(
            {
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "second_wave_2a_ready": APPROVED_READY_COUNT - 1,
            },
            expected_sha256=APPROVED_MANIFEST_SHA256,
            expected_count=APPROVED_READY_COUNT,
        )


def test_snapshot_aprovado_corresponde_a_auditoria_de_producao():
    assert APPROVED_READY_COUNT == 27
    assert APPROVED_MANIFEST_SHA256 == "7ab088f1705c28894adadd4b9d294440cf07d77030ed6ae2d8af7435b043b546"


def test_backup_e_selado_e_preserva_pre_state(tmp_path: Path):
    target = tmp_path / "backup"
    manifest_report = {
        "summary": {
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "second_wave_2a_ready": APPROVED_READY_COUNT,
            "source_38e_manifest_sha256": "source-sha",
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
    assert result["mode"] == "SECOND_WAVE_2A_PREFLIGHT_READ_ONLY"
    assert result["mutates_database"] is False
    assert result["file_counts"]["manifest.json"] == 1


def test_backup_nunca_sobrescreve_diretorio_existente(tmp_path: Path):
    target = tmp_path / "backup"
    target.mkdir()

    with pytest.raises(FileExistsError):
        write_backup_directory(
            target,
            manifest_report={"summary": {}, "manifest": []},
            bundle={"scope": {}, "collections": {}},
        )


def test_preflight_contem_zero_mutadores_mongo_e_zero_apply_cli():
    assert_script_read_only()
    src = Path("scripts/prepare_dvd_second_wave_2a.py").read_text(encoding="utf-8")
    assert "apply_dvd_cutover_phase38g" not in src
    assert "APPLY_CONFIRMATION" not in src
    assert "ROLLBACK_CONFIRMATION" not in src
