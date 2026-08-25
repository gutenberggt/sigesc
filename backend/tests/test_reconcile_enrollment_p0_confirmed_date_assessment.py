from scripts.reconcile_enrollment_p0_confirmed_date_2026 import assess_snapshot


def base_student():
    return {
        "id": "student-1",
        "status": "active",
        "class_id": "class-1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "enrollment_number": "202600123",
        "enrollment_date": "",
    }


def base_class():
    return {
        "id": "class-1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "atendimento_programa": None,
    }


def test_ready_with_confirmed_date_and_first_attendance_after_it():
    disposition, blockers = assess_snapshot(
        row={"student_id": "student-1", "class_id": "class-1", "enrollment_number": "202600123"},
        student=base_student(),
        class_doc=base_class(),
        existing_docs=[],
        same_number_student_ids=["student-1"],
        same_number_enrollment_student_ids=[],
        first_attendance="2026-02-09",
        confirmed_date="2026-01-15",
    )
    assert disposition == "READY"
    assert blockers == []


def test_blocks_when_confirmed_date_is_after_first_attendance():
    disposition, blockers = assess_snapshot(
        row={"student_id": "student-1", "class_id": "class-1", "enrollment_number": "202600123"},
        student=base_student(),
        class_doc=base_class(),
        existing_docs=[],
        same_number_student_ids=["student-1"],
        same_number_enrollment_student_ids=[],
        first_attendance="2026-01-10",
        confirmed_date="2026-01-15",
    )
    assert disposition == "BLOCKED"
    assert "CONFIRMED_DATE_AFTER_FIRST_ATTENDANCE" in blockers


def test_blocks_without_first_attendance():
    disposition, blockers = assess_snapshot(
        row={"student_id": "student-1", "class_id": "class-1", "enrollment_number": "202600123"},
        student=base_student(),
        class_doc=base_class(),
        existing_docs=[],
        same_number_student_ids=["student-1"],
        same_number_enrollment_student_ids=[],
        first_attendance=None,
        confirmed_date="2026-01-15",
    )
    assert disposition == "BLOCKED"
    assert "FIRST_ATTENDANCE_EVIDENCE_REQUIRED" in blockers


def test_idempotent_when_exact_repair_already_exists():
    existing = [{
        "student_id": "student-1",
        "class_id": "class-1",
        "academic_year": 2026,
        "status": "active",
        "enrollment_number": "202600123",
        "enrollment_date": "2026-01-15",
        "source": "repair:p0-enrollment-confirmed-date-2026",
    }]
    disposition, blockers = assess_snapshot(
        row={"student_id": "student-1", "class_id": "class-1", "enrollment_number": "202600123"},
        student=base_student(),
        class_doc=base_class(),
        existing_docs=existing,
        same_number_student_ids=["student-1"],
        same_number_enrollment_student_ids=["student-1"],
        first_attendance="2026-02-09",
        confirmed_date="2026-01-15",
    )
    assert disposition == "ALREADY_CANONICAL"
    assert blockers == []
