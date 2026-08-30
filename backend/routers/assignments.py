"""
Router para Lotações.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from datetime import datetime, timezone

from models import *
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create
from utils.carga_horaria_calculator import calcular_carga_por_lotacao
from services.teacher_assignment_integrity import (
    TeacherAssignmentIntegrityError,
    is_active_teacher_assignment_status,
    validate_teacher_assignment_curriculum,
    validate_teacher_assignment_workload,
)


router = APIRouter(tags=["Lotações"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""

    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    def integrity_http_error(exc: TeacherAssignmentIntegrityError) -> HTTPException:
        return HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": exc.message,
                "curricular_fit": dict(exc.fit or {}),
            },
        )

    def assert_context_tenant(tenant_id: str, *docs: dict) -> None:
        """Fail-closed para impedir combinação de documentos de tenants distintos."""
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Mantenedora da alocação não pôde ser determinada")
        for doc in docs:
            if not doc or str(doc.get('mantenedora_id') or '') != str(tenant_id):
                raise HTTPException(status_code=403, detail="Contexto da alocação pertence a outra mantenedora ou está sem escopo")

    async def load_teacher_assignment_context(
        *,
        current_user: dict,
        request: Request,
        staff_id: str,
        school_id: str,
        class_id: str,
        course_id: str,
    ):
        """Carrega o contexto mínimo de escrita já preso ao tenant da request."""
        staff = await db.staff.find_one(
            apply_tenant_filter({"id": staff_id}, current_user, request)
        )
        if not staff:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")

        school = await db.schools.find_one(
            apply_tenant_filter({"id": school_id}, current_user, request)
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        turma = await db.classes.find_one(
            apply_tenant_filter({"id": class_id}, current_user, request)
        )
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        course = await db.courses.find_one(
            apply_tenant_filter({"id": course_id}, current_user, request)
        )
        if not course:
            raise HTTPException(status_code=404, detail="Componente curricular não encontrado")

        tenant_id = await resolve_tenant_id_for_create(
            db,
            current_user,
            request,
            school_id=school_id,
        )
        assert_context_tenant(tenant_id, staff, school, turma, course)
        return staff, school, turma, course, tenant_id

    @router.get("/school-assignments")
    async def list_school_assignments(
        request: Request,
        school_id: Optional[str] = None,
        staff_id: Optional[str] = None,
        status: Optional[str] = None,
        academic_year: Optional[int] = None
    ):
        """Lista lotações"""
        await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3', 'diretor'])(request)
        current_user = await AuthMiddleware.get_current_user(request)

        query = {}
        if school_id:
            query["school_id"] = school_id
        if staff_id:
            query["staff_id"] = staff_id
        if status:
            query["status"] = status
        if academic_year:
            query["academic_year"] = academic_year

        # Multi-tenancy
        query = apply_tenant_filter(query, current_user, request)

        assignments = await db.school_assignments.find(query, {"_id": 0}).to_list(1000)

        # Enriquecer com dados
        for assign in assignments:
            staff = await db.staff.find_one({"id": assign['staff_id']}, {"_id": 0})
            if staff:
                assign['staff'] = staff

            school = await db.schools.find_one({"id": assign['school_id']}, {"_id": 0, "name": 1})
            if school:
                assign['school_name'] = school['name']

            # [Fev/2026] CH derivada (fonte única). Substitui o campo manual antigo.
            if assign.get('status') == 'ativo':
                try:
                    assign['carga_horaria_calculada'] = await calcular_carga_por_lotacao(
                        db, assign['staff_id'], assign['school_id'], modo='atual'
                    )
                except Exception:  # noqa: BLE001
                    assign['carga_horaria_calculada'] = None

        return assignments

    @router.post("/school-assignments")
    async def create_school_assignment(assignment: SchoolAssignmentCreate, request: Request):
        """Cria nova lotação"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        # Verifica se servidor existe
        staff = await db.staff.find_one({"id": assignment.staff_id})
        if not staff:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")

        # Verifica se escola existe
        school = await db.schools.find_one({"id": assignment.school_id})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        # Verifica se já existe lotação ativa para mesma escola/ano/função
        # Permite múltiplas funções na mesma escola
        existing = await db.school_assignments.find_one({
            "staff_id": assignment.staff_id,
            "school_id": assignment.school_id,
            "academic_year": assignment.academic_year,
            "funcao": assignment.funcao,
            "status": "ativo"
        })
        if existing:
            raise HTTPException(status_code=400, detail="Servidor já possui lotação ativa com esta função nesta escola para este ano")

        new_assignment = SchoolAssignment(**assignment.model_dump())
        sa_doc = new_assignment.model_dump()
        # Multi-tenancy: injeta mantenedora_id derivada da escola
        sa_doc['mantenedora_id'] = await resolve_tenant_id_for_create(
            db, current_user, request, school_id=assignment.school_id
        )
        await db.school_assignments.insert_one(sa_doc)

        # Auditoria de criação de lotação
        await audit_service.log(
            action='create',
            collection='school_assignments',
            user=current_user,
            request=request,
            document_id=new_assignment.id,
            description=f"Criou lotação do servidor {staff.get('nome', staff.get('full_name', 'N/A'))} como {assignment.funcao} na escola {school.get('name', 'N/A')}",
            school_id=assignment.school_id,
            school_name=school.get('name'),
            academic_year=assignment.academic_year,
            new_value={'staff_id': assignment.staff_id, 'funcao': assignment.funcao, 'carga_horaria': assignment.carga_horaria}
        )

        return await db.school_assignments.find_one({"id": new_assignment.id}, {"_id": 0})

    @router.get("/school-assignments/staff/{staff_id}/schools")
    async def get_staff_schools(staff_id: str, request: Request, academic_year: Optional[int] = None):
        """Busca as escolas onde um servidor está lotado"""
        await AuthMiddleware.get_current_user(request)

        query = {
            "staff_id": staff_id,
            "status": "ativo"
        }
        if academic_year:
            query["academic_year"] = academic_year

        lotacoes = await db.school_assignments.find(query, {"_id": 0}).to_list(100)

        # Busca os dados das escolas
        schools = []
        for lot in lotacoes:
            school = await db.schools.find_one({"id": lot['school_id']}, {"_id": 0})
            if school:
                schools.append(school)

        return schools

    @router.put("/school-assignments/{assignment_id}")
    async def update_school_assignment(assignment_id: str, assignment_data: SchoolAssignmentUpdate, request: Request):
        """Atualiza lotação"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        existing = await db.school_assignments.find_one({"id": assignment_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Lotação não encontrada")

        update_data = {k: v for k, v in assignment_data.model_dump().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        await db.school_assignments.update_one({"id": assignment_id}, {"$set": update_data})

        # Auditoria de atualização de lotação
        staff = await db.staff.find_one({"id": existing.get('staff_id')}, {"_id": 0, "full_name": 1})
        school = await db.schools.find_one({"id": existing.get('school_id')}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='update',
            collection='school_assignments',
            user=current_user,
            request=request,
            document_id=assignment_id,
            description=f"Atualizou lotação do servidor {staff.get('nome', staff.get('full_name', 'N/A')) if staff else 'N/A'}",
            school_id=existing.get('school_id'),
            school_name=school.get('name') if school else None,
            academic_year=existing.get('academic_year'),
            old_value={'funcao': existing.get('funcao'), 'status': existing.get('status'), 'carga_horaria': existing.get('carga_horaria')},
            new_value=update_data
        )

        return await db.school_assignments.find_one({"id": assignment_id}, {"_id": 0})

    @router.delete("/school-assignments/{assignment_id}")
    async def delete_school_assignment(assignment_id: str, request: Request):
        """Remove lotação"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        existing = await db.school_assignments.find_one({"id": assignment_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Lotação não encontrada")

        # Guarda dados para auditoria
        staff = await db.staff.find_one({"id": existing.get('staff_id')}, {"_id": 0, "full_name": 1})
        school = await db.schools.find_one({"id": existing.get('school_id')}, {"_id": 0, "name": 1})

        await db.school_assignments.delete_one({"id": assignment_id})

        # Auditoria de exclusão de lotação
        await audit_service.log(
            action='delete',
            collection='school_assignments',
            user=current_user,
            request=request,
            document_id=assignment_id,
            description=f"EXCLUIU lotação do servidor {staff.get('nome', staff.get('full_name', 'N/A')) if staff else 'N/A'} da escola {school.get('name', 'N/A') if school else 'N/A'}",
            school_id=existing.get('school_id'),
            school_name=school.get('name') if school else None,
            academic_year=existing.get('academic_year'),
            old_value={'staff_id': existing.get('staff_id'), 'funcao': existing.get('funcao'), 'status': existing.get('status')}
        )

        return {"message": "Lotação removida com sucesso"}

    @router.get("/teacher-assignments")
    async def list_teacher_assignments(
        request: Request,
        school_id: Optional[str] = None,
        staff_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        status: Optional[str] = None
    ):
        """Lista alocações de professores"""
        await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3', 'diretor', 'coordenador', 'auxiliar_secretaria'])(request)
        current_user = await AuthMiddleware.get_current_user(request)

        query = {}
        if school_id:
            query["school_id"] = school_id
        if staff_id:
            query["staff_id"] = staff_id
        if class_id:
            query["class_id"] = class_id
        if course_id:
            query["course_id"] = course_id
        if academic_year:
            query["academic_year"] = academic_year
        if status:
            query["status"] = status

        # Multi-tenancy
        query = apply_tenant_filter(query, current_user, request)

        assignments = await db.teacher_assignments.find(query, {"_id": 0}).to_list(1000)

        # Enriquecer com dados
        for assign in assignments:
            staff = await db.staff.find_one({"id": assign['staff_id']}, {"_id": 0})
            if staff:
                assign['staff_name'] = staff.get('nome')

            turma = await db.classes.find_one({"id": assign['class_id']}, {"_id": 0, "name": 1})
            if turma:
                assign['class_name'] = turma['name']

            course = await db.courses.find_one({"id": assign['course_id']}, {"_id": 0, "name": 1})
            if course:
                assign['course_name'] = course['name']

            school = await db.schools.find_one({"id": assign['school_id']}, {"_id": 0, "name": 1})
            if school:
                assign['school_name'] = school['name']

        return assignments

    @router.post("/teacher-assignments")
    async def create_teacher_assignment(assignment: TeacherAssignmentCreate, request: Request):
        """Cria nova alocação de professor com integridade curricular fail-closed."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        staff, school, turma, course, tenant_id = await load_teacher_assignment_context(
            current_user=current_user,
            request=request,
            staff_id=assignment.staff_id,
            school_id=assignment.school_id,
            class_id=assignment.class_id,
            course_id=assignment.course_id,
        )
        if staff.get('cargo') != 'professor':
            raise HTTPException(status_code=400, detail="Servidor não é professor")

        try:
            integrity = validate_teacher_assignment_curriculum(
                class_info=turma,
                course=course,
                school_id=assignment.school_id,
                academic_year=assignment.academic_year,
            )
            workload_integrity = validate_teacher_assignment_workload(
                class_info=turma,
                course=course,
                weekly_workload=assignment.carga_horaria_semanal,
            )
        except TeacherAssignmentIntegrityError as exc:
            raise integrity_http_error(exc) from exc

        existing_query = apply_tenant_filter({
            "staff_id": assignment.staff_id,
            "class_id": assignment.class_id,
            "course_id": assignment.course_id,
            "academic_year": assignment.academic_year,
            "status": {"$in": ["ativo", "active"]},
        }, current_user, request)
        existing = await db.teacher_assignments.find_one(existing_query)
        if existing:
            raise HTTPException(status_code=400, detail="Este professor já está alocado para este componente nesta turma")

        new_assignment = TeacherAssignment(**assignment.model_dump())
        ta_doc = new_assignment.model_dump()
        ta_doc['mantenedora_id'] = tenant_id
        await db.teacher_assignments.insert_one(ta_doc)

        await audit_service.log(
            action='create',
            collection='teacher_assignments',
            user=current_user,
            request=request,
            document_id=new_assignment.id,
            description='Criou alocação docente com validação curricular P0-F7.9B + carga P0-F7.9D7.8',
            school_id=assignment.school_id,
            school_name=school.get('name'),
            academic_year=assignment.academic_year,
            new_value={
                'staff_id': assignment.staff_id,
                'class_id': assignment.class_id,
                'course_id': assignment.course_id,
                'status': assignment.status,
                'curricular_write_policy': integrity.get('write_policy'),
                'workload_write_policy': workload_integrity.get('workload_policy'),
                'canonical_weekly_workload': workload_integrity.get('canonical_weekly_workload'),
            },
        )

        return await db.teacher_assignments.find_one(
            apply_tenant_filter({"id": new_assignment.id}, current_user, request),
            {"_id": 0},
        )

    @router.post("/teacher-assignments/substitutions")
    async def create_teacher_substitution(assignment: TeacherAssignmentCreate, request: Request):
        """Cria substituição preservando as barreiras curricular e de carga da alocação titular."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        payload = assignment.model_dump()
        payload['is_substituicao'] = True

        staff, school, turma, course, tenant_id = await load_teacher_assignment_context(
            current_user=current_user,
            request=request,
            staff_id=payload['staff_id'],
            school_id=payload['school_id'],
            class_id=payload['class_id'],
            course_id=payload['course_id'],
        )
        if staff.get('cargo') != 'professor':
            raise HTTPException(status_code=400, detail="Servidor não é professor")

        if not payload.get('data_inicio_substituicao'):
            raise HTTPException(status_code=400, detail="Data de início da substituição é obrigatória")

        try:
            integrity = validate_teacher_assignment_curriculum(
                class_info=turma,
                course=course,
                school_id=payload['school_id'],
                academic_year=payload['academic_year'],
            )
        except TeacherAssignmentIntegrityError as exc:
            raise integrity_http_error(exc) from exc

        # Se não informou o titular, deduz a partir da alocação ativa naquela turma/componente.
        if not payload.get('substituted_staff_id'):
            titular_query = apply_tenant_filter({
                "class_id": payload['class_id'],
                "course_id": payload['course_id'],
                "academic_year": payload['academic_year'],
                "status": {"$in": ["ativo", "active"]},
                "is_substituicao": {"$ne": True},
            }, current_user, request)
            titular_assign = await db.teacher_assignments.find_one(
                titular_query,
                {"_id": 0, "staff_id": 1, "carga_horaria_semanal": 1},
            )
            if titular_assign:
                payload['substituted_staff_id'] = titular_assign.get('staff_id')
                if not payload.get('carga_horaria_semanal'):
                    payload['carga_horaria_semanal'] = titular_assign.get('carga_horaria_semanal')

        try:
            workload_integrity = validate_teacher_assignment_workload(
                class_info=turma,
                course=course,
                weekly_workload=payload.get('carga_horaria_semanal'),
            )
        except TeacherAssignmentIntegrityError as exc:
            raise integrity_http_error(exc) from exc

        new_assignment = TeacherAssignment(**payload)
        ta_doc = new_assignment.model_dump()
        ta_doc['mantenedora_id'] = tenant_id
        await db.teacher_assignments.insert_one(ta_doc)

        # Garantir que o substituto tenha lotação ativa na escola, para a Folha de Pagamento.
        school_assign_query = apply_tenant_filter({
            "staff_id": payload['staff_id'],
            "school_id": payload['school_id'],
            "status": "ativo",
        }, current_user, request)
        school_assign = await db.school_assignments.find_one(school_assign_query)
        if not school_assign:
            try:
                from models import SchoolAssignment
                lot_temp = SchoolAssignment(
                    staff_id=payload['staff_id'],
                    school_id=payload['school_id'],
                    funcao='professor',
                    tipo_lotacao='regular',
                    data_inicio=payload.get('data_inicio_substituicao') or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    data_fim=payload.get('data_fim_substituicao'),
                    carga_horaria=payload.get('carga_horaria_semanal'),
                    academic_year=payload['academic_year'],
                    status='ativo',
                    observacoes='Lotação criada automaticamente via Substituição',
                )
                lot_doc = lot_temp.model_dump()
                lot_doc['mantenedora_id'] = tenant_id
                await db.school_assignments.insert_one(lot_doc)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).warning(f"Não foi possível criar lotação auto p/ substituição: {e}")

        await audit_service.log(
            action='create',
            collection='teacher_assignments',
            user=current_user,
            request=request,
            document_id=new_assignment.id,
            description='Criou substituição docente com validação curricular P0-F7.9B + carga P0-F7.9D7.8',
            school_id=payload['school_id'],
            school_name=school.get('name'),
            academic_year=payload['academic_year'],
            new_value={
                'staff_id': payload['staff_id'],
                'class_id': payload['class_id'],
                'course_id': payload['course_id'],
                'is_substituicao': True,
                'curricular_write_policy': integrity.get('write_policy'),
                'workload_write_policy': workload_integrity.get('workload_policy'),
                'canonical_weekly_workload': workload_integrity.get('canonical_weekly_workload'),
            },
        )

        return await db.teacher_assignments.find_one(
            apply_tenant_filter({"id": new_assignment.id}, current_user, request),
            {"_id": 0},
        )

    @router.put("/teacher-assignments/{assignment_id}")
    async def update_teacher_assignment(assignment_id: str, assignment_data: TeacherAssignmentUpdate, request: Request):
        """Atualiza vínculo; vínculos ativos precisam continuar curricularmente válidos."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        existing_query = apply_tenant_filter({"id": assignment_id}, current_user, request)
        existing = await db.teacher_assignments.find_one(existing_query)
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")
        assert_same_tenant(existing, current_user, request)

        update_data = {k: v for k, v in assignment_data.model_dump().items() if v is not None}
        resulting = dict(existing)
        resulting.update(update_data)

        integrity = None
        workload_integrity = None
        # Encerramento/inativação de passivo histórico precisa permanecer possível.
        if is_active_teacher_assignment_status(resulting.get('status', 'ativo')):
            staff, school, turma, course, tenant_id = await load_teacher_assignment_context(
                current_user=current_user,
                request=request,
                staff_id=resulting['staff_id'],
                school_id=resulting['school_id'],
                class_id=resulting['class_id'],
                course_id=resulting['course_id'],
            )
            if str(existing.get('mantenedora_id') or '') != str(tenant_id):
                raise HTTPException(status_code=403, detail="Alocação pertence a outra mantenedora")
            if staff.get('cargo') != 'professor':
                raise HTTPException(status_code=400, detail="Servidor não é professor")
            try:
                integrity = validate_teacher_assignment_curriculum(
                    class_info=turma,
                    course=course,
                    school_id=resulting['school_id'],
                    academic_year=resulting['academic_year'],
                )
                workload_integrity = validate_teacher_assignment_workload(
                    class_info=turma,
                    course=course,
                    weekly_workload=resulting.get('carga_horaria_semanal'),
                )
            except TeacherAssignmentIntegrityError as exc:
                raise integrity_http_error(exc) from exc
        else:
            school = await db.schools.find_one(
                apply_tenant_filter({"id": resulting['school_id']}, current_user, request),
                {"_id": 0, "name": 1},
            )

        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        await db.teacher_assignments.update_one(existing_query, {"$set": update_data})

        await audit_service.log(
            action='update',
            collection='teacher_assignments',
            user=current_user,
            request=request,
            document_id=assignment_id,
            description='Atualizou alocação docente sob política de integridade P0-F7.9B + P0-F7.9D7.8',
            school_id=resulting.get('school_id'),
            school_name=school.get('name') if school else None,
            academic_year=resulting.get('academic_year'),
            old_value={
                'staff_id': existing.get('staff_id'),
                'class_id': existing.get('class_id'),
                'course_id': existing.get('course_id'),
                'status': existing.get('status'),
                'carga_horaria_semanal': existing.get('carga_horaria_semanal'),
            },
            new_value={
                **update_data,
                'curricular_write_policy': integrity.get('write_policy') if integrity else 'INACTIVE_REMEDIATION_ALLOWED',
                'workload_write_policy': workload_integrity.get('workload_policy') if workload_integrity else 'INACTIVE_REMEDIATION_ALLOWED',
                'canonical_weekly_workload': workload_integrity.get('canonical_weekly_workload') if workload_integrity else None,
            },
        )

        return await db.teacher_assignments.find_one(existing_query, {"_id": 0})

    @router.delete("/teacher-assignments/{assignment_id}")
    async def delete_teacher_assignment(assignment_id: str, request: Request):
        """Hard delete segue bloqueado; a tentativa passa a ser auditada."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        existing_query = apply_tenant_filter({"id": assignment_id}, current_user, request)
        existing = await db.teacher_assignments.find_one(existing_query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")
        assert_same_tenant(existing, current_user, request)

        school = await db.schools.find_one(
            apply_tenant_filter({"id": existing.get('school_id')}, current_user, request),
            {"_id": 0, "name": 1},
        )
        await audit_service.log(
            action='delete_blocked',
            collection='teacher_assignments',
            user=current_user,
            request=request,
            document_id=assignment_id,
            description='Tentativa de hard delete bloqueada pelo P0 Global',
            school_id=existing.get('school_id'),
            school_name=school.get('name') if school else None,
            academic_year=existing.get('academic_year'),
            old_value={
                'staff_id': existing.get('staff_id'),
                'class_id': existing.get('class_id'),
                'course_id': existing.get('course_id'),
                'status': existing.get('status'),
            },
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code": "TEACHER_ASSIGNMENT_HARD_DELETE_DISABLED_P0",
                "message": (
                    "Exclusão física de vínculo docente está bloqueada pelo P0 Global. "
                    "Use atualização de status/encerramento até a consolidação da fonte canônica."
                ),
                "assignment_id": assignment_id,
            },
        )

    return router