from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_p0f7_9d76_authorized_revised_executor_js.py"
_spec = importlib.util.spec_from_file_location("p0f7_9d76_builder_test", SCRIPT)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def _operation(index: int) -> dict:
    common = {
        "operation_index": index,
        "scope": {
            "mantenedora_id": "tenant-1",
            "academic_year": 2026,
            "school_id": f"school-{index % 3}",
            "class_id": f"class-{index}",
            "assignment_id": f"assignment-{index}",
        },
        "d74_preflight": "CAS_DRY_RUN_CLEAR",
        "d74_current_write_policy": "active_curriculum_validated",
    }
    if index <= 21:
        common.update(
            {
                "operation_type": "REMAP_COURSE",
                "cas_expected": {
                    "status": "ativo_or_active",
                    "course_id": f"legacy-course-{index}",
                },
                "set_fields": {"course_id": f"target-course-{index}"},
                "rollback_set_fields": {"course_id": f"legacy-course-{index}"},
            }
        )
    elif index == 22:
        common.update(
            {
                "operation_type": "RETIRE_DUPLICATE_ASSIGNMENT",
                "cas_expected": {
                    "status": "ativo_or_active",
                    "course_id": "legacy-geo-duplicate",
                    "carga_horaria_semanal": 3,
                },
                "set_fields": {"status": "inativo"},
                "rollback_set_fields": {"status": "ativo"},
            }
        )
    else:
        common.update(
            {
                "operation_type": "CONSOLIDATE_SURVIVOR",
                "cas_expected": {
                    "status": "ativo_or_active",
                    "course_id": "legacy-geo-survivor",
                    "carga_horaria_semanal": 2,
                },
                "set_fields": {
                    "course_id": "canonical-geo",
                    "carga_horaria_semanal": 2,
                },
                "rollback_set_fields": {
                    "course_id": "legacy-geo-survivor",
                    "carga_horaria_semanal": 2,
                },
            }
        )
    return common


def _manifest() -> dict:
    payload = {
        "phase": builder.MANIFEST_PHASE,
        "status": "PASS",
        "mode": builder.MANIFEST_MODE,
        "source_revised_plan_sha256": builder.EXPECTED_REVISED_PLAN_SHA256,
        "source_d74_report_sha256": builder.EXPECTED_D74_REPORT_SHA256,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "strategy": builder.EXPECTED_STRATEGY,
        "summary": {
            "operations": 23,
            "remap_course": 21,
            "retire_duplicate_assignment": 1,
            "consolidate_survivor": 1,
            "cas_preflight_clear": 23,
            "forward_simulation_clear": True,
            "pair_postconditions_clear": True,
            "rollback_simulation_clear": True,
            "manifest_ready_for_explicit_authorization": True,
            "production_write_authorized": False,
            "executor_authorized": False,
            "executor_materialized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "operations": [_operation(i) for i in range(1, 24)],
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
            "executor_materialized": False,
            "requires_separate_explicit_production_write_authorization": True,
            "authorization_must_pin_manifest_sha256": True,
            "authorization_must_pin_revised_plan_sha256": True,
            "authorization_must_pin_d74_report_sha256": True,
            "old_23_write_authorization_reusable": False,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "required_execution_strategy": builder.EXPECTED_STRATEGY,
            "required_operation_order": "SEALED_OPERATION_INDEX_ASC",
            "required_pair_order": "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR",
            "required_rollback_order": "REVERSE_OPERATION_ORDER",
            "hard_delete_allowed": False,
        },
        "safety": {
            "production_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
            "staff_id_exposed": False,
            "hard_delete_allowed": False,
        },
    }
    payload["manifest_sha256"] = builder._canonical_sha256(payload)
    return payload


def test_explicit_authorization_is_required() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="EXPLICIT_PRODUCTION_AUTHORIZATION_REQUIRED"):
        builder.build_executor(
            manifest,
            "sigesc",
            authorized=False,
            expected_manifest_sha=manifest["manifest_sha256"],
        )


def test_materialized_executor_is_pinned_and_fail_closed() -> None:
    manifest = _manifest()
    js, metadata = builder.build_executor(
        manifest,
        "sigesc",
        authorized=True,
        expected_manifest_sha=manifest["manifest_sha256"],
    )
    assert metadata["executor_materialized"] is True
    assert metadata["production_write_authorized"] is True
    assert metadata["executor_authorized"] is True
    assert metadata["execution_performed"] is False
    assert metadata["database_mutation"] is False
    assert metadata["production_writes"] is False
    assert metadata["expected_operations"] == 23
    assert "P0F79D76_EXECUTION_RECEIPT=" in js
    assert "P0F79D76_GLOBAL_CAS_BLOCKED" in js
    assert "P0F79D76_IMMEDIATE_COLLISION" in js
    assert "SAFE_ROLLBACK" in js
    assert "ROLLBACK_INCOMPLETE" in js
    assert "updateOne" in js
    assert "deleteOne" not in js
    assert "deleteMany" not in js
    assert "insertOne" not in js
    assert "replaceOne" not in js
    assert "bulkWrite" not in js


def test_manifest_tampering_is_rejected() -> None:
    manifest = _manifest()
    tampered = copy.deepcopy(manifest)
    tampered["operations"][22]["set_fields"]["carga_horaria_semanal"] = 3
    with pytest.raises(ValueError, match="MANIFEST_SHA_INVALID"):
        builder.validate_manifest(
            tampered,
            expected_manifest_sha=manifest["manifest_sha256"],
        )


def test_pair_order_is_invariant() -> None:
    manifest = _manifest()
    manifest["operations"][21], manifest["operations"][22] = (
        manifest["operations"][22],
        manifest["operations"][21],
    )
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = builder._canonical_sha256(manifest)
    with pytest.raises(ValueError, match="OPERATION_SEQUENCE_INVALID|PAIR_ORDER_INVALID"):
        builder.validate_manifest(
            manifest,
            expected_manifest_sha=manifest["manifest_sha256"],
        )
