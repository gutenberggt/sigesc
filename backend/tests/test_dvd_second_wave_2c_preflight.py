from pathlib import Path

import pytest

import scripts.prepare_dvd_second_wave_2c as m


def _row(legacy_id: str):
    expected = m.APPROVED_TARGETS[legacy_id]
    residue_slot = next(iter(expected["residue_slots"]))
    return {
        "id": expected["proposed_id"],
        "teacher_id": m.TEACHER_USER_ID,
        "teacher_name": "Juliana da Silva Leao",
        "class_id": m.CLASS_ID,
        "class_name": "Berçario II A",
        "school_id": m.SCHOOL_ID,
        "component_id": f"component-{legacy_id}",
        "component_name": expected["component_name"],
        "weekly_slots": [
            {
                "weekday": i % 5,
                "aula_numero": i + 1,
                "start_time": "08:00",
                "end_time": "08:40",
            }
            for i in range(expected["weekly_slots"])
        ],
        "diary_settings": {"enabled": True, "profile": "regular"},
        "cutover_provenance": {
            "phase": m.PROVENANCE_PHASE,
            "state": "DRY_RUN_ONLY",
            "source_legacy_assignment_id": legacy_id,
            "evidence": m.REQUIRED_EVIDENCE,
            "slots_per_day": m.REQUIRED_SLOTS_PER_DAY,
            "ignored_out_of_range_slots": [
                {
                    "day": day,
                    "slot_number": residue_slot,
                    "course_id": f"component-{legacy_id}",
                }
                for day in ["segunda", "terca", "quarta", "quinta", "sexta"]
            ],
        },
    }


def _report():
    manifest = [_row(legacy_id) for legacy_id in m.APPROVED_TARGETS]
    return {
        "summary": {
            "ready": 2,
            "missing_total": 4,
            "blocked": 2,
            "manifest_sha256": m.APPROVED_MANIFEST_SHA256,
        },
        "manifest": manifest,
        "details": [
            {
                "state": "blocked",
                "component_name": "Contação de Histórias e Iniciação Musical",
                "blockers": ["no_out_of_range_residue"],
            },
            {
                "state": "blocked",
                "component_name": "Higiene e Saúde",
                "blockers": ["no_out_of_range_residue"],
            },
        ],
    }


def test_production_snapshot_is_pinned():
    assert m.ACADEMIC_YEAR == 2026
    assert m.APPROVED_READY_COUNT == 2
    assert m.APPROVED_MANIFEST_SHA256 == (
        "09aa29dd9c535c1b83de8390a14c24d6cf44d77e7eb811530c87dc8222cc0223"
    )
    assert m.TEACHER_USER_ID == "2e5004ac-dad2-4d07-a6aa-372ff49bb54a"
    assert m.CLASS_ID == "a76ccc2c-317c-4bd6-8b39-ed5fa806d67c"
    assert set(m.APPROVED_TARGETS) == {
        "8d48d5bd-418c-414a-88ce-015a8bd20fa6",
        "0f96bcb8-33e9-47ca-add4-e9d9f9b4635d",
    }


def test_two_ready_pass_even_when_other_missing_are_blocked(monkeypatch):
    monkeypatch.setattr(m, "manifest_digest", lambda _: m.APPROVED_MANIFEST_SHA256)
    result = m.validate_2c_report(_report())
    assert result["ready"] == 2
    assert result["source_missing_total"] == 4
    assert result["source_blocked"] == 2
    assert result["excluded_blockers"] == {"no_out_of_range_residue": 2}
    assert result["weekly_slots_counts"] == {"3": 1, "4": 1}
    assert result["residue_counts"] == {"5": 2}


def test_rejects_manifest_hash_drift(monkeypatch):
    monkeypatch.setattr(m, "manifest_digest", lambda _: "0" * 64)
    with pytest.raises(m.PreflightGateError, match="MANIFEST_SHA256_MISMATCH"):
        m.validate_2c_report(_report())


def test_rejects_unexpected_third_ready(monkeypatch):
    monkeypatch.setattr(m, "manifest_digest", lambda _: m.APPROVED_MANIFEST_SHA256)
    report = _report()
    report["manifest"].append(dict(report["manifest"][0], id="unexpected"))
    report["summary"]["ready"] = 3
    with pytest.raises(m.PreflightGateError, match="READY_COUNT_MISMATCH"):
        m.validate_2c_report(report)


def test_rejects_residue_inside_declared_grid(monkeypatch):
    monkeypatch.setattr(m, "manifest_digest", lambda _: m.APPROVED_MANIFEST_SHA256)
    report = _report()
    report["manifest"][0]["cutover_provenance"]["ignored_out_of_range_slots"][0][
        "slot_number"
    ] = 7
    with pytest.raises(m.PreflightGateError, match="RESIDUE_NOT_OUT_OF_RANGE"):
        m.validate_2c_report(report)


def test_rejects_wrong_weekly_slot_count(monkeypatch):
    monkeypatch.setattr(m, "manifest_digest", lambda _: m.APPROVED_MANIFEST_SHA256)
    report = _report()
    report["manifest"][0]["weekly_slots"].pop()
    with pytest.raises(m.PreflightGateError, match="WEEKLY_SLOTS_COUNT_MISMATCH"):
        m.validate_2c_report(report)


def test_backup_path_must_be_persistent():
    m.validate_persistent_backup_path(
        Path("/data/sigesc-dvd-backups/dvd-second-wave-2c-preflight-v1")
    )
    with pytest.raises(m.PreflightGateError, match="BACKUP_PATH_NOT_PERSISTENT"):
        m.validate_persistent_backup_path(Path("/tmp/dvd-2c"))


def test_backup_is_sealed_and_never_overwrites(tmp_path: Path):
    target = tmp_path / "backup"
    validated = {
        "manifest": [{"id": "dvd-1"}],
        "manifest_sha256": m.APPROVED_MANIFEST_SHA256,
        "ready": 2,
        "source_missing_total": 4,
        "source_blocked": 2,
        "excluded_blockers": {"no_out_of_range_residue": 2},
        "weekly_slots_counts": {"3": 1, "4": 1},
        "residue_counts": {"5": 2},
    }
    bundle = {
        "scope": {"academic_year": 2026},
        "collections": {
            "teacher_class_assignments_before": [],
            "teacher_assignments_source": [],
        },
    }
    result = m.write_backup_directory(target, validated=validated, bundle=bundle)
    assert (target / "BACKUP-SEAL.json").is_file()
    assert (target / "backup-metadata.json").is_file()
    assert len(result["backup_bundle_sha256"]) == 64
    assert result["mode"] == m.BACKUP_MODE
    assert result["mutates_database"] is False

    with pytest.raises(FileExistsError):
        m.write_backup_directory(target, validated=validated, bundle=bundle)


def test_preflight_has_no_mongo_mutators_or_apply_cli():
    m.assert_script_read_only()
    src = Path("scripts/prepare_dvd_second_wave_2c.py").read_text(encoding="utf-8")
    assert "--apply" not in src
    assert "--rollback" not in src
    assert "APPLY-P0-DVD-OUT-OF-RANGE" not in src
