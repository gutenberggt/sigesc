"""SIE — Motor de Diagnóstico ESTRUTURADO. Função PURA.

Regra de ouro: a coleção `student_diagnostics` guarda ESTRUTURA, não texto.
O texto (`risk_factors`) é CONSEQUÊNCIA dos campos estruturados — nunca o contrário.
Assim o assistente de IA (fase futura) consome inteligência estruturada e confiável.
"""
from __future__ import annotations

from typing import Any, Dict

from services.overall_risk_engine import classify_risk


def build_diagnostic(student: Dict[str, Any], academic: Dict[str, Any],
                     attendance: Dict[str, Any], overall: Dict[str, Any],
                     config: Dict[str, Any]) -> Dict[str, Any]:
    passing = float(config.get('passing_grade', 6.0))
    min_pct = float(config.get('attendance_min_pct', 75))

    academic_status = classify_risk(academic['score'], config)
    attendance_status = classify_risk(attendance['score'], config)
    trend_status = academic.get('trend_status', 'stable')

    # Fatores legíveis (CONSEQUÊNCIA da estrutura)
    risk_factors = []
    if trend_status == 'falling':
        risk_factors.append('Queda contínua de desempenho')
    ap = attendance.get('attendance_pct')
    if ap is not None and ap < min_pct:
        risk_factors.append(f'Frequência abaixo de {min_pct:.0f}% ({ap:.0f}%)')
    rec = int(academic.get('recovery_subjects', 0) or 0)
    if rec > 0:
        risk_factors.append(f"{rec} recuperaç{'ão' if rec == 1 else 'ões'}")
    fail = int(academic.get('failed_subjects', 0) or 0)
    if fail > 0:
        risk_factors.append(f"{fail} componente(s) reprovado(s)")
    ag = academic.get('average_grade')
    if ag is not None and ag < passing:
        risk_factors.append('Média abaixo do esperado')

    return {
        'academic_status': academic_status,
        'attendance_status': attendance_status,
        'trend_status': trend_status,
        'overall_status': overall['risk_level'],
        'recovery_subjects': rec,
        'failed_subjects': fail,
        'critical_components': int(academic.get('critical_components', 0) or 0),
        'average_grade': ag,
        'attendance_pct': ap,
        'risk_factors': risk_factors,
        'has_data': bool(academic.get('has_grade_data') or attendance.get('has_attendance_data')),
    }
