from scripts.reconcile_enrollment_p0_2026 import (
    CONFIRM_TOKEN,
    SOURCE,
    YEAR,
    evaluate_snapshot,
)


def base_row():
    return {
        "student_id": "student-1",
        "full_name": "Aluno Teste",
        "class_id": "class-2026",
        "enrollment_number": "202600123",
        "blockers": [],
    }


def base_student():
    return {
        "id": "student-1",
        "full_name": "Aluno Teste",
        "status": "active",
        "class_id": "class-2026",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "enrollment_number": "202600123",
        "enrollment_date": "2026-02-02",
    }


def base_class():
    return {
        "id": "class-2026",
        "name": "1º ANO A",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "atendimento_programa": None,
    }


def evaluate(**overrides):
    data = {
        "manifest_row": base_row(),
        "student": base_student(),
        "class_doc": base_class(),
        "enrollment_docs": [],
        "same_number_student_ids": ["student-1"],
        "same_number_enrollment_student_ids": [],
        "grade_count": 2,
        "attendance_count": 10,
        "enrollment_date": "2026-02-02",
    }
    data.update(overrides)
    return evaluate_snapshot(**data)


def test_repair_constants_are_intentionally_scoped_to_2026():
    assert YEAR == 2026
    assert CONFIRM_TOKEN == "RECONCILE-P0-2026"
    assert SOURCE == "repair:p0-enrollment-reconcile-2026"


def test_ready_when_all_runtime_evidence_matches_manifest():
    disposition, blockers, exact = evaluate()
    assert disposition == "READY"
    assert blockers == []
    assert exact is None


def test_blocks_when_student_changed_class_after_manifest():
    student = base_student()
    student["class_id"] = "class-other"
    class_doc = base_class()
    class_doc["id"] = "class-other"

    disposition, blockers, _ = evaluate(student=student, class_doc=class_doc)

    assert disposition == "BLOCKED"
    assert "CLASS_CHANGED_SINCE_MANIFEST" in blockers


def test_blocks_special_class_instead_of_turning_aee_into_home_enrollment():
    class_doc = base_class()
    class_doc["atendimento_programa"] = "aee"

    disposition, blockers, _ = evaluate(class_doc=class_doc)

    assert disposition == "BLOCKED"
    assert "SPECIAL_CLASS" in blockers


def test_blocks_foreign_enrollment_number_in_students():
    disposition, blockers, _ = evaluate(
        same_number_student_ids=["student-1", "student-2"]
    )

    assert disposition == "BLOCKED"
    assert "ENROLLMENT_NUMBER_DUPLICATED_IN_STUDENTS" in blockers


def test_blocks_foreign_enrollment_number_in_enrollments():
    disposition, blockers, _ = evaluate(
        same_number_enrollment_student_ids=["student-2"]
    )

    assert disposition == "BLOCKED"
    assert "ENROLLMENT_NUMBER_USED_BY_OTHER_STUDENT" in blockers


def test_blocks_if_no_academic_activity_in_current_class():
    disposition, blockers, _ = evaluate(grade_count=0, attendance_count=0)

    assert disposition == "BLOCKED"
    assert "NO_CURRENT_CLASS_ACADEMIC_ACTIVITY_2026" in blockers


def test_blocks_if_enrollment_date_has_no_evidence():
    disposition, blockers, _ = evaluate(enrollment_date=None)

    assert disposition == "BLOCKED"
    assert "MISSING_ENROLLMENT_DATE_EVIDENCE" in blockers


def test_blocks_any_preexisting_noncanonical_enrollment_document():
    disposition, blockers, _ = evaluate(
        enrollment_docs=[{
            "id": "old-enrollment",
            "student_id": "student-1",
            "class_id": "old-class",
            "academic_year": 2025,
            "status": "relocated",
            "enrollment_number": "202500111",
        }]
    )

    assert disposition == "BLOCKED"
    assert "ENROLLMENT_DOCUMENT_ALREADY_EXISTS" in blockers


def test_idempotent_when_exact_active_canonical_enrollment_already_exists():
    existing = {
        "id": "canonical-1",
        "student_id": "student-1",
        "class_id": "class-2026",
        "academic_year": 2026,
        "status": "active",
        "enrollment_number": "202600123",
        "source": SOURCE,
    }

    disposition, blockers, exact = evaluate(
        enrollment_docs=[existing],
        same_number_enrollment_student_ids=["student-1"],
    )

    assert disposition == "ALREADY_CANONICAL"
    assert blockers == []
    assert exact == existing


def test_existing_exact_enrollment_with_changed_number_is_blocked():
    existing = {
        "id": "canonical-1",
        "student_id": "student-1",
        "class_id": "class-2026",
        "academic_year": 2026,
        "status": "active",
        "enrollment_number": "202699999",
    }

    disposition, blockers, _ = evaluate(
        enrollment_docs=[existing],
        same_number_enrollment_student_ids=["student-1"],
    )

    assert disposition == "BLOCKED"
    assert "EXISTING_CANONICAL_NUMBER_MISMATCH" in blockers


def test_blocks_school_and_tenant_divergence():
    class_doc = base_class()
    class_doc["school_id"] = "school-other"
    class_doc["mantenedora_id"] = "tenant-other"

    disposition, blockers, _ = evaluate(class_doc=class_doc)

    assert disposition == "BLOCKED"
    assert "SCHOOL_MISMATCH" in blockers
    assert "TENANT_MISMATCH_OR_MISSING" in blockers
