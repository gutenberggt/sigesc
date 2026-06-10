"""SIE — Serviço de orquestração (acesso a banco + pipeline).

Carrega os sinais do aluno (notas + frequência), invoca os motores PUROS e
devolve o pacote completo {academic, attendance, overall, diagnostic, alerts}.
Também provê a config por mantenedora (defaults + merge).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.academic_risk_engine import compute_academic_risk
from services.attendance_risk_engine import compute_attendance_risk
from services.overall_risk_engine import compute_overall_risk
from services.diagnostic_engine import build_diagnostic
from services.alert_engine import build_alerts

# Defaults validados (Jun/2026): 4 níveis, scores separados, tendência,
# explicabilidade. Educação básica BR → frequência tem peso alto (evasão).
DEFAULT_SIE_CONFIG: Dict[str, Any] = {
    'passing_grade': 6.0,
    'attendance_min_pct': 75,
    'recent_window_days': 30,
    'academic_weights': {'notas': 50, 'recuperacao': 20, 'reprovacao': 20, 'tendencia': 10},
    'attendance_weights': {'presenca_anual': 70, 'faltas_recentes': 30},
    'overall_weights': {'academic': 55, 'attendance': 45},
    'caps': {'recovery_max': 3, 'failed_max': 2, 'trend_drop_max': 3, 'recent_absence_max': 0.5},
    'risk_bands': {'low_max': 24, 'moderate_max': 49, 'high_max': 74},
}

_NESTED_KEYS = ('academic_weights', 'attendance_weights', 'overall_weights', 'caps', 'risk_bands')
_PRESENT_SET = {'p', 'presente', 'present', '1', 'true', 'pr'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_defaults(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Garante que toda chave (incl. aninhadas) exista, preservando overrides."""
    out = dict(DEFAULT_SIE_CONFIG)
    if cfg:
        for k, v in cfg.items():
            if k not in _NESTED_KEYS:
                out[k] = v
    for nested in _NESTED_KEYS:
        merged = dict(DEFAULT_SIE_CONFIG[nested])
        if cfg and isinstance(cfg.get(nested), dict):
            merged.update(cfg[nested])
        out[nested] = merged
    return out


async def get_or_create_config(db, mantenedora_id: Optional[str]) -> Dict[str, Any]:
    if mantenedora_id:
        doc = await db.sie_config.find_one({'mantenedora_id': mantenedora_id}, {'_id': 0})
        if doc:
            return merge_defaults(doc)
        cfg = {
            'id': str(uuid.uuid4()),
            'mantenedora_id': mantenedora_id,
            **DEFAULT_SIE_CONFIG,
            'created_at': _now_iso(),
            'updated_at': _now_iso(),
        }
        await db.sie_config.insert_one(dict(cfg))
        return merge_defaults(cfg)
    # super_admin cross-tenant sem scope → usa defaults em memória
    return merge_defaults(None)


async def _student_class_ids(db, student: Dict[str, Any], year: int) -> List[str]:
    ids = set()
    if student.get('class_id'):
        ids.add(student['class_id'])
    async for e in db.enrollments.find(
        {'student_id': student['id'], 'status': 'active'}, {'_id': 0, 'class_id': 1}
    ):
        if e.get('class_id'):
            ids.add(e['class_id'])
    return list(ids)


async def load_signals(db, student: Dict[str, Any], config: Dict[str, Any], year: int) -> Dict[str, Any]:
    sid = student['id']
    grades = [g async for g in db.grades.find(
        {'student_id': sid, 'academic_year': year}, {'_id': 0}
    )]

    class_ids = await _student_class_ids(db, student, year)
    recent_days = int(config.get('recent_window_days', 30))
    recent_cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date().isoformat()

    total = present = recent_total = recent_present = 0
    q: Dict[str, Any] = {'academic_year': year}
    if class_ids:
        q['class_id'] = {'$in': class_ids}
    else:
        q['records.student_id'] = sid

    async for a in db.attendance.find(q, {'_id': 0, 'date': 1, 'records': 1}):
        date_s = str(a.get('date') or '')[:10]
        is_recent = bool(date_s) and date_s >= recent_cutoff
        for rec in (a.get('records') or []):
            if rec.get('student_id') != sid:
                continue
            st = (rec.get('status') or '').strip().lower()
            is_present = st in _PRESENT_SET
            total += 1
            if is_present:
                present += 1
            if is_recent:
                recent_total += 1
                if is_present:
                    recent_present += 1

    return {
        'grades': grades,
        'attendance_summary': {
            'total': total, 'present': present,
            'recent_total': recent_total, 'recent_present': recent_present,
        },
    }


async def compute_for_student(db, student: Dict[str, Any], config: Dict[str, Any], year: int) -> Dict[str, Any]:
    signals = await load_signals(db, student, config, year)
    academic = compute_academic_risk(signals['grades'], config)
    attendance = compute_attendance_risk(signals['attendance_summary'], config)
    overall = compute_overall_risk(academic['score'], attendance['score'], config)
    diagnostic = build_diagnostic(student, academic, attendance, overall, config)
    alerts = build_alerts(student, academic, attendance, overall, config)
    return {
        'academic': academic,
        'attendance': attendance,
        'overall': overall,
        'diagnostic': diagnostic,
        'alerts': alerts,
    }
