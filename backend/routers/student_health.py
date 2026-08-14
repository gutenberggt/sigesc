"""Ficha de Saúde do Estudante — coleção segregada e acesso restrito."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError

from tenant_scope import apply_tenant_filter, resolve_tenant_id_for_create
from utils.student_health import (
    HEALTH_DATA_FIELDS,
    HEALTH_READ_ROLES,
    HEALTH_WRITE_ROLES,
    SCHOOL_SCOPED_HEALTH_ROLES,
    blank_profile,
    changed_health_fields,
    normalize_health_payload,
)

BloodType = Literal['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']


class StudentHealthPayload(BaseModel):
    """Campos canônicos. Booleanos são tri-state: True / False / None."""

    model_config = ConfigDict(extra='forbid')

    blood_type: Optional[BloodType] = None
    has_allergies: Optional[bool] = None
    allergies_description: Optional[str] = Field(default=None, max_length=2000)
    has_comorbidities: Optional[bool] = None
    comorbidities_description: Optional[str] = Field(default=None, max_length=2000)
    uses_continuous_medication: Optional[bool] = None
    continuous_medication_description: Optional[str] = Field(default=None, max_length=2000)
    continuous_medication_instructions: Optional[str] = Field(default=None, max_length=2000)
    individualized_nutritional_need: Optional[bool] = None
    nutritional_need_details: Optional[str] = Field(default=None, max_length=2000)
    health_notes: Optional[str] = Field(default=None, max_length=4000)

    @field_validator(
        'allergies_description',
        'comorbidities_description',
        'continuous_medication_description',
        'continuous_medication_instructions',
        'nutritional_need_details',
        'health_notes',
        mode='before',
    )
    @classmethod
    def empty_text_to_none(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


async def ensure_student_health_indexes(database) -> None:
    """Índices idempotentes; um perfil por estudante e mantenedora."""
    await database.student_health_profiles.create_index(
        [('mantenedora_id', 1), ('student_id', 1)],
        unique=True,
        name='uniq_student_health_tenant_student',
    )
    await database.student_health_profiles.create_index(
        [('mantenedora_id', 1), ('school_id', 1)],
        name='idx_student_health_tenant_school',
    )


def setup_student_health_router(db, auth_middleware, audit_service, sandbox_db=None):
    router = APIRouter(prefix='/student-health', tags=['Saúde do Estudante'])

    def get_current_db(current_user: dict):
        if current_user.get('role') == 'admin_teste' and sandbox_db is not None:
            return sandbox_db
        return db

    async def authorize_student(request: Request, student_id: str, *, write: bool = False):
        current_user = await auth_middleware.get_current_user(request)
        role = current_user.get('role', '')
        allowed_roles = HEALTH_WRITE_ROLES if write else HEALTH_READ_ROLES
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Sem permissão para acessar dados de saúde do estudante',
            )

        current_db = get_current_db(current_user)
        student_query = apply_tenant_filter({'id': student_id}, current_user, request)
        student = await current_db.students.find_one(
            student_query,
            {'_id': 0, 'id': 1, 'full_name': 1, 'school_id': 1, 'mantenedora_id': 1},
        )
        if not student:
            raise HTTPException(status_code=404, detail='Aluno não encontrado')

        school_id = student.get('school_id')
        if not school_id:
            enrollment = await current_db.enrollments.find_one(
                {
                    'student_id': student_id,
                    'status': {'$in': ['active', 'Ativo']},
                },
                {'_id': 0, 'school_id': 1},
            )
            school_id = (enrollment or {}).get('school_id')
            if school_id:
                student['school_id'] = school_id

        if role in SCHOOL_SCOPED_HEALTH_ROLES:
            if not school_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail='Não foi possível determinar a escola ativa do aluno',
                )
            if school_id not in (current_user.get('school_ids') or []):
                staff_id = current_user.get('staff_id') or current_user.get('id')
                assignment = await current_db.school_assignments.find_one({
                    'staff_id': staff_id,
                    'school_id': school_id,
                    'status': {'$in': ['active', 'Ativo']},
                })
                if not assignment:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail='Sem permissão: usuário não está vinculado à escola deste aluno',
                    )

        return current_user, current_db, student

    async def audit_access(request: Request, current_user: dict, student: dict) -> None:
        await audit_service.log(
            action='access',
            collection='student_health_profiles',
            user=current_user,
            request=request,
            document_id=student['id'],
            description=f"Acessou ficha de saúde do aluno {student.get('full_name', student['id'])}",
            school_id=student.get('school_id'),
            extra_data={
                'student_id': student['id'],
                'contains_sensitive_health_data': True,
                'values_logged': False,
            },
        )

    @router.get('/student/{student_id}', response_model=dict)
    async def get_student_health(request: Request, student_id: str):
        current_user, current_db, student = await authorize_student(
            request, student_id, write=False
        )
        profile_query = apply_tenant_filter(
            {'student_id': student_id}, current_user, request
        )
        profile = await current_db.student_health_profiles.find_one(
            profile_query, {'_id': 0}
        )
        await audit_access(request, current_user, student)

        public_profile = blank_profile(student_id)
        if profile:
            for field in HEALTH_DATA_FIELDS:
                public_profile[field] = profile.get(field)

        return {
            'exists': profile is not None,
            'can_write': current_user.get('role') in HEALTH_WRITE_ROLES,
            'profile': public_profile,
        }

    @router.put('/student/{student_id}', response_model=dict)
    async def upsert_student_health(
        request: Request,
        student_id: str,
        payload: StudentHealthPayload,
    ):
        current_user, current_db, student = await authorize_student(
            request, student_id, write=True
        )
        profile_query = apply_tenant_filter(
            {'student_id': student_id}, current_user, request
        )
        previous = await current_db.student_health_profiles.find_one(
            profile_query, {'_id': 0}
        )

        incoming = normalize_health_payload(payload.model_dump())
        now = datetime.now(timezone.utc).isoformat()
        changed_fields = changed_health_fields(previous, incoming)

        tenant_id = student.get('mantenedora_id') or await resolve_tenant_id_for_create(
            current_db, current_user, request, student_id=student_id
        )
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Não foi possível determinar a Unidade Mantenedora do aluno',
            )

        base_doc = {
            **incoming,
            'student_id': student_id,
            'school_id': student.get('school_id'),
            'mantenedora_id': tenant_id,
            'schema_version': 1,
            'updated_at': now,
            'updated_by': current_user.get('id'),
        }

        created = previous is None
        if created:
            insert_doc = {
                **base_doc,
                'id': str(uuid.uuid4()),
                'created_at': now,
                'created_by': current_user.get('id'),
            }
            try:
                await current_db.student_health_profiles.insert_one(insert_doc)
            except DuplicateKeyError:
                # Corrida concorrente: preserva id/created_at do documento que venceu.
                created = False
                await current_db.student_health_profiles.update_one(
                    profile_query, {'$set': base_doc}
                )
        else:
            await current_db.student_health_profiles.update_one(
                profile_query, {'$set': base_doc}
            )

        await audit_service.log(
            action='create' if created else 'update',
            collection='student_health_profiles',
            user=current_user,
            request=request,
            document_id=student_id,
            description=(
                f"{'Criou' if created else 'Atualizou'} ficha de saúde do aluno "
                f"{student.get('full_name', student_id)}"
            ),
            school_id=student.get('school_id'),
            extra_data={
                'student_id': student_id,
                'changed_fields': changed_fields,
                'contains_sensitive_health_data': True,
                'values_logged': False,
            },
        )

        saved = await current_db.student_health_profiles.find_one(
            profile_query, {'_id': 0}
        )
        public_profile = blank_profile(student_id)
        if saved:
            for field in HEALTH_DATA_FIELDS:
                public_profile[field] = saved.get(field)

        return {
            'message': 'Ficha de saúde salva com sucesso',
            'created': created,
            'profile': public_profile,
        }

    return router
