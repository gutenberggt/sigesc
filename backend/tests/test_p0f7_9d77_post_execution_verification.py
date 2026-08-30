from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build_p0f7_9d77_post_execution_verifier_js.py"
SEALER_PATH = ROOT / "scripts" / "seal_p0f7_9d77_post_execution.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx():
    operations = []
    for index in range(1, 24):
        if index <= 21:
            op_type = "REMAP_COURSE"
            set_fields = {"course_id": f"target-{index}"}
        elif index == 22:
            op_type = "RETIRE_DUPLICATE_ASSIGNMENT"
            set_fields = {"status": "inativo"}
        else:
            op_type = "CONSOLIDATE_SURVIVOR"
            set_fields = {"course_id": "target-23", "carga_horaria_semanal": 2}
        operations.append(
            {
                "operation_index": index,
                "operation_type": op_type,
                "scope": {
                    "mantenedora_id": "tenant",
                    "academic_year": 2026,
                    "school_id": f"school-{index}",
                    "class_id": f"class-{index}",
                    "assignment_id": f"assignment-{index}",
                },
                "cas_expected": {},
                "set_fields": set_fields,
                "rollback_set_fields": {},
            }
        )
    return {
        "phase": "unused",
        "authorization_marker": "unused",
        "manifest_sha256": "89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc",
        "source_revised_plan_sha256": "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb",
        "source_d74_report_sha256": "b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e",
        "mantenedora_id": "tenant",
        "academic_year": 2026,
        "strategy": "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED",
        "operations": operations,
    }


def test_verifier_is_read_only_and_bounded(monkeypatch):
    builder = _load_module(BUILDER_PATH, "p0f7_9d77_builder_test")
    monkeypatch.setattr(builder.d763.d761.d76, "validate_manifest", lambda manifest: _ctx())
    js = builder.build_verifier({"placeholder": True}, "sigesc")

    assert js.count("teacher_assignments.find(") == 2
    assert "P0F79D77_POST_EXECUTION_JSON=" in js
    assert "operations_verified:23" in js
    assert "active_unique_tuples_verified:22" in js
    assert "database_mutation:false" in js
    assert "production_writes:0" in js
    for token in builder.BANNED_MUTATION_TOKENS:
        assert token not in js


def _snapshot():
    return {
        "phase": "P0F7.9D7.7-POST-EXECUTION-VERIFICATION-2026",
        "status": "PASS",
        "manifest_sha256": "89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc",
        "source_revised_plan_sha256": "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb",
        "source_d74_report_sha256": "b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e",
        "operations_verified": 23,
        "documents_verified": 23,
        "active_final_assignments": 22,
        "active_unique_tuples_verified": 22,
        "retired_duplicate_verified": True,
        "survivor_verified": True,
        "survivor_canonical_weekly_workload": 2,
        "query_budget": 2,
        "query_calls": 2,
        "student_records_read": 0,
        "teacher_names_read": 0,
        "database_mutation": False,
        "production_writes": 0,
        "remediation_final_state_verified": True,
        "hard_delete": False,
    }


def test_final_seal_passes_only_clear_snapshot():
    sealer = _load_module(SEALER_PATH, "p0f7_9d77_sealer_test")
    seal = sealer.build_seal(_snapshot(), run_id="123", code_sha="abc")
    assert seal["status"] == "PASS"
    assert seal["operations_verified"] == 23
    assert seal["active_unique_tuples_verified"] == 22
    assert seal["verification_database_mutation"] is False
    assert seal["verification_production_writes"] == 0
    assert seal["final_classification"] == "REMEDIATION_APPLIED_AND_POST_STATE_VERIFIED"
    assert len(seal["seal_sha256"]) == 64


def test_final_seal_fails_closed_on_any_drift():
    sealer = _load_module(SEALER_PATH, "p0f7_9d77_sealer_drift_test")
    snapshot = _snapshot()
    snapshot["active_unique_tuples_verified"] = 21
    try:
        sealer.build_seal(snapshot, run_id="123", code_sha="abc")
    except ValueError as exc:
        assert "active_unique_tuples_verified" in str(exc)
    else:
        raise AssertionError("expected fail-closed drift rejection")
