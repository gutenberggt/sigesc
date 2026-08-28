from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_p0f7_3_teacher_workload_triangulation.py"
spec = importlib.util.spec_from_file_location("p0f73", SCRIPT)
assert spec and spec.loader
p0f73 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f73)


def _base_case(number=1):
    return {
        "case_number": number,
        "classification": "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW",
        "divergent_fields": ["carga_horaria_semanal"],
        "teacher": {"staff_id": "staff-1", "name": "Professor"},
        "class": {"class_id": f"class-{number}", "name": "Turma", "academic_year": 2026},
        "school": {"school_id": "school-1", "name": "Escola"},
        "source_assignment": {"id": f"s-{number}", "status": "ativo", "carga_horaria_semanal": 2},
        "target_assignment": {"id": f"t-{number}", "status": "ativo", "carga_horaria_semanal": 3},
    }


def _report():
    payload = {
        "phase": p0f73.P0F72_PHASE,
        "mode": "READ_ONLY_TEACHER_ASSIGNMENT_FORENSIC",
        "status": "PASS",
        "group_name": "Geografia",
        "source_course_id": "course-source",
        "target_course_id": "course-target",
        "summary": {
            "documented_cases": 3,
            "complete_blocker_coverage": True,
        },
        "safety": {
            "read_only": True,
            "contains_student_data": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": [_base_case(1), _base_case(2), _base_case(3)],
    }
    payload["manifest_sha256"] = p0f73._canonical_sha256(payload)
    return payload


def test_read_only_guard_passes():
    p0f73.assert_read_only()


def test_signal_source_only():
    assert p0f73._signal(1, 0) == "SOURCE_ONLY"


def test_signal_target_only():
    assert p0f73._signal(0, 2) == "TARGET_ONLY"


def test_signal_both():
    assert p0f73._signal(1, 1) == "BOTH"


def test_signal_none():
    assert p0f73._signal(0, 0) == "NONE"


def test_classification_mixed():
    out = p0f73.classify_identity_evidence({
        "matrix": "SOURCE_ONLY",
        "schedule": "TARGET_ONLY",
    })
    assert out["classification"] == "MIXED_IDENTITY_EVIDENCE_REQUIRES_REVIEW"
    assert out["automatic_workload_decision"] is False


def test_classification_leans_source_requires_two_independent_signals():
    out = p0f73.classify_identity_evidence({
        "matrix": "SOURCE_ONLY",
        "schedule": "SOURCE_ONLY",
        "grades": "NONE",
    })
    assert out["classification"] == "IDENTITY_EVIDENCE_LEANS_SOURCE"
    assert out["workload_resolution"].startswith("REQUIRES_")


def test_classification_leans_target():
    out = p0f73.classify_identity_evidence({
        "matrix": "TARGET_ONLY",
        "attendance": "TARGET_ONLY",
    })
    assert out["classification"] == "IDENTITY_EVIDENCE_LEANS_TARGET"


def test_classification_shared():
    out = p0f73.classify_identity_evidence({
        "matrix": "BOTH",
        "schedule": "BOTH",
    })
    assert out["classification"] == "SHARED_IDENTITY_EVIDENCE_REQUIRES_REVIEW"


def test_classification_no_evidence():
    out = p0f73.classify_identity_evidence({
        "matrix": "NONE",
        "schedule": "NONE",
    })
    assert out["classification"] == "NO_EXTERNAL_IDENTITY_EVIDENCE"


def test_validate_p0f72_accepts_sealed_report():
    out = p0f73.validate_p0f72(_report())
    assert out["source_course_id"] == "course-source"
    assert out["target_course_id"] == "course-target"
    assert len(out["cases"]) == 3


def test_validate_p0f72_rejects_manifest_tamper():
    report = _report()
    report["group_name"] = "História"
    try:
        p0f73.validate_p0f72(report)
    except ValueError as exc:
        assert str(exc) == "P0F7_2_SHA_MISMATCH"
    else:
        raise AssertionError("tamper should fail")


def test_validate_p0f72_rejects_unexpected_field():
    report = _report()
    report["cases"][0]["divergent_fields"] = ["school_id"]
    report["manifest_sha256"] = p0f73._canonical_sha256(
        {k: v for k, v in report.items() if k != "manifest_sha256"}
    )
    try:
        p0f73.validate_p0f72(report)
    except ValueError as exc:
        assert str(exc) == "P0F7_2_UNEXPECTED_DIVERGENT_FIELDS"
    else:
        raise AssertionError("unexpected divergent field should fail")


def test_validate_p0f72_rejects_write_flag():
    report = _report()
    report["safety"]["production_writes_executed"] = True
    report["manifest_sha256"] = p0f73._canonical_sha256(
        {k: v for k, v in report.items() if k != "manifest_sha256"}
    )
    try:
        p0f73.validate_p0f72(report)
    except ValueError as exc:
        assert str(exc) == "P0F7_2_WRITES_FLAG_INVALID"
    else:
        raise AssertionError("write flag should fail")


def test_validate_p0f72_rejects_executor_authorization():
    report = _report()
    report["safety"]["not_authorization_for_executor"] = False
    report["manifest_sha256"] = p0f73._canonical_sha256(
        {k: v for k, v in report.items() if k != "manifest_sha256"}
    )
    try:
        p0f73.validate_p0f72(report)
    except ValueError as exc:
        assert str(exc) == "P0F7_2_EXECUTOR_FLAG_INVALID"
    else:
        raise AssertionError("executor authorization should fail")


def test_source_contains_no_apply_surface():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--apply" not in source
    assert "automatic_workload_recommendation" in source
