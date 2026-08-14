"""Testes da Fase C1 — Ficha de Saúde do Estudante."""
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from audit_service import AuditService
from utils.student_health import changed_health_fields, normalize_health_payload

# Carrega somente o arquivo do router em teste, sem executar routers/__init__.py.
_SPEC = importlib.util.spec_from_file_location(
    "student_health_router_under_test",
    BACKEND_DIR / "routers" / "student_health.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)
StudentHealthPayload = _MODULE.StudentHealthPayload
setup_student_health_router = _MODULE.setup_student_health_router


def test_normalize_health_payload_clears_orphan_details():
    result = normalize_health_payload({
        'has_allergies': False,
        'allergies_description': 'Não deveria permanecer',
        'uses_continuous_medication': None,
        'continuous_medication_description': 'Também não',
        'continuous_medication_instructions': 'Também não',
    })
    assert result['allergies_description'] is None
    assert result['continuous_medication_description'] is None
    assert result['continuous_medication_instructions'] is None


def test_changed_health_fields_returns_names_only():
    previous = {'blood_type': 'A+', 'has_allergies': False}
    incoming = normalize_health_payload({'blood_type': 'O+', 'has_allergies': False})
    changed = changed_health_fields(previous, incoming)
    assert 'blood_type' in changed
    assert 'has_allergies' not in changed
    assert 'O+' not in changed


def test_payload_rejects_invalid_blood_type():
    with pytest.raises(ValidationError):
        StudentHealthPayload(blood_type='X+')


def test_audit_sanitizer_redacts_health_fields():
    sanitized = AuditService()._sanitize_value({
        'blood_type': 'O+',
        'has_allergies': True,
        'allergies_description': 'Exemplo',
        'health_notes': 'Observação',
    })
    assert sanitized['blood_type'] == '***REDACTED***'
    assert sanitized['has_allergies'] == '***REDACTED***'
    assert sanitized['allergies_description'] == '***REDACTED***'
    assert sanitized['health_notes'] == '***REDACTED***'


@pytest.mark.asyncio
async def test_professor_cannot_read_health_profile():
    db = MagicMock()
    auth = MagicMock()
    auth.get_current_user = AsyncMock(return_value={
        'id': 'u-prof', 'role': 'professor', 'mantenedora_id': 'm-1'
    })
    audit = MagicMock()
    audit.log = AsyncMock()

    router = setup_student_health_router(db, auth, audit)
    route = next(
        r for r in router.routes
        if getattr(r, 'path', '') == '/student-health/student/{student_id}'
        and 'GET' in getattr(r, 'methods', set())
    )

    with pytest.raises(HTTPException) as exc:
        await route.endpoint(request=MagicMock(), student_id='s-1')
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_secretary_requires_school_assignment_to_read():
    db = MagicMock()
    db.students.find_one = AsyncMock(return_value={
        'id': 's-1',
        'full_name': 'Aluno Teste',
        'school_id': 'sch-1',
        'mantenedora_id': 'm-1',
    })
    db.school_assignments.find_one = AsyncMock(return_value=None)

    auth = MagicMock()
    auth.get_current_user = AsyncMock(return_value={
        'id': 'u-sec',
        'staff_id': 'st-1',
        'role': 'secretario',
        'mantenedora_id': 'm-1',
        'school_ids': [],
    })
    audit = MagicMock()
    audit.log = AsyncMock()

    router = setup_student_health_router(db, auth, audit)
    route = next(
        r for r in router.routes
        if getattr(r, 'path', '') == '/student-health/student/{student_id}'
        and 'GET' in getattr(r, 'methods', set())
    )

    with pytest.raises(HTTPException) as exc:
        await route.endpoint(request=MagicMock(), student_id='s-1')
    assert exc.value.status_code == 403
