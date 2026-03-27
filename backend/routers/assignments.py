"""
Router para Lotações.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from datetime import datetime, timezone

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Lotações"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



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

        query = {}
        if school_id:
            query["school_id"] = school_id
        if staff_id:
            query["staff_id"] = staff_id
        if status:
            query["status"] = status
        if academic_year:
            query["academic_year"] = academic_year

        assignments = await db.school_assignments.find(query, {"_id": 0}).to_list(1000)

        # Enriquecer com dados
        for assign in assignments:
            staff = await db.staff.find_one({"id": assign['staff_id']}, {"_id": 0})
            if staff:
                assign['staff'] = staff

            school = await db.schools.find_one({"id": assign['school_id']}, {"_id": 0, "name": 1})
            if school:
                assign['school_name'] = school['name']

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
        await db.school_assignments.insert_one(new_assignment.model_dump())

        # Auditoria de criação de lotação
        await audit_service.log(
            action='create',
            collection='school_assignments',
            user=current_user,
            request=request,
            document_id=new_assignment.id,
            description=f"Criou lotação do servidor {staff.get('full_name', 'N/A')} como {assignment.funcao} na escola {school.get('name', 'N/A')}",
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
            description=f"Atualizou lotação do servidor {staff.get('full_name', 'N/A') if staff else 'N/A'}",
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
            description=f"EXCLUIU lotação do servidor {staff.get('full_name', 'N/A') if staff else 'N/A'} da escola {school.get('name', 'N/A') if school else 'N/A'}",
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
        """Cria nova alocação de professor"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        # Verifica se servidor existe e é professor
        staff = await db.staff.find_one({"id": assignment.staff_id})
        if not staff:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")
        if staff['cargo'] != 'professor':
            raise HTTPException(status_code=400, detail="Servidor não é professor")

        # Verifica se turma existe
        turma = await db.classes.find_one({"id": assignment.class_id})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Verifica se componente existe
        course = await db.courses.find_one({"id": assignment.course_id})
        if not course:
            raise HTTPException(status_code=404, detail="Componente curricular não encontrado")

        # Verifica se o MESMO professor já está alocado para o MESMO componente na MESMA turma/ano
        # (permite múltiplos componentes na mesma turma, mas não duplicar a mesma alocação)
        existing = await db.teacher_assignments.find_one({
            "staff_id": assignment.staff_id,
            "class_id": assignment.class_id,
            "course_id": assignment.course_id,
            "academic_year": assignment.academic_year,
            "status": "ativo"
        })
        if existing:
            raise HTTPException(status_code=400, detail="Este professor já está alocado para este componente nesta turma")

        new_assignment = TeacherAssignment(**assignment.model_dump())
        await db.teacher_assignments.insert_one(new_assignment.model_dump())

        return await db.teacher_assignments.find_one({"id": new_assignment.id}, {"_id": 0})


    @router.put("/teacher-assignments/{assignment_id}")
    async def update_teacher_assignment(assignment_id: str, assignment_data: TeacherAssignmentUpdate, request: Request):
        """Atualiza alocação de professor"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        existing = await db.teacher_assignments.find_one({"id": assignment_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")

        update_data = {k: v for k, v in assignment_data.model_dump().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        await db.teacher_assignments.update_one({"id": assignment_id}, {"$set": update_data})

        return await db.teacher_assignments.find_one({"id": assignment_id}, {"_id": 0})


    @router.delete("/teacher-assignments/{assignment_id}")
    async def delete_teacher_assignment(assignment_id: str, request: Request):
        """Remove alocação de professor"""
        await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        existing = await db.teacher_assignments.find_one({"id": assignment_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")

        await db.teacher_assignments.delete_one({"id": assignment_id})
        return {"message": "Alocação removida com sucesso"}



    return router
