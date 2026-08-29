from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build_p0f7_9d72_duplicate_pair_snapshot_js.py"
ANALYZER_PATH = ROOT / "scripts" / "analyze_p0f7_9d72_duplicate_pair_forensic.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load(BUILDER_PATH, "p0f7_9d72_builder")
analyzer = _load(ANALYZER_PATH, "p0f7_9d72_analyzer")


def _sign(payload: dict, field: str, module) -> dict:
    payload[field] = module._canonical_sha256(payload)
    return payload


def _plan() -> dict:
    p = {
        "phase": builder.PLAN_PHASE,
        "status": "PASS",
        "mode": builder.PLAN_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "execution_contract": {"executable": False},
        "entries": [
            {
                "ordinal": 21,
                "assignment_id": "a1",
                "school_id": "s1",
                "class_id": "c1",
                "academic_year": 2026,
                "class_name": "MULTI 3º E 4º ETAPA",
                "source": {"course_id": "src1", "course_name": "Geografia", "course_level": "fundamental_anos_finais"},
                "target": {"course_id": "eja", "course_name": "Geografia", "course_level": "eja_final"},
            },
            {
                "ordinal": 22,
                "assignment_id": "a2",
                "school_id": "s1",
                "class_id": "c1",
                "academic_year": 2026,
                "class_name": "MULTI 3º E 4º ETAPA",
                "source": {"course_id": "src2", "course_name": "Geografia", "course_level": "fundamental_anos_finais"},
                "target": {"course_id": "eja", "course_name": "Geografia", "course_level": "eja_final"},
            },
        ] + [
            {
                "ordinal": i,
                "assignment_id": f"x{i}",
                "school_id": "sx",
                "class_id": f"cx{i}",
                "academic_year": 2026,
                "source": {"course_id": f"cs{i}"},
                "target": {"course_id": f"ct{i}"},
            }
            for i in range(1, 21)
        ] + [
            {
                "ordinal": 23,
                "assignment_id": "x23",
                "school_id": "sx",
                "class_id": "cx23",
                "academic_year": 2026,
                "source": {"course_id": "cs23"},
                "target": {"course_id": "ct23"},
            }
        ],
    }
    # Production D7.2 is pinned to the authorized SHA. Unit tests patch the constant
    # to the canonical synthetic plan so we still exercise the same fail-closed path.
    p["plan_sha256"] = builder._canonical_sha256(p)
    return p


def _d71(plan: dict) -> dict:
    blocked = [
        {
            "ordinal": 21,
            "assignment_id": "a1",
            "class_id": "c1",
            "school_id": "s1",
            "source_course_id": "src1",
            "target_course_id": "eja",
        },
        {
            "ordinal": 22,
            "assignment_id": "a2",
            "class_id": "c1",
            "school_id": "s1",
            "source_course_id": "src2",
            "target_course_id": "eja",
        },
    ]
    d = {
        "phase": builder.D71_PHASE,
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
        "blocked_entries": blocked,
    }
    d["report_sha256"] = builder._canonical_sha256(d)
    return d


def _snapshot(plan: dict, d71: dict) -> dict:
    return {
        "phase": analyzer.SNAPSHOT_PHASE,
        "mode": analyzer.SNAPSHOT_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "sealed_plan_sha256": plan["plan_sha256"],
        "source_d71_report_sha256": d71["report_sha256"],
        "query_budget": 5,
        "query_calls": 5,
        "requests": [],
        "teacher_assignments": [
            {
                "id": "a1",
                "staff_id": "staff-1",
                "school_id": "s1",
                "class_id": "c1",
                "course_id": "src1",
                "academic_year": 2026,
                "status": "ativo",
                "carga_horaria_semanal": 2,
                "is_substituicao": False,
                "created_at": "2026-01-01T10:00:00Z",
                "updated_at": "2026-02-01T10:00:00Z",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "a2",
                "staff_id": "staff-1",
                "school_id": "s1",
                "class_id": "c1",
                "course_id": "src2",
                "academic_year": "2026",
                "status": "active",
                "carga_horaria_semanal": 3,
                "is_substituicao": False,
                "created_at": "2026-01-02T10:00:00Z",
                "updated_at": "2026-02-02T10:00:00Z",
                "mantenedora_id": "tenant-1",
            },
        ],
        "audit_summaries": {
            "a1": {"event_count": 1, "first_event_at": "2026-01-01", "last_event_at": "2026-01-01", "action_counts": {"create": 1}},
            "a2": {"event_count": 2, "first_event_at": "2026-01-02", "last_event_at": "2026-02-02", "action_counts": {"create": 1, "update": 1}},
        },
        "class_record": {
            "id": "c1",
            "name": "MULTI 3º E 4º ETAPA",
            "school_id": "s1",
            "academic_year": 2026,
            "mantenedora_id": "tenant-1",
            "education_level": "eja_final",
            "grade_level": "EJA 3ª ETAPA",
            "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
        },
        "courses": [
            {"id": "src1", "name": "Geografia", "nivel_ensino": "fundamental_anos_finais", "mantenedora_id": "tenant-1"},
            {"id": "src2", "name": "Geografia", "nivel_ensino": "fundamental_anos_finais", "mantenedora_id": "tenant-1"},
            {"id": "eja", "name": "Geografia", "nivel_ensino": "eja_final", "grade_levels": [], "active": True, "mantenedora_id": "tenant-1"},
        ],
        "schedule_slot_counts_by_course": {"src1": 0, "src2": 2, "eja": 0},
    }


def test_builder_emits_only_bounded_reads(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(builder, "AUTHORIZED_PLAN_SHA256", plan["plan_sha256"])
    d71 = _d71(plan)
    js = builder.build_js(plan, d71, "sigesc")
    assert "P0F79D72_PAIR_JSON=" in js
    assert "teacher_assignments.find(" in js
    assert "audit_logs.find(" in js
    assert "class_schedules.find(" in js
    for token in ("updateOne(", "updateMany(", "deleteOne(", "insertOne(", "bulkWrite("):
        assert token not in js


def test_analyzer_confirms_pair_and_keeps_decisions_human(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(analyzer, "EXPECTED_PLAN_SHA", plan["plan_sha256"])
    d71 = _d71(plan)
    report = analyzer.analyze(plan, d71, _snapshot(plan, d71))
    assert report["status"] == "PASS"
    assert report["summary"]["blocked_assignments"] == 2
    assert report["summary"]["semantic_pair_confirmed"] is True
    assert report["summary"]["weekly_workload_conflict"] is True
    assert report["summary"]["survivor_decision_required"] is True
    assert report["summary"]["workload_decision_required"] is True
    assert report["adjudication_contract"]["current_23_write_authorization_reusable"] is False
    rendered = str(report)
    assert "staff-1" not in rendered


def test_analyzer_fails_if_pair_is_not_same_staff(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(analyzer, "EXPECTED_PLAN_SHA", plan["plan_sha256"])
    d71 = _d71(plan)
    snap = _snapshot(plan, d71)
    snap["teacher_assignments"][1]["staff_id"] = "staff-2"
    try:
        analyzer.analyze(plan, d71, snap)
    except ValueError as exc:
        assert "PAIR_STAFF_MISMATCH" in str(exc)
    else:
        raise AssertionError("expected fail-closed staff mismatch")
