from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adjudicate_p0f7_9d73_duplicate_pair.py"

spec = importlib.util.spec_from_file_location("p0f7_9d73", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _plan() -> dict:
    entries = []
    for i in range(1, 21):
        entries.append({
            "ordinal": i,
            "assignment_id": f"x{i}",
            "school_id": "sx",
            "class_id": f"cx{i}",
            "academic_year": 2026,
            "source": {"course_id": f"cs{i}", "course_name": "X"},
            "target": {"course_id": f"ct{i}", "course_name": "X"},
        })
    entries.extend([
        {
            "ordinal": 21,
            "assignment_id": "a1",
            "school_id": "s1",
            "class_id": "c1",
            "class_name": "MULTI 3º E 4º ETAPA",
            "academic_year": 2026,
            "source": {"course_id": "src1", "course_name": "Geografia"},
            "target": {"course_id": "eja", "course_name": "Geografia"},
        },
        {
            "ordinal": 22,
            "assignment_id": "a2",
            "school_id": "s1",
            "class_id": "c1",
            "class_name": "MULTI 3º E 4º ETAPA",
            "academic_year": 2026,
            "source": {"course_id": "src2", "course_name": "Geografia"},
            "target": {"course_id": "eja", "course_name": "Geografia"},
        },
        {
            "ordinal": 23,
            "assignment_id": "x23",
            "school_id": "sx",
            "class_id": "cx23",
            "academic_year": 2026,
            "source": {"course_id": "cs23", "course_name": "X"},
            "target": {"course_id": "ct23", "course_name": "X"},
        },
    ])
    p = {
        "phase": mod.PLAN_PHASE,
        "status": "PASS",
        "mode": mod.PLAN_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "execution_contract": {"executable": False},
        "entries": entries,
    }
    p["plan_sha256"] = mod._canonical_sha256(p)
    return p


def _d71(plan: dict) -> dict:
    safe = []
    for row in plan["entries"]:
        if row["assignment_id"] in {"a1", "a2"}:
            continue
        safe.append({
            "ordinal": row["ordinal"],
            "assignment_id": row["assignment_id"],
            "school_id": row["school_id"],
            "class_id": row["class_id"],
            "source_course_id": row["source"]["course_id"],
            "target_course_id": row["target"]["course_id"],
        })
    blocked = [
        {
            "ordinal": 21,
            "assignment_id": "a1",
            "school_id": "s1",
            "class_id": "c1",
            "source_course_id": "src1",
            "target_course_id": "eja",
        },
        {
            "ordinal": 22,
            "assignment_id": "a2",
            "school_id": "s1",
            "class_id": "c1",
            "source_course_id": "src2",
            "target_course_id": "eja",
        },
    ]
    d = {
        "phase": mod.D71_PHASE,
        "status": "PASS",
        "mode": "LOCAL_OFFLINE_READ_ONLY",
        "sealed_plan_sha256": plan["plan_sha256"],
        "summary": {
            "entries": 23,
            "safe_noncolliding": 21,
            "blocked_intra_batch": 2,
            "collision_groups": 1,
            "execution_gate_open": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "safe_entries": safe,
        "blocked_entries": blocked,
    }
    d["report_sha256"] = mod._canonical_sha256(d)
    return d


def _d72(plan: dict, d71: dict) -> dict:
    d = {
        "phase": mod.D72_PHASE,
        "status": "PASS",
        "mode": mod.D72_MODE,
        "sealed_plan_sha256": plan["plan_sha256"],
        "source_d71_report_sha256": d71["report_sha256"],
        "class": {
            "class_id": "c1",
            "class_name": "MULTI 3º E 4º ETAPA",
            "class_level": "eja_final",
            "grade_level": "EJA 3ª ETAPA",
            "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
        },
        "pair": {
            "classification": "ACTIVE_DUPLICATE_SEMANTIC_PAIR_REQUIRES_CONSOLIDATION",
            "same_staff": True,
            "same_school": True,
            "same_class": True,
            "same_academic_year": True,
            "both_active": True,
            "substitution_present": False,
            "weekly_workload_conflict": True,
            "assignments": [
                {
                    "ordinal": 21,
                    "assignment_id": "a1",
                    "source_course_id": "src1",
                    "source_course_name": "Geografia",
                    "source_course_level": "fundamental_anos_finais",
                    "weekly_workload": 2,
                    "status": "ativo",
                    "created_at": "2026-01-01T10:00:00Z",
                    "updated_at": "2026-02-01T10:00:00Z",
                    "audit": {"event_count": 1, "first_event_at": "2026-01-01", "last_event_at": "2026-01-01"},
                    "schedule_slots_for_source_course": 0,
                },
                {
                    "ordinal": 22,
                    "assignment_id": "a2",
                    "source_course_id": "src2",
                    "source_course_name": "Geografia",
                    "source_course_level": "fundamental_anos_finais",
                    "weekly_workload": 3,
                    "status": "active",
                    "created_at": "2026-01-02T10:00:00Z",
                    "updated_at": "2026-02-02T10:00:00Z",
                    "audit": {"event_count": 2, "first_event_at": "2026-01-02", "last_event_at": "2026-02-02"},
                    "schedule_slots_for_source_course": 2,
                },
            ],
            "shared_target": {
                "course_id": "eja",
                "course_name": "Geografia",
                "course_level": "eja_final",
                "workload": 80,
                "schedule_slots": 0,
            },
        },
        "adjudication_contract": {
            "automatic_survivor_selection": False,
            "survivor_decision_required": True,
            "automatic_workload_decision": False,
            "workload_decision_required": True,
            "current_23_write_authorization_reusable": False,
        },
        "summary": {
            "blocked_assignments": 2,
            "collision_groups": 1,
            "semantic_pair_confirmed": True,
            "weekly_workload_conflict": True,
            "survivor_decision_required": True,
            "workload_decision_required": True,
            "production_write_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "staff_id_exposed_in_report": False,
            "student_records_read": 0,
        },
    }
    d["report_sha256"] = mod._canonical_sha256(d)
    return d


def _validated(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(mod, "EXPECTED_PLAN_SHA256", plan["plan_sha256"])
    d71 = _d71(plan)
    d72 = _d72(plan, d71)
    monkeypatch.setattr(mod, "EXPECTED_D72_REPORT_SHA256", d72["report_sha256"])
    return plan, d71, d72, mod.validate_inputs(plan, d71, d72)


def _decision(validated: dict, survivor="a1", workload=3):
    return {
        "phase": mod.DECISION_PHASE,
        "source_d72_report_sha256": validated["d72_sha256"],
        "responsible": "Responsável Institucional",
        "authority_confirmed": True,
        "survivor": {
            "decision": mod.SURVIVOR_SELECT if survivor else mod.SURVIVOR_DEFER,
            "assignment_id": survivor,
            "justification": "Escolha institucional com base no dossiê auditável." if survivor else "",
        },
        "workload": {
            "decision": mod.WORKLOAD_SELECT if workload is not None else mod.WORKLOAD_DEFER,
            "value": workload,
            "justification": "Carga semanal confirmada institucionalmente no processo." if workload is not None else "",
        },
        "duplicate_retirement_confirmed": bool(survivor),
        "production_write_authorized": False,
        "executor_authorized": False,
    }


def test_offline_guard_passes():
    mod.assert_offline_only()


def test_build_template_keeps_both_decisions_deferred(monkeypatch):
    plan, d71, d72, validated = _validated(monkeypatch)
    template = mod.build_decision_template(validated)
    assert template["survivor"]["decision"] == mod.SURVIVOR_DEFER
    assert template["workload"]["decision"] == mod.WORKLOAD_DEFER
    assert set(template["allowed_survivor_assignment_ids"]) == {"a1", "a2"}
    assert {_ for _ in template["allowed_workload_values"]} == {2, 3}
    assert template["production_write_authorized"] is False


def test_deferred_decision_seals_but_keeps_revised_plan_blocked(monkeypatch):
    plan, d71, d72, validated = _validated(monkeypatch)
    decision = _decision(validated, survivor=None, workload=None)
    report = mod.seal(plan, d71, d72, decision)
    assert report["status"] == "PASS"
    assert report["summary"]["revised_plan_ready"] is False
    assert report["summary"]["revised_document_updates"] == 0
    assert report["revised_plan"]["operations"] == []
    assert report["revised_plan"]["old_23_write_authorization_reusable"] is False
    assert report["summary"]["production_writes"] is False


def test_resolved_decision_builds_21_plus_retire_plus_survivor(monkeypatch):
    plan, d71, d72, validated = _validated(monkeypatch)
    decision = _decision(validated, survivor="a1", workload=3)
    report = mod.seal(plan, d71, d72, decision)
    ops = report["revised_plan"]["operations"]
    assert report["summary"]["revised_plan_ready"] is True
    assert report["summary"]["safe_noncolliding_operations"] == 21
    assert report["summary"]["duplicate_retirement_operations"] == 1
    assert report["summary"]["survivor_consolidation_operations"] == 1
    assert len(ops) == 23
    assert ops[-2]["operation_type"] == "RETIRE_DUPLICATE_ASSIGNMENT"
    assert ops[-2]["scope"]["assignment_id"] == "a2"
    assert ops[-2]["set_fields"] == {"status": "inativo"}
    assert ops[-2]["hard_delete"] is False
    assert ops[-1]["operation_type"] == "CONSOLIDATE_SURVIVOR"
    assert ops[-1]["scope"]["assignment_id"] == "a1"
    assert ops[-1]["set_fields"] == {"course_id": "eja", "carga_horaria_semanal": 3}
    assert report["revised_plan"]["executable"] is False
    assert report["summary"]["production_write_authorized"] is False


def test_survivor_current_workload_does_not_mutate_workload(monkeypatch):
    plan, d71, d72, validated = _validated(monkeypatch)
    decision = _decision(validated, survivor="a1", workload=2)
    report = mod.seal(plan, d71, d72, decision)
    survivor_op = report["revised_plan"]["operations"][-1]
    assert survivor_op["set_fields"] == {"course_id": "eja"}
    assert survivor_op["rollback_set_fields"] == {"course_id": "src1"}


def test_invalid_workload_fails_closed(monkeypatch):
    plan, d71, d72, validated = _validated(monkeypatch)
    decision = _decision(validated, survivor="a1", workload=4)
    with pytest.raises(ValueError, match="WORKLOAD_NOT_EXISTING_PAIR_VALUE"):
        mod.seal(plan, d71, d72, decision)


def test_unexpected_d72_report_is_rejected(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(mod, "EXPECTED_PLAN_SHA256", plan["plan_sha256"])
    d71 = _d71(plan)
    d72 = _d72(plan, d71)
    monkeypatch.setattr(mod, "EXPECTED_D72_REPORT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="D72_NOT_REAL_EXECUTED_REPORT"):
        mod.validate_inputs(plan, d71, d72)
