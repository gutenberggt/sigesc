import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_enrollment_orphans_forensic_phase_d.py"
spec = importlib.util.spec_from_file_location("phase_d", MODULE_PATH)
phase_d = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(phase_d)


def test_norm_cpf_keeps_only_digits():
    assert phase_d.norm_cpf("123.456.789-01") == "12345678901"


def test_cpf_shape_valid_requires_11_non_repeated_digits():
    assert phase_d.cpf_shape_valid("123.456.789-01") is True
    assert phase_d.cpf_shape_valid("111.111.111-11") is False
    assert phase_d.cpf_shape_valid("123") is False


def test_identity_disposition_verified_cpf_and_name():
    assert phase_d.identity_disposition(
        1,
        1,
        unique_cpf_name_match=True,
    ) == "VERIFIED_CPF_AND_NAME"


def test_identity_disposition_verified_cpf_name_changed():
    assert phase_d.identity_disposition(
        1,
        0,
        unique_cpf_name_match=False,
    ) == "VERIFIED_CPF_NAME_CHANGED"


def test_identity_disposition_detects_cpf_collision():
    assert phase_d.identity_disposition(2, 1) == "AMBIGUOUS_CPF_COLLISION"


def test_identity_disposition_name_only_is_not_verified():
    assert phase_d.identity_disposition(0, 1) == "NAME_ONLY_UNVERIFIED"


def test_identity_disposition_none():
    assert phase_d.identity_disposition(0, 0) == "NO_CURRENT_MATCH"


def test_safe_student_never_exposes_cpf_or_identity_sensitive_fields():
    source = {
        "id": "student-1",
        "full_name": "Pessoa Teste",
        "cpf": "123.456.789-01",
        "birth_date": "2018-01-01",
        "mother_name": "Responsável",
        "inep_code": "123456789012",
        "status": "active",
        "enrollment_number": "202600001",
    }
    safe = phase_d._safe_student(source)
    assert safe["id"] == "student-1"
    assert safe["full_name"] == "Pessoa Teste"
    assert "cpf" not in safe
    assert "birth_date" not in safe
    assert "mother_name" not in safe
    assert "inep_code" not in safe


def test_safe_delete_event_drops_description_and_old_value():
    event = {
        "action": "delete",
        "timestamp": "2026-04-01T10:00:00+00:00",
        "user_email": "admin@example.com",
        "description": "EXCLUIU estudante (CPF: 123.456.789-01)",
        "old_value": {"cpf": "123.456.789-01", "full_name": "Pessoa Teste"},
    }
    safe = phase_d._safe_delete_event(event)
    assert safe == {
        "action": "delete",
        "timestamp": "2026-04-01T10:00:00+00:00",
        "user_email": "admin@example.com",
    }


def test_privacy_guard_detects_raw_sensitive_keys_recursively():
    assert phase_d._contains_raw_sensitive_key({"candidate": {"cpf": "123"}}) is True
    assert phase_d._contains_raw_sensitive_key({"cpf_exact_match": True}) is False
    assert phase_d._contains_raw_sensitive_key({"historical_cpf_present": True}) is False


def test_days_between_handles_same_day_and_negative_values():
    assert phase_d.days_between(
        "2026-04-01T10:00:00+00:00",
        "2026-04-01T12:00:00+00:00",
    ) == 0
    assert phase_d.days_between(
        "2026-04-02T10:00:00+00:00",
        "2026-04-01T10:00:00+00:00",
    ) == -1
