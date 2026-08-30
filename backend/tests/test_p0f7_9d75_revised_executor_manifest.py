from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seal_p0f7_9d75_revised_executor_manifest.py"
_spec = importlib.util.spec_from_file_location("p0f7_9d75", SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _hash(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _d74_report():
    results = []
    for i in range(1, 24):
        results.append(
            {
                "operation_index": i,
                "operation_type": "REMAP_COURSE" if i <= 21 else ("RETIRE_DUPLICATE_ASSIGNMENT" if i == 22 else "CONSOLIDATE_SURVIVOR"),
                "assignment_id": f"a-{i}",
                "preflight": "CAS_DRY_RUN_CLEAR",
                "reasons": [],
                "active_collision_assignment_ids": [],
                "staff_id_present": True,
                "current_write_policy": "CURRENT_CURRICULUM_VALIDATED" if i != 22 else "",
            }
        )
    report = {
        "phase": mod.D74_PHASE,
        "status": "PASS",
        "mode": mod.D74_MODE,
        "sealed_report_sha256": mod.EXPECTED_REVISED_PLAN_SHA256,
        "source_snapshot_sha256": "snapshot-sha",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "summary": {
            "operations": 23,
            "cas_dry_run_clear": 23,
            "cas_dry_run_blocked": 0,
            "curricular_checks_passed": 22,
            "forward_simulation_clear": True,
            "pair_postconditions_clear": True,
            "rollback_simulation_clear": True,
            "clear_for_executor_sealing": True,
            "production_write_authorized": False,
            "executor_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "topology": {
            "classification": mod.EXPECTED_TOPOLOGY,
            "multi_document_transactions_available": False,
            "required_future_execution_strategy": mod.EXPECTED_STRATEGY,
        },
        "results": results,
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
            "requires_separate_explicit_production_write_authorization": True,
            "old_23_write_authorization_reusable": False,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "required_future_execution_strategy": mod.EXPECTED_STRATEGY,
            "required_operation_order": "SEALED_OPERATION_INDEX_ASC",
            "required_rollback_order": "REVERSE_OPERATION_ORDER",
        },
        "safety": {
            "analyzer_production_access": False,
            "snapshot_origin_read_only": True,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
            "staff_id_exposed_in_report": False,
            "hard_delete_allowed": False,
        },
    }
    report["report_sha256"] = _hash(report)
    return report


def _ctx():
    operations = []
    for i in range(1, 24):
        op_type = "REMAP_COURSE" if i <= 21 else ("RETIRE_DUPLICATE_ASSIGNMENT" if i == 22 else "CONSOLIDATE_SURVIVOR")
        set_fields = {"course_id": f"target-{i}"}
        rollback = {"course_id": f"source-{i}"}
        cas = {"course_id": f"source-{i}", "status": "ativo_or_active"}
        if i == 22:
            set_fields = {"status": "inativo"}
            rollback = {"status": "ativo"}
            cas["carga_horaria_semanal"] = 3
        if i == 23:
            set_fields = {"course_id": "target-23", "carga_horaria_semanal": 2}
            rollback = {"course_id": "source-23", "carga_horaria_semanal": 2}
            cas["carga_horaria_semanal"] = 2
        operations.append(
            {
                "operation_index": i,
                "operation_type": op_type,
                "scope": {
                    "mantenedora_id": "tenant-1",
                    "academic_year": 2026,
                    "school_id": f"school-{i}",
                    "class_id": f"class-{i}",
                    "assignment_id": f"a-{i}",
                },
                "cas_expected": cas,
                "set_fields": set_fields,
                "rollback_set_fields": rollback,
            }
        )
    return {
        "sealed_report_sha256": mod.EXPECTED_REVISED_PLAN_SHA256,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "operations": operations,
    }


def test_validate_d74_report_accepts_all_clear_contract():
    report = _d74_report()
    assert mod.validate_d74_report(report, expected_sha=report["report_sha256"]) == report["report_sha256"]


def test_validate_d74_report_fails_closed_on_blocked_cas():
    report = _d74_report()
    report["summary"]["cas_dry_run_clear"] = 22
    report["summary"]["cas_dry_run_blocked"] = 1
    report["report_sha256"] = _hash({k: v for k, v in report.items() if k != "report_sha256"})
    with pytest.raises(ValueError, match="D74_SUMMARY_INVALID"):
        mod.validate_d74_report(report, expected_sha=report["report_sha256"])


def test_validate_d74_report_rejects_old_authorization_reuse():
    report = _d74_report()
    report["execution_contract"]["old_23_write_authorization_reusable"] = True
    report["report_sha256"] = _hash({k: v for k, v in report.items() if k != "report_sha256"})
    with pytest.raises(ValueError, match="EXECUTION_CONTRACT_INVALID"):
        mod.validate_d74_report(report, expected_sha=report["report_sha256"])


def test_build_manifest_is_non_executable_and_pins_sources(monkeypatch):
    report = _d74_report()
    ctx = _ctx()
    monkeypatch.setattr(mod.d74_builder, "validate_sealed_report", lambda payload: ctx)
    monkeypatch.setattr(mod, "validate_d74_report", lambda payload: report["report_sha256"])

    manifest = mod.build_manifest({"synthetic": True}, report)

    assert manifest["status"] == "PASS"
    assert manifest["source_revised_plan_sha256"] == mod.EXPECTED_REVISED_PLAN_SHA256
    assert manifest["source_d74_report_sha256"] == report["report_sha256"]
    assert manifest["summary"]["operations"] == 23
    assert manifest["summary"]["manifest_ready_for_explicit_authorization"] is True
    assert manifest["summary"]["production_write_authorized"] is False
    assert manifest["summary"]["executor_authorized"] is False
    assert manifest["summary"]["executor_materialized"] is False
    assert manifest["execution_contract"]["executable"] is False
    assert manifest["execution_contract"]["writer_implementation_present"] is False
    assert manifest["execution_contract"]["authorization_must_pin_manifest_sha256"] is True
    assert manifest["execution_contract"]["old_23_write_authorization_reusable"] is False
    assert manifest["execution_contract"]["hard_delete_allowed"] is False
    assert len(manifest["operations"]) == 23
    assert [op["operation_type"] for op in manifest["operations"][-2:]] == [
        "RETIRE_DUPLICATE_ASSIGNMENT",
        "CONSOLIDATE_SURVIVOR",
    ]
    assert manifest["manifest_sha256"] == _hash({k: v for k, v in manifest.items() if k != "manifest_sha256"})


def test_build_manifest_fails_if_d74_assignment_chain_drifts(monkeypatch):
    report = _d74_report()
    report["results"][0]["assignment_id"] = "wrong-id"
    ctx = _ctx()
    monkeypatch.setattr(mod.d74_builder, "validate_sealed_report", lambda payload: ctx)
    monkeypatch.setattr(mod, "validate_d74_report", lambda payload: "d74-sha")
    with pytest.raises(ValueError, match="ASSIGNMENT_CHAIN_MISMATCH"):
        mod.build_manifest({}, report)


def test_source_contains_no_database_or_network_client():
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = ("pymongo", "motor", "requests.", "httpx.", "subprocess", "updateOne", "deleteOne", "insertOne")
    for token in forbidden:
        assert token not in source
