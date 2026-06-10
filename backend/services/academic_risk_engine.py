"""SIE — Motor de Risco Acadêmico (0–100). Função PURA, sem I/O.

Composição (pesos default, configuráveis via `sie_config.academic_weights`):
  notas        50  → quão abaixo da nota de corte está a média do aluno
  recuperacao  20  → nº de componentes em recuperação
  reprovacao   20  → nº de componentes reprovados
  tendencia    10  → queda contínua de desempenho (b1 → b4)

Maior score = maior risco. Todo resultado carrega `breakdown` (explicabilidade).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_RECOVERY_STATUSES = {
    'recuperacao', 'recuperação', 'recovery', 'em recuperacao',
    'em recuperação', 'em_recuperacao',
}
_FAILED_STATUSES = {'reprovado', 'reprovada', 'retido', 'failed', 'reprovado_falta'}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _course_bimesters(g: Dict[str, Any]) -> List[float]:
    vals: List[float] = []
    for b in ('b1', 'b2', 'b3', 'b4'):
        v = g.get(b)
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return vals


def _course_average(g: Dict[str, Any]) -> Optional[float]:
    fa = g.get('final_average')
    if isinstance(fa, (int, float)):
        return float(fa)
    vals = _course_bimesters(g)
    return sum(vals) / len(vals) if vals else None


def compute_academic_risk(grades: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    passing = float(config.get('passing_grade', 6.0))
    aw = config.get('academic_weights', {}) or {}
    w_notas = float(aw.get('notas', 50))
    w_rec = float(aw.get('recuperacao', 20))
    w_rep = float(aw.get('reprovacao', 20))
    w_trend = float(aw.get('tendencia', 10))
    caps = config.get('caps', {}) or {}
    rec_max = float(caps.get('recovery_max', 3)) or 1
    fail_max = float(caps.get('failed_max', 2)) or 1
    trend_drop_max = float(caps.get('trend_drop_max', 3)) or 1

    course_avgs: List[float] = []
    recovery_subjects = 0
    failed_subjects = 0
    critical_components = 0
    deltas: List[float] = []

    for g in grades:
        status = (g.get('status') or '').strip().lower()
        avg = _course_average(g)
        if avg is not None:
            course_avgs.append(avg)
            if avg < passing:
                critical_components += 1
        # Recuperação: status explícito OU nota de recuperação registrada (conta 1x)
        if status in _RECOVERY_STATUSES:
            recovery_subjects += 1
        elif any(g.get(k) is not None for k in ('recovery', 'rec_s1', 'rec_s2')):
            recovery_subjects += 1
        if status in _FAILED_STATUSES:
            failed_subjects += 1
        vals = _course_bimesters(g)
        if len(vals) >= 2:
            deltas.append(vals[-1] - vals[0])

    average_grade = round(sum(course_avgs) / len(course_avgs), 2) if course_avgs else None

    # 1. Notas — quão abaixo da nota de corte (acima do corte = 0 risco)
    if average_grade is None:
        notas_frac = 0.0
        has_grade_data = False
    else:
        notas_frac = _clamp((passing - average_grade) / passing) if passing > 0 else 0.0
        has_grade_data = True

    # 2. Recuperação / 3. Reprovação
    rec_frac = _clamp(recovery_subjects / rec_max)
    rep_frac = _clamp(failed_subjects / fail_max)

    # 4. Tendência (apenas QUEDA adiciona risco)
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
    if avg_delta <= -0.5:
        trend_status = 'falling'
    elif avg_delta >= 0.5:
        trend_status = 'improving'
    else:
        trend_status = 'stable'
    trend_frac = _clamp(-avg_delta / trend_drop_max)

    contrib_notas = round(w_notas * notas_frac, 2)
    contrib_rec = round(w_rec * rec_frac, 2)
    contrib_rep = round(w_rep * rep_frac, 2)
    contrib_trend = round(w_trend * trend_frac, 2)
    score = round(_clamp(contrib_notas + contrib_rec + contrib_rep + contrib_trend, 0, 100), 1)

    return {
        'score': score,
        'average_grade': average_grade,
        'recovery_subjects': recovery_subjects,
        'failed_subjects': failed_subjects,
        'critical_components': critical_components,
        'trend_status': trend_status,
        'trend_delta': round(avg_delta, 2),
        'has_grade_data': has_grade_data,
        'breakdown': [
            {'factor': 'notas', 'weight': w_notas, 'contribution': contrib_notas, 'raw_value': average_grade},
            {'factor': 'recuperacao', 'weight': w_rec, 'contribution': contrib_rec, 'raw_value': recovery_subjects},
            {'factor': 'reprovacao', 'weight': w_rep, 'contribution': contrib_rep, 'raw_value': failed_subjects},
            {'factor': 'tendencia', 'weight': w_trend, 'contribution': contrib_trend, 'raw_value': round(avg_delta, 2)},
        ],
    }
