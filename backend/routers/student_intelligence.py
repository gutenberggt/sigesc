"""SIE — Student Intelligence Engine (FASE 0, baseado em regras).

Endpoints (`/api/sie/...`): config por mantenedora, cálculo individual e em
lote, listagem de risco e alertas. Tudo multi-tenant (tenant_scope.py).

Coleções: sie_config, student_diagnostics, student_risk_scores,
student_snapshots, student_alerts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from tenant_scope import (
    apply_tenant_filter,
    assert_same_tenant,
    resolve_tenant_id_for_create,
)
from services import sie_service

router = APIRouter(prefix="/sie", tags=["SIE — Student Intelligence"])

MANAGEMENT_ROLES = [
    'super_admin', 'admin', 'admin_teste', 'gerente',
    'semed', 'semed1', 'semed2', 'semed3',
    'secretario', 'coordenador', 'diretor', 'apoio_pedagogico',
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConfigUpdate(BaseModel):
    passing_grade: Optional[float] = None
    attendance_min_pct: Optional[float] = None
    recent_window_days: Optional[int] = None
    academic_weights: Optional[Dict[str, float]] = None
    attendance_weights: Optional[Dict[str, float]] = None
    overall_weights: Optional[Dict[str, float]] = None
    caps: Optional[Dict[str, float]] = None
    risk_bands: Optional[Dict[str, float]] = None


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    def _get_db(user: dict):
        if user and user.get('is_sandbox'):
            return sandbox_db if sandbox_db is not None else db
        return db

    async def _persist(current_db, student: Dict[str, Any], result: Dict[str, Any],
                       year: int, tenant_id: Optional[str]) -> None:
        sid = student['id']
        school_id = student.get('school_id')
        class_id = student.get('class_id')
        ac = result['academic']
        at = result['attendance']
        ov = result['overall']
        diag = result['diagnostic']
        now = _now_iso()

        # 1. Risk score (1 doc corrente por aluno/ano)
        risk_doc = {
            'mantenedora_id': tenant_id,
            'student_id': sid,
            'school_id': school_id,
            'class_id': class_id,
            'academic_year': year,
            'overall_risk': ov['overall_risk'],
            'risk_level': ov['risk_level'],
            'academic_risk': ac['score'],
            'attendance_risk': at['score'],
            'trend_status': ac['trend_status'],
            'factors': ov['factors'],
            'academic_breakdown': ac['breakdown'],
            'attendance_breakdown': at['breakdown'],
            'recovery_subjects': ac['recovery_subjects'],
            'failed_subjects': ac['failed_subjects'],
            'critical_components': ac['critical_components'],
            'average_grade': ac['average_grade'],
            'attendance_pct': at['attendance_pct'],
            'updated_at': now,
        }
        await current_db.student_risk_scores.update_one(
            {'student_id': sid, 'academic_year': year},
            {'$set': risk_doc, '$setOnInsert': {'id': str(uuid.uuid4()), 'computed_at': now}},
            upsert=True,
        )

        # 2. Diagnóstico estruturado (1 doc corrente por aluno/ano)
        diag_doc = {
            'mantenedora_id': tenant_id,
            'student_id': sid,
            'school_id': school_id,
            'class_id': class_id,
            'academic_year': year,
            **diag,
            'updated_at': now,
        }
        await current_db.student_diagnostics.update_one(
            {'student_id': sid, 'academic_year': year},
            {'$set': diag_doc, '$setOnInsert': {'id': str(uuid.uuid4()), 'computed_at': now}},
            upsert=True,
        )

        # 3. Snapshot (1 por dia → série temporal para gráficos)
        snap_date = datetime.now(timezone.utc).date().isoformat()
        await current_db.student_snapshots.update_one(
            {'student_id': sid, 'academic_year': year, 'snapshot_date': snap_date},
            {'$set': {
                'mantenedora_id': tenant_id,
                'student_id': sid,
                'school_id': school_id,
                'class_id': class_id,
                'academic_year': year,
                'snapshot_date': snap_date,
                'academic_risk': ac['score'],
                'attendance_risk': at['score'],
                'overall_risk': ov['overall_risk'],
                'risk_level': ov['risk_level'],
                'trend': ac['trend_status'],
                'updated_at': now,
            }, '$setOnInsert': {'id': str(uuid.uuid4()), 'created_at': now}},
            upsert=True,
        )

        # 4. Alertas (materializa sinais; resolve os que não disparam mais)
        current_types = set()
        for al in result['alerts']:
            current_types.add(al['alert_type'])
            await current_db.student_alerts.update_one(
                {'student_id': sid, 'academic_year': year, 'alert_type': al['alert_type']},
                {'$set': {
                    'mantenedora_id': tenant_id,
                    'student_id': sid,
                    'school_id': school_id,
                    'class_id': class_id,
                    'academic_year': year,
                    'alert_type': al['alert_type'],
                    'severity': al['severity'],
                    'message': al['message'],
                    'resolved_at': None,
                    'updated_at': now,
                }, '$setOnInsert': {'id': str(uuid.uuid4()), 'created_at': now}},
                upsert=True,
            )
        # Resolve alertas que não dispararam neste cálculo
        await current_db.student_alerts.update_many(
            {'student_id': sid, 'academic_year': year,
             'alert_type': {'$nin': list(current_types)}, 'resolved_at': None},
            {'$set': {'resolved_at': now, 'updated_at': now}},
        )

    # ===================== CONFIG =====================

    @router.get("/config")
    async def get_config(request: Request):
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        tenant_id = await resolve_tenant_id_for_create(current_db, user, request)
        cfg = await sie_service.get_or_create_config(current_db, tenant_id)
        return cfg

    @router.put("/config")
    async def update_config(payload: ConfigUpdate, request: Request):
        user = await AuthMiddleware.require_roles(['super_admin', 'admin', 'admin_teste', 'gerente'])(request)
        current_db = _get_db(user)
        tenant_id = await resolve_tenant_id_for_create(current_db, user, request)
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Mantenedora não identificada para salvar a configuração.")
        await sie_service.get_or_create_config(current_db, tenant_id)  # garante doc base
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        updates['updated_at'] = _now_iso()
        await current_db.sie_config.update_one(
            {'mantenedora_id': tenant_id}, {'$set': updates}, upsert=True
        )
        return await sie_service.get_or_create_config(current_db, tenant_id)

    # ===================== ALUNO =====================

    async def _load_student(current_db, user, request, student_id: str) -> Dict[str, Any]:
        student = await current_db.students.find_one({'id': student_id}, {'_id': 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        assert_same_tenant(student, user, request)
        return student

    @router.get("/students/{student_id}")
    async def get_student_intelligence(student_id: str, request: Request,
                                       academic_year: Optional[int] = None):
        """Computa AO VIVO (sem persistir) o diagnóstico + risco do aluno."""
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        student = await _load_student(current_db, user, request, student_id)
        year = academic_year or datetime.now().year
        cfg = await sie_service.get_or_create_config(current_db, student.get('mantenedora_id'))
        result = await sie_service.compute_for_student(current_db, student, cfg, year)
        return {
            'student': {'id': student['id'], 'full_name': student.get('full_name'),
                        'school_id': student.get('school_id'), 'class_id': student.get('class_id'),
                        'enrollment_number': student.get('enrollment_number')},
            'academic_year': year,
            **result,
        }

    @router.post("/students/{student_id}/compute")
    async def compute_student_intelligence(student_id: str, request: Request,
                                           academic_year: Optional[int] = None):
        """Computa E PERSISTE (risk_score, diagnóstico, snapshot, alertas)."""
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        student = await _load_student(current_db, user, request, student_id)
        year = academic_year or datetime.now().year
        tenant_id = student.get('mantenedora_id') or await resolve_tenant_id_for_create(
            current_db, user, request, school_id=student.get('school_id'))
        cfg = await sie_service.get_or_create_config(current_db, tenant_id)
        result = await sie_service.compute_for_student(current_db, student, cfg, year)
        await _persist(current_db, student, result, year, tenant_id)
        return {
            'student': {'id': student['id'], 'full_name': student.get('full_name')},
            'academic_year': year,
            **result,
        }

    # ===================== LOTE =====================

    @router.post("/compute")
    async def compute_batch(request: Request, academic_year: Optional[int] = None,
                            school_id: Optional[str] = None, class_id: Optional[str] = None):
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        year = academic_year or datetime.now().year

        q: Dict[str, Any] = {'status': 'active'}
        if school_id:
            q['school_id'] = school_id
        if class_id:
            q['class_id'] = class_id
        q = apply_tenant_filter(q, user, request)
        # Secretário: restringe às escolas atribuídas
        if user.get('role') == 'secretario':
            q['school_id'] = {'$in': user.get('school_ids', []) or []}

        stats = {'processed': 0, 'by_level': {'low': 0, 'moderate': 0, 'high': 0, 'critical': 0},
                 'alerts_open': 0}
        cfg_cache: Dict[str, Any] = {}
        async for student in current_db.students.find(q, {'_id': 0}):
            tenant_id = student.get('mantenedora_id')
            cfg = cfg_cache.get(tenant_id or '__none__')
            if cfg is None:
                cfg = await sie_service.get_or_create_config(current_db, tenant_id)
                cfg_cache[tenant_id or '__none__'] = cfg
            result = await sie_service.compute_for_student(current_db, student, cfg, year)
            await _persist(current_db, student, result, year, tenant_id)
            stats['processed'] += 1
            stats['by_level'][result['overall']['risk_level']] += 1
            stats['alerts_open'] += len(result['alerts'])

        if audit_service:
            await audit_service.log(
                action='compute', collection='student_risk_scores', user=user, request=request,
                document_id='sie-batch',
                description=f"SIE: recomputou risco de {stats['processed']} alunos (ano {year}).",
            )
        return {'academic_year': year, **stats}

    # ===================== LISTAGENS =====================

    @router.get("/risk")
    async def list_risk(request: Request, academic_year: Optional[int] = None,
                        school_id: Optional[str] = None, class_id: Optional[str] = None,
                        level: Optional[str] = None, limit: int = 200):
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        year = academic_year or datetime.now().year
        q: Dict[str, Any] = {'academic_year': year}
        if school_id:
            q['school_id'] = school_id
        if class_id:
            q['class_id'] = class_id
        if level:
            q['risk_level'] = level
        q = apply_tenant_filter(q, user, request)
        if user.get('role') == 'secretario':
            q['school_id'] = {'$in': user.get('school_ids', []) or []}

        rows = await current_db.student_risk_scores.find(q, {'_id': 0}) \
            .sort('overall_risk', -1).limit(min(limit, 1000)).to_list(min(limit, 1000))

        sids = [r['student_id'] for r in rows]
        names: Dict[str, str] = {}
        if sids:
            async for s in current_db.students.find({'id': {'$in': sids}}, {'_id': 0, 'id': 1, 'full_name': 1, 'enrollment_number': 1}):
                names[s['id']] = s.get('full_name')
        for r in rows:
            r['student_name'] = names.get(r['student_id'])
        return {'academic_year': year, 'total': len(rows), 'items': rows}

    @router.get("/alerts")
    async def list_alerts(request: Request, academic_year: Optional[int] = None,
                         severity: Optional[str] = None, alert_type: Optional[str] = None,
                         resolved: bool = False, limit: int = 200):
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        year = academic_year or datetime.now().year
        q: Dict[str, Any] = {'academic_year': year}
        if severity:
            q['severity'] = severity
        if alert_type:
            q['alert_type'] = alert_type
        q['resolved_at'] = {'$ne': None} if resolved else None
        q = apply_tenant_filter(q, user, request)
        if user.get('role') == 'secretario':
            q['school_id'] = {'$in': user.get('school_ids', []) or []}

        sev_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        rows = await current_db.student_alerts.find(q, {'_id': 0}).limit(min(limit, 1000)).to_list(min(limit, 1000))
        rows.sort(key=lambda r: sev_order.get(r.get('severity'), 9))

        sids = list({r['student_id'] for r in rows})
        names: Dict[str, str] = {}
        if sids:
            async for s in current_db.students.find({'id': {'$in': sids}}, {'_id': 0, 'id': 1, 'full_name': 1}):
                names[s['id']] = s.get('full_name')
        for r in rows:
            r['student_name'] = names.get(r['student_id'])
        return {'academic_year': year, 'total': len(rows), 'items': rows}

    @router.get("/students/{student_id}/snapshots")
    async def list_snapshots(student_id: str, request: Request, academic_year: Optional[int] = None):
        user = await AuthMiddleware.require_roles(MANAGEMENT_ROLES)(request)
        current_db = _get_db(user)
        await _load_student(current_db, user, request, student_id)
        year = academic_year or datetime.now().year
        rows = await current_db.student_snapshots.find(
            {'student_id': student_id, 'academic_year': year}, {'_id': 0}
        ).sort('snapshot_date', 1).to_list(1000)
        return {'student_id': student_id, 'academic_year': year, 'total': len(rows), 'items': rows}

    return router
