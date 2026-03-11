"""
Router para Pré-Matrícula.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Pré-Matrícula"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.post("/pre-matricula", response_model=PreMatricula, status_code=status.HTTP_201_CREATED)
    async def create_pre_matricula(pre_matricula: PreMatriculaCreate):
        """Cria uma nova pré-matrícula (rota pública - não requer autenticação)"""
        # Verifica se a escola existe e tem pré-matrícula ativa
        school = await db.schools.find_one(
            {"id": pre_matricula.school_id, "pre_matricula_ativa": True, "status": "active"},
            {"_id": 0}
        )

        if not school:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Escola não encontrada ou pré-matrícula não está ativa"
            )

        # Cria a pré-matrícula
        pre_matricula_obj = PreMatricula(**pre_matricula.model_dump())
        doc = pre_matricula_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()

        await db.pre_matriculas.insert_one(doc)

        return pre_matricula_obj


    @router.get("/pre-matriculas", response_model=List[PreMatricula])
    async def list_pre_matriculas(
        request: Request,
        school_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ):
        """Lista pré-matrículas (apenas admin, secretário, diretor)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        query = {}

        # Filtro por escola
        if school_id:
            query['school_id'] = school_id
        elif current_user['role'] not in ['admin']:
            # Não-admin só vê das escolas vinculadas
            query['school_id'] = {"$in": current_user['school_ids']}

        # Filtro por status
        if status_filter:
            query['status'] = status_filter

        pre_matriculas = await db.pre_matriculas.find(
            query, {"_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

        return pre_matriculas


    @router.get("/pre-matriculas/{pre_matricula_id}", response_model=PreMatricula)
    async def get_pre_matricula(pre_matricula_id: str, request: Request):
        """Busca pré-matrícula por ID"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        pre_matricula = await db.pre_matriculas.find_one(
            {"id": pre_matricula_id}, {"_id": 0}
        )

        if not pre_matricula:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pré-matrícula não encontrada"
            )

        # Verifica acesso à escola
        if current_user['role'] not in ['admin']:
            if pre_matricula['school_id'] not in current_user['school_ids']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acesso negado a esta pré-matrícula"
                )

        return pre_matricula


    @router.put("/pre-matriculas/{pre_matricula_id}/status")
    async def update_pre_matricula_status(
        pre_matricula_id: str,
        request: Request,
        new_status: str = Query(..., description="Novo status: analisando, aprovada, rejeitada"),
        rejection_reason: Optional[str] = None
    ):
        """Atualiza status da pré-matrícula"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        if new_status not in ['analisando', 'aprovada', 'rejeitada']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status inválido"
            )

        update_data = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "analyzed_by": current_user['id'],
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }

        if new_status == 'rejeitada' and rejection_reason:
            update_data['rejection_reason'] = rejection_reason

        result = await db.pre_matriculas.update_one(
            {"id": pre_matricula_id},
            {"$set": update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pré-matrícula não encontrada"
            )

        return {"message": "Status atualizado com sucesso"}


    @router.post("/pre-matriculas/{pre_matricula_id}/convert")
    async def convert_pre_matricula_to_student(
        pre_matricula_id: str,
        request: Request,
        class_id: Optional[str] = Query(None, description="ID da turma para matricular o aluno")
    ):
        """
        Converte uma pré-matrícula aprovada em um novo aluno.
        Cria o registro do aluno com os dados da pré-matrícula.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)

        # Buscar a pré-matrícula
        pre_matricula = await db.pre_matriculas.find_one(
            {"id": pre_matricula_id}, {"_id": 0}
        )

        if not pre_matricula:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pré-matrícula não encontrada"
            )

        # Verificar se a pré-matrícula está aprovada
        if pre_matricula.get('status') != 'aprovada':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Apenas pré-matrículas aprovadas podem ser convertidas em alunos"
            )

        # Verificar se já foi convertida
        if pre_matricula.get('converted_student_id'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta pré-matrícula já foi convertida em aluno"
            )

        # Buscar a escola para obter o próximo número de matrícula
        school = await db.schools.find_one(
            {"id": pre_matricula['school_id']}, {"_id": 0}
        )

        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )

        # Gerar número de matrícula único
        current_year = datetime.now().year
        student_count = await db.students.count_documents({"school_id": pre_matricula['school_id']})
        enrollment_number = f"{current_year}{str(student_count + 1).zfill(5)}"

        # Mapear parentesco para tipo de responsável legal
        parentesco_map = {
            'mae': 'mother',
            'pai': 'father',
            'avo': 'other',
            'tio': 'other',
            'responsavel': 'other',
            'outro': 'other'
        }

        # Criar o documento do aluno
        student_id = str(uuid.uuid4())
        student_data = {
            "id": student_id,
            "school_id": pre_matricula['school_id'],
            "enrollment_number": enrollment_number,
            "full_name": pre_matricula.get('aluno_nome'),
            "birth_date": pre_matricula.get('aluno_data_nascimento'),
            "sex": pre_matricula.get('aluno_sexo'),
            "cpf": pre_matricula.get('aluno_cpf'),

            # Responsável
            "guardian_name": pre_matricula.get('responsavel_nome'),
            "guardian_cpf": pre_matricula.get('responsavel_cpf'),
            "guardian_phone": pre_matricula.get('responsavel_telefone'),
            "guardian_relationship": pre_matricula.get('responsavel_parentesco'),
            "legal_guardian_type": parentesco_map.get(pre_matricula.get('responsavel_parentesco', ''), 'other'),

            # Turma (se fornecida)
            "class_id": class_id,

            # Observações
            "observations": f"Aluno criado a partir da pré-matrícula. Email do responsável: {pre_matricula.get('responsavel_email', 'N/A')}",

            # Status
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Inserir o aluno
        await db.students.insert_one(student_data)

        # Atualizar a pré-matrícula como convertida
        await db.pre_matriculas.update_one(
            {"id": pre_matricula_id},
            {"$set": {
                "status": "convertida",
                "converted_student_id": student_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Registrar no histórico do aluno
        history_doc = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": pre_matricula['school_id'],
            "school_name": school.get('name', 'N/A'),
            "class_id": class_id,
            "class_name": None,
            "action_type": "matricula",
            "previous_status": None,
            "new_status": "active",
            "observations": f"Matrícula criada a partir de pré-matrícula online (ID: {pre_matricula_id})",
            "user_id": current_user['id'],
            "user_name": current_user.get('full_name', current_user.get('email')),
            "action_date": datetime.now(timezone.utc).isoformat()
        }

        # Se tiver turma, buscar o nome
        if class_id:
            class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "name": 1})
            if class_doc:
                history_doc["class_name"] = class_doc.get('name')

        await db.student_history.insert_one(history_doc)

        # Registrar no audit log
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "create",
            "collection": "students",
            "document_id": student_id,
            "user_id": current_user['id'],
            "user_email": current_user.get('email'),
            "user_role": current_user.get('role'),
            "user_name": current_user.get('full_name'),
            "school_id": pre_matricula['school_id'],
            "school_name": school.get('name'),
            "description": f"Aluno '{pre_matricula.get('aluno_nome')}' criado a partir de pré-matrícula online",
            "new_value": {
                "full_name": pre_matricula.get('aluno_nome'),
                "enrollment_number": enrollment_number,
                "pre_matricula_id": pre_matricula_id
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "info",
            "category": "academic"
        })

        return {
            "message": "Pré-matrícula convertida em aluno com sucesso",
            "student_id": student_id,
            "enrollment_number": enrollment_number,
            "student_name": pre_matricula.get('aluno_nome')
        }

    # ============= ANNOUNCEMENT ENDPOINTS =============

    def can_user_create_announcement(user: dict, recipient: dict) -> bool:
        """Verifica se o usuário pode criar um aviso para os destinatários especificados"""
        user_role = user.get('role', '')
        user_school_links = user.get('school_links', [])
        user_school_ids = [link['school_id'] for link in user_school_links]

        recipient_type = recipient.get('type', '')

        # Admin pode enviar para qualquer um
        if user_role == 'admin':
            return True

        # Secretário, Diretor, Coordenador - limitado à escola
        if user_role in ['secretario', 'diretor', 'coordenador', 'auxiliar_secretaria']:
            if recipient_type == 'school':
                # Só pode enviar para escolas vinculadas
                target_schools = recipient.get('school_ids', [])
                return all(s in user_school_ids for s in target_schools)
            elif recipient_type == 'class':
                # Classes precisam ser da escola vinculada (verificar no momento da criação)
                return True
            elif recipient_type == 'individual':
                # Pode enviar para usuários da escola
                return True
            elif recipient_type == 'role':
                # Pode enviar para roles dentro da escola
                return True

        # Professor - limitado às turmas
        if user_role == 'professor':
            if recipient_type in ['class', 'individual']:
                # Verificar se as turmas são vinculadas ao professor
                return True
            return False

        return False

    async def get_announcement_target_users(db, recipient: dict, sender: dict) -> List[str]:
        """Obtém a lista de user_ids que devem receber o aviso"""
        target_user_ids = []
        recipient_type = recipient.get('type', '')
        sender_role = sender.get('role', '')
        sender_school_ids = [link['school_id'] for link in sender.get('school_links', [])]

        if recipient_type == 'individual':
            # Usuários específicos
            target_user_ids = recipient.get('user_ids', [])

        elif recipient_type == 'role':
            # Todos os usuários com os papéis especificados
            target_roles = recipient.get('target_roles', [])
            query = {'role': {'$in': target_roles}, 'status': 'active'}

            # Se não for admin, limitar à escola
            if sender_role != 'admin':
                query['school_links.school_id'] = {'$in': sender_school_ids}

            users = await db.users.find(query, {'_id': 0, 'id': 1}).to_list(10000)
            target_user_ids = [u['id'] for u in users]

        elif recipient_type == 'school':
            # Todos os usuários das escolas
            school_ids = recipient.get('school_ids', [])
            users = await db.users.find(
                {'school_links.school_id': {'$in': school_ids}, 'status': 'active'},
                {'_id': 0, 'id': 1}
            ).to_list(10000)
            target_user_ids = [u['id'] for u in users]

        elif recipient_type == 'class':
            # Alunos/responsáveis das turmas (via matrículas)
            class_ids = recipient.get('class_ids', [])
            enrollments = await db.enrollments.find(
                {'class_id': {'$in': class_ids}, 'status': 'active'},
                {'_id': 0, 'student_id': 1}
            ).to_list(10000)

            student_ids = [e['student_id'] for e in enrollments]

            # Buscar usuários dos alunos (se houver) e responsáveis
            students = await db.students.find(
                {'id': {'$in': student_ids}},
                {'_id': 0, 'user_id': 1, 'guardian_id': 1}
            ).to_list(10000)

            for student in students:
                if student.get('user_id'):
                    target_user_ids.append(student['user_id'])
                # Buscar usuário do responsável
                if student.get('guardian_id'):
                    guardian = await db.guardians.find_one(
                        {'id': student['guardian_id']},
                        {'_id': 0, 'user_id': 1}
                    )
                    if guardian and guardian.get('user_id'):
                        target_user_ids.append(guardian['user_id'])

        return list(set(target_user_ids))  # Remover duplicatas



    return router
