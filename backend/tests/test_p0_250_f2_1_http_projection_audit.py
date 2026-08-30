from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "p0_250_f2_1_http_projection_audit.py"
SPEC = importlib.util.spec_from_file_location("p0_250_f2_1_http_projection_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _grade(student_id: str, course_id: str, *, b1=8, class_id="class-5a"):
    return {
        "id": f"g-{student_id}-{course_id}",
        "student_id": student_id,
        "class_id": class_id,
        "course_id": course_id,
        "academic_year": 2026,
        "b1": b1,
        "b2": 7,
        "b3": None,
        "b4": None,
        "rec_s1": None,
        "rec_s2": None,
    }


def _matrix_payloads():
    students = [f"student-{i:02d}" for i in range(1, 22)]
    courses = [f"course-{i}" for i in range(1, 10)]
    generic = {
        sid: [_grade(sid, cid) for cid in courses]
        for sid in students
    }
    by_class = {}
    for cid in courses:
        rows = [
            {"student": {"id": sid}, "grade": _grade(sid, cid)}
            for sid in students
        ]
        # F2 observed one additional by-class roster member. The F2.1 comparison
        # must intersect it away and preserve exactly the 21 Promotion students.
        rows.append({
            "student": {"id": "student-outside-promotion"},
            "grade": _grade("student-outside-promotion", cid),
        })
        by_class[cid] = rows
    return students, courses, generic, by_class


def test_21x9_http_shapes_are_projected_to_exact_189_pairs():
    students, courses, generic, by_class = _matrix_payloads()
    result = MODULE.analyze_http_projection(
        promotion_student_ids=students,
        allowed_course_ids=courses,
        class_id="class-5a",
        generic_payloads=generic,
        by_class_payloads=by_class,
    )

    assert result["classification"] == "HTTP_AND_FRONTEND_PROJECTION_PARITY_FOR_PROMOTION_21"
    assert result["promotion_student_count"] == 21
    assert result["allowed_course_count"] == 9
    assert result["expected_student_course_pairs"] == 189
    assert result["generic_document_pairs"] == 189
    assert result["by_class_row_pairs"] == 189
    assert result["by_class_rows_total"] == 198
    assert result["by_class_rows_in_promotion"] == 189
    assert result["by_class_rows_outside_promotion"] == 9
    assert result["document_presence_mismatch_pairs"] == 0
    assert result["field_presence_mismatches"] == 0
    assert result["field_value_mismatches"] == 0
    assert result["students_with_all_course_documents"] == 21


def test_detects_live_value_divergence_without_returning_values():
    students, courses, generic, by_class = _matrix_payloads()
    by_class[courses[0]][0]["grade"]["b1"] = 6

    result = MODULE.analyze_http_projection(
        promotion_student_ids=students,
        allowed_course_ids=courses,
        class_id="class-5a",
        generic_payloads=generic,
        by_class_payloads=by_class,
    )

    assert result["classification"] == "HTTP_VALUE_DIVERGENCE_FOR_PROMOTION_21"
    assert result["field_value_mismatches"] == 1
    serialized = repr(result)
    assert "'b1': 6" not in serialized
    assert "'b1': 8" not in serialized


def test_detects_by_class_placeholder_vs_persisted_generic_document():
    students, courses, generic, by_class = _matrix_payloads()
    by_class[courses[0]][0]["grade"] = {
        "student_id": students[0],
        "class_id": "class-5a",
        "course_id": courses[0],
        "academic_year": 2026,
        "b1": None,
        "b2": None,
        "b3": None,
        "b4": None,
        "rec_s1": None,
        "rec_s2": None,
    }

    result = MODULE.analyze_http_projection(
        promotion_student_ids=students,
        allowed_course_ids=courses,
        class_id="class-5a",
        generic_payloads=generic,
        by_class_payloads=by_class,
    )

    assert result["classification"] == "HTTP_DOCUMENT_DIVERGENCE_FOR_PROMOTION_21"
    assert result["document_presence_mismatch_pairs"] == 1


def test_frontend_projection_ignores_unentitled_course_without_losing_authorized_pairs():
    students, courses, generic, by_class = _matrix_payloads()
    for sid in students:
        generic[sid].append(_grade(sid, "course-10"))

    result = MODULE.analyze_http_projection(
        promotion_student_ids=students,
        allowed_course_ids=courses,
        class_id="class-5a",
        generic_payloads=generic,
        by_class_payloads=by_class,
    )

    assert result["classification"] == "HTTP_AND_FRONTEND_PROJECTION_PARITY_FOR_PROMOTION_21"
    assert result["ignored_non_authorized_documents"] == 21
    assert result["generic_document_pairs"] == 189


def test_source_has_no_mongo_mutator_call_and_no_http_write_method():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    forbidden_attrs = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
    }
    mutation_calls = []
    write_methods = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_attrs:
                mutation_calls.append(node.func.attr)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "method" and isinstance(kw.value, ast.Constant):
                    method = str(kw.value.value).upper()
                    if method in {"POST", "PUT", "PATCH", "DELETE"}:
                        write_methods.append(method)

    assert mutation_calls == []
    assert write_methods == []


def test_privacy_contract_is_explicit_in_live_output_builder():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"grade_values_emitted": False' in source
    assert '"student_ids_emitted": False' in source
    assert '"student_pii_emitted": False' in source
    assert '"access_token_emitted": False' in source
    assert '"access_token_persisted": False' in source
    assert '"database_mutation": False' in source
    assert '"production_writes": False' in source
