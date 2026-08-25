import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_enrollment_orphans_forensic_phase_c.py"
spec = importlib.util.spec_from_file_location("phase_c", MODULE_PATH)
phase_c = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(phase_c)


def test_norm_text_removes_accents_and_collapses_spaces():
    assert phase_c.norm_text("  Cecília   Cirqueira Aguiar ") == "CECILIA CIRQUEIRA AGUIAR"


def test_strong_identity_match_name_birth_and_mother():
    old = {
        "full_name": "ANA MARIA DA SILVA",
        "birth_date": "10/05/2018",
        "mother_name": "JOANA DA SILVA",
        "father_name": "",
        "sex": "feminino",
        "inep_code": "",
    }
    current = {
        "full_name": "Ana Maria da Silva",
        "birth_date": "10/05/2018",
        "mother_name": "Joana da Silva",
        "sex": "feminino",
    }
    score, confidence, flags = phase_c.score_identity(old, current)
    assert confidence == "STRONG"
    assert score >= 14
    assert flags["full_name"] is True
    assert flags["birth_date"] is True
    assert flags["mother_name"] is True


def test_probable_identity_match_name_and_birth():
    old = {
        "full_name": "JOAO TESTE",
        "birth_date": "01/01/2017",
        "mother_name": "",
        "father_name": "",
        "sex": "masculino",
        "inep_code": "",
    }
    current = {
        "full_name": "João Teste",
        "birth_date": "01/01/2017",
        "sex": "masculino",
    }
    _, confidence, _ = phase_c.score_identity(old, current)
    assert confidence == "PROBABLE"


def test_weak_name_only_never_becomes_probable():
    old = {
        "full_name": "MARIA TESTE",
        "birth_date": "01/01/2016",
        "mother_name": "MAE ANTIGA",
        "father_name": "",
        "sex": "feminino",
        "inep_code": "",
    }
    current = {
        "full_name": "Maria Teste",
        "birth_date": "02/02/2016",
        "mother_name": "OUTRA MAE",
        "sex": "feminino",
    }
    _, confidence, flags = phase_c.score_identity(old, current)
    assert confidence == "WEAK"
    assert flags["full_name"] is True
    assert flags["birth_date"] is False


def test_inep_plus_name_is_strong_without_exposing_inep_in_safe_subset():
    old = {
        "full_name": "ALUNO TESTE",
        "birth_date": "",
        "mother_name": "",
        "father_name": "",
        "sex": "masculino",
        "inep_code": "123456789012",
    }
    current = {
        "id": "student-current",
        "full_name": "Aluno Teste",
        "inep_code": "123456789012",
        "birth_date": "",
        "mother_name": "",
        "father_name": "",
        "sex": "masculino",
        "enrollment_number": "202600001",
    }
    _, confidence, flags = phase_c.score_identity(old, current)
    safe = phase_c._safe_subset(current)
    assert confidence == "STRONG"
    assert flags["inep_code"] is True
    assert "inep_code" not in safe
    assert "birth_date" not in safe
    assert "mother_name" not in safe


def test_days_between_supports_utc_and_naive_iso():
    assert phase_c._days_between(
        "2026-04-01T10:00:00+00:00",
        "2026-04-03T10:00:00",
    ) == 2


def test_safe_audit_event_filters_sensitive_or_identity_changes():
    event = {
        "action": "update",
        "timestamp": "2026-04-01T10:00:00+00:00",
        "user_email": "admin@example.com",
        "changes": {
            "status": {"old": "active", "new": "inactive"},
            "class_id": {"old": "A", "new": None},
            "birth_date": {"old": "01/01/2018", "new": "02/02/2018"},
            "mother_name": {"old": "X", "new": "Y"},
        },
    }
    safe = phase_c._safe_audit_event(event)
    assert "status" in safe["changes"]
    assert "class_id" in safe["changes"]
    assert "birth_date" not in safe["changes"]
    assert "mother_name" not in safe["changes"]
