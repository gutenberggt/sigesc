from scripts.audit_enrollment_orphans_forensic import (
    escaped,
    has_control_chars,
    is_uuid_like,
    orphan_kind,
)


def test_orphan_kind_is_exact():
    assert orphan_kind(student_exists=False, class_exists=False) == "BOTH_MISSING"
    assert orphan_kind(student_exists=True, class_exists=False) == "MISSING_CLASS_ONLY"
    assert orphan_kind(student_exists=False, class_exists=True) == "MISSING_STUDENT_ONLY"
    assert orphan_kind(student_exists=True, class_exists=True) == "NOT_ORPHAN"


def test_uuid_detection_accepts_canonical_uuid():
    assert is_uuid_like("123e4567-e89b-12d3-a456-426614174000") is True


def test_malformed_id_control_chars_are_visible_and_detected():
    value = "abc\x0bdef\nxyz"
    assert has_control_chars(value) is True
    assert is_uuid_like(value) is False
    assert "\\u000b" in escaped(value)
    assert "\\n" in escaped(value)


def test_normal_uuid_has_no_control_chars():
    value = "123e4567-e89b-12d3-a456-426614174000"
    assert has_control_chars(value) is False
