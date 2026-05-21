"""Fase 2 (Fev/2026) — Suggestion Engine determinística para BF.

Valida regras explícitas em `services/bf_reason_suggestion.py`:
  - R1) ≥50% das ausências do mês têm atestado médico → sugerir `1a`.
  - R2) (reservado — Layer 2 futura)
  - R3) reason atual com severity_level ≥ 5 → requires_followup_flag = True.

Critérios:
  - Determinística: mesma entrada → mesma saída.
  - Auditável: rules_triggered + human_explanation sempre preenchidos.
  - Conservadora: sem ausências observadas → sem sugestão.
"""
from services.bf_reason_suggestion import (
    SUGGESTION_ENGINE_VERSION,
    PROPORTION_THRESHOLD,
    SEVERITY_FOLLOWUP_THRESHOLD,
    suggest_reason_for_month,
)


REASONS_FIXTURE = {
    "1a": {
        "id": "reason-1a-uuid",
        "mec_subcode": "1a",
        "name": "Doença/problemas físicos",
        "severity_level": 2,
        "requires_followup": False,
    },
    "3b": {
        "id": "reason-3b-uuid",
        "mec_subcode": "3b",
        "name": "Falta de transporte escolar",
        "severity_level": 3,
        "requires_followup": True,
    },
    "11a": {
        "id": "reason-11a-uuid",
        "mec_subcode": "11a",
        "name": "Violência no ambiente escolar",
        "severity_level": 5,
        "requires_followup": True,
    },
    "9a": {
        "id": "reason-9a-uuid",
        "mec_subcode": "9a",
        "name": "Situação de rua",
        "severity_level": 5,
        "requires_followup": True,
    },
}


# ============================================================================
# R1 — Atestados médicos
# ============================================================================

def test_r1_triggers_when_all_absences_are_medical():
    """100% das ausências são atestado → sugere 1a com confidence 1.0."""
    out = suggest_reason_for_month(
        medical_days_count=8,
        valid_absences=0,
        school_days=20,
        frequency_percentage=100.0,
        reasons_by_subcode=REASONS_FIXTURE,
    )
    assert out["suggested_reason_id"] == "reason-1a-uuid"
    assert out["suggested_reason_subcode"] == "1a"
    assert out["confidence"] == 1.0
    assert out["should_show_suggestion"] is True
    codes = [r["code"] for r in out["rules_triggered"]]
    assert "R1_MEDICAL_DAYS_GTE_50PCT" in codes
    assert "atestado médico" in out["human_explanation"].lower()


def test_r1_triggers_at_exactly_50pct():
    """Threshold é INCLUSIVO em 50% (≥ não >). 5 atestados + 5 faltas válidas."""
    out = suggest_reason_for_month(
        medical_days_count=5,
        valid_absences=5,
        school_days=20,
        frequency_percentage=75.0,
        reasons_by_subcode=REASONS_FIXTURE,
    )
    assert out["suggested_reason_id"] == "reason-1a-uuid"
    assert out["confidence"] == 0.5


def test_r1_does_not_trigger_below_50pct():
    """2 atestados em 8 ausências = 25% → não sugere."""
    out = suggest_reason_for_month(
        medical_days_count=2,
        valid_absences=6,
        school_days=20,
        frequency_percentage=70.0,
        reasons_by_subcode=REASONS_FIXTURE,
    )
    assert out["suggested_reason_id"] is None
    assert out["confidence"] == 0.0
    assert out["rules_triggered"] == []


def test_r1_does_not_trigger_when_no_absences_observed():
    """0 ausências (presença total) → sem sugestão mesmo sem freq calculada."""
    out = suggest_reason_for_month(
        medical_days_count=0,
        valid_absences=0,
        school_days=20,
        frequency_percentage=100.0,
        reasons_by_subcode=REASONS_FIXTURE,
    )
    assert out["suggested_reason_id"] is None
    assert out["should_show_suggestion"] is False


def test_r1_handles_missing_1a_in_reasons():
    """Se reason 1a não está no índice, engine não estoura mas retorna None."""
    fixture_sem_1a = {k: v for k, v in REASONS_FIXTURE.items() if k != "1a"}
    out = suggest_reason_for_month(
        medical_days_count=10,
        valid_absences=0,
        school_days=20,
        reasons_by_subcode=fixture_sem_1a,
    )
    assert out["suggested_reason_id"] is None


# ============================================================================
# R3 — Severidade alta (followup flag)
# ============================================================================

def test_r3_triggers_when_current_reason_has_high_severity():
    """reason atual = 11a (severity 5) → requires_followup_flag=True."""
    out = suggest_reason_for_month(
        medical_days_count=0,
        valid_absences=3,
        school_days=20,
        reasons_by_subcode=REASONS_FIXTURE,
        current_reason=REASONS_FIXTURE["11a"],
    )
    assert out["requires_followup_flag"] is True
    codes = [r["code"] for r in out["rules_triggered"]]
    assert "R3_HIGH_SEVERITY" in codes
    assert "busca ativa" in out["human_explanation"].lower()


def test_r3_does_not_trigger_for_low_severity_reason():
    """reason atual = 1a (severity 2) → requires_followup_flag=False."""
    out = suggest_reason_for_month(
        medical_days_count=0,
        valid_absences=3,
        school_days=20,
        reasons_by_subcode=REASONS_FIXTURE,
        current_reason=REASONS_FIXTURE["1a"],
    )
    assert out["requires_followup_flag"] is False


def test_r3_does_not_trigger_without_current_reason():
    """Sem reason atual selecionado → sem flag de followup."""
    out = suggest_reason_for_month(
        medical_days_count=0,
        valid_absences=3,
        school_days=20,
        reasons_by_subcode=REASONS_FIXTURE,
        current_reason=None,
    )
    assert out["requires_followup_flag"] is False


# ============================================================================
# Combinação R1 + R3
# ============================================================================

def test_r1_and_r3_can_trigger_together():
    """R1 e R3 são independentes — podem disparar simultaneamente."""
    out = suggest_reason_for_month(
        medical_days_count=8,
        valid_absences=0,
        school_days=20,
        reasons_by_subcode=REASONS_FIXTURE,
        current_reason=REASONS_FIXTURE["9a"],  # severity 5
    )
    codes = [r["code"] for r in out["rules_triggered"]]
    assert "R1_MEDICAL_DAYS_GTE_50PCT" in codes
    assert "R3_HIGH_SEVERITY" in codes
    assert out["suggested_reason_id"] == "reason-1a-uuid"
    assert out["requires_followup_flag"] is True


def test_should_show_suggestion_false_when_already_selected():
    """Não devemos pedir ao operador que selecione o que já está selecionado."""
    out = suggest_reason_for_month(
        medical_days_count=8,
        valid_absences=0,
        school_days=20,
        reasons_by_subcode=REASONS_FIXTURE,
        current_reason=REASONS_FIXTURE["1a"],
    )
    # R1 dispara mas a sugestão já está aplicada
    assert out["suggested_reason_id"] == "reason-1a-uuid"
    assert out["should_show_suggestion"] is False


# ============================================================================
# Determinismo / Contract
# ============================================================================

def test_engine_is_deterministic():
    """Mesma entrada → mesma saída exata."""
    params = {
        "medical_days_count": 6,
        "valid_absences": 2,
        "school_days": 20,
        "frequency_percentage": 80.0,
        "reasons_by_subcode": REASONS_FIXTURE,
    }
    a = suggest_reason_for_month(**params)
    b = suggest_reason_for_month(**params)
    assert a == b


def test_response_contract_shape():
    """Verifica todas as chaves do contrato V1.0."""
    out = suggest_reason_for_month(
        medical_days_count=0,
        valid_absences=0,
        school_days=0,
        reasons_by_subcode={},
    )
    required_keys = {
        "engine_version",
        "suggested_reason_id",
        "suggested_reason_subcode",
        "confidence",
        "rules_triggered",
        "requires_followup_flag",
        "human_explanation",
        "should_show_suggestion",
    }
    assert required_keys.issubset(out.keys())
    assert out["engine_version"] == SUGGESTION_ENGINE_VERSION
    assert isinstance(out["rules_triggered"], list)


def test_constants_are_locked():
    """Garante que os thresholds não foram acidentalmente alterados."""
    assert PROPORTION_THRESHOLD == 0.50
    assert SEVERITY_FOLLOWUP_THRESHOLD == 5
    assert SUGGESTION_ENGINE_VERSION == "1.0"
