"""SIE — Motor de Alertas. Função PURA.

Gera alertas acionáveis a partir do diagnóstico/risco já calculado. A coleção
`student_alerts` materializa esses sinais para alimentar notificações SEM
recalcular todo o pipeline.

Severidades: low | medium | high | critical (alinhadas ao restante do sistema).
"""
from __future__ import annotations

from typing import Any, Dict, List

from services.overall_risk_engine import classify_risk


def build_alerts(student: Dict[str, Any], academic: Dict[str, Any],
                 attendance: Dict[str, Any], overall: Dict[str, Any],
                 config: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    def mk(alert_type: str, severity: str, message: str) -> Dict[str, Any]:
        return {'alert_type': alert_type, 'severity': severity, 'message': message}

    # 1. Queda de frequência (sinal precoce de evasão)
    att_level = classify_risk(attendance['score'], config)
    if att_level in ('high', 'critical'):
        ap = attendance.get('attendance_pct')
        alerts.append(mk('attendance_drop', att_level,
                         f"Frequência em risco ({ap if ap is not None else '—'}%)"))

    # 2. Declínio acadêmico (tendência de queda)
    if academic.get('trend_status') == 'falling' and classify_risk(academic['score'], config) in ('moderate', 'high', 'critical'):
        sev = 'high' if academic['score'] >= 50 else 'medium'
        alerts.append(mk('academic_decline', sev, 'Queda contínua de desempenho'))

    # 3. Múltiplas recuperações
    rec = int(academic.get('recovery_subjects', 0) or 0)
    if rec >= 2:
        alerts.append(mk('multiple_recoveries', 'high' if rec >= 3 else 'medium', f"{rec} recuperações"))

    # 4. Reprovação
    fail = int(academic.get('failed_subjects', 0) or 0)
    if fail >= 1:
        alerts.append(mk('failing', 'critical' if fail >= 2 else 'high', f"{fail} componente(s) reprovado(s)"))

    # 5. Risco geral crítico
    if overall['risk_level'] == 'critical':
        alerts.append(mk('critical_overall', 'critical', f"Risco geral crítico ({overall['overall_risk']})"))

    return alerts
