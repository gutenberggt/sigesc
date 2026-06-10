"""SIE — Motor de Risco Geral + classificação por faixas. Função PURA.

Combina risco acadêmico e de frequência num score 0–100, com explicabilidade
(`factors`). Classificação em 4 níveis (operacionalmente importante para a SEMED):

    0–24   low       (Baixo)
    25–49  moderate  (Moderado)
    50–74  high      (Alto)
    75–100 critical  (Crítico)

Pesos default (configuráveis via `sie_config.overall_weights`):
  academic   55%
  attendance 45%
"""
from __future__ import annotations

from typing import Any, Dict


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def classify_risk(score: float, config: Dict[str, Any]) -> str:
    bands = config.get('risk_bands', {}) or {}
    low_max = float(bands.get('low_max', 24))
    mod_max = float(bands.get('moderate_max', 49))
    high_max = float(bands.get('high_max', 74))
    if score <= low_max:
        return 'low'
    if score <= mod_max:
        return 'moderate'
    if score <= high_max:
        return 'high'
    return 'critical'


def compute_overall_risk(academic_score: float, attendance_score: float, config: Dict[str, Any]) -> Dict[str, Any]:
    ow = config.get('overall_weights', {}) or {}
    w_ac = float(ow.get('academic', 55))
    w_at = float(ow.get('attendance', 45))
    total_w = (w_ac + w_at) or 1.0

    overall = (w_ac * academic_score + w_at * attendance_score) / total_w
    overall = round(_clamp(overall, 0, 100), 1)
    level = classify_risk(overall, config)

    contrib_ac = round((w_ac / total_w) * academic_score, 1)
    contrib_at = round((w_at / total_w) * attendance_score, 1)

    return {
        'overall_risk': overall,
        'risk_level': level,
        'factors': [
            {'factor': 'academic', 'weight': round(w_ac / total_w * 100, 1), 'contribution': contrib_ac, 'raw_value': academic_score},
            {'factor': 'attendance', 'weight': round(w_at / total_w * 100, 1), 'contribution': contrib_at, 'raw_value': attendance_score},
        ],
    }
