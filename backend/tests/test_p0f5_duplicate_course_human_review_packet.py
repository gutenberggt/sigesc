from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_duplicate_course_human_review_packet_p0f5.py"
spec = importlib.util.spec_from_file_location("p0f5_review", SCRIPT)
assert spec and spec.loader
p0f5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f5)


def _lookups():
    classes = {"c1": {"id": "c1", "name": "8º ANO A", "school_id": "s1", "academic_year": 2026}}
    schools = {"s1": {"id": "s1", "name": "Escola Teste"}}
    students = {"stu1": {"id": "stu1", "full_name": "Aluno Teste"}}
    users = {"u1": {"id": "u1", "full_name": "Professor Um"}, "u2": {"id": "u2", "full_name": "Professor Dois"}}
    staff = {}
    return classes, schools, students, users, staff


def test_source_has_no_mongo_mutators_or_apply_cli():
    text = SCRIPT.read_text(encoding="utf-8")
    for token in p0f5.MUTATOR_TOKENS:
        assert token not in "\n".join(
            line for line in text.splitlines()
            if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
        )
    assert "--apply" not in text
    assert "--rollback" not in text


def test_review_unit_id_is_deterministic_and_value_independent():
    a = p0f5._review_unit_id(
        group_number=1,
        collection="grades",
        key_sha256="abc",
        unit_type="GRADE_FIELD_DECISION",
        field_name="b1",
        student_id="stu1",
    )
    b = p0f5._review_unit_id(
        group_number=1,
        collection="grades",
        key_sha256="abc",
        unit_type="GRADE_FIELD_DECISION",
        field_name="b1",
        student_id="stu1",
    )
    assert a == b
    assert len(a) == 64


def test_grade_conflict_expands_one_unit_per_conflicting_field():
    classes, schools, students, users, staff = _lookups()
    docs = {
        "g-source": {
            "id": "g-source", "student_id": "stu1", "class_id": "c1", "academic_year": 2026,
            "b1": 7.0, "b2": 8.0, "created_by": "u1",
        },
        "g-target": {
            "id": "g-target", "student_id": "stu1", "class_id": "c1", "academic_year": 2026,
            "b1": 9.0, "b2": 6.0, "created_by": "u2",
        },
    }
    conflict = {
        "key_sha256": "grade-key",
        "field_names": ["b1", "b2"],
        "source_document_ids": ["g-source"],
        "target_document_ids": ["g-target"],
    }
    units, error = p0f5.expand_grade_conflict(
        group_number=1, conflict=conflict, docs=docs,
        classes=classes, schools=schools, students=students, users=users, staff=staff,
    )
    assert error is None
    assert len(units) == 2
    assert {u["field_name"] for u in units} == {"b1", "b2"}
    b1 = next(u for u in units if u["field_name"] == "b1")
    assert b1["source_value"] == 7.0
    assert b1["target_value"] == 9.0
    assert b1["context"]["student_name"] == "Aluno Teste"
    assert b1["context"]["school_name"] == "Escola Teste"
    assert b1["decision_contract"]["automatic_recommendation"] is None


def test_attendance_conflict_expands_only_different_overlap_students_and_doc_fields():
    classes, schools, students, users, staff = _lookups()
    students = {
        **students,
        "stu2": {"id": "stu2", "full_name": "Aluno Dois"},
        "stu3": {"id": "stu3", "full_name": "Aluno Três"},
    }
    docs = {
        "a-source": {
            "id": "a-source", "class_id": "c1", "academic_year": 2026,
            "date": "2026-08-20", "period": "regular", "aula_numero": 2,
            "records": [
                {"student_id": "stu1", "status": "P"},
                {"student_id": "stu2", "status": "F"},
                {"student_id": "stu3", "status": "P"},
            ],
            "observations": "origem", "number_of_classes": 1, "created_by": "u1",
        },
        "a-target": {
            "id": "a-target", "class_id": "c1", "academic_year": 2026,
            "date": "2026-08-20", "period": "regular", "aula_numero": 2,
            "records": [
                {"student_id": "stu1", "status": "F"},
                {"student_id": "stu2", "status": "F"},
            ],
            "observations": "destino", "number_of_classes": 1, "created_by": "u2",
        },
    }
    conflict = {
        "key_sha256": "attendance-key",
        "field_names": ["records.status_or_dependency_id", "observations"],
        "source_document_ids": ["a-source"],
        "target_document_ids": ["a-target"],
    }
    units, error = p0f5.expand_attendance_conflict(
        group_number=2, conflict=conflict, docs=docs,
        classes=classes, schools=schools, students=students, users=users, staff=staff,
    )
    assert error is None
    assert len(units) == 2
    student_units = [u for u in units if u["unit_type"] == "ATTENDANCE_STUDENT_DECISION"]
    assert len(student_units) == 1
    assert student_units[0]["student_id"] == "stu1"
    assert student_units[0]["source_value"] == [{"status": "P", "dependency_id": None}]
    assert student_units[0]["target_value"] == [{"status": "F", "dependency_id": None}]
    assert any(u["field_name"] == "observations" for u in units)
    assert all(u["student_id"] != "stu3" for u in student_units)


def test_learning_conflict_expands_field_values_without_automatic_choice():
    classes, schools, students, users, staff = _lookups()
    docs = {
        "l-source": {
            "id": "l-source", "class_id": "c1", "date": "2026-08-21",
            "content": "Conteúdo A", "methodology": "Método A", "recorded_by": "u1",
        },
        "l-target": {
            "id": "l-target", "class_id": "c1", "date": "2026-08-21",
            "content": "Conteúdo B", "methodology": "Método B", "recorded_by": "u2",
        },
    }
    conflict = {
        "key_sha256": "learning-key",
        "field_names": ["content", "methodology"],
        "source_document_ids": ["l-source"],
        "target_document_ids": ["l-target"],
    }
    units, error = p0f5.expand_learning_conflict(
        group_number=3, conflict=conflict, docs=docs,
        classes=classes, schools=schools, students=students, users=users, staff=staff,
    )
    assert error is None
    assert len(units) == 2
    content = next(u for u in units if u["field_name"] == "content")
    assert content["source_value"] == "Conteúdo A"
    assert content["target_value"] == "Conteúdo B"
    assert content["source_actor"]["recorded_by"]["name"] == "Professor Um"
    assert content["decision_contract"]["decision"] is None


def test_multiplicity_is_fail_closed_not_silently_expanded():
    classes, schools, students, users, staff = _lookups()
    conflict = {
        "key_sha256": "multi",
        "field_names": ["b1"],
        "source_document_ids": ["s1", "s2"],
        "target_document_ids": ["t1"],
    }
    units, error = p0f5.expand_grade_conflict(
        group_number=1, conflict=conflict, docs={},
        classes=classes, schools=schools, students=students, users=users, staff=staff,
    )
    assert units == []
    assert error == "GRADE_MULTIPLICITY_REQUIRES_DEEP_REVIEW"


def test_private_write_forces_0600_and_roundtrips(tmp_path):
    target = tmp_path / "packet.json"
    p0f5._private_write_json(target, {"secret": "academic-value"})
    mode = os.stat(target).st_mode & 0o777
    assert mode == 0o600
    assert json.loads(target.read_text(encoding="utf-8"))["secret"] == "academic-value"


def test_compact_summary_does_not_expose_sensitive_values():
    report = {
        "phase": p0f5.PHASE_ID,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "summary": {"review_units": 2},
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Ciências"},
            "p0f4_conflicts": 1,
            "review_units": 2,
            "conflicts": [{"review_units": [{"source_value": 10, "student_name": "Privado"}]}],
        }],
        "manifest_sha256": "abc",
    }
    compact = p0f5.compact_summary(report)
    rendered = json.dumps(compact, ensure_ascii=False)
    assert "Privado" not in rendered
    assert "source_value" not in rendered
    assert compact["sensitive_payload_printed"] is False
