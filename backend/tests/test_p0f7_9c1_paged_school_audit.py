from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ref_builder = _load_module(
    "p0f79c1_reference",
    BACKEND / "scripts" / "build_p0f7_9c1_reference_snapshot_js.py",
)
page_builder = _load_module(
    "p0f79c1_pages",
    BACKEND / "scripts" / "build_p0f7_9c1_school_pages_js.py",
)
analyzer = _load_module(
    "p0f79c1_analyzer",
    BACKEND / "scripts" / "audit_p0f7_9c1_school_pages_offline.py",
)


def _report() -> dict:
    return {
        "phase": analyzer.REPORT_PHASE,
        "status": "PASS",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "collection_strategy": "PAGED_BY_SCHOOL_SNAPSHOT",
        "counts": {
            "schools": 1,
            "classes": 2,
            "classes_without_explicit_level": 1,
            "teacher_assignments": 3,
            "active_teacher_assignments": 3,
            "courses": 2,
        },
    }


def _reference(report: dict) -> dict:
    return {
        "phase": analyzer.REFERENCE_PHASE,
        "mode": analyzer.REFERENCE_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "source_p0f7_9c0_report_sha256": analyzer._canonical_sha256(report),
        "query_budget": 2,
        "query_calls": 2,
        "schools": [{"id": "school-1", "name": "School 1", "mantenedora_id": "tenant-1"}],
        "courses": [
            {
                "id": "course-eja",
                "name": "Ciências",
                "nivel_ensino": "eja_final",
                "grade_levels": [],
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "course-ei",
                "name": "O Eu, O Outro e Nós",
                "nivel_ensino": "educacao_infantil",
                "grade_levels": [],
                "mantenedora_id": "tenant-1",
            },
        ],
    }


def _page(report: dict, reference: dict) -> dict:
    return {
        "phase": analyzer.PAGE_PHASE,
        "mode": analyzer.PAGE_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "school_id": "school-1",
        "school_name": "School 1",
        "source_reference_sha256": analyzer._canonical_sha256(reference),
        "source_p0f7_9c0_report_sha256": analyzer._canonical_sha256(report),
        "query_budget": 4,
        "query_calls": 4,
        "counts": {"classes": 2, "teacher_assignments": 3},
        "classes": [
            {
                "id": "class-eja",
                "name": "EJA",
                "school_id": "school-1",
                "academic_year": 2026,
                "mantenedora_id": "tenant-1",
                "education_level": "eja_final",
                "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
            },
            {
                "id": "class-no-level",
                "name": "Sem nível",
                "school_id": "school-1",
                "academic_year": 2026,
                "mantenedora_id": "tenant-1",
                "education_level": "",
                "nivel_ensino": "",
                "series": ["EJA 3ª ETAPA"],
            },
        ],
        "teacher_assignments": [
            {
                "id": "a1",
                "school_id": "school-1",
                "class_id": "class-eja",
                "course_id": "course-eja",
                "academic_year": 2026,
                "status": "ativo",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "a2",
                "school_id": "school-1",
                "class_id": "class-eja",
                "course_id": "course-ei",
                "academic_year": 2026,
                "status": "ativo",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "a3",
                "school_id": "school-1",
                "class_id": "class-no-level",
                "course_id": "course-eja",
                "academic_year": 2026,
                "status": "ativo",
                "mantenedora_id": "tenant-1",
            },
        ],
    }


def test_reference_collector_is_two_bounded_queries_and_read_only() -> None:
    report = _report()
    js = ref_builder.build_js(report, "sigesc")
    assert "const QUERY_BUDGET = 2" in js
    assert js.count(".find(") == 2
    assert js.count(".toArray()") == 2
    for token in (
        "students",
        "enrollments",
        "grades",
        "attendance",
        "insertOne",
        "updateOne",
        "deleteOne",
        "bulkWrite",
    ):
        assert token not in js


def test_school_collector_is_four_queries_and_has_hard_bounds() -> None:
    report = _report()
    reference = _reference(report)
    with tempfile.TemporaryDirectory() as tmp:
        count = page_builder.build_pages(report, reference, "sigesc", Path(tmp))
        assert count == 1
        js = next(Path(tmp).glob("school-*.js")).read_text(encoding="utf-8")
    assert "const QUERY_BUDGET = 4" in js
    assert js.count("countDocuments(") == 2
    assert js.count(".find(") == 2
    assert "MAX_CLASSES = 100" in js
    assert "MAX_ASSIGNMENTS = 600" in js
    assert "staff_id" not in js
    for token in ("students", "enrollments", "grades", "attendance", "insertOne", "updateMany", "deleteMany"):
        assert token not in js


def test_offline_analyzer_reuses_writer_integrity_codes() -> None:
    report = _report()
    reference = _reference(report)
    result = analyzer.build_report(report, reference, [_page(report, reference)])
    summary = result["summary"]
    assert result["status"] == "PASS"
    assert summary["compatible_assignments"] == 1
    assert summary["active_noncompatible_or_blocked_assignments"] == 2
    assert summary["active_educacao_infantil_to_eja_final"] == 1
    assert summary["integrity_codes"]["TEACHER_ASSIGNMENT_LEVEL_MISMATCH"] == 1
    assert summary["integrity_codes"]["TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED"] == 1
    assert result["safety"]["teacher_identity_fields_collected"] == 0
    assert result["safety"]["remediation_executed"] is False


def test_analyzer_source_does_not_duplicate_curricular_fit() -> None:
    text = (BACKEND / "scripts" / "audit_p0f7_9c1_school_pages_offline.py").read_text(encoding="utf-8")
    assert "validate_teacher_assignment_curriculum" in text
    assert "_curricular_fit" not in text
    assert "staff_id" not in text
