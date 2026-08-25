from scripts.reconcile_enrollment_p0_legacy_relocation_2026 import (
    CASES,
    SOURCE,
    assess_snapshot,
)
from scripts.reconcile_enrollment_p0_legacy_relocation_historical_school_2026 import (
    MOVEMENT_AT_BY_STUDENT,
    assess_snapshot as assess_snapshot_historical,
    class_belongs_to_school_at,
)


def case():
    return dict(CASES[0])


def student(c):
    return {
        "id": c["student_id"],
        "status": "active",
        "school_id": c["school_id"],
        "class_id": c["destination_class_id"],
        "enrollment_number": c["current_student_number"],
        "mantenedora_id": "tenant-1",
    }


def cls(cid, school_id):
    return {
        "id": cid,
        "school_id": school_id,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "atendimento_programa": None,
    }


def origin(c):
    return {
        "id": c["origin_enrollment_id"],
        "student_id": c["student_id"],
        "class_id": c["origin_class_id"],
        "academic_year": 2026,
        "status": c["origin_status"],
        "enrollment_number": c["origin_number"],
    }


def destination_ready(c):
    return {
        "id": c["destination_enrollment_id"],
        "student_id": c["student_id"],
        "class_id": c["destination_class_id"],
        "academic_year": 2026,
        "status": "relocated",
        "enrollment_number": c["destination_legacy_number"],
        "previous_enrollment_number": None,
        "source": None,
    }


def assess(**overrides):
    c = case()
    kwargs = {
        "case": c,
        "student": student(c),
        "destination": destination_ready(c),
        "origin": origin(c),
        "destination_class": cls(c["destination_class_id"], c["school_id"]),
        "origin_class": cls(c["origin_class_id"], c["school_id"]),
        "same_student_number_students": [{"id": c["student_id"]}],
        "same_student_number_enrollments": [],
        "same_legacy_number_enrollments": [
            {"id": c["destination_enrollment_id"], "student_id": c["student_id"]}
        ],
        "other_active_regular": [],
    }
    kwargs.update(overrides)
    return assess_snapshot(**kwargs)


def test_exact_legacy_snapshot_is_ready():
    disposition, blockers = assess()
    assert disposition == "READY"
    assert blockers == []


def test_exact_repaired_snapshot_is_idempotent():
    c = case()
    repaired = destination_ready(c)
    repaired.update(
        {
            "status": "active",
            "enrollment_number": c["current_student_number"],
            "previous_enrollment_number": c["destination_legacy_number"],
            "source": SOURCE,
        }
    )
    disposition, blockers = assess(
        destination=repaired,
        same_student_number_enrollments=[
            {"id": c["destination_enrollment_id"], "student_id": c["student_id"]}
        ],
        same_legacy_number_enrollments=[],
    )
    assert disposition == "ALREADY_CANONICAL"
    assert blockers == []


def test_blocks_if_student_number_is_owned_by_another_student():
    c = case()
    disposition, blockers = assess(
        same_student_number_students=[{"id": c["student_id"]}, {"id": "other-student"}]
    )
    assert disposition == "BLOCKED"
    assert "CURRENT_NUMBER_USED_BY_OTHER_STUDENT" in blockers


def test_blocks_if_student_number_is_used_by_foreign_enrollment():
    disposition, blockers = assess(
        same_student_number_enrollments=[{"id": "other-enrollment", "student_id": "other-student"}]
    )
    assert disposition == "BLOCKED"
    assert "CURRENT_NUMBER_USED_BY_OTHER_ENROLLMENT" in blockers


def test_blocks_if_origin_status_has_changed():
    c = case()
    changed_origin = origin(c)
    changed_origin["status"] = "active"
    disposition, blockers = assess(origin=changed_origin)
    assert disposition == "BLOCKED"
    assert "ORIGIN_STATUS_CHANGED" in blockers


def test_blocks_if_other_active_regular_enrollment_exists():
    disposition, blockers = assess(
        other_active_regular=[{"id": "unexpected-active-regular"}]
    )
    assert disposition == "BLOCKED"
    assert "OTHER_ACTIVE_REGULAR_ENROLLMENT_EXISTS" in blockers


def test_blocks_if_destination_is_special():
    c = case()
    special = cls(c["destination_class_id"], c["school_id"])
    special["atendimento_programa"] = "aee"
    disposition, blockers = assess(destination_class=special)
    assert disposition == "BLOCKED"
    assert "DESTINATION_CLASS_SPECIAL" in blockers


def test_blocks_if_destination_number_has_changed():
    c = case()
    changed = destination_ready(c)
    changed["enrollment_number"] = "999999999"
    disposition, blockers = assess(destination=changed)
    assert disposition == "BLOCKED"
    assert "DESTINATION_NUMBER_CHANGED" in blockers


def test_blocks_if_any_tenant_is_missing():
    c = case()
    destination_class = cls(c["destination_class_id"], c["school_id"])
    destination_class["mantenedora_id"] = None
    disposition, blockers = assess(destination_class=destination_class)
    assert disposition == "BLOCKED"
    assert "TENANT_MISMATCH_OR_MISSING" in blockers


def test_historical_school_membership_accepts_interval_covering_movement():
    c = dict(CASES[1])
    origin_class = cls(c["origin_class_id"], "school-current-after-transfer")
    origin_class["school_history"] = [
        {
            "school_id": c["school_id"],
            "start_date": "2026-03-19T14:04:43.538906+00:00",
            "end_date": "2026-08-05T11:50:09.114042+00:00",
        },
        {
            "school_id": "school-current-after-transfer",
            "start_date": "2026-08-05T11:50:09.114042+00:00",
            "end_date": None,
        },
    ]
    assert class_belongs_to_school_at(
        origin_class,
        c["school_id"],
        MOVEMENT_AT_BY_STUDENT[c["student_id"]],
    )


def test_historical_school_membership_rejects_interval_not_covering_movement():
    c = dict(CASES[1])
    origin_class = cls(c["origin_class_id"], "school-current-after-transfer")
    origin_class["school_history"] = [
        {
            "school_id": c["school_id"],
            "start_date": "2026-06-02T00:00:00+00:00",
            "end_date": "2026-08-05T11:50:09.114042+00:00",
        }
    ]
    assert not class_belongs_to_school_at(
        origin_class,
        c["school_id"],
        MOVEMENT_AT_BY_STUDENT[c["student_id"]],
    )


def _assess_ana_historical(origin_school_history):
    c = dict(CASES[1])
    origin_class = cls(c["origin_class_id"], "7883abfb-035c-464a-bf49-a24e0068f260")
    origin_class["school_history"] = origin_school_history
    return assess_snapshot_historical(
        case=c,
        student=student(c),
        destination=destination_ready(c),
        origin=origin(c),
        destination_class=cls(c["destination_class_id"], c["school_id"]),
        origin_class=origin_class,
        same_student_number_students=[{"id": c["student_id"]}],
        same_student_number_enrollments=[],
        same_legacy_number_enrollments=[
            {"id": c["destination_enrollment_id"], "student_id": c["student_id"]}
        ],
        other_active_regular=[],
    )


def test_ana_snapshot_ready_when_school_history_proves_origin_at_movement():
    c = dict(CASES[1])
    disposition, blockers = _assess_ana_historical(
        [
            {
                "school_id": c["school_id"],
                "start_date": "2026-03-19T14:04:43.538906+00:00",
                "end_date": "2026-08-05T11:50:09.114042+00:00",
            },
            {
                "school_id": "7883abfb-035c-464a-bf49-a24e0068f260",
                "start_date": "2026-08-05T11:50:09.114042+00:00",
                "end_date": None,
            },
        ]
    )
    assert disposition == "READY"
    assert blockers == []


def test_ana_snapshot_stays_blocked_without_temporal_school_proof():
    disposition, blockers = _assess_ana_historical([])
    assert disposition == "BLOCKED"
    assert "ORIGIN_CLASS_SCHOOL_MISMATCH" in blockers
