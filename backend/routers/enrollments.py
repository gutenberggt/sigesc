"""
Router de Matrículas - SIGESC
Endpoints para gestão de matrículas de alunos.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional
from pymongo.errors import DuplicateKeyError

from models import Enrollment, EnrollmentCreate, EnrollmentUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/enrollments", tags=["Matrículas"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=Enrollment, status_code=status.HTTP_201_CREATED)
    async def create_enrollment(enrollment_data: EnrollmentCreate, request: Request):
        """Cria nova matrícula com validação de duplicidade"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        # Verifica o tipo da turma de destino
        target_class = await db.classes.find_one(
            {"id": enrollment_data.class_id}, {"_id": 0, "atendimento_programa": 1, "name": 1}
        )
        target_programa = (target_class.get('atendimento_programa', '') or '').strip().lower() if target_class else ''
        turmas_especiais = {'aee', 'recomposicao_aprendizagem', 'reforco_escolar'}
        is_turma_especial = target_programa in turmas_especiais
        
        # Verifica duplicidade na MESMA turma
        existing_same_class = await db.enrollments.find_one({
            "student_id": enrollment_data.student_id,
            "class_id": enrollment_data.class_id,
            "academic_year": enrollment_data.academic_year,
            "status": "active"
        })
        if existing_same_class:
            turma_nome = target_class.get('name', '') if target_class else ''
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Este aluno já está matriculado nesta turma '{turma_nome}' no ano letivo {enrollment_data.academic_year}."
            )
        
        # Se NÃO é turma especial, verifica se aluno já está ativo em turma regular
        if not is_turma_especial:
            # Busca TODAS as matrículas ativas do aluno no mesmo ano
            active_cursor = db.enrollments.find({
                "student_id": enrollment_data.student_id,
                "academic_year": enrollment_data.academic_year,
                "status": "active"
            })
            active_enrollments = await active_cursor.to_list(50)
            
            for enr in active_enrollments:
                enr_class = await db.classes.find_one(
                    {"id": enr.get('class_id')},
                    {"_id": 0, "atendimento_programa": 1, "name": 1}
                )
                enr_programa = (enr_class.get('atendimento_programa', '') or '').strip().lower() if enr_class else ''
                if enr_programa not in turmas_especiais:
                    turma_nome = enr_class.get('name', '') if enr_class else ''
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Este aluno já possui matrícula ativa na turma regular '{turma_nome}' no ano letivo {enrollment_data.academic_year}. Não é permitido duplicar matrícula em turma regular."
                    )
        
        enrollment_obj = Enrollment(**enrollment_data.model_dump())
        doc = enrollment_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        try:
            await db.enrollments.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este aluno já possui matrícula ativa nesta turma. Não é possível duplicar."
            )
        
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

    @router.post("/cancel-enrollment", status_code=status.HTTP_200_OK)
    async def cancel_enrollment(request: Request):
        """Cancela um vínculo ativo de aluno com turma específica (mantém histórico)."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        body = await request.json()
        student_id = body.get('student_id')
        class_id = body.get('class_id')
        reason = body.get('reason', '')

        if not student_id or not class_id:
            raise HTTPException(status_code=400, detail="student_id e class_id são obrigatórios")

        # Busca matrícula ativa do aluno nesta turma
        enrollment = await db.enrollments.find_one({
            "student_id": student_id,
            "class_id": class_id,
            "status": "active"
        }, {"_id": 0})

        if not enrollment:
            raise HTTPException(status_code=404, detail="Nenhuma matrícula ativa encontrada para este aluno nesta turma")

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Cancela a matrícula (mantém o registro)
        await db.enrollments.update_one(
            {"id": enrollment['id']},
            {"$set": {
                "status": "cancelled",
                "cancellation_reason": reason,
                "cancellation_date": now,
                "cancelled_by": current_user.get('id', '')
            }}
        )

        # Se o class_id do aluno é o mesmo da turma cancelada, limpar
        student = await db.students.find_one({"id": student_id}, {"_id": 0, "full_name": 1, "class_id": 1})
        student_name = student.get('full_name', 'N/A') if student else 'N/A'

        if student and student.get('class_id') == class_id:
            # Verifica se há outra matrícula ativa para atualizar o class_id
            other_enrollment = await db.enrollments.find_one({
                "student_id": student_id,
                "status": "active",
                "class_id": {"$ne": class_id}
            }, {"_id": 0, "class_id": 1})

            new_class_id = other_enrollment['class_id'] if other_enrollment else None
            await db.students.update_one(
                {"id": student_id},
                {"$set": {"class_id": new_class_id}}
            )

        # Busca nome da turma para auditoria
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "name": 1})
        class_name = class_doc.get('name', 'N/A') if class_doc else 'N/A'

        # Auditoria
        await audit_service.log(
            action='cancel',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id=enrollment['id'],
            description=f"CANCELOU vínculo do aluno {student_name} com a turma {class_name}. Motivo: {reason}",
            school_id=enrollment.get('school_id'),
            academic_year=enrollment.get('academic_year'),
            old_value={'student_id': student_id, 'class_id': class_id, 'status': 'active'},
            new_value={'status': 'cancelled', 'reason': reason}
        )

        return {"message": f"Vínculo do aluno {student_name} com a turma {class_name} cancelado com sucesso."}

    return router
