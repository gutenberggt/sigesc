"""SIE — Motor de Risco de Frequência (0–100). Função PURA, sem I/O.

Composição (pesos default, configuráveis via `sie_config.attendance_weights`):
  presenca_anual  70  → quão abaixo da frequência mínima está o aluno no ano
  faltas_recentes 30  → taxa de faltas na janela recente (sinal precoce de evasão)

Maior score = maior risco. Recebe um SUMÁRIO já agregado (sem acesso a banco):
  {total, present, recent_total, recent_present}
"""
from __future__ import annotations

from typing import Any, Dict


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_attendance_risk(summary: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    min_pct = float(config.get('attendance_min_pct', 75))
    aw = config.get('attendance_weights', {}) or {}
    w_annual = float(aw.get('presenca_anual', 70))
    w_recent = float(aw.get('faltas_recentes', 30))
    caps = config.get('caps', {}) or {}
    recent_abs_max = float(caps.get('recent_absence_max', 0.5)) or 0.5

    total = int(summary.get('total', 0) or 0)
    present = int(summary.get('present', 0) or 0)
    recent_total = int(summary.get('recent_total', 0) or 0)
    recent_present = int(summary.get('recent_present', 0) or 0)

    if total > 0:
        attendance_pct = round(100.0 * present / total, 1)
        has_attendance_data = True
    else:
        attendance_pct = None
        has_attendance_data = False

    # 1. Presença anual — risco cresce conforme cai abaixo do mínimo
    if attendance_pct is None:
        annual_frac = 0.0
    else:
        annual_frac = _clamp((min_pct - attendance_pct) / min_pct) if min_pct > 0 else 0.0

    # 2. Faltas recentes
    if recent_total > 0:
        recent_absence_rate = (recent_total - recent_present) / recent_total
    else:
        recent_absence_rate = 0.0
    recent_frac = _clamp(recent_absence_rate / recent_abs_max)

    contrib_annual = round(w_annual * annual_frac, 2)
    contrib_recent = round(w_recent * recent_frac, 2)
    score = round(_clamp(contrib_annual + contrib_recent, 0, 100), 1)

    return {
        'score': score,
        'attendance_pct': attendance_pct,
        'recent_absence_rate': round(recent_absence_rate * 100, 1),
        'has_attendance_data': has_attendance_data,
        'breakdown': [
            {'factor': 'presenca_anual', 'weight': w_annual, 'contribution': contrib_annual, 'raw_value': attendance_pct},
            {'factor': 'faltas_recentes', 'weight': w_recent, 'contribution': contrib_recent, 'raw_value': round(recent_absence_rate * 100, 1)},
        ],
    }
