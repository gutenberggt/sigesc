from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = _load_module("p0f7_9d74_builder_test", SCRIPTS / "build_p0f7_9d74_revised_preflight_snapshot_js.py")
auditor = _load_module("p0f7_9d74_auditor_test", SCRIPTS / "audit_p0f7_9d74_revised_preflight_offline.py")


def _sealed(monkeypatch):
    tenant = "tenant-1"
    year = 2026
    ops = []
    for i in range(1, 22):
        ops.append({
            "operation_index": i,
            "operation_type": "REMAP_COURSE",
            "scope": {"mantenedora_id": tenant, "academic_year": year, "school_id": "school", "class_id": f"c{i}", "assignment_id": f"x{i}"},
            "cas_expected": {"status": "ativo_or_active", "course_id": f"src{i}"},
            "set_fields": {"course_id": f"tgt{i}"},
            "rollback_set_fields": {"course_id": f"src{i}"},
            "source_d4_ordinal": i,
        })
    ops.append({
        "operation_index": 22,
        "operation_type": "RETIRE_DUPLICATE_ASSIGNMENT",
        "scope": {"mantenedora_id": tenant, "academic_year": year, "school_id": "school", "class_id": "cpair", "assignment_id": "e62376c8-5e41-4165-b4bb-5040547ae9f3"},
        "cas_expected": {"status": "ativo", "course_id": "src-retire", "carga_horaria_semanal": 3},
        "set_fields": {"status": "inativo"},
        "rollback_set_fields": {"status": "ativo"},
        "hard_delete": False,
        "source_d4_ordinal": 22,
    })
    ops.append({
        "operation_index": 23,
        "operation_type": "CONSOLIDATE_SURVIVOR",
        "scope": {"mantenedora_id": tenant, "academic_year": year, "school_id": "school", "class_id": "cpair", "assignment_id": "47feaf78-62be-4b62-975b-7b389e11f13d"},
        "cas_expected": {"status": "ativo", "course_id": "src-survivor", "carga_horaria_semanal": 2},
        "set_fields": {"course_id": "geo-target"},
        "rollback_set_fields": {"course_id": "src-survivor"},
        "shared_target_course_id": "geo-target",
        "source_d4_ordinal": 21,
    })
    report = {
        "phase": builder.SEALED_PHASE,
        "status": "PASS",
        "mode": builder.SEALED_MODE,
        "sealed_plan_sha256": "d4",
        "source_d71_report_sha256": "d71",
        "source_d72_report_sha256": "d72",
        "human_decision_sha256": "decision",
        "decision": {"fully_resolved": True},
        "pair_resolution": {
            "survivor_assignment_id": "47feaf78-62be-4b62-975b-7b389e11f13d",
            "retired_assignment_id": "e62376c8-5e41-4165-b4bb-5040547ae9f3",
            "retirement_status": "inativo",
            "shared_target_course_id": "geo-target",
            "selected_weekly_workload": 2,
            "hard_delete": False,
        },
        "revised_plan": {
            "ready": True,
            "executable": False,
            "operation_count": 23,
            "operations": ops,
            "pair_ordering_rule": "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR",
            "rollback_order": "REVERSE_OPERATION_ORDER",
            "requires_fresh_last_mile_preflight": True,
            "requires_new_cas_dry_run": True,
            "requires_new_explicit_production_write_authorization": True,
            "old_23_write_authorization_reusable": False,
        },
        "summary": {
            "safe_noncolliding_operations": 21,
            "duplicate_retirement_operations": 1,
            "survivor_consolidation_operations": 1,
            "revised_document_updates": 23,
            "survivor_decision_resolved": True,
            "workload_decision_resolved": True,
            "revised_plan_ready": True,
            "production_write_authorized": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "workload_resolution_source": "CURRICULAR_POLICY",
        },
        "safety": {"database_mutation": False, "production_writes": False, "executor_authorized": False},
        "curricular_workload_policy": {
            "phase": builder.POLICY_PHASE,
            "component": "geografia",
            "class_level": "eja_final",
            "series": [3, 4],
            "multigrade": True,
            "multigrade_rule": "MAX_ANNUAL_WORKLOAD",
            "conversion_formula": {
                "ha_definition": "horas anuais",
                "hm_definition": "horas mensais",
                "hs_definition": "horas semanais",
                "annual_to_monthly": "ha / 8 = hm",
                "monthly_to_weekly": "hm / 5 = hs",
                "annual_to_weekly_equivalent": "ha / 40 = hs",
            },
            "canonical_annual_workload": 80,
            "canonical_monthly_workload": 10,
            "canonical_weekly_workload": 2,
            "human_workload_choice_required": False,
        },
    }
    report["report_sha256"] = builder._canonical_sha256(report)
    monkeypatch.setattr(builder, "EXPECTED_SEALED_REPORT_SHA256", report["report_sha256"])
    monkeypatch.setattr(auditor.builder, "EXPECTED_SEALED_REPORT_SHA256", report["report_sha256"])
    return report


def _snapshot(report):
    ctx = builder.validate_sealed_report(report)
    tenant, year = ctx["mantenedora_id"], ctx["academic_year"]
    assignments = []
    classes = []
    courses = []
    for i in range(1, 22):
        assignments.append({"id": f"x{i}", "staff_id": f"staff{i}", "school_id": "school", "class_id": f"c{i}", "course_id": f"src{i}", "academic_year": year, "status": "ativo", "mantenedora_id": tenant, "carga_horaria_semanal": 2})
        classes.append({"id": f"c{i}", "school_id": "school", "academic_year": year, "mantenedora_id": tenant, "nivel_ensino": "fundamental_anos_finais", "series": ["7º ANO"]})
        courses.append({"id": f"tgt{i}", "name": "X", "nivel_ensino": "fundamental_anos_finais", "mantenedora_id": tenant, "active": True})
    assignments.extend([
        {"id": "e62376c8-5e41-4165-b4bb-5040547ae9f3", "staff_id": "pair-staff", "school_id": "school", "class_id": "cpair", "course_id": "src-retire", "academic_year": year, "status": "ativo", "mantenedora_id": tenant, "carga_horaria_semanal": 3},
        {"id": "47feaf78-62be-4b62-975b-7b389e11f13d", "staff_id": "pair-staff", "school_id": "school", "class_id": "cpair", "course_id": "src-survivor", "academic_year": year, "status": "ativo", "mantenedora_id": tenant, "carga_horaria_semanal": 2},
    ])
    classes.append({"id": "cpair", "school_id": "school", "academic_year": year, "mantenedora_id": tenant, "nivel_ensino": "eja_final", "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"]})
    courses.append({"id": "geo-target", "name": "Geografia", "nivel_ensino": "eja_final", "mantenedora_id": tenant, "active": True})
    return {
        "phase": builder.OUTPUT_PHASE,
        "mode": builder.OUTPUT_MODE,
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_report_sha256": report["report_sha256"],
        "source_operations": 23,
        "query_budget": 5,
        "query_calls": 5,
        "topology": {"set_name": "", "msg": "", "logical_session_timeout_minutes": None, "max_wire_version": 21},
        "counts": {"matching_assignments": len(assignments), "classes": len(classes), "target_courses": len(courses)},
        "teacher_assignments": assignments,
        "classes": classes,
        "target_courses": courses,
    }


def test_sealed_report_pins_formula_survivor_and_order(monkeypatch):
    report = _sealed(monkeypatch)
    ctx = builder.validate_sealed_report(report)
    assert len(ctx["operations"]) == 23
    assert ctx["operations"][-2]["operation_type"] == "RETIRE_DUPLICATE_ASSIGNMENT"
    assert ctx["operations"][-1]["operation_type"] == "CONSOLIDATE_SURVIVOR"


def test_wrong_workload_fails_closed(monkeypatch):
    report = _sealed(monkeypatch)
    report["pair_resolution"]["selected_weekly_workload"] = 3
    report["report_sha256"] = builder._canonical_sha256({k: v for k, v in report.items() if k != "report_sha256"})
    monkeypatch.setattr(builder, "EXPECTED_SEALED_REPORT_SHA256", report["report_sha256"])
    with pytest.raises(ValueError, match="PAIR_RESOLUTION_INVALID"):
        builder.validate_sealed_report(report)


def test_collector_is_read_only_and_bounded(monkeypatch):
    report = _sealed(monkeypatch)
    js = builder.build_js(report, "sigesc")
    assert "QUERY_BUDGET = 5" in js
    assert ".find(" in js and ".countDocuments(" in js
    for mutator in ("updateOne(", "updateMany(", "deleteOne(", "deleteMany(", "insertOne(", "insertMany(", "bulkWrite("):
        assert mutator not in js


def test_revised_cas_and_reverse_rollback_pass(monkeypatch):
    report = _sealed(monkeypatch)
    snapshot = _snapshot(report)
    monkeypatch.setattr(auditor, "validate_teacher_assignment_curriculum", lambda **kwargs: {"write_policy": "ACTIVE"})
    result = auditor.build_report(report, snapshot)
    assert result["summary"]["cas_dry_run_clear"] == 23
    assert result["summary"]["cas_dry_run_blocked"] == 0
    assert result["summary"]["curricular_checks_passed"] == 22
    assert result["summary"]["forward_simulation_clear"] is True
    assert result["summary"]["pair_postconditions_clear"] is True
    assert result["summary"]["rollback_simulation_clear"] is True
    assert result["summary"]["clear_for_executor_sealing"] is True
    assert result["summary"]["production_write_authorized"] is False


def test_active_target_collision_blocks(monkeypatch):
    report = _sealed(monkeypatch)
    snapshot = _snapshot(report)
    snapshot["teacher_assignments"].append({"id": "collision", "staff_id": "staff1", "school_id": "school", "class_id": "c1", "course_id": "tgt1", "academic_year": 2026, "status": "ativo", "mantenedora_id": "tenant-1", "carga_horaria_semanal": 2})
    snapshot["counts"]["matching_assignments"] += 1
    monkeypatch.setattr(auditor, "validate_teacher_assignment_curriculum", lambda **kwargs: {"write_policy": "ACTIVE"})
    result = auditor.build_report(report, snapshot)
    assert result["summary"]["cas_dry_run_blocked"] >= 1
    assert result["summary"]["clear_for_executor_sealing"] is False
    assert "ACTIVE_DUPLICATE_TUPLE_WOULD_RESULT" in result["results"][0]["reasons"]


def test_cas_workload_drift_blocks_pair_retirement(monkeypatch):
    report = _sealed(monkeypatch)
    snapshot = _snapshot(report)
    for row in snapshot["teacher_assignments"]:
        if row["id"] == "e62376c8-5e41-4165-b4bb-5040547ae9f3":
            row["carga_horaria_semanal"] = 2
    monkeypatch.setattr(auditor, "validate_teacher_assignment_curriculum", lambda **kwargs: {"write_policy": "ACTIVE"})
    result = auditor.build_report(report, snapshot)
    pair_retire = next(r for r in result["results"] if r["operation_type"] == "RETIRE_DUPLICATE_ASSIGNMENT")
    assert "CAS_CARGA_HORARIA_SEMANAL_DRIFT" in pair_retire["reasons"]
    assert result["summary"]["clear_for_executor_sealing"] is False
