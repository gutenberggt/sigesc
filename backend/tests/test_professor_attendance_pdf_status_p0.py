"""Regressão P0 — PDF de frequência do professor não pode perder P/F/J."""

from pdf_status_compat import (
    normalize_attendance_status_for_pdf,
    normalize_students_attendance_for_pdf,
)


def test_normalize_legacy_attendance_statuses_for_pdf():
    assert normalize_attendance_status_for_pdf("P") == "present"
    assert normalize_attendance_status_for_pdf("F") == "absent"
    assert normalize_attendance_status_for_pdf("J") == "justified"


def test_canonical_attendance_statuses_remain_unchanged():
    assert normalize_attendance_status_for_pdf("present") == "present"
    assert normalize_attendance_status_for_pdf("absent") == "absent"
    assert normalize_attendance_status_for_pdf("justified") == "justified"


def test_students_payload_is_normalized_without_mutating_source():
    source = [{
        "name": "Estudante Teste",
        "attendance_by_date": {
            "2026-02-09": "P",
            "2026-02-10": "F",
            "2026-02-11": "J",
            "2026-02-12": "present",
        },
        "attendance_classes_by_date": {
            "2026-02-09": 1,
            "2026-02-10": 1,
            "2026-02-11": 1,
            "2026-02-12": 1,
        },
    }]

    result = normalize_students_attendance_for_pdf(source)

    assert result[0]["attendance_by_date"] == {
        "2026-02-09": "present",
        "2026-02-10": "absent",
        "2026-02-11": "justified",
        "2026-02-12": "present",
    }
    assert source[0]["attendance_by_date"]["2026-02-09"] == "P"
    assert result is not source
    assert result[0] is not source[0]
