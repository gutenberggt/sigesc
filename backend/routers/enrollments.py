"""
Router de Matrículas - SIGESC.

Desde Ago/2026, ``enrollments`` é a fonte canônica do vínculo aluno↔turma↔ano.
O router delega invariáveis de criação/cancelamento ao serviço de domínio e
mantém ``students.*`` apenas como projeção da matrícula REGULAR ativa.
"""

from fastapi import APIRouter, HTTPException, Request, status
from typing import List, Optional

from models import Enrollment, EnrollmentCreate, EnrollmentUpdate
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create
from services.enrollment_service import (
    EnrollmentConflictError,
    EnrollmentDomainError,
    EnrollmentNotFoundError,
    EnrollmentValidationError,
    cancel_active_enrollment,
    canonicalize_enrollment_status,
    create_active_enrollment,
    is_special_class,
    rebuild_student_home_projection,
)

router = APIRouter(prefix="/enrollments", tags=["Matrículas"])


def _raise_http(exc: EnrollmentDomainError):
    if isinstance(exc, EnrollmentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, EnrollmentConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, EnrollmentValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias."""

    @router.post("", response_model=Enrollment, status_code=status.HTTP_201_CREATED)
    async def create_enrollment(enrollment_data: EnrollmentCreate, request: Request):
        """Cria matrícula através do serviço canônico de domínio."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        tenant_id = await resolve_tenant_id_for_create(
            db,
            current_user,
            request,
            school_id=enrollment_data.school_id,
            class_id=enrollment_data.class_id,
        )

        try:
            result = await create_active_enrollment(
                db,
                student_id=enrollment_data.student_id,
                school_id=enrollment_data.school_id,
                class_id=enrollment_data.class_id,
                academic_year=enrollment_data.academic_year,
                enrollment_date=enrollment_data.enrollment_date,
                # Nunca confiar no número enviado pelo cliente: o serviço gera
                # o número atômico no servidor.
                enrollment_number=None,
                student_series=enrollment_data.student_series,
                course_ids=enrollment_data.course_ids,
                observations=enrollment_data.observations,
                mantenedora_id=tenant_id,
                source="enrollments_api",
            )
        except EnrollmentDomainError as exc:
            _raise_http(exc)

        doc = result["enrollment"]

        # Campos complementares do modelo que não participam da identidade do
        # vínculo são persistidos depois da criação canônica.
        optional_fields = {
            "enrollment_end_date": getattr(enrollment_data, "enrollment_end_date", None),
            "high_school_eja_completion_date": getattr(
                enrollment_data, "high_school_eja_completion_date", None
            ),
            "needs_pedagogical_support": getattr(
                enrollment_data, "needs_pedagogical_support", None
            ),
            "sgp_enrollment_id": getattr(enrollment_data, "sgp_enrollment_id", None),
        }
        optional_fields = {k: v for k, v in optional_fields.items() if v is not None}
        if optional_fields:
            await db.enrollments.update_one(
                {"id": doc["id"]}, {"$set": optional_fields}
            )
            doc.update(optional_fields)

        # Auditoria de criação de matrícula.
        student_doc = await db.students.find_one(
            {"id": enrollment_data.student_id}, {"_id": 0, "full_name": 1}
        )
        school = await db.schools.find_one(
            {"id": enrollment_data.school_id}, {"_id": 0, "name": 1}
        )
        await audit_service.log(
            action='create',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=doc["id"],
            description=(
                f"Criou matrícula do aluno "
                f"{student_doc.get('full_name', 'N/A') if student_doc else 'N/A'}"
            ),
            school_id=enrollment_data.school_id,
            school_name=school.get('name') if school else None,
            academic_year=enrollment_data.academic_year,
            new_value={
                'student_id': enrollment_data.student_id,
                'class_id': enrollment_data.class_id,
                'enrollment_kind': result['program'],
                'canonical_source': 'enrollments',
            },
        )

        return Enrollment(**doc)

    @router.get("", response_model=List[Enrollment])
    async def list_enrollments(
        request: Request,
        student_id: Optional[str] = None,
        class_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ):
        """Lista matrículas."""
        current_user = await AuthMiddleware.get_current_user(request)

        filter_query = {}
        if student_id:
            filter_query['student_id'] = student_id
        if class_id:
            filter_query['class_id'] = class_id

        filter_query = apply_tenant_filter(filter_query, current_user, request)
        return await db.enrollments.find(
            filter_query, {"_id": 0}
        ).skip(skip).limit(limit).to_list(limit)

    @router.get("/{enrollment_id}", response_model=Enrollment)
    async def get_enrollment(enrollment_id: str, request: Request):
        """Busca matrícula por ID."""
        current_user = await AuthMiddleware.get_current_user(request)
        enrollment_doc = await db.enrollments.find_one(
            {"id": enrollment_id}, {"_id": 0}
        )
        if not enrollment_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada",
            )
        assert_same_tenant(enrollment_doc, current_user, request)
        return Enrollment(**enrollment_doc)

    @router.put("/{enrollment_id}", response_model=Enrollment)
    async def update_enrollment(
        enrollment_id: str,
        enrollment_update: EnrollmentUpdate,
        request: Request,
    ):
        """Atualiza campos não-identitários ou encerra uma matrícula.

        Mudança de escola/turma/ano de uma matrícula ativa não é edição: é
        movimentação acadêmica e deve passar pelo fluxo de estudante, que preserva
        histórico, notas e frequência. Reativação também deve usar rematrícula.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        existing = await db.enrollments.find_one(
            {"id": enrollment_id}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada",
            )
        assert_same_tenant(existing, current_user, request)

        update_data = enrollment_update.model_dump(exclude_unset=True)
        if not update_data:
            return Enrollment(**existing)

        identity_fields = ("student_id", "school_id", "class_id", "academic_year")
        identity_change = any(
            field in update_data and update_data[field] != existing.get(field)
            for field in identity_fields
        )
        if existing.get("status") == "active" and identity_change:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Uma matrícula ativa não pode trocar aluno/escola/turma/ano por edição. "
                    "Use o fluxo de remanejamento, transferência, progressão ou rematrícula."
                ),
            )

        if "status" in update_data:
            try:
                update_data["status"] = canonicalize_enrollment_status(update_data["status"])
            except EnrollmentDomainError as exc:
                _raise_http(exc)

            if existing.get("status") != "active" and update_data["status"] == "active":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Reativação de matrícula não pode ser feita por edição direta. "
                        "Use o fluxo de rematrícula para validar duplicidade e histórico."
                    ),
                )

        from utils.text_normalize import normalize_input_fields
        update_data = normalize_input_fields(update_data, "enrollments")
        await db.enrollments.update_one(
            {"id": enrollment_id}, {"$set": update_data}
        )

        class_doc = await db.classes.find_one(
            {"id": existing.get("class_id")},
            {"_id": 0, "atendimento_programa": 1},
        )
        was_special = is_special_class(class_doc)

        # Só a matrícula regular governa students.class_id/status. Encerrar AEE,
        # reforço ou recomposição não altera a turma regular do estudante.
        if (
            not was_special
            and existing.get("status") == "active"
            and update_data.get("status")
            and update_data["status"] != "active"
        ):
            status_when_none = {
                "transferred": "transferred",
                "dropout": "dropout",
                "cancelled": "cancelled",
                "progressed": "progressed",
                "completed": "inactive",
                "relocated": "inactive",
            }.get(update_data["status"], "inactive")
            await rebuild_student_home_projection(
                db,
                existing["student_id"],
                academic_year=existing.get("academic_year"),
                no_primary_status=status_when_none,
            )

        student_doc = await db.students.find_one(
            {"id": existing['student_id']}, {"_id": 0, "full_name": 1}
        )
        await audit_service.log(
            action='update',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment_id,
            description=(
                f"Atualizou matrícula do aluno "
                f"{student_doc.get('full_name', 'N/A') if student_doc else 'N/A'}"
            ),
            school_id=update_data.get('school_id') or existing.get('school_id'),
            academic_year=existing.get('academic_year'),
            old_value={
                'status': existing.get('status'),
                'class_id': existing.get('class_id'),
            },
            new_value=update_data,
        )

        updated = await db.enrollments.find_one(
            {"id": enrollment_id}, {"_id": 0}
        )
        return Enrollment(**updated)

    @router.delete("/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_enrollment(enrollment_id: str, request: Request):
        """Exclui matrícula e reconstrói a projeção regular quando necessário."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        existing = await db.enrollments.find_one(
            {"id": enrollment_id}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada",
            )
        assert_same_tenant(existing, current_user, request)

        class_doc = await db.classes.find_one(
            {"id": existing.get("class_id")},
            {"_id": 0, "atendimento_programa": 1},
        )
        was_active_regular = (
            existing.get("status") == "active" and not is_special_class(class_doc)
        )

        result = await db.enrollments.delete_one({"id": enrollment_id})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada",
            )

        if was_active_regular:
            await rebuild_student_home_projection(
                db,
                existing["student_id"],
                academic_year=existing.get("academic_year"),
                no_primary_status="inactive",
            )

        student_doc = await db.students.find_one(
            {"id": existing.get('student_id')}, {"_id": 0, "full_name": 1}
        )
        await audit_service.log(
            action='delete',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment_id,
            description=(
                f"EXCLUIU matrícula do aluno "
                f"{student_doc.get('full_name', 'N/A') if student_doc else 'N/A'}"
            ),
            school_id=existing.get('school_id'),
            academic_year=existing.get('academic_year'),
            old_value={
                'student_id': existing.get('student_id'),
                'class_id': existing.get('class_id'),
                'status': existing.get('status'),
            },
        )
        return None

    @router.post("/cancel-enrollment", status_code=status.HTTP_200_OK)
    async def cancel_enrollment(request: Request):
        """Cancela vínculo ativo preservando histórico e a home class regular."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        body = await request.json()
        student_id = body.get('student_id')
        class_id = body.get('class_id')
        reason = body.get('reason', '')

        if not student_id or not class_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="student_id e class_id são obrigatórios",
            )

        try:
            result = await cancel_active_enrollment(
                db,
                student_id=student_id,
                class_id=class_id,
                reason=reason,
                cancelled_by=current_user.get('id'),
            )
        except EnrollmentDomainError as exc:
            _raise_http(exc)

        enrollment = result["enrollment"]
        student_doc = await db.students.find_one(
            {"id": student_id}, {"_id": 0, "full_name": 1}
        )
        student_name = student_doc.get('full_name', 'N/A') if student_doc else 'N/A'
        class_doc = await db.classes.find_one(
            {"id": class_id}, {"_id": 0, "name": 1}
        )
        class_name = class_doc.get('name', 'N/A') if class_doc else 'N/A'

        await audit_service.log(
            action='cancel',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment['id'],
            description=(
                f"CANCELOU vínculo do aluno {student_name} com a turma {class_name}. "
                f"Motivo: {reason}"
            ),
            school_id=enrollment.get('school_id'),
            academic_year=enrollment.get('academic_year'),
            old_value={
                'student_id': student_id,
                'class_id': class_id,
                'status': 'active',
            },
            new_value={
                'status': 'cancelled',
                'reason': reason,
                'enrollment_kind': result['program'],
            },
        )

        return {
            "message": (
                f"Vínculo do aluno {student_name} com a turma {class_name} "
                "cancelado com sucesso."
            )
        }

    return router
