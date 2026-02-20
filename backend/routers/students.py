"""
Router de Alunos - SIGESC
PATCH 4.x: Rotas de alunos extraídas do server.py

Endpoints para gestão de alunos incluindo:
- CRUD básico
- Remanejamento de turma
- Transferência entre escolas
- Histórico de movimentações
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from datetime import datetime, timezone
import uuid

from models import Student, StudentCreate, StudentUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/students", tags=["Alunos"])


def setup_students_router(db, audit_service, sandbox_db=None):
    """Configura o router de alunos com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
        return db

    @router.post("", response_model=Student, status_code=status.HTTP_201_CREATED)
    async def create_student(student_data: StudentCreate, request: Request):
        """Cria novo aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verifica acesso à escola
        await AuthMiddleware.verify_school_access(request, student_data.school_id)
        
        student_obj = Student(**student_data.model_dump())
        doc = student_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await current_db.students.insert_one(doc)
        
        # Se o aluno tem turma, cria a matrícula automaticamente
        if student_obj.class_id and student_obj.status == 'active':
            academic_year = datetime.now().year
            
            # Gera número de matrícula
            last_enrollment = await current_db.enrollments.find_one(
                {"academic_year": academic_year},
                sort=[("enrollment_number", -1)]
            )
            if last_enrollment and last_enrollment.get('enrollment_number'):
                try:
                    last_num = int(str(last_enrollment['enrollment_number'])[-5:])
                    new_enrollment_number = f"{academic_year}{str(last_num + 1).zfill(5)}"
                except:
                    new_enrollment_number = f"{academic_year}00001"
            else:
                new_enrollment_number = f"{academic_year}00001"
            
            enrollment_doc = {
                "id": str(uuid.uuid4()),
                "student_id": student_obj.id,
                "school_id": student_obj.school_id,
                "class_id": student_obj.class_id,
                "academic_year": academic_year,
                "status": "active",
                "enrollment_number": new_enrollment_number,
                "enrollment_date": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            }
            await current_db.enrollments.insert_one(enrollment_doc)
        
        # Registra auditoria
        school = await current_db.schools.find_one({"id": student_data.school_id}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='create',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_obj.id,
            description=f"Cadastrou aluno: {student_obj.full_name}",
            school_id=student_data.school_id,
            school_name=school.get('name') if school else None,
            new_value={'full_name': student_obj.full_name, 'cpf': student_obj.cpf, 'class_id': student_obj.class_id}
        )
        
        return student_obj

    @router.get("")
    async def list_students(
        request: Request, 
        school_id: Optional[str] = None, 
        class_id: Optional[str] = None, 
        skip: int = 0, 
        limit: int = 5000
    ):
        """Lista alunos com filtros opcionais"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Constrói filtro
        filter_query = {}
        
        # Admin, admin_teste, SEMED e Secretário podem ver TODOS os alunos
        if current_user['role'] in ['admin', 'admin_teste', 'semed', 'secretario']:
            if school_id:
                filter_query['school_id'] = school_id
            if class_id:
                filter_query['class_id'] = class_id
        else:
            # Outros papéis veem apenas das escolas vinculadas
            if school_id and school_id in current_user.get('school_ids', []):
                filter_query['school_id'] = school_id
            else:
                filter_query['school_id'] = {"$in": current_user.get('school_ids', [])}
            
            if class_id:
                filter_query['class_id'] = class_id
        
        students = await current_db.students.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Garante compatibilidade com registros antigos
        for student in students:
            student.setdefault('full_name', '')
            student.setdefault('inep_code', None)
            student.setdefault('sex', None)
            student.setdefault('nationality', 'Brasileira')
            student.setdefault('birth_city', None)
            student.setdefault('birth_state', None)
            student.setdefault('color_race', None)
            student.setdefault('cpf', None)
            student.setdefault('rg', None)
            student.setdefault('nis', None)
            student.setdefault('status', 'active')
            student.setdefault('authorized_persons', [])
            student.setdefault('benefits', [])
            student.setdefault('disabilities', [])
            student.setdefault('documents_urls', [])
        
        return students

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        """Busca aluno por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Verifica acesso à escola do aluno
        await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
        
        return Student(**student_doc)

    @router.put("/{student_id}", response_model=Student)
    async def update_student(student_id: str, student_update: StudentUpdate, request: Request):
        """
        Atualiza aluno com suporte a:
        - Edição de dados básicos
        - Remanejamento (mudança de turma na mesma escola)
        - Preparação para transferência (mudança de status)
        
        NOTA: Coordenadores NÃO podem editar alunos (apenas visualizar).
        """
        current_user = await AuthMiddleware.require_roles_with_coordinator_edit(
            ['admin', 'admin_teste', 'secretario', 'coordenador'], 
            'students'
        )(request)
        current_db = get_db_for_user(current_user)
        
        # Busca aluno
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Verifica permissões de acesso
        user_school_ids = current_user.get('school_ids', [])
        current_school_id = student_doc.get('school_id')
        student_status = student_doc.get('status', '')
        
        # Admin tem acesso total
        if current_user.get('role') in ['admin', 'admin_teste']:
            pass
        elif current_user.get('role') == 'secretario':
            is_active = student_status in ['active', 'Ativo']
            is_from_user_school = current_school_id in user_school_ids if current_school_id else False
            
            if is_active and not is_from_user_school:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você só pode editar alunos ativos da sua escola"
                )
        elif current_user.get('role') not in ['semed']:
            if current_school_id and current_school_id not in user_school_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para editar alunos desta escola"
                )
        
        update_data = student_update.model_dump(exclude_unset=True)
        
        if not update_data:
            return Student(**student_doc)
        
        # Detecta tipo de operação
        old_class_id = student_doc.get('class_id')
        old_school_id = student_doc.get('school_id')
        old_status = student_doc.get('status')
        new_class_id = update_data.get('class_id', old_class_id)
        new_school_id = update_data.get('school_id', old_school_id)
        new_status = update_data.get('status', old_status)
        
        # VALIDAÇÃO: Não permite status "Ativo" sem escola e turma definidas
        if new_status == 'active':
            final_school_id = new_school_id or old_school_id
            final_class_id = new_class_id or old_class_id
            
            if not final_school_id or not final_class_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível definir o status como 'Ativo' sem escola e turma definidas. O aluno precisa estar matriculado em uma turma."
                )
        
        action_type = 'edicao'
        history_obs = None
        
        # Verifica se é mudança de turma (remanejamento)
        if new_class_id and new_class_id != old_class_id and new_school_id == old_school_id:
            action_type = 'remanejamento'
            
            academic_year = datetime.now().year
            await current_db.enrollments.update_one(
                {"student_id": student_id, "school_id": old_school_id, "status": "active", "academic_year": academic_year},
                {"$set": {"class_id": new_class_id}}
            )
            
            new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
            history_obs = f"Remanejado para turma: {new_class.get('name') if new_class else new_class_id}"
        
        # Verifica se é mudança de status para transferência
        if new_status != old_status:
            if new_status == 'transferred':
                action_type = 'transferencia_saida'
                history_obs = "Aluno marcado para transferência"
                
                await current_db.enrollments.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {"status": "transferred"}}
                )
            
            # Se está sendo matriculado (de transferido/inativo para ativo)
            elif new_status == 'active' and old_status in ['transferred', 'inactive', 'dropout', None, '']:
                action_type = 'matricula'
                academic_year = update_data.get('academic_year', datetime.now().year)
                
                # Verifica se já existe matrícula ativa para esse ano
                existing_enrollment = await current_db.enrollments.find_one({
                    "student_id": student_id,
                    "class_id": new_class_id,
                    "academic_year": academic_year,
                    "status": "active"
                })
                
                if not existing_enrollment and new_school_id and new_class_id:
                    # Gera número de matrícula
                    last_enrollment = await current_db.enrollments.find_one(
                        {"academic_year": academic_year},
                        sort=[("enrollment_number", -1)]
                    )
                    if last_enrollment and last_enrollment.get('enrollment_number'):
                        try:
                            last_num = int(str(last_enrollment['enrollment_number'])[-5:])
                            new_enrollment_number = f"{academic_year}{str(last_num + 1).zfill(5)}"
                        except:
                            new_enrollment_number = f"{academic_year}00001"
                    else:
                        new_enrollment_number = f"{academic_year}00001"
                    
                    # Cria nova matrícula
                    new_enrollment = {
                        "id": str(uuid.uuid4()),
                        "student_id": student_id,
                        "school_id": new_school_id,
                        "class_id": new_class_id,
                        "academic_year": academic_year,
                        "enrollment_number": new_enrollment_number,
                        "status": "active",
                        "enrollment_date": datetime.now(timezone.utc).isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await current_db.enrollments.insert_one(new_enrollment)
                    
                    new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
                    history_obs = f"Matriculado na turma {new_class.get('name') if new_class else new_class_id} - Ano letivo {academic_year} - Matrícula: {new_enrollment_number}"
        
        # Remove academic_year do update_data pois não é um campo do aluno
        update_data.pop('academic_year', None)
        
        # Atualiza o aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": update_data}
        )
        
        # Busca dados para o histórico
        school = await current_db.schools.find_one({"id": new_school_id or old_school_id}, {"_id": 0, "name": 1})
        class_info = await current_db.classes.find_one({"id": new_class_id or old_class_id}, {"_id": 0, "name": 1})
        
        # Registra no histórico
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": new_school_id or old_school_id,
            "school_name": school.get('name') if school else 'N/A',
            "class_id": new_class_id or old_class_id,
            "class_name": class_info.get('name') if class_info else 'N/A',
            "action_type": action_type,
            "previous_status": old_status,
            "new_status": new_status,
            "observations": history_obs,
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.student_history.insert_one(history_entry)
        
        # Registra auditoria
        await audit_service.log(
            action='update',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_id,
            description=f"Atualizou aluno: {student_doc.get('full_name')} - {action_type}",
            school_id=new_school_id or old_school_id,
            school_name=school.get('name') if school else None,
            old_value={'class_id': old_class_id, 'school_id': old_school_id, 'status': old_status},
            new_value={'class_id': new_class_id, 'school_id': new_school_id, 'status': new_status},
            extra_data={'action_type': action_type, 'observations': history_obs}
        )
        
        updated_student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        return Student(**updated_student)

    @router.get("/{student_id}/history")
    async def get_student_history(student_id: str, request: Request):
        """Retorna o histórico de movimentações do aluno"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0, "school_id": 1})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        history = await current_db.student_history.find(
            {"student_id": student_id},
            {"_id": 0}
        ).sort("action_date", -1).to_list(100)
        
        return history

    @router.post("/{student_id}/transfer")
    async def transfer_student(student_id: str, request: Request):
        """
        Transfere aluno para outra escola.
        Requer que o aluno esteja com status 'transferred' na escola de origem.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        body = await request.json()
        new_school_id = body.get('school_id')
        new_class_id = body.get('class_id')
        academic_year = body.get('academic_year', datetime.now().year)
        
        if not new_school_id or not new_class_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="school_id e class_id são obrigatórios"
            )
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        if student.get('status') != 'transferred':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O aluno precisa estar com status 'Transferido' para ser matriculado em outra escola"
            )
        
        if student.get('school_id') == new_school_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A escola de destino deve ser diferente da escola atual"
            )
        
        new_school = await current_db.schools.find_one({"id": new_school_id}, {"_id": 0, "name": 1})
        new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
        
        if not new_school or not new_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola ou turma de destino não encontrada"
            )
        
        # Gera número de matrícula
        last_enrollment = await current_db.enrollments.find_one(
            {"academic_year": academic_year},
            sort=[("enrollment_number", -1)]
        )
        if last_enrollment and last_enrollment.get('enrollment_number'):
            try:
                last_num = int(str(last_enrollment['enrollment_number'])[-5:])
                new_enrollment_number = f"{academic_year}{str(last_num + 1).zfill(5)}"
            except:
                new_enrollment_number = f"{academic_year}00001"
        else:
            new_enrollment_number = f"{academic_year}00001"
        
        # Cria nova matrícula
        enrollment_id = str(uuid.uuid4())
        new_enrollment = {
            "id": enrollment_id,
            "student_id": student_id,
            "school_id": new_school_id,
            "class_id": new_class_id,
            "academic_year": academic_year,
            "enrollment_number": new_enrollment_number,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.enrollments.insert_one(new_enrollment)
        
        # Atualiza dados do aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": {
                "school_id": new_school_id,
                "class_id": new_class_id,
                "status": "active"
            }}
        )
        
        # Registra no histórico
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": new_school_id,
            "school_name": new_school.get('name'),
            "class_id": new_class_id,
            "class_name": new_class.get('name'),
            "enrollment_id": enrollment_id,
            "action_type": "transferencia_entrada",
            "previous_status": "transferred",
            "new_status": "active",
            "observations": f"Transferido da escola anterior. Nova matrícula: {new_enrollment_number}",
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.student_history.insert_one(history_entry)
        
        updated_student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        return {
            "message": "Aluno transferido com sucesso",
            "student": updated_student,
            "enrollment": new_enrollment
        }

    @router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_student(student_id: str, request: Request):
        """Deleta aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
        
        result = await current_db.students.delete_one({"id": student_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Registra auditoria
        school = await current_db.schools.find_one({"id": student_doc.get('school_id')}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='delete',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_id,
            description=f"EXCLUIU aluno: {student_doc.get('full_name')} (CPF: {student_doc.get('cpf', 'N/A')})",
            school_id=student_doc.get('school_id'),
            school_name=school.get('name') if school else None,
            old_value={'full_name': student_doc.get('full_name'), 'cpf': student_doc.get('cpf'), 'class_id': student_doc.get('class_id')}
        )
        
        return None

    @router.post("/{student_id}/copy-data")
    async def copy_student_data_to_new_class(student_id: str, request: Request):
        """
        Copia dados de frequência e notas do aluno da turma de origem para a turma de destino.
        Usado durante remanejamento e progressão.
        
        - Remanejamento: copia frequência E notas
        - Progressão (mesma escola): copia apenas frequência
        
        Os dados na turma de origem são mantidos, mas ficam bloqueados para edição pelo professor.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        body = await request.json()
        source_class_id = body.get('source_class_id')
        target_class_id = body.get('target_class_id')
        copy_type = body.get('copy_type', 'remanejamento')  # 'remanejamento' ou 'progressao'
        academic_year = body.get('academic_year', datetime.now().year)
        
        if not source_class_id or not target_class_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_class_id e target_class_id são obrigatórios"
            )
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        copied_data = {
            "attendance_records": 0,
            "grades_records": 0
        }
        
        # Copia frequência - SEMPRE copiado (remanejamento e progressão)
        attendances = await current_db.attendance.find({
            "class_id": source_class_id,
            "academic_year": academic_year,
            "records.student_id": student_id
        }, {"_id": 0}).to_list(1000)
        
        for att in attendances:
            # Verifica se já existe frequência para esta data na turma destino
            existing = await current_db.attendance.find_one({
                "class_id": target_class_id,
                "date": att['date'],
                "academic_year": academic_year
            })
            
            # Extrai o registro do aluno
            student_record = None
            for rec in att.get('records', []):
                if rec['student_id'] == student_id:
                    student_record = rec
                    break
            
            if student_record:
                if existing:
                    # Adiciona o registro do aluno na frequência existente
                    existing_records = existing.get('records', [])
                    # Remove registro antigo do aluno se existir
                    existing_records = [r for r in existing_records if r['student_id'] != student_id]
                    existing_records.append(student_record)
                    
                    await current_db.attendance.update_one(
                        {"id": existing['id']},
                        {"$set": {"records": existing_records}}
                    )
                else:
                    # Cria nova frequência para a turma destino
                    new_attendance = {
                        "id": str(uuid.uuid4()),
                        "class_id": target_class_id,
                        "date": att['date'],
                        "academic_year": academic_year,
                        "records": [student_record],
                        "period": att.get('period', 'regular'),
                        "course_id": att.get('course_id'),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await current_db.attendance.insert_one(new_attendance)
                
                copied_data["attendance_records"] += 1
        
        # Copia notas - APENAS para remanejamento (mesma série)
        if copy_type == 'remanejamento':
            grades = await current_db.grades.find({
                "class_id": source_class_id,
                "student_id": student_id,
                "academic_year": academic_year
            }, {"_id": 0}).to_list(100)
            
            for grade in grades:
                # Verifica se já existe nota para este componente na turma destino
                existing_grade = await current_db.grades.find_one({
                    "class_id": target_class_id,
                    "student_id": student_id,
                    "course_id": grade['course_id'],
                    "academic_year": academic_year
                })
                
                if not existing_grade:
                    # Cria nova nota na turma destino
                    new_grade = {
                        **grade,
                        "id": str(uuid.uuid4()),
                        "class_id": target_class_id,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await current_db.grades.insert_one(new_grade)
                    copied_data["grades_records"] += 1
        
        return {
            "message": f"Dados copiados com sucesso ({copy_type})",
            "student_id": student_id,
            "source_class_id": source_class_id,
            "target_class_id": target_class_id,
            "copied_data": copied_data
        }

    return router
