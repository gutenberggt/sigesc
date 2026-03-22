"""
Router de Alunos - SIGESC
PATCH 4.x: Rotas de alunos extraídas do server.py

Endpoints para gestão de alunos incluindo:
- CRUD básico
- Remanejamento de turma
- Transferência entre escolas
- Histórico de movimentações
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from typing import Optional
from datetime import datetime, timezone
import uuid
from pymongo.errors import DuplicateKeyError

from models import Student, StudentCreate, StudentUpdate
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase

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
        
        # VALIDAÇÃO: Não permite status "Ativo" sem escola e turma definidas
        if student_data.status == 'active':
            if not student_data.school_id or not student_data.class_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível criar aluno com status 'Ativo' sem escola e turma definidas. O aluno precisa estar matriculado em uma turma."
                )
        
        student_dict = format_data_uppercase(student_data.model_dump())
        student_obj = Student(**student_dict)
        doc = student_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await current_db.students.insert_one(doc)
        
        # Se o aluno tem turma, cria a matrícula automaticamente
        if student_obj.class_id and student_obj.status == 'active':
            academic_year = datetime.now().year
            
            # Busca grade_level da turma para student_series
            class_info = await current_db.classes.find_one(
                {"id": student_obj.class_id}, {"_id": 0, "grade_level": 1}
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
            
            enrollment_doc = {
                "id": str(uuid.uuid4()),
                "student_id": student_obj.id,
                "school_id": student_obj.school_id,
                "class_id": student_obj.class_id,
                "academic_year": academic_year,
                "status": "active",
                "student_series": student_data.student_series or (class_info.get('grade_level') if class_info else None),
                "enrollment_number": new_enrollment_number,
                "enrollment_date": student_data.enrollment_date or datetime.now().isoformat(),
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
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        skip: int = 0, 
        limit: int = 5000
    ):
        """Lista alunos com filtros, busca e paginação server-side"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Constrói filtro
        filter_query = {}
        
        # Admin, admin_teste, SEMED, SEMED3, Secretário e Assistente Social podem ver TODOS os alunos
        if current_user['role'] in ['admin', 'admin_teste', 'semed', 'semed3', 'secretario', 'ass_social']:
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
        
        # Filtro por status
        if status:
            filter_query['status'] = status
        
        # Busca por nome ou CPF
        if search and len(search) >= 3:
            search_upper = search.upper()
            search_clean = search.replace('.', '').replace('-', '').replace('/', '')
            filter_query['$or'] = [
                {'full_name': {'$regex': search_upper, '$options': 'i'}},
                {'cpf': {'$regex': search_clean}}
            ]
        
        # Conta total para paginação
        total = await current_db.students.count_documents(filter_query)
        
        # Conta alunos ativos (para exibição no frontend)
        active_filter = {**filter_query, 'status': 'active'}
        active_count = await current_db.students.count_documents(active_filter) if not status else (total if status == 'active' else 0)
        
        # Calcula skip com base na página
        effective_skip = (page - 1) * page_size if page > 0 else skip
        effective_limit = page_size if page > 0 else limit
        
        # Projeta apenas campos necessários para listagem (mais leve)
        list_projection = {
            "_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1,
            "status": 1, "cpf": 1, "birth_date": 1, "sex": 1, "inep_code": 1,
            "student_series": 1
        }
        
        students = await current_db.students.find(
            filter_query, list_projection
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).skip(effective_skip).limit(effective_limit).to_list(effective_limit)
        
        # Busca student_series das matrículas ativas (batch)
        student_ids = [s.get('id') for s in students if s.get('id')]
        if student_ids:
            enrollments = await current_db.enrollments.find(
                {"student_id": {"$in": student_ids}, "status": "active"},
                {"_id": 0, "student_id": 1, "student_series": 1}
            ).to_list(None)
            enrollment_series_map = {e['student_id']: e.get('student_series') for e in enrollments}
        else:
            enrollment_series_map = {}
        
        # Garante compatibilidade e inclui student_series
        for student in students:
            student.setdefault('full_name', '')
            student.setdefault('status', 'active')
            student['student_series'] = enrollment_series_map.get(student.get('id'))
        
        return {
            "items": students,
            "total": total,
            "active_count": active_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }

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
            ['admin', 'admin_teste', 'secretario', 'coordenador', 'auxiliar_secretaria'], 
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
        
        # Extrai campos auxiliares ANTES de qualquer lógica de negócio
        custom_action_date = update_data.pop('action_date', None)
        action_hint = update_data.pop('action_hint', None)
        
        # Converte dados para maiúsculas
        update_data = format_data_uppercase(update_data)
        
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
        
        # Verifica se é mudança de turma (remanejamento ou progressão)
        if new_class_id and new_class_id != old_class_id and new_school_id == old_school_id:
            if action_hint == 'progressao':
                action_type = 'progressao'
                enrollment_inactive_status = 'progressed'
            else:
                action_type = 'remanejamento'
                enrollment_inactive_status = 'relocated'
            
            academic_year = datetime.now().year
            
            # Marca a matrícula antiga como inativa (mantém registro na turma de origem)
            await current_db.enrollments.update_one(
                {"student_id": student_id, "school_id": old_school_id, "class_id": old_class_id, "status": "active", "academic_year": academic_year},
                {"$set": {"status": enrollment_inactive_status}}
            )
            
            # Cria nova matrícula ativa na turma de destino
            old_enrollment = await current_db.enrollments.find_one(
                {"student_id": student_id, "school_id": old_school_id, "class_id": old_class_id, "academic_year": academic_year},
                {"_id": 0}
            )
            new_enrollment = {
                "id": str(uuid.uuid4()),
                "student_id": student_id,
                "school_id": old_school_id,
                "class_id": new_class_id,
                "academic_year": academic_year,
                "status": "active",
                "enrollment_number": old_enrollment.get("enrollment_number") if old_enrollment else None,
                "student_series": update_data.get('student_series') or (old_enrollment.get("student_series") if old_enrollment else None)
            }
            await current_db.enrollments.insert_one(new_enrollment)
            
            new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
            if action_type == 'progressao':
                history_obs = f"Progressão para turma: {new_class.get('name') if new_class else new_class_id}"
            else:
                history_obs = f"Remanejado para turma: {new_class.get('name') if new_class else new_class_id}"
        
        # Proteção contra re-matrícula quando aluno já está ativo (UI stale / clique duplo)
        if new_status == 'active' and old_status == 'active' and new_class_id and new_class_id == old_class_id:
            # Aluno já está ativo nesta turma - ignora silenciosamente (idempotente)
            pass
        elif new_status == 'active' and old_status == 'active' and new_class_id and new_class_id != old_class_id:
            # Aluno já ativo tentando mudar de turma - tratar como remanejamento, não matrícula
            pass
        
        # Verifica se é mudança de status para transferência
        if new_status != old_status:
            if new_status == 'transferred':
                action_type = 'transferencia_saida'
                history_obs = "Aluno marcado para transferência"
                
                await current_db.enrollments.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {"status": "transferred"}}
                )
            
            elif new_status == 'dropout':
                action_type = 'desistencia'
                history_obs = "Aluno registrado como desistente"
                
                await current_db.enrollments.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {"status": "dropout"}}
                )
            
            elif new_status == 'cancelled':
                action_type = 'cancelamento'
                history_obs = "Matrícula cancelada"
                academic_year = datetime.now().year
                
                # Busca matrículas ativas para obter class_ids e school_ids antes de deletar
                active_enrollments_cursor = current_db.enrollments.find(
                    {"student_id": student_id, "status": "active"},
                    {"_id": 0, "class_id": 1, "school_id": 1, "id": 1}
                )
                active_enrollments = await active_enrollments_cursor.to_list(50)
                cancelled_class_ids = list(set(e.get('class_id') for e in active_enrollments if e.get('class_id')))
                
                # 1. Remover aluno dos registros de frequência das turmas
                if cancelled_class_ids:
                    await current_db.attendance.update_many(
                        {"class_id": {"$in": cancelled_class_ids}},
                        {"$pull": {"records": {"student_id": student_id}}}
                    )
                
                # 2. Deletar notas do aluno nas turmas
                if cancelled_class_ids:
                    await current_db.grades.delete_many(
                        {"student_id": student_id, "class_id": {"$in": cancelled_class_ids}}
                    )
                
                # 3. Deletar as matrículas ativas (não apenas marcar como cancelled)
                await current_db.enrollments.delete_many(
                    {"student_id": student_id, "status": "active"}
                )
                
                # 4. Status do aluno: inativo, sem escola e turma
                update_data['status'] = 'inactive'
                update_data['school_id'] = ''
                update_data['class_id'] = ''
                new_status = 'inactive'
            
            # Se está sendo matriculado (de transferido/inativo para ativo)
            elif new_status == 'active' and old_status in ['transferred', 'inactive', 'dropout', None, '']:
                action_type = 'matricula'
                academic_year = update_data.get('academic_year', datetime.now().year)
                
                # Verifica o tipo da turma de destino
                target_class = await current_db.classes.find_one(
                    {"id": new_class_id}, {"_id": 0, "atendimento_programa": 1, "name": 1}
                )
                target_programa = (target_class.get('atendimento_programa', '') or '').strip().lower() if target_class else ''
                
                # Turmas especiais que permitem matrícula mesmo com aluno já ativo
                turmas_especiais = {'aee', 'recomposicao_aprendizagem', 'reforco_escolar'}
                is_turma_especial = target_programa in turmas_especiais
                
                # Se NÃO é turma especial, verifica se aluno já está ativo em turma regular
                if not is_turma_especial:
                    # Busca TODAS as matrículas ativas do aluno no mesmo ano
                    active_cursor = current_db.enrollments.find({
                        "student_id": student_id,
                        "academic_year": academic_year,
                        "status": "active"
                    })
                    active_enrollments = await active_cursor.to_list(50)
                    
                    for enr in active_enrollments:
                        enr_class = await current_db.classes.find_one(
                            {"id": enr.get('class_id')},
                            {"_id": 0, "atendimento_programa": 1, "name": 1}
                        )
                        enr_programa = (enr_class.get('atendimento_programa', '') or '').strip().lower() if enr_class else ''
                        
                        if enr_programa not in turmas_especiais:
                            turma_nome = enr_class.get('name', '') if enr_class else ''
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Este aluno já possui matrícula ativa na turma '{turma_nome}' no ano letivo {academic_year}. Para rematrícula, primeiro cancele ou transfira a matrícula atual."
                            )
                
                # Verifica se já existe matrícula ativa na MESMA turma
                existing_enrollment = await current_db.enrollments.find_one({
                    "student_id": student_id,
                    "class_id": new_class_id,
                    "academic_year": academic_year,
                    "status": "active"
                })
                
                if existing_enrollment:
                    turma_nome = target_class.get('name', '') if target_class else ''
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Este aluno já está matriculado nesta turma '{turma_nome}' no ano letivo {academic_year}."
                    )
                
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
                        "student_series": update_data.get('student_series') or (target_class.get('grade_level') if target_class else None),
                        "status": "active",
                        "enrollment_date": update_data.get('enrollment_date') or (f"{custom_action_date}T12:00:00+00:00" if custom_action_date else datetime.now(timezone.utc).isoformat()),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    try:
                        await current_db.enrollments.insert_one(new_enrollment)
                    except DuplicateKeyError:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Este aluno já possui matrícula ativa nesta turma. Não é possível duplicar."
                        )
                    
                    new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
                    history_obs = f"Matriculado na turma {new_class.get('name') if new_class else new_class_id} - Ano letivo {academic_year} - Matrícula: {new_enrollment_number}"
        
        # Remove academic_year do update_data pois não é campo do aluno
        update_data.pop('academic_year', None)
        
        # Atualiza o aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": update_data}
        )
        
        # Propaga student_series para a matrícula ativa (se foi alterado)
        if 'student_series' in update_data:
            await current_db.enrollments.update_one(
                {"student_id": student_id, "status": "active", "academic_year": datetime.now().year},
                {"$set": {"student_series": update_data['student_series']}}
            )
        
        # Propaga enrollment_date para a matrícula ativa (se foi alterado)
        if 'enrollment_date' in update_data:
            await current_db.enrollments.update_one(
                {"student_id": student_id, "status": "active", "academic_year": datetime.now().year},
                {"$set": {"enrollment_date": update_data['enrollment_date']}}
            )
        
        # Busca dados para o histórico
        school = await current_db.schools.find_one({"id": new_school_id or old_school_id}, {"_id": 0, "name": 1})
        class_info = await current_db.classes.find_one({"id": new_class_id or old_class_id}, {"_id": 0, "name": 1})
        
        # Define a data da ação: usa a data informada pelo usuário ou a data atual
        if custom_action_date:
            history_action_date = f"{custom_action_date}T12:00:00+00:00"
        else:
            history_action_date = datetime.now(timezone.utc).isoformat()
        
        # Define class_id do histórico: para remanejamento/progressão, usa a turma de ORIGEM
        history_class_id = old_class_id if action_type in ('remanejamento', 'progressao') else (new_class_id or old_class_id)
        
        # Registra no histórico
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": new_school_id or old_school_id,
            "school_name": school.get('name') if school else 'N/A',
            "class_id": history_class_id,
            "class_name": class_info.get('name') if class_info else 'N/A',
            "action_type": action_type,
            "previous_status": old_status,
            "new_status": new_status,
            "observations": history_obs,
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": history_action_date
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
        new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1, "grade_level": 1})
        
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
            "student_series": student_doc.get('student_series') or (new_class.get('grade_level') if new_class else None),
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

    # ============= CPF VALIDATION =============

    def validate_cpf_algorithm(cpf: str) -> bool:
        """Valida CPF usando o algoritmo oficial brasileiro."""
        if not cpf:
            return False
        numbers = ''.join(filter(str.isdigit, cpf))
        if len(numbers) != 11:
            return False
        if len(set(numbers)) == 1:
            return False
        total = sum(int(numbers[i]) * (10 - i) for i in range(9))
        remainder = (total * 10) % 11
        if remainder == 10:
            remainder = 0
        if remainder != int(numbers[9]):
            return False
        total = sum(int(numbers[i]) * (11 - i) for i in range(10))
        remainder = (total * 10) % 11
        if remainder == 10:
            remainder = 0
        if remainder != int(numbers[10]):
            return False
        return True

    @router.get("/validate-cpf/{cpf}")
    async def validate_cpf(cpf: str, request: Request):
        """Valida se um CPF é válido usando o algoritmo oficial."""
        await AuthMiddleware.get_current_user(request)
        cpf_numbers = ''.join(filter(str.isdigit, cpf))
        is_valid = validate_cpf_algorithm(cpf_numbers)
        return {
            "cpf": cpf_numbers,
            "is_valid": is_valid,
            "message": "CPF válido" if is_valid else "CPF inválido"
        }

    @router.get("/check-cpf-duplicate/{cpf}")
    async def check_cpf_duplicate(
        cpf: str,
        request: Request,
        context: str = Query("student", description="Contexto: 'student' ou 'staff'"),
        exclude_id: Optional[str] = Query(None, description="ID para excluir da verificação")
    ):
        """Verifica se um CPF já está cadastrado no sistema."""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        cpf_numbers = ''.join(filter(str.isdigit, cpf))
        if len(cpf_numbers) != 11:
            return {"is_duplicate": False, "message": "CPF incompleto"}
        
        duplicates = []
        def normalize_cpf(cpf_value):
            if not cpf_value:
                return ""
            return ''.join(filter(str.isdigit, str(cpf_value)))
        
        cpf_regex = '.*'.join(cpf_numbers)
        
        student_query = {"cpf": {"$regex": cpf_regex}}
        if context == "student" and exclude_id:
            student_query["id"] = {"$ne": exclude_id}
        student_with_cpf = await current_db.students.find_one(student_query, {"_id": 0, "id": 1, "full_name": 1, "cpf": 1})
        if student_with_cpf and normalize_cpf(student_with_cpf.get("cpf")) == cpf_numbers:
            if context != "staff":
                duplicates.append({
                    "type": "student",
                    "name": student_with_cpf.get("full_name"),
                    "message": f"CPF já cadastrado para o aluno: {student_with_cpf.get('full_name')}"
                })
        
        staff_query = {"cpf": {"$regex": cpf_regex}}
        if context == "staff" and exclude_id:
            staff_query["id"] = {"$ne": exclude_id}
        staff_with_cpf = await current_db.staff.find_one(staff_query, {"_id": 0, "id": 1, "nome": 1, "cpf": 1})
        if staff_with_cpf and normalize_cpf(staff_with_cpf.get("cpf")) == cpf_numbers:
            if context != "student":
                duplicates.append({
                    "type": "staff",
                    "name": staff_with_cpf.get("nome"),
                    "message": f"CPF já cadastrado para o servidor: {staff_with_cpf.get('nome')}"
                })
        
        parent_query = {"$or": [
            {"father_cpf": {"$regex": cpf_regex}},
            {"mother_cpf": {"$regex": cpf_regex}}
        ]}
        parent_student = await current_db.students.find_one(parent_query, {"_id": 0, "id": 1, "full_name": 1, "father_name": 1, "mother_name": 1, "father_cpf": 1, "mother_cpf": 1})
        if parent_student:
            if context != "staff":
                parent_name = None
                if normalize_cpf(parent_student.get("father_cpf")) == cpf_numbers:
                    parent_name = parent_student.get("father_name", "Pai")
                elif normalize_cpf(parent_student.get("mother_cpf")) == cpf_numbers:
                    parent_name = parent_student.get("mother_name", "Mãe")
                if parent_name:
                    duplicates.append({
                        "type": "parent",
                        "name": parent_name,
                        "student_name": parent_student.get("full_name"),
                        "message": f"CPF já cadastrado como responsável ({parent_name}) do aluno: {parent_student.get('full_name')}"
                    })
        
        return {
            "cpf": cpf_numbers,
            "is_duplicate": len(duplicates) > 0,
            "duplicates": duplicates,
            "message": duplicates[0]["message"] if duplicates else "CPF disponível"
        }

    return router
