from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_p0_250_f2_promotion_case_audit_js.py"


def _load():
    spec = importlib.util.spec_from_file_location("p0_250_f2", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collector_is_case_bounded_and_read_only():
    mod = _load()
    js = mod.build_js("sigesc_ci_inert")

    assert mod.TEACHER_NAME == "Abadia Alves Martins"
    assert mod.SCHOOL_NAME == "E M E I E F Jose Pereira Barbosa"
    assert mod.CLASS_NAME == "5º ANO A"
    assert mod.ACADEMIC_YEAR == 2026
    assert mod.EXPECTED_COMPONENT_COUNT == 9

    for token in mod.MUTATOR_TOKENS:
        assert token not in js

    assert "targetDb.teacher_assignments.find(" in js
    assert "targetDb.courses.find(" in js
    assert "targetDb.students.find(" in js
    assert "targetDb.enrollments.find(" in js
    assert "targetDb.grades.aggregate([" in js
    assert "grade_values_emitted: false" in js
    assert "database_mutation: false" in js
    assert "production_writes: false" in js


def test_grade_projection_emits_presence_not_values():
    mod = _load()
    js = mod.build_js("sigesc_ci_inert")

    # Raw grade fields may only be consumed inside Mongo to produce booleans.
    for field in ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2"):
        assert f"has_{field}" in js
    assert "grade_documents_with_any_recorded_field" in js
    assert "GRADE_VALUES_EMITTED" not in js  # runtime marker belongs to Python CLI, not snapshot payload


def test_collector_compares_promotion_and_byclass_student_universes():
    mod = _load()
    js = mod.build_js("sigesc_ci_inert")

    assert "promotionStudentIds" in js
    assert "byClassStudentIds" in js
    assert "promotion_student_matches" in js
    assert "by_class_student_matches" in js
    assert "PROMOTION_BYCLASS_STUDENT_SET_DIVERGENCE" in js
    assert "DUPLICATE_GRADE_DOCUMENTS" in js
    assert "ID_TYPE_DIVERGENCE" in js
