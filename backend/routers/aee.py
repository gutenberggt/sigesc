"""
Router de AEE (Atendimento Educacional Especializado)
Endpoints para gestão de Planos AEE, Atendimentos e Diário AEE
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
from datetime import datetime, timezone
import uuid
from io import BytesIO

from models import (
    PlanoAEE, PlanoAEECreate, PlanoAEEUpdate,
    AtendimentoAEE, AtendimentoAEECreate, AtendimentoAEEUpdate,
    EvolucaoAEE, ArticulacaoSalaComum
)
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase

router = APIRouter(prefix="/aee", tags=["AEE"])

# Roles permitidos para AEE (leitura + escrita)
ROLES_AEE_WRITE = ['admin', 'admin_teste', 'super_admin', 'gerente', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'secretario']
# Roles somente visualização
ROLES_AEE_VIEW = ['diretor', 'semed', 'semed1', 'semed2', 'semed3']
# Todos com acesso
ROLES_AEE = ROLES_AEE_WRITE + ROLES_AEE_VIEW


def setup_aee_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    async def check_aee_access(request: Request):
        """Verifica se o usuário tem acesso ao módulo AEE"""
        user = await AuthMiddleware.get_current_user(request)
        if user.get('role') not in ROLES_AEE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso não autorizado ao módulo AEE"
            )
        return user

    async def check_aee_write_access(request: Request):
        """Verifica se o usuário pode editar no módulo AEE"""
        user = await AuthMiddleware.get_current_user(request)
        if user.get('role') not in ROLES_AEE_WRITE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu perfil permite apenas visualização no módulo AEE"
            )
        return user

    # ==================== PLANOS AEE ====================

    @router.post("/planos", response_model=PlanoAEE, status_code=status.HTTP_201_CREATED)
    async def create_plano_aee(plano_data: PlanoAEECreate, request: Request):
        """Cria novo Plano de AEE"""
        current_user = await check_aee_write_access(request)
        
        # Busca dados do aluno
        student = await db.students.find_one({"id": plano_data.student_id}, {"_id": 0, "full_name": 1})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        
        # Verifica se já existe plano ativo para este aluno no ano
        existing = await db.planos_aee.find_one({
            "student_id": plano_data.student_id,
            "academic_year": plano_data.academic_year,
            "status": {"$in": ["ativo", "rascunho"]}
        })
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Já existe um Plano AEE ativo ou em rascunho para este aluno neste ano letivo"
            )
        
        # Cria o plano
        plano_dict = format_data_uppercase(plano_data.model_dump())
        plano_obj = PlanoAEE(**plano_dict)
        doc = plano_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.planos_aee.insert_one(doc)
        
        # Auditoria
        await audit_service.log(
            action='create',
            collection='planos_aee',
            user=current_user,
            request=request,
            document_id=plano_obj.id,
            description=f"Criou Plano AEE para aluno: {student.get('full_name', 'N/A')}",
            school_id=plano_data.school_id,
            academic_year=plano_data.academic_year,
            new_value={'student_id': plano_data.student_id, 'publico_alvo': plano_data.publico_alvo}
        )
        
        return plano_obj

    @router.get("/planos")
    async def list_planos_aee(
        request: Request,
        school_id: Optional[str] = None,
        student_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        status_filter: Optional[str] = None,
        professor_aee_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ):
        """Lista Planos AEE com filtros"""
        current_user = await check_aee_access(request)
        
        filter_query = {}
        
        if school_id:
            filter_query['school_id'] = school_id
        if student_id:
            filter_query['student_id'] = student_id
        if academic_year:
            filter_query['academic_year'] = academic_year
        if status_filter:
            filter_query['status'] = status_filter
        if professor_aee_id:
            filter_query['professor_aee_id'] = professor_aee_id
        
        # Se for professor, filtra apenas seus planos
        if current_user.get('role') == 'professor':
            filter_query['professor_aee_id'] = current_user.get('id')
        
        planos = await db.planos_aee.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Enriquecer com nome do aluno
        for plano in planos:
            student = await db.students.find_one({"id": plano.get('student_id')}, {"_id": 0, "full_name": 1})
            plano['student_name'] = student.get('full_name') if student else 'N/A'
        
        total = await db.planos_aee.count_documents(filter_query)
        
        return {"items": planos, "total": total}

    @router.get("/planos/{plano_id}")
    async def get_plano_aee(plano_id: str, request: Request):
        """Busca Plano AEE por ID"""
        current_user = await check_aee_access(request)
        
        plano = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not plano:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")
        
        # Busca nome do aluno
        student = await db.students.find_one({"id": plano.get('student_id')}, {"_id": 0, "full_name": 1, "birth_date": 1})
        plano['student_name'] = student.get('full_name') if student else 'N/A'
        plano['student_birth_date'] = student.get('birth_date') if student else None
        
        return plano

    @router.put("/planos/{plano_id}")
    async def update_plano_aee(plano_id: str, plano_update: PlanoAEEUpdate, request: Request):
        """Atualiza Plano AEE"""
        current_user = await check_aee_write_access(request)
        
        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")
        
        update_data = plano_update.model_dump(exclude_unset=True)
        update_data = format_data_uppercase(update_data)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await db.planos_aee.update_one({"id": plano_id}, {"$set": update_data})
        
        # Auditoria
        await audit_service.log(
            action='update',
            collection='planos_aee',
            user=current_user,
            request=request,
            document_id=plano_id,
            description=f"Atualizou Plano AEE",
            school_id=existing.get('school_id'),
            academic_year=existing.get('academic_year'),
            old_value=existing,
            new_value=update_data
        )
        
        updated = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        return updated

    @router.delete("/planos/{plano_id}")
    async def delete_plano_aee(plano_id: str, request: Request):
        """Exclui Plano AEE.

        Apenas super_admin/gerente podem excluir planos ativos ou em revisão.
        Demais roles administrativas podem excluir apenas rascunhos.
        """
        current_user = await AuthMiddleware.require_roles(['super_admin', 'gerente', 'admin', 'admin_teste', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'secretario'])(request)

        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        is_privileged = current_user.get('role') in ['super_admin', 'gerente']
        if not is_privileged and existing.get('status') not in ['rascunho']:
            raise HTTPException(
                status_code=400,
                detail="Apenas planos em rascunho podem ser excluídos (super_admin/gerente podem excluir planos ativos)"
            )

        # Conta atendimentos vinculados para log de auditoria
        atend_count = await db.atendimentos_aee.count_documents({"plano_aee_id": plano_id})

        await db.planos_aee.delete_one({"id": plano_id})

        # Audit log da exclusão
        try:
            await audit_service.log(
                action='delete',
                collection='planos_aee',
                user=current_user,
                request=request,
                document_id=plano_id,
                description=(
                    f"Plano AEE excluído (status: {existing.get('status')}, "
                    f"{atend_count} atendimento(s) vinculado(s) permanecem)"
                ),
                old_value=existing,
            )
        except Exception:
            pass

        return {
            "message": "Plano AEE excluído com sucesso",
            "atendimentos_vinculados": atend_count,
        }

    @router.post("/planos/{plano_id}/duplicate", status_code=status.HTTP_201_CREATED)
    async def duplicate_plano_aee(plano_id: str, request: Request):
        """Duplica um Plano AEE existente (cria nova cópia em rascunho)."""
        current_user = await check_aee_write_access(request)

        original = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not original:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        from datetime import date
        novo = dict(original)
        novo['id'] = str(uuid.uuid4())
        novo['status'] = 'rascunho'
        novo['data_elaboracao'] = date.today().strftime('%Y-%m-%d')
        novo['created_at'] = datetime.now(timezone.utc).isoformat()
        novo['updated_at'] = novo['created_at']
        # Promove o usuário que duplicou como criador
        novo['created_by'] = current_user.get('id')

        await db.planos_aee.insert_one(novo)
        # Garante que _id do Mongo não vaze para a resposta
        novo.pop('_id', None)

        try:
            await audit_service.log(
                action='create',
                collection='planos_aee',
                user=current_user,
                request=request,
                document_id=novo['id'],
                description=f"Plano AEE duplicado a partir de {plano_id}",
                school_id=novo.get('school_id'),
                academic_year=novo.get('academic_year'),
                new_value=novo,
            )
        except Exception:
            pass

        return novo

    @router.get("/planos/{plano_id}/pdf")
    async def generate_plano_aee_pdf(plano_id: str, request: Request):
        """Gera PDF do Plano AEE para visualização/impressão."""
        _user = await check_aee_access(request)

        plano = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not plano:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        # Busca dados relacionados para enriquecer o PDF
        student = await db.students.find_one(
            {"id": plano.get('student_id')},
            {"_id": 0, "full_name": 1, "enrollment_number": 1, "birthday": 1, "atendimento_programa_class_id": 1}
        ) or {}
        school = await db.schools.find_one(
            {"id": plano.get('school_id')},
            {"_id": 0, "name": 1, "mantenedora_id": 1}
        ) or {}
        mantenedora = await db.mantenedoras.find_one(
            {"id": school.get('mantenedora_id')}, {"_id": 0}
        ) or {}

        # Resolve professor AEE a partir da turma AEE (Feb 2026)
        # O professor AEE é o docente alocado à turma AEE onde o aluno está matriculado.
        aee_class_id = student.get('atendimento_programa_class_id')
        if aee_class_id:
            ta = await db.teacher_assignments.find_one(
                {"class_id": aee_class_id, "status": {"$in": ["ativo", "active"]}},
                {"_id": 0, "staff_id": 1}
            )
            if ta:
                staff = await db.staff.find_one(
                    {"id": ta.get('staff_id')}, {"_id": 0, "nome": 1}
                )
                if staff and staff.get('nome'):
                    plano['professor_aee_nome'] = staff.get('nome')

        from pdf.plano_aee import generate_plano_aee_pdf as _gen
        from fastapi.responses import StreamingResponse
        pdf_bytes = _gen(plano=plano, student=student, school=school, mantenedora=mantenedora)
        filename = f"plano_aee_{(student.get('full_name') or 'aluno').replace(' ', '_')}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # ==================== ATENDIMENTOS AEE ====================

    @router.post("/atendimentos", response_model=AtendimentoAEE, status_code=status.HTTP_201_CREATED)
    async def create_atendimento_aee(atendimento_data: AtendimentoAEECreate, request: Request):
        """Registra novo atendimento AEE"""
        current_user = await check_aee_write_access(request)
        
        # Verifica se o plano existe e está ativo
        plano = await db.planos_aee.find_one({"id": atendimento_data.plano_aee_id}, {"_id": 0})
        if not plano:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")
        if plano.get('status') not in ['ativo', 'rascunho']:
            raise HTTPException(status_code=400, detail="Plano AEE não está ativo")
        
        # Calcula duração se não informada
        if not atendimento_data.duracao_minutos and atendimento_data.horario_inicio and atendimento_data.horario_fim:
            try:
                inicio = datetime.strptime(atendimento_data.horario_inicio, "%H:%M")
                fim = datetime.strptime(atendimento_data.horario_fim, "%H:%M")
                duracao = (fim - inicio).seconds // 60
                atendimento_data.duracao_minutos = duracao
            except:
                pass
        
        atend_dict = format_data_uppercase(atendimento_data.model_dump())
        atendimento_obj = AtendimentoAEE(**atend_dict)
        doc = atendimento_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.atendimentos_aee.insert_one(doc)
        
        # Auditoria
        student = await db.students.find_one({"id": atendimento_data.student_id}, {"_id": 0, "full_name": 1})
        await audit_service.log(
            action='create',
            collection='atendimentos_aee',
            user=current_user,
            request=request,
            document_id=atendimento_obj.id,
            description=f"Registrou atendimento AEE para: {student.get('full_name', 'N/A')} em {atendimento_data.data}",
            school_id=atendimento_data.school_id,
            academic_year=atendimento_data.academic_year
        )
        
        return atendimento_obj

    @router.get("/atendimentos")
    async def list_atendimentos_aee(
        request: Request,
        plano_aee_id: Optional[str] = None,
        student_id: Optional[str] = None,
        school_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ):
        """Lista atendimentos AEE com filtros"""
        current_user = await check_aee_access(request)
        
        filter_query = {}
        
        if plano_aee_id:
            filter_query['plano_aee_id'] = plano_aee_id
        if student_id:
            filter_query['student_id'] = student_id
        if school_id:
            filter_query['school_id'] = school_id
        if academic_year:
            filter_query['academic_year'] = academic_year
        
        # Filtro de data
        if data_inicio or data_fim:
            filter_query['data'] = {}
            if data_inicio:
                filter_query['data']['$gte'] = data_inicio
            if data_fim:
                filter_query['data']['$lte'] = data_fim
        
        # Se for professor, filtra apenas seus atendimentos
        if current_user.get('role') == 'professor':
            filter_query['professor_aee_id'] = current_user.get('id')
        
        atendimentos = await db.atendimentos_aee.find(filter_query, {"_id": 0}).sort("data", -1).skip(skip).limit(limit).to_list(limit)
        
        # Enriquecer com nome do aluno
        for atendimento in atendimentos:
            student = await db.students.find_one({"id": atendimento.get('student_id')}, {"_id": 0, "full_name": 1})
            atendimento['student_name'] = student.get('full_name') if student else 'N/A'
        
        total = await db.atendimentos_aee.count_documents(filter_query)
        
        return {"items": atendimentos, "total": total}

    @router.get("/atendimentos/{atendimento_id}")
    async def get_atendimento_aee(atendimento_id: str, request: Request):
        """Busca atendimento AEE por ID"""
        current_user = await check_aee_access(request)
        
        atendimento = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        if not atendimento:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
        
        return atendimento

    @router.put("/atendimentos/{atendimento_id}")
    async def update_atendimento_aee(atendimento_id: str, atendimento_update: AtendimentoAEEUpdate, request: Request):
        """Atualiza atendimento AEE"""
        current_user = await check_aee_write_access(request)
        
        existing = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
        
        update_data = atendimento_update.model_dump(exclude_unset=True)
        update_data = format_data_uppercase(update_data)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Recalcula duração se horários foram alterados
        horario_inicio = update_data.get('horario_inicio', existing.get('horario_inicio'))
        horario_fim = update_data.get('horario_fim', existing.get('horario_fim'))
        if horario_inicio and horario_fim:
            try:
                inicio = datetime.strptime(horario_inicio, "%H:%M")
                fim = datetime.strptime(horario_fim, "%H:%M")
                update_data['duracao_minutos'] = (fim - inicio).seconds // 60
            except:
                pass
        
        await db.atendimentos_aee.update_one({"id": atendimento_id}, {"$set": update_data})
        
        updated = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        return updated

    @router.delete("/atendimentos/{atendimento_id}")
    async def delete_atendimento_aee(atendimento_id: str, request: Request):
        """Exclui atendimento AEE"""
        current_user = await check_aee_write_access(request)
        
        existing = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
        
        await db.atendimentos_aee.delete_one({"id": atendimento_id})
        
        return {"message": "Atendimento excluído com sucesso"}

    # ==================== EVOLUÇÃO/SÍNTESE ====================

    @router.post("/evolucoes")
    async def create_evolucao_aee(evolucao_data: dict, request: Request):
        """Registra síntese de evolução bimestral/semestral"""
        current_user = await check_aee_write_access(request)
        
        evolucao = EvolucaoAEE(**evolucao_data)
        doc = evolucao.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.evolucoes_aee.insert_one(doc)
        
        return evolucao

    @router.get("/evolucoes")
    async def list_evolucoes_aee(
        request: Request,
        plano_aee_id: Optional[str] = None,
        student_id: Optional[str] = None,
        academic_year: Optional[int] = None
    ):
        """Lista evoluções AEE"""
        current_user = await check_aee_access(request)
        
        filter_query = {}
        if plano_aee_id:
            filter_query['plano_aee_id'] = plano_aee_id
        if student_id:
            filter_query['student_id'] = student_id
        if academic_year:
            filter_query['academic_year'] = academic_year
        
        evolucoes = await db.evolucoes_aee.find(filter_query, {"_id": 0}).to_list(100)
        
        return evolucoes

    # ==================== ARTICULAÇÃO SALA COMUM ====================

    @router.post("/articulacoes")
    async def create_articulacao(articulacao_data: dict, request: Request):
        """Registra articulação com sala comum"""
        current_user = await check_aee_write_access(request)
        
        articulacao = ArticulacaoSalaComum(**articulacao_data)
        doc = articulacao.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.articulacoes_aee.insert_one(doc)
        
        return articulacao

    @router.get("/articulacoes")
    async def list_articulacoes(
        request: Request,
        plano_aee_id: Optional[str] = None,
        student_id: Optional[str] = None
    ):
        """Lista articulações com sala comum"""
        current_user = await check_aee_access(request)
        
        filter_query = {}
        if plano_aee_id:
            filter_query['plano_aee_id'] = plano_aee_id
        if student_id:
            filter_query['student_id'] = student_id
        
        articulacoes = await db.articulacoes_aee.find(filter_query, {"_id": 0}).sort("data", -1).to_list(100)
        
        return articulacoes

    # ==================== DIÁRIO AEE (VISÃO CONSOLIDADA) ====================

    @router.get("/diario")
    async def get_diario_aee(
        request: Request,
        school_id: str = Query(...),
        academic_year: int = Query(...),
        professor_aee_id: Optional[str] = None,
        bimestre: Optional[int] = None
    ):
        """
        Retorna visão consolidada do Diário AEE para impressão/visualização
        Inclui: calendário, grade de atendimentos, lista de estudantes, fichas
        """
        current_user = await check_aee_access(request)
        
        # Busca escola
        school = await db.schools.find_one({"id": school_id}, {"_id": 0, "name": 1})
        
        # Filtro base
        filter_planos = {"school_id": school_id, "academic_year": academic_year, "status": {"$in": ["ativo", "rascunho"]}}
        if professor_aee_id:
            filter_planos['professor_aee_id'] = professor_aee_id
        
        # Se for professor, filtra apenas seus planos
        if current_user.get('role') == 'professor':
            filter_planos['professor_aee_id'] = current_user.get('id')
        
        # Busca planos
        planos = await db.planos_aee.find(filter_planos, {"_id": 0}).to_list(100)
        
        # Enriquece com dados dos alunos e atendimentos
        fichas = []
        for plano in planos:
            # Dados do aluno
            student = await db.students.find_one(
                {"id": plano.get('student_id')}, 
                {"_id": 0, "full_name": 1, "birth_date": 1, "enrollment_number": 1, "class_id": 1, "atendimento_programa_class_id": 1}
            )
            
            # Atendimentos do período
            filter_atend = {"plano_aee_id": plano['id']}
            atendimentos = await db.atendimentos_aee.find(filter_atend, {"_id": 0}).sort("data", 1).to_list(500)
            
            # Evoluções
            evolucoes = await db.evolucoes_aee.find({"plano_aee_id": plano['id']}, {"_id": 0}).to_list(10)
            
            # Articulações
            articulacoes = await db.articulacoes_aee.find({"plano_aee_id": plano['id']}, {"_id": 0}).to_list(50)
            
            # Calcula estatísticas
            total_atendimentos = len(atendimentos)
            presencas = sum(1 for a in atendimentos if a.get('presente', True))
            carga_horaria_realizada = sum(a.get('duracao_minutos', 0) for a in atendimentos if a.get('presente', True))
            
            fichas.append({
                "plano": plano,
                "student": {
                    "id": plano.get('student_id'),
                    "full_name": student.get('full_name') if student else 'N/A',
                    "birth_date": student.get('birth_date') if student else None,
                    "enrollment_number": student.get('enrollment_number') if student else None,
                    "class_id": student.get('class_id') if student else None,
                    "atendimento_programa_class_id": student.get('atendimento_programa_class_id') if student else None
                },
                "atendimentos": atendimentos,
                "evolucoes": evolucoes,
                "articulacoes": articulacoes,
                "estatisticas": {
                    "total_atendimentos": total_atendimentos,
                    "presencas": presencas,
                    "ausencias": total_atendimentos - presencas,
                    "frequencia_percentual": round((presencas / total_atendimentos * 100) if total_atendimentos > 0 else 0),
                    "carga_horaria_realizada_minutos": carga_horaria_realizada,
                    "carga_horaria_realizada_horas": round(carga_horaria_realizada / 60, 1)
                }
            })
        
        # Monta grade de horários (agregando todos os planos)
        grade_horarios = {}
        for ficha in fichas:
            plano = ficha['plano']
            for dia in plano.get('dias_atendimento', []):
                if dia not in grade_horarios:
                    grade_horarios[dia] = []
                grade_horarios[dia].append({
                    "student_id": plano.get('student_id'),
                    "student_name": ficha['student']['full_name'],
                    "horario_inicio": plano.get('horario_inicio'),
                    "horario_fim": plano.get('horario_fim'),
                    "modalidade": plano.get('modalidade')
                })
        
        # Ordena por horário
        for dia in grade_horarios:
            grade_horarios[dia].sort(key=lambda x: x.get('horario_inicio', '00:00'))
        
        return {
            "escola": school.get('name') if school else 'N/A',
            "school_id": school_id,
            "academic_year": academic_year,
            "professor_aee_id": professor_aee_id,
            "total_estudantes": len(fichas),
            "grade_horarios": grade_horarios,
            "fichas": fichas
        }

    # ==================== PDF DO DIÁRIO AEE ====================

    @router.get("/diario/pdf")
    async def get_diario_aee_pdf(
        request: Request,
        school_id: str = Query(...),
        academic_year: int = Query(...),
        student_id: Optional[str] = None,
        professor_aee_id: Optional[str] = None,
        data_inicio: Optional[str] = Query(None, description="Filtro: data inicial YYYY-MM-DD"),
        data_fim: Optional[str] = Query(None, description="Filtro: data final YYYY-MM-DD"),
        periodo_label: Optional[str] = Query(None, description="Rótulo do período (ex: '1º Bimestre')"),
    ):
        """
        Gera PDF do Diário AEE - Visão Consolidada (espelhando a tela):
        cabeçalho institucional, KPIs, grade semanal e fichas individuais.
        Aceita filtro de período via data_inicio/data_fim (YYYY-MM-DD).
        """
        current_user = await check_aee_access(request)

        # Parse das datas de filtro (datas dos atendimentos vêm em "dd/mm/aaaa")
        from datetime import datetime as _dt
        di = df = None
        if data_inicio:
            try:
                di = _dt.strptime(data_inicio, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="data_inicio inválida (use YYYY-MM-DD)")
        if data_fim:
            try:
                df = _dt.strptime(data_fim, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="data_fim inválida (use YYYY-MM-DD)")

        def _in_range(data_str: str) -> bool:
            """Aceita 'dd/mm/aaaa' ou 'YYYY-MM-DD'. Sem filtro = sempre True."""
            if not (di or df):
                return True
            if not data_str:
                return False
            for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
                try:
                    d = _dt.strptime(data_str, fmt).date()
                    if di and d < di:
                        return False
                    if df and d > df:
                        return False
                    return True
                except ValueError:
                    continue
            return False

        # Busca planos
        filter_planos = {
            "school_id": school_id,
            "academic_year": academic_year,
            "status": {"$in": ["ativo", "rascunho"]},
        }
        if student_id:
            filter_planos['student_id'] = student_id
        if professor_aee_id:
            filter_planos['professor_aee_id'] = professor_aee_id
        if current_user.get('role') == 'professor':
            filter_planos['professor_aee_id'] = current_user.get('id')

        planos = await db.planos_aee.find(filter_planos, {"_id": 0}).to_list(100)
        if not planos:
            raise HTTPException(status_code=404, detail="Nenhum plano AEE encontrado")

        # Busca escola e mantenedora
        school = await db.schools.find_one(
            {"id": school_id}, {"_id": 0, "name": 1, "mantenedora_id": 1}
        ) or {}
        mantenedora = await db.mantenedoras.find_one(
            {"id": school.get('mantenedora_id')}, {"_id": 0}
        ) or {}

        # Resolve turma AEE e professor AEE a partir do primeiro aluno AEE da escola
        turma_aee_nome = '-'
        professor_aee_nome = '-'
        aee_turma = await db.classes.find_one(
            {"school_id": school_id, "atendimento_programa": {"$regex": "^aee$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1}
        )
        if aee_turma:
            turma_aee_nome = aee_turma.get('name') or '-'
            ta = await db.teacher_assignments.find_one(
                {"class_id": aee_turma.get('id'), "status": {"$in": ["ativo", "active"]}},
                {"_id": 0, "staff_id": 1}
            )
            if ta:
                staff = await db.staff.find_one(
                    {"id": ta.get('staff_id')}, {"_id": 0, "nome": 1}
                )
                if staff:
                    professor_aee_nome = staff.get('nome') or '-'

        # Monta fichas de cada aluno + agrega dados
        fichas = []
        grade_horarios: dict = {}
        total_atendimentos_geral = 0
        planos_ativos = 0
        carga_total_minutos = 0

        for plano in planos:
            student = await db.students.find_one(
                {"id": plano.get('student_id')},
                {"_id": 0, "full_name": 1, "birth_date": 1, "enrollment_number": 1,
                 "class_id": 1, "atendimento_programa_class_id": 1}
            ) or {}
            atendimentos = await db.atendimentos_aee.find(
                {"plano_aee_id": plano['id']}, {"_id": 0}
            ).sort("data", 1).to_list(500)

            # Filtra atendimentos pelo período se especificado
            if di or df:
                atendimentos = [a for a in atendimentos if _in_range(a.get('data', ''))]

            total = len(atendimentos)
            presencas = sum(1 for a in atendimentos if a.get('presente', True))
            carga_min = sum(a.get('duracao_minutos', 0) for a in atendimentos if a.get('presente', True))

            total_atendimentos_geral += total
            carga_total_minutos += carga_min
            if plano.get('status') == 'ativo':
                planos_ativos += 1

            # Grade semanal
            for dia in plano.get('dias_atendimento', []):
                grade_horarios.setdefault(dia, []).append({
                    "student_name": student.get('full_name') or 'N/A',
                    "horario_inicio": plano.get('horario_inicio'),
                    "horario_fim": plano.get('horario_fim'),
                })

            fichas.append({
                "plano": plano,
                "student": student,
                "atendimentos": atendimentos,
                "estatisticas": {
                    "total_atendimentos": total,
                    "presencas": presencas,
                    "ausencias": total - presencas,
                    "frequencia_percentual": round((presencas / total * 100) if total > 0 else 0),
                    "carga_horaria_realizada_horas": round(carga_min / 60, 1),
                },
            })

        # Ordena grade por horário
        for dia in grade_horarios:
            grade_horarios[dia].sort(key=lambda x: x.get('horario_inicio') or '00:00')

        # Gera PDF com o módulo dedicado
        from pdf.diario_aee import generate_diario_aee_pdf
        pdf_bytes = generate_diario_aee_pdf(
            school=school,
            mantenedora=mantenedora,
            academic_year=academic_year,
            turma_aee_nome=turma_aee_nome,
            professor_aee_nome=professor_aee_nome,
            fichas=fichas,
            grade_horarios=grade_horarios,
            total_atendimentos=total_atendimentos_geral,
            planos_ativos=planos_ativos,
            carga_horaria_horas=round(carga_total_minutos / 60, 1),
            periodo_label=periodo_label,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )

        filename = f"diario_aee_{academic_year}.pdf"
        if student_id:
            filename = f"diario_aee_{student_id[:8]}_{academic_year}.pdf"

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # ==================== ESTUDANTES ATENDIDOS ====================

    @router.get("/estudantes")
    async def list_estudantes_aee(
        request: Request,
        school_id: str = Query(...),
        academic_year: int = Query(...)
    ):
        """Lista estudantes com planos AEE ativos na escola e alunos matriculados em turma AEE"""
        current_user = await check_aee_access(request)
        
        # 1. Busca alunos com planos AEE existentes
        filter_query = {
            "school_id": school_id,
            "academic_year": academic_year,
            "status": {"$in": ["ativo", "rascunho"]}
        }
        
        if current_user.get('role') == 'professor':
            filter_query['professor_aee_id'] = current_user.get('id')
        
        planos = await db.planos_aee.find(filter_query, {"_id": 0, "student_id": 1, "publico_alvo": 1, "modalidade": 1, "dias_atendimento": 1}).to_list(100)
        
        estudantes = []
        student_ids_added = set()
        
        for plano in planos:
            student = await db.students.find_one(
                {"id": plano.get('student_id')},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "class_id": 1, "school_id": 1, "atendimento_programa_class_id": 1}
            )
            if student:
                turma = await db.classes.find_one({"id": student.get('class_id')}, {"_id": 0, "name": 1})
                escola_origem = await db.schools.find_one({"id": student.get('school_id')}, {"_id": 0, "name": 1})
                # Busca professor regente da turma de origem
                professor_regente = None
                if student.get('class_id'):
                    ta = await db.teacher_assignments.find_one(
                        {"class_id": student.get('class_id'), "status": {"$in": ["ativo", "active"]}},
                        {"_id": 0, "staff_id": 1}
                    )
                    if ta:
                        staff = await db.staff.find_one({"id": ta.get('staff_id')}, {"_id": 0, "nome": 1})
                        professor_regente = staff.get('nome') if staff else None
                estudantes.append({
                    "student_id": student.get('id'),
                    "full_name": student.get('full_name'),
                    "class_id": student.get('class_id'),
                    "atendimento_programa_class_id": student.get('atendimento_programa_class_id'),
                    "turma_origem": turma.get('name') if turma else 'N/A',
                    "escola_origem": escola_origem.get('name') if escola_origem else 'N/A',
                    "professor_regente": professor_regente,
                    "publico_alvo": plano.get('publico_alvo'),
                    "modalidade": plano.get('modalidade'),
                    "dias_atendimento": plano.get('dias_atendimento', [])
                })
                student_ids_added.add(student.get('id'))
        
        # 2. Busca alunos matriculados em turma AEE (que ainda não têm plano)
        aee_students = await db.students.find(
            {
                "school_id": school_id,
                "atendimento_programa_tipo": "aee",
                "atendimento_programa_class_id": {"$exists": True, "$nin": [None, ""]},
                "status": "active",
                "id": {"$nin": list(student_ids_added)}
            },
            {"_id": 0, "id": 1, "full_name": 1, "class_id": 1, "school_id": 1, "disabilities": 1, "atendimento_programa_class_id": 1}
        ).to_list(100)
        
        for student in aee_students:
            turma = await db.classes.find_one({"id": student.get('class_id')}, {"_id": 0, "name": 1})
            escola_origem = await db.schools.find_one({"id": student.get('school_id')}, {"_id": 0, "name": 1})
            professor_regente = None
            if student.get('class_id'):
                ta = await db.teacher_assignments.find_one(
                    {"class_id": student.get('class_id'), "status": {"$in": ["ativo", "active"]}},
                    {"_id": 0, "staff_id": 1}
                )
                if ta:
                    staff_doc = await db.staff.find_one({"id": ta.get('staff_id')}, {"_id": 0, "nome": 1})
                    professor_regente = staff_doc.get('nome') if staff_doc else None
            estudantes.append({
                "student_id": student.get('id'),
                "full_name": student.get('full_name'),
                "class_id": student.get('class_id'),
                "atendimento_programa_class_id": student.get('atendimento_programa_class_id'),
                "turma_origem": turma.get('name') if turma else 'N/A',
                "escola_origem": escola_origem.get('name') if escola_origem else 'N/A',
                "professor_regente": professor_regente,
                "publico_alvo": None,
                "modalidade": None,
                "dias_atendimento": [],
                "sem_plano": True
            })
        
        return estudantes

    return router
