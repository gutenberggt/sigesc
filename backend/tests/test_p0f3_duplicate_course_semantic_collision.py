from __future__ import annotations

import importlib.util
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "audit_duplicate_course_semantic_collision_p0f3.py"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_duplicate_course_semantic_collision_p0f3", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_is_explicit_and_read_only():
    m = load_module()
    assert m.PHASE_ID == "P0F3-DUPLICATE-COURSE-SEMANTIC-COLLISION-READ-ONLY-2026"
    assert m.MANIFEST_VERSION == 1
    m.assert_read_only()


def test_no_apply_or_rollback_mode_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply"' not in source
    assert '"--rollback"' not in source


def test_supported_collections_are_registered_in_ssot():
    m = load_module()
    registered = {spec.collection for spec in m.COURSE_REFERENCE_SPECS}
    assert m.SUPPORTED_COLLECTIONS <= registered


def test_grade_collision_uses_real_writer_key_and_exact_equivalent():
    m = load_module()
    src = [{
        "id": "s", "student_id": "stu", "class_id": "c", "academic_year": 2026,
        "b1": 8.0, "b2": None, "observations": None,
    }]
    tgt = [{
        "id": "t", "student_id": "stu", "class_id": "c", "academic_year": 2026,
        "b1": 8, "b2": None, "observations": None,
    }]
    r = m.analyze_grades(src, tgt, 10)
    assert r["shared_natural_keys"] == 1
    assert r["classifications"] == {"EXACT_EQUIVALENT": 1}
    assert r["hard_conflicts"] == 0


def test_grade_complementary_values_are_not_hard_conflict():
    m = load_module()
    src = [{"id": "s", "student_id": "stu", "class_id": "c", "academic_year": 2026, "b1": 8, "b2": None}]
    tgt = [{"id": "t", "student_id": "stu", "class_id": "c", "academic_year": 2026, "b1": None, "b2": 9}]
    r = m.analyze_grades(src, tgt, 10)
    assert r["classifications"] == {"COMPLEMENTARY_MERGEABLE": 1}
    assert r["hard_conflicts"] == 0


def test_grade_divergent_nonempty_values_are_hard_conflict_without_exposing_values():
    m = load_module()
    src = [{"id": "s", "student_id": "stu", "class_id": "c", "academic_year": 2026, "b1": 8}]
    tgt = [{"id": "t", "student_id": "stu", "class_id": "c", "academic_year": 2026, "b1": 5}]
    r = m.analyze_grades(src, tgt, 10)
    assert r["classifications"] == {"VALUE_CONFLICT": 1}
    assert r["hard_conflicts"] == 1
    example = r["examples"][0]
    assert example["field_names"] == ["b1"]
    assert set(example) == {
        "key_sha256",
        "classification",
        "field_names",
        "source_document_ids",
        "target_document_ids",
    }
    assert "values" not in example
    assert "source_values" not in example
    assert "target_values" not in example


def test_attendance_different_aula_numero_is_not_collision():
    m = load_module()
    src = [{"id": "s", "class_id": "c", "date": "2026-08-20", "period": "regular", "aula_numero": 1, "records": []}]
    tgt = [{"id": "t", "class_id": "c", "date": "2026-08-20", "period": "regular", "aula_numero": 2, "records": []}]
    r = m.analyze_attendance(src, tgt, 10)
    assert r["shared_natural_keys"] == 0
    assert r["hard_conflicts"] == 0


def test_attendance_same_aula_conflicting_student_status_is_hard_conflict():
    m = load_module()
    src = [{
        "id": "s", "class_id": "c", "date": "2026-08-20", "aula_numero": 1,
        "records": [{"student_id": "stu", "status": "present"}], "number_of_classes": 1,
    }]
    tgt = [{
        "id": "t", "class_id": "c", "date": "2026-08-20", "aula_numero": 1,
        "records": [{"student_id": "stu", "status": "absent"}], "number_of_classes": 1,
    }]
    r = m.analyze_attendance(src, tgt, 10)
    assert r["classifications"] == {"DATA_CONFLICT": 1}
    assert r["hard_conflicts"] == 1
    assert r["examples"][0]["conflicting_student_count"] == 1


def test_attendance_same_aula_disjoint_students_is_merge_compatible():
    m = load_module()
    src = [{
        "id": "s", "class_id": "c", "date": "2026-08-20", "aula_numero": 1,
        "records": [{"student_id": "a", "status": "present"}], "number_of_classes": 1,
    }]
    tgt = [{
        "id": "t", "class_id": "c", "date": "2026-08-20", "aula_numero": 1,
        "records": [{"student_id": "b", "status": "absent"}], "number_of_classes": 1,
    }]
    r = m.analyze_attendance(src, tgt, 10)
    assert r["classifications"] == {"RECORDS_MERGE_COMPATIBLE": 1}
    assert r["hard_conflicts"] == 0


def test_attendance_missing_aula_numero_fails_closed_when_key_collides():
    m = load_module()
    src = [{"id": "s", "class_id": "c", "date": "2026-08-20", "records": []}]
    tgt = [{"id": "t", "class_id": "c", "date": "2026-08-20", "records": []}]
    r = m.analyze_attendance(src, tgt, 10)
    assert r["missing_aula_numero_shared_keys"] == 1
    assert r["hard_conflicts"] >= 1


def test_learning_object_writer_key_is_class_plus_date_after_course_collapse():
    m = load_module()
    src = [{"id": "s", "class_id": "c", "date": "2026-08-20", "content": "A", "number_of_classes": 1}]
    tgt = [{"id": "t", "class_id": "c", "date": "2026-08-20", "content": "A", "number_of_classes": 1}]
    r = m.analyze_learning_objects(src, tgt, 10)
    assert r["shared_natural_keys"] == 1
    assert r["classifications"] == {"EXACT_EQUIVALENT": 1}


def test_learning_object_different_content_is_hard_conflict_but_redacted():
    m = load_module()
    src = [{"id": "s", "class_id": "c", "date": "2026-08-20", "content": "conteudo-secreto-A"}]
    tgt = [{"id": "t", "class_id": "c", "date": "2026-08-20", "content": "conteudo-secreto-B"}]
    r = m.analyze_learning_objects(src, tgt, 10)
    assert r["classifications"] == {"PEDAGOGICAL_CONTENT_CONFLICT": 1}
    assert r["hard_conflicts"] == 1
    rendered = str(r["examples"])
    assert "conteudo-secreto" not in rendered
    assert r["examples"][0]["field_names"] == ["content"]


def test_teacher_assignment_only_active_rows_collide():
    m = load_module()
    src = [{"id": "s", "staff_id": "p", "class_id": "c", "academic_year": 2026, "status": "inativo"}]
    tgt = [{"id": "t", "staff_id": "p", "class_id": "c", "academic_year": 2026, "status": "ativo"}]
    r = m.analyze_teacher_assignments(src, tgt, 10)
    assert r["shared_natural_keys"] == 0


def test_teacher_assignment_exact_active_duplicate_requires_plan_not_hard_conflict():
    m = load_module()
    src = [{"id": "s", "staff_id": "p", "class_id": "c", "academic_year": 2026, "status": "ativo", "school_id": "x"}]
    tgt = [{"id": "t", "staff_id": "p", "class_id": "c", "academic_year": 2026, "status": "active", "school_id": "x"}]
    r = m.analyze_teacher_assignments(src, tgt, 10)
    assert r["classifications"] == {"EXACT_ACTIVE_ASSIGNMENT_DUPLICATE": 1}
    assert r["hard_conflicts"] == 0
    assert r["collision_items"] == 1


def _tca(doc_id, component, *, aula=1, valid_from="2026-02-01", valid_until=None):
    return {
        "id": doc_id,
        "teacher_id": "u", "class_id": "c", "component_id": component,
        "valid_from": valid_from, "valid_until": valid_until, "deleted": False,
        "is_substitute": False,
        "weekly_slots": [{"weekday": 2, "aula_numero": aula, "start_time": "08:00", "end_time": "08:50"}],
    }


def test_teacher_class_assignments_different_slots_do_not_collide():
    m = load_module()
    r = m.analyze_teacher_class_assignments([_tca("s", "A", aula=1)], [_tca("t", "B", aula=2)], 10)
    assert r["collision_items"] == 0


def test_teacher_class_assignments_same_slot_is_operational_collision():
    m = load_module()
    r = m.analyze_teacher_class_assignments([_tca("s", "A", aula=1)], [_tca("t", "B", aula=1)], 10)
    assert r["collision_items"] == 1
    assert r["classifications"] == {"EXACT_ASSIGNMENT_DUPLICATE": 1}


def test_class_schedule_shared_document_with_distinct_slots_is_normal():
    m = load_module()
    row = {
        "id": "sch", "class_id": "c",
        "schedule_slots": [
            {"day": "segunda", "slot_number": 1, "course_id": "SRC"},
            {"day": "segunda", "slot_number": 2, "course_id": "TGT"},
        ],
    }
    r = m.analyze_class_schedules([row], "SRC", "TGT", 10)
    assert r["shared_schedule_documents"] == 1
    assert r["same_day_slot_collisions"] == 0
    assert r["collision_items"] == 0


def test_class_schedule_same_day_and_slot_is_material_collision():
    m = load_module()
    row = {
        "id": "sch", "class_id": "c",
        "schedule_slots": [
            {"day": "segunda", "slot_number": 1, "course_id": "SRC"},
            {"day": "segunda", "slot_number": 1, "course_id": "TGT"},
        ],
    }
    r = m.analyze_class_schedules([row], "SRC", "TGT", 10)
    assert r["same_day_slot_collisions"] == 1
    assert r["collision_items"] == 1


def test_student_dependency_key_matches_router_rule_and_ignores_class():
    m = load_module()
    src = [{"id": "s", "student_id": "stu", "origin_academic_year": 2025, "class_id": "A", "status": "active"}]
    tgt = [{"id": "t", "student_id": "stu", "origin_academic_year": 2025, "class_id": "B", "status": "active"}]
    r = m.analyze_student_dependencies(src, tgt, 10)
    assert r["shared_natural_keys"] == 1
    assert r["collision_items"] == 1


def test_group_classification_is_fail_closed():
    m = load_module()
    assert m.classify_group(unique_kept=False, unsupported_reference_count=0, hard_conflicts=0, collision_items=0) == "NO_UNIQUE_HISTORICAL_KEPT_BLOCKED"
    assert m.classify_group(unique_kept=True, unsupported_reference_count=1, hard_conflicts=0, collision_items=0) == "UNANALYZED_REFERENCES_BLOCKED"
    assert m.classify_group(unique_kept=True, unsupported_reference_count=0, hard_conflicts=1, collision_items=1) == "SEMANTIC_DATA_CONFLICTS_FOUND_BLOCKED"
    assert m.classify_group(unique_kept=True, unsupported_reference_count=0, hard_conflicts=0, collision_items=1) == "SEMANTIC_COLLISIONS_REQUIRE_DETERMINISTIC_PLAN"
    assert m.classify_group(unique_kept=True, unsupported_reference_count=0, hard_conflicts=0, collision_items=0) == "NO_SEMANTIC_COLLISIONS_REQUIRES_REVIEW"


def test_compact_summary_never_contains_examples_or_payload_values():
    m = load_module()
    report = {
        "phase": m.PHASE_ID,
        "mode": "READ_ONLY_SEMANTIC_COLLISION_ANALYSIS",
        "status": "PASS",
        "summary": {},
        "manifest_sha256": "sha",
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Ciências"},
            "source_id": "s", "target_id": "t", "hard_conflicts": 1,
            "collision_items": 2, "unsupported_reference_count": 0,
            "forensic_classification": "SEMANTIC_DATA_CONFLICTS_FOUND_BLOCKED",
            "analyses": {"grades": {"shared_natural_keys": 1, "examples": [{"secret": "x"}], "hard_conflicts": 1, "collision_items": 1}},
        }],
    }
    compact = m.compact_summary(report)
    assert "examples" not in compact["cases"][0]["analyses"]["grades"]
    assert "secret" not in str(compact)
