"""
Router de Matrículas - SIGESC
Endpoints para gestão de matrículas de alunos.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Enrollment, EnrollmentCreate, EnrollmentUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/enrollments", tags=["Matrículas"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=Enrollment, status_code=status.HTTP_201_CREATED)
    async def create_enrollment(enrollment_data: EnrollmentCreate, request: Request):
        """Cria nova matrícula"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        enrollment_obj = Enrollment(**enrollment_data.model_dump())
        doc = enrollment_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.enrollments.insert_one(doc)
        
        # Sincroniza dados do aluno com a matrícula (school_id, class_id, status)
        await db.students.update_one(
            {"id": enrollment_data.student_id},
            {"$set": {
                "school_id": enrollment_data.school_id,
                "class_id": enrollment_data.class_id,
                "status": "active"
            }}
        )
        
        # Auditoria de criação de matrícula
        student = await db.students.find_one({"id": enrollment_data.student_id}, {"_id": 0, "full_name": 1})
        school = await db.schools.find_one({"id": enrollment_data.school_id}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='create',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment_obj.id,
            description=f"Criou matrícula do aluno {student.get('full_name', 'N/A') if student else 'N/A'}",
            school_id=enrollment_data.school_id,
            school_name=school.get('name') if school else None,
            academic_year=enrollment_data.academic_year,
            new_value={'student_id': enrollment_data.student_id, 'class_id': enrollment_data.class_id}
        )
        
        return enrollment_obj

    @router.get("", response_model=List[Enrollment])
    async def list_enrollments(request: Request, student_id: Optional[str] = None, class_id: Optional[str] = None, skip: int = 0, limit: int = 100):
        """Lista matrículas"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        filter_query = {}
        if student_id:
            filter_query['student_id'] = student_id
        if class_id:
            filter_query['class_id'] = class_id
        
        enrollments = await db.enrollments.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        return enrollments

    @router.get("/{enrollment_id}", response_model=Enrollment)
    async def get_enrollment(enrollment_id: str, request: Request):
        """Busca matrícula por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        enrollment_doc = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
        
        if not enrollment_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada"
            )
        
        return Enrollment(**enrollment_doc)

    @router.put("/{enrollment_id}", response_model=Enrollment)
    async def update_enrollment(enrollment_id: str, enrollment_update: EnrollmentUpdate, request: Request):
        """Atualiza matrícula"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        # Busca matrícula atual para obter student_id
        existing_enrollment = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
        if not existing_enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada"
            )
        
        update_data = enrollment_update.model_dump(exclude_unset=True)
        
        if update_data:
            await db.enrollments.update_one(
                {"id": enrollment_id},
                {"$set": update_data}
            )
            
            # Sincroniza dados do aluno se school_id, class_id ou status mudaram
            student_update = {}
            if 'school_id' in update_data:
                student_update['school_id'] = update_data['school_id']
            if 'class_id' in update_data:
                student_update['class_id'] = update_data['class_id']
            if 'status' in update_data:
                # Se matrícula foi cancelada/transferida, atualiza status do aluno
                if update_data['status'] in ['cancelled', 'transferred']:
                    student_update['status'] = 'transferred'
                elif update_data['status'] == 'active':
                    student_update['status'] = 'active'
            
            if student_update:
                await db.students.update_one(
                    {"id": existing_enrollment['student_id']},
                    {"$set": student_update}
                )
            
            # Auditoria de atualização de matrícula
            student = await db.students.find_one({"id": existing_enrollment['student_id']}, {"_id": 0, "full_name": 1})
            await audit_service.log(
                action='update',
                collection='enrollments',
                user=current_user,
                request=request,
                document_id=enrollment_id,
                description=f"Atualizou matrícula do aluno {student.get('full_name', 'N/A') if student else 'N/A'}",
                school_id=update_data.get('school_id') or existing_enrollment.get('school_id'),
                academic_year=existing_enrollment.get('academic_year'),
                old_value={'status': existing_enrollment.get('status'), 'class_id': existing_enrollment.get('class_id')},
                new_value=update_data
            )
        
        updated_enrollment = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
        return Enrollment(**updated_enrollment)

    @router.delete("/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_enrollment(enrollment_id: str, request: Request):
        """Deleta matrícula"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        # Busca matrícula antes de deletar para auditoria
        existing = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada"
            )
        
        result = await db.enrollments.delete_one({"id": enrollment_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matrícula não encontrada"
            )
        
        # Auditoria de exclusão de matrícula
        student = await db.students.find_one({"id": existing.get('student_id')}, {"_id": 0, "full_name": 1})
        await audit_service.log(
            action='delete',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment_id,
            description=f"EXCLUIU matrícula do aluno {student.get('full_name', 'N/A') if student else 'N/A'}",
            school_id=existing.get('school_id'),
            academic_year=existing.get('academic_year'),
            old_value={'student_id': existing.get('student_id'), 'class_id': existing.get('class_id'), 'status': existing.get('status')}
        )
        
        return None

    return router
