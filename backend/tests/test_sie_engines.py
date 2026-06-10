"""Testes unitários dos motores PUROS do SIE (FASE 0).

Determinísticos, sem banco. Validam fórmula, faixas e explicabilidade.
Rodar: cd /app/backend && python3 -m pytest tests/test_sie_engines.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sie_service import merge_defaults, DEFAULT_SIE_CONFIG  # noqa: E402
from services.academic_risk_engine import compute_academic_risk  # noqa: E402
from services.attendance_risk_engine import compute_attendance_risk  # noqa: E402
from services.overall_risk_engine import compute_overall_risk, classify_risk  # noqa: E402
from services.diagnostic_engine import build_diagnostic  # noqa: E402
from services.alert_engine import build_alerts  # noqa: E402

CFG = merge_defaults(None)


def test_classify_bands():
    assert classify_risk(0, CFG) == 'low'
    assert classify_risk(24, CFG) == 'low'
    assert classify_risk(25, CFG) == 'moderate'
    assert classify_risk(49, CFG) == 'moderate'
    assert classify_risk(50, CFG) == 'high'
    assert classify_risk(74, CFG) == 'high'
    assert classify_risk(75, CFG) == 'critical'
    assert classify_risk(100, CFG) == 'critical'


def test_academic_good_student_zero_risk():
    grades = [{'b1': 9, 'b2': 9, 'b3': 9, 'b4': 9, 'final_average': 9.0, 'status': 'aprovado'}]
    r = compute_academic_risk(grades, CFG)
    assert r['score'] == 0.0
    assert r['average_grade'] == 9.0
    assert r['critical_components'] == 0
    assert r['recovery_subjects'] == 0
    assert r['failed_subjects'] == 0


def test_academic_falling_trend_detected():
    grades = [{'b1': 8.0, 'b2': 7.5, 'b3': 7.0, 'b4': 6.5, 'final_average': 7.25, 'status': 'aprovado'}]
    r = compute_academic_risk(grades, CFG)
    assert r['trend_status'] == 'falling'
    # delta = 6.5 - 8.0 = -1.5 → trend_frac = 1.5/3 = 0.5 → contrib 5.0
    trend = next(b for b in r['breakdown'] if b['factor'] == 'tendencia')
    assert trend['contribution'] == 5.0


def test_academic_failing_and_recovery_raise_risk():
    grades = [
        {'b1': 3, 'b2': 4, 'b3': 3, 'b4': 2, 'final_average': 3.0, 'status': 'reprovado'},
        {'b1': 5, 'b2': 5, 'b3': 5, 'b4': 5, 'final_average': 5.0, 'status': 'recuperacao'},
    ]
    r = compute_academic_risk(grades, CFG)
    assert r['failed_subjects'] == 1
    assert r['recovery_subjects'] == 1
    assert r['critical_components'] == 2  # both below 6
    assert r['score'] > 30  # 16.7(notas)+6.7(rec)+10(rep)+1.7(trend) ≈ 35


def test_attendance_high_presence_low_risk():
    r = compute_attendance_risk({'total': 100, 'present': 95, 'recent_total': 10, 'recent_present': 10}, CFG)
    assert r['attendance_pct'] == 95.0
    assert r['score'] == 0.0


def test_attendance_below_min_raises_risk():
    # 50% presença anual (min 75) → annual_frac=(75-50)/75=0.333 → 70*0.333=23.3
    # faltas recentes 100% → recent_frac=min(1/0.5,1)=1 → 30 → score≈53.3
    r = compute_attendance_risk({'total': 100, 'present': 50, 'recent_total': 10, 'recent_present': 0}, CFG)
    assert r['attendance_pct'] == 50.0
    assert r['score'] > 50
    assert classify_risk(r['score'], CFG) in ('high', 'critical')


def test_overall_weights_and_factors():
    ov = compute_overall_risk(80.0, 40.0, CFG)
    # 0.55*80 + 0.45*40 = 44 + 18 = 62 → high
    assert ov['overall_risk'] == 62.0
    assert ov['risk_level'] == 'high'
    assert len(ov['factors']) == 2
    ac = next(f for f in ov['factors'] if f['factor'] == 'academic')
    assert ac['contribution'] == 44.0


def test_diagnostic_is_structured():
    grades = [{'b1': 8.0, 'b2': 6.0, 'b3': 5.0, 'b4': 4.0, 'final_average': 5.75, 'status': 'recuperacao'}]
    ac = compute_academic_risk(grades, CFG)
    at = compute_attendance_risk({'total': 100, 'present': 70, 'recent_total': 10, 'recent_present': 6}, CFG)
    ov = compute_overall_risk(ac['score'], at['score'], CFG)
    diag = build_diagnostic({'id': 'x'}, ac, at, ov, CFG)
    assert diag['trend_status'] == 'falling'
    assert diag['overall_status'] in ('low', 'moderate', 'high', 'critical')
    assert isinstance(diag['risk_factors'], list)
    assert 'Queda contínua de desempenho' in diag['risk_factors']
    assert diag['attendance_pct'] == 70.0


def test_alerts_generated_for_risky_student():
    grades = [
        {'b1': 3, 'b2': 3, 'b3': 2, 'b4': 2, 'final_average': 2.5, 'status': 'reprovado'},
        {'b1': 5, 'b2': 4, 'b3': 4, 'b4': 3, 'final_average': 4.0, 'status': 'reprovado'},
    ]
    ac = compute_academic_risk(grades, CFG)
    at = compute_attendance_risk({'total': 100, 'present': 40, 'recent_total': 10, 'recent_present': 2}, CFG)
    ov = compute_overall_risk(ac['score'], at['score'], CFG)
    alerts = build_alerts({'id': 'x'}, ac, at, ov, CFG)
    types = {a['alert_type'] for a in alerts}
    assert 'failing' in types
    assert 'attendance_drop' in types


def test_merge_defaults_preserves_overrides():
    cfg = merge_defaults({'passing_grade': 7.0, 'overall_weights': {'academic': 60}})
    assert cfg['passing_grade'] == 7.0
    assert cfg['overall_weights']['academic'] == 60
    # chave aninhada faltante herda default
    assert cfg['overall_weights']['attendance'] == DEFAULT_SIE_CONFIG['overall_weights']['attendance']
    assert cfg['risk_bands']['high_max'] == 74


def test_no_data_is_not_penalized():
    ac = compute_academic_risk([], CFG)
    at = compute_attendance_risk({'total': 0, 'present': 0, 'recent_total': 0, 'recent_present': 0}, CFG)
    assert ac['score'] == 0.0
    assert at['score'] == 0.0
    assert ac['has_grade_data'] is False
    assert at['has_attendance_data'] is False
