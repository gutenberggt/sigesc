from pathlib import Path

from services.curriculum_coverage_alerts_s5 import (
    ACTIVE_TARGET_ROLES,
    classify_coverage_alert,
)


def _days(n=50):
    return [f"2026-08-{i:02d}" for i in range(1, min(n, 31) + 1)] + [
        f"2026-09-{i:02d}" for i in range(1, max(0, n - 31) + 1)
    ]


def test_first_15_instructional_days_are_tolerance_even_at_50_or_less():
    days = _days(45)
    decision = classify_coverage_alert(
        pct=12.0,
        percentage_available=True,
        bimestre_state="em_andamento",
        today_ymd=days[14],
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is False
    assert decision.policy_state == "janela_inicial_tolerancia"
    assert decision.instructional_days_elapsed == 15


def test_after_day_15_any_coverage_below_70_alerts():
    days = _days(50)
    decision = classify_coverage_alert(
        pct=69.9,
        percentage_available=True,
        bimestre_state="em_andamento",
        today_ymd=days[15],
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is True
    assert decision.severity == "informativo"
    assert decision.instructional_days_elapsed == 16


def test_70_percent_is_not_alert():
    days = _days(50)
    decision = classify_coverage_alert(
        pct=70.0,
        percentage_available=True,
        bimestre_state="em_andamento",
        today_ymd=days[20],
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is False
    assert decision.policy_state == "cobertura_adequada"


def test_last_15_instructional_days_at_50_or_less_is_grave():
    days = _days(50)
    today = days[-15]
    decision = classify_coverage_alert(
        pct=50.0,
        percentage_available=True,
        bimestre_state="em_andamento",
        today_ymd=today,
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is True
    assert decision.severity == "grave"
    assert decision.instructional_days_remaining == 15


def test_last_15_above_50_but_below_70_is_informational():
    days = _days(50)
    decision = classify_coverage_alert(
        pct=50.1,
        percentage_available=True,
        bimestre_state="em_andamento",
        today_ymd=days[-15],
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is True
    assert decision.severity == "informativo"


def test_no_f5_percentage_never_becomes_zero_alert():
    days = _days(50)
    decision = classify_coverage_alert(
        pct=None,
        percentage_available=False,
        bimestre_state="em_andamento",
        today_ymd=days[20],
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert decision.active is False
    assert decision.coverage_pct is None
    assert decision.policy_state == "percentual_indisponivel"


def test_future_and_closed_periods_do_not_create_active_delay_alerts():
    days = _days(50)
    future = classify_coverage_alert(
        pct=10,
        percentage_available=True,
        bimestre_state="futuro",
        today_ymd="2026-07-01",
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    closed = classify_coverage_alert(
        pct=10,
        percentage_available=True,
        bimestre_state="fechado",
        today_ymd="2026-10-01",
        period_start=days[0],
        period_end=days[-1],
        instructional_days=days,
    )
    assert future.active is False
    assert closed.active is False
    assert future.policy_state == "periodo_futuro"
    assert closed.policy_state == "bimestre_encerrado"


def test_active_audience_contract_excludes_super_admin():
    assert {"admin", "gerente", "semed", "semed3", "coordenador"} <= ACTIVE_TARGET_ROLES
    assert "super_admin" not in ACTIVE_TARGET_ROLES


def test_detector_no_longer_reads_learning_objects_or_owns_thresholds():
    root = Path(__file__).resolve().parents[1]
    detector = (root / "services" / "intervention_detector.py").read_text(encoding="utf-8")
    assert "learning_objects" not in detector
    assert "0.9" not in detector
    assert "run_curriculum_coverage_alert_detection" in detector


def test_s5_engine_reuses_f5_calculator_instead_of_reimplementing_coverage():
    root = Path(__file__).resolve().parents[1]
    engine = (root / "services" / "curriculum_coverage_alerts_s5.py").read_text(encoding="utf-8")
    assert "calculate_curriculum_coverage_v2" in engine
    assert "coverage_source\": \"curriculum_coverage_v2" in engine
    # learning_objects pode existir dentro do próprio F5 como contagem histórica,
    # mas o motor S5.5 não deve consultá-lo diretamente.
    assert ".learning_objects" not in engine
