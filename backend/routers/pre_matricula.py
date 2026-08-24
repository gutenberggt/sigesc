"""
Router para Pré-Matrícula.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from typing import List, Optional
from datetime import datetime, timezone
import logging
import uuid

from models import *
from auth_middleware import AuthMiddleware
from services.enrollment_service import (
    EnrollmentConflictError,
    EnrollmentDomainError,
    EnrollmentNotFoundError,
    EnrollmentValidationError,
    create_active_enrollment,
)


router = APIRouter(tags=["Pré-Matrícula"])
logger = logging.getLogger(__name__)


def _raise_enrollment_http(exc: EnrollmentDomainError):
    if isinstance(exc, EnrollmentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, EnrollmentConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, EnrollmentValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""

    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.post("/pre-matricula", response_model=PreMatricula, status_code=status.HTTP_201_CREATED)
    async def create_pre_matricula(pre_matricula: PreMatriculaCreate):
        """Cria uma nova pré-matrícula (rota pública - não requer autenticação)."""
        school = await db.schools.find_one(
            {"id": pre_matricula.school_id, "pre_matricula_ativa": True, "status": "active"},
            {"_id": 0},
        )
        if not school:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Escola não encontrada ou pré-matrícula não está ativa",
            )

        pre_matricula_obj = PreMatricula(**pre_matricula.model_dump())
        doc = pre_matricula_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        if school.get("mantenedora_id"):
            doc["mantenedora_id"] = school.get("mantenedora_id")

        await db.pre_matriculas.insert_one(doc)
        return pre_matricula_obj

    @router.get("/pre-matriculas", response_model=List[PreMatricula])
    async def list_pre_matriculas(
        request: Request,
        school_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ):
        """Lista pré-matrículas (apenas admin, secretário, diretor)."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
        query = {}
        if school_id:
            query['school_id'] = school_id
        elif current_user['role'] not in ['admin']:
            query['school_id'] = {"$in": current_user['school_ids']}
        if status_filter:
            query['status'] = status_filter

        return await db.pre_matriculas.find(
            query, {"_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    @router.get("/pre-matriculas/{pre_matricula_id}", response_model=PreMatricula)
    async def get_pre_matricula(pre_matricula_id: str, request: Request):
        """Busca pré-matrícula por ID."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
        pre_matricula = await db.pre_matriculas.find_one(
            {"id": pre_matricula_id}, {"_id": 0}
        )
        if not pre_matricula:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pré-matrícula não encontrada",
            )
        if current_user['role'] not in ['admin']:
            if pre_matricula['school_id'] not in current_user['school_ids']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acesso negado a esta pré-matrícula",
                )
        return pre_matricula

    @router.put("/pre-matriculas/{pre_matricula_id}/status")
    async def update_pre_matricula_status(
        pre_matricula_id: str,
        request: Request,
        new_status: str = Query(..., description="Novo status: analisando, aprovada, rejeitada"),
        rejection_reason: Optional[str] = None,
    ):
        """Atualiza status da pré-matrícula."""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
        if new_status not in ['analisando', 'aprovada', 'rejeitada']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status inválido",
            )

        update_data = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "analyzed_by": current_user['id'],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        if new_status == 'rejeitada' and rejection_reason:
            update_data['rejection_reason'] = rejection_reason

        result = await db.pre_matriculas.update_one(
            {"id": pre_matricula_id}, {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pré-matrícula não encontrada",
            )
        return {"message": "Status atualizado com sucesso"}

    @router.post("/pre-matriculas/{pre_matricula_id}/convert")
    async def convert_pre_matricula_to_student(
        pre_matricula_id: str,
        request: Request,
        class_id: str = Query(..., description="ID da turma REGULAR para efetivar a matrícula"),
    ):
        """Converte pré-matrícula aprovada em estudante + matrícula canônica.

        A conversão só é concluída depois que existe um documento em ``students``
        e o vínculo correspondente em ``enrollments``. O estudante é criado
        inicialmente como inativo/sem turma e só se torna ativo pela projeção
        produzida pelo serviço canônico de matrícula.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
        current_db = get_db_for_user(current_user)

        pre_matricula = await db.pre_matriculas.find_one(
            {"id": pre_matricula_id}, {"_id": 0}
        )
        if not pre_matricula:
            raise HTTPException(status_code=404, detail="Pré-matrícula não encontrada")
        if pre_matricula.get('status') != 'aprovada':
            if pre_matricula.get('status') == 'convertida' or pre_matricula.get('converted_student_id'):
                raise HTTPException(status_code=409, detail="Esta pré-matrícula já foi convertida em estudante")
            raise HTTPException(
                status_code=400,
                detail="Apenas pré-matrículas aprovadas podem ser convertidas em estudantes",
            )
        if pre_matricula.get('converted_student_id'):
            raise HTTPException(status_code=409, detail="Esta pré-matrícula já foi convertida em estudante")

        school = await current_db.schools.find_one(
            {"id": pre_matricula['school_id']}, {"_id": 0}
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(status_code=422, detail="Turma selecionada não existe")
        if class_doc.get("school_id") != pre_matricula['school_id']:
            raise HTTPException(
                status_code=422,
                detail="A turma selecionada pertence a outra escola",
            )
        if str(class_doc.get("atendimento_programa") or "").strip().lower() in {
            "aee", "recomposicao_aprendizagem", "reforco_escolar"
        }:
            raise HTTPException(
                status_code=422,
                detail="A conversão da pré-matrícula deve ocorrer primeiro em uma turma regular",
            )

        await AuthMiddleware.verify_school_access(request, pre_matricula['school_id'])

        parentesco_map = {
            'mae': 'mother',
            'pai': 'father',
            'avo': 'other',
            'tio': 'other',
            'responsavel': 'other',
            'outro': 'other',
        }

        student_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Claim otimista contra cliques/processos concorrentes. O modelo legado
        # persiste converted_student_id=None, portanto não usamos $exists=False
        # nesse campo. O pré-check acima garante que ele ainda não foi convertido.
        claim = await db.pre_matriculas.update_one(
            {
                "id": pre_matricula_id,
                "status": "aprovada",
                "$or": [
                    {"conversion_lock_id": {"$exists": False}},
                    {"conversion_lock_id": None},
                    {"conversion_lock_id": ""},
                ],
            },
            {"$set": {
                "conversion_lock_id": student_id,
                "conversion_started_at": now,
            }},
        )
        if claim.matched_count == 0:
            raise HTTPException(
                status_code=409,
                detail="Esta pré-matrícula já está sendo convertida ou já foi convertida",
            )

        student_data = {
            "id": student_id,
            "school_id": pre_matricula['school_id'],
            "class_id": None,
            "enrollment_number": None,
            "full_name": pre_matricula.get('aluno_nome'),
            "birth_date": pre_matricula.get('aluno_data_nascimento'),
            "sex": pre_matricula.get('aluno_sexo'),
            "cpf": pre_matricula.get('aluno_cpf'),
            "guardian_name": pre_matricula.get('responsavel_nome'),
            "guardian_cpf": pre_matricula.get('responsavel_cpf'),
            "guardian_phone": pre_matricula.get('responsavel_telefone'),
            "guardian_relationship": pre_matricula.get('responsavel_parentesco'),
            "legal_guardian_type": parentesco_map.get(
                pre_matricula.get('responsavel_parentesco', ''), 'other'
            ),
            "observations": (
                "Aluno criado a partir da pré-matrícula. "
                f"Email do responsável: {pre_matricula.get('responsavel_email', 'N/A')}"
            ),
            "status": "inactive",
            "created_at": now,
        }
        if school.get("mantenedora_id"):
            student_data["mantenedora_id"] = school.get("mantenedora_id")

        enrollment_id = None
        try:
            await current_db.students.insert_one(student_data)
            academic_year = int(class_doc.get("academic_year") or datetime.now().year)
            result = await create_active_enrollment(
                current_db,
                student_id=student_id,
                school_id=pre_matricula['school_id'],
                class_id=class_id,
                academic_year=academic_year,
                enrollment_date=now,
                mantenedora_id=school.get("mantenedora_id"),
                source="pre_matricula",
            )
            enrollment = result["enrollment"]
            enrollment_id = enrollment["id"]
            enrollment_number = enrollment["enrollment_number"]

            converted = await db.pre_matriculas.update_one(
                {"id": pre_matricula_id, "conversion_lock_id": student_id},
                {
                    "$set": {
                        "status": "convertida",
                        "converted_student_id": student_id,
                        "converted_enrollment_id": enrollment_id,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "$unset": {
                        "conversion_lock_id": "",
                        "conversion_started_at": "",
                    },
                },
            )
            if converted.matched_count == 0:
                raise RuntimeError("Falha ao consolidar o estado da pré-matrícula convertida")
        except EnrollmentDomainError as exc:
            if enrollment_id:
                await current_db.enrollments.delete_one({"id": enrollment_id})
            await current_db.students.delete_one({"id": student_id})
            await db.pre_matriculas.update_one(
                {"id": pre_matricula_id, "conversion_lock_id": student_id},
                {"$unset": {"conversion_lock_id": "", "conversion_started_at": ""}},
            )
            _raise_enrollment_http(exc)
        except Exception:
            if enrollment_id:
                await current_db.enrollments.delete_one({"id": enrollment_id})
            await current_db.students.delete_one({"id": student_id})
            await db.pre_matriculas.update_one(
                {"id": pre_matricula_id, "conversion_lock_id": student_id},
                {"$unset": {"conversion_lock_id": "", "conversion_started_at": ""}},
            )
            raise

        history_doc = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": pre_matricula['school_id'],
            "school_name": school.get('name', 'N/A'),
            "class_id": class_id,
            "class_name": class_doc.get('name'),
            "action_type": "matricula",
            "previous_status": None,
            "new_status": "active",
            "observations": (
                f"Matrícula canônica criada a partir de pré-matrícula online "
                f"(ID: {pre_matricula_id}; enrollment_id: {enrollment_id})"
            ),
            "user_id": current_user['id'],
            "user_name": current_user.get('full_name', current_user.get('email')),
            "action_date": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await current_db.student_history.insert_one(history_doc)
        except Exception:
            logger.exception(
                "Falha ao registrar student_history da conversão %s; matrícula %s permanece válida",
                pre_matricula_id,
                enrollment_id,
            )

        try:
            await current_db.audit_logs.insert_one({
                "id": str(uuid.uuid4()),
                "action": "create",
                "collection": "enrollments",
                "document_id": enrollment_id,
                "user_id": current_user['id'],
                "user_email": current_user.get('email'),
                "user_role": current_user.get('role'),
                "user_name": current_user.get('full_name'),
                "school_id": pre_matricula['school_id'],
                "school_name": school.get('name'),
                "description": (
                    f"Aluno '{pre_matricula.get('aluno_nome')}' e matrícula canônica "
                    "criados a partir de pré-matrícula online"
                ),
                "new_value": {
                    "student_id": student_id,
                    "class_id": class_id,
                    "enrollment_number": enrollment_number,
                    "pre_matricula_id": pre_matricula_id,
                    "canonical_source": "enrollments",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": "info",
                "category": "academic",
                "mantenedora_id": school.get("mantenedora_id"),
            })
        except Exception:
            logger.exception(
                "Falha ao registrar audit_log da conversão %s; matrícula %s permanece válida",
                pre_matricula_id,
                enrollment_id,
            )

        return {
            "message": "Pré-matrícula convertida em estudante e matrícula com sucesso",
            "student_id": student_id,
            "enrollment_id": enrollment_id,
            "enrollment_number": enrollment_number,
            "student_name": pre_matricula.get('aluno_nome'),
        }

    # ============= ANNOUNCEMENT ENDPOINTS =============

    def can_user_create_announcement(user: dict, recipient: dict) -> bool:
        """Verifica se o usuário pode criar um aviso para os destinatários especificados"""
        user_role = user.get('role', '')
        user_school_links = user.get('school_links', [])
        user_school_ids = [link['school_id'] for link in user_school_links]
        recipient_type = recipient.get('type', '')

        if user_role in ('admin', 'admin_teste', 'super_admin', 'gerente'):
            return True
        if user_role in ['secretario', 'diretor', 'coordenador', 'auxiliar_secretaria']:
            if recipient_type == 'school':
                target_schools = recipient.get('school_ids', [])
                return all(s in user_school_ids for s in target_schools)
            elif recipient_type in ['class', 'individual', 'role']:
                return True
        if user_role == 'professor':
            return recipient_type in ['class', 'individual']
        return False

    async def get_announcement_target_users(db, recipient: dict, sender: dict) -> List[str]:
        """Obtém a lista de user_ids que devem receber o aviso"""
        target_user_ids = []
        recipient_type = recipient.get('type', '')
        sender_role = sender.get('role', '')
        sender_school_ids = [link['school_id'] for link in sender.get('school_links', [])]

        if recipient_type == 'individual':
            target_user_ids = recipient.get('user_ids', [])
        elif recipient_type == 'role':
            target_roles = recipient.get('target_roles', [])
            query = {'role': {'$in': target_roles}, 'status': 'active'}
            if sender_role != 'admin':
                query['school_links.school_id'] = {'$in': sender_school_ids}
            users = await db.users.find(query, {'_id': 0, 'id': 1}).to_list(10000)
            target_user_ids = [u['id'] for u in users]
        elif recipient_type == 'school':
            school_ids = recipient.get('school_ids', [])
            users = await db.users.find(
                {'school_links.school_id': {'$in': school_ids}, 'status': 'active'},
                {'_id': 0, 'id': 1},
            ).to_list(10000)
            target_user_ids = [u['id'] for u in users]
        elif recipient_type == 'class':
            class_ids = recipient.get('class_ids', [])
            enrollments = await db.enrollments.find(
                {'class_id': {'$in': class_ids}, 'status': 'active'},
                {'_id': 0, 'student_id': 1},
            ).to_list(10000)
            student_ids = [e['student_id'] for e in enrollments]
            students = await db.students.find(
                {'id': {'$in': student_ids}},
                {'_id': 0, 'user_id': 1, 'guardian_id': 1},
            ).to_list(10000)
            for student in students:
                if student.get('user_id'):
                    target_user_ids.append(student['user_id'])
                if student.get('guardian_id'):
                    guardian = await db.guardians.find_one(
                        {'id': student['guardian_id']},
                        {'_id': 0, 'user_id': 1},
                    )
                    if guardian and guardian.get('user_id'):
                        target_user_ids.append(guardian['user_id'])

        return list(set(target_user_ids))

    return router
