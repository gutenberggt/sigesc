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

# Roles permitidos para AEE
ROLES_AEE = ['admin', 'admin_teste', 'coordenador', 'professor']


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

    # ==================== PLANOS AEE ====================

    @router.post("/planos", response_model=PlanoAEE, status_code=status.HTTP_201_CREATED)
    async def create_plano_aee(plano_data: PlanoAEECreate, request: Request):
        """Cria novo Plano de AEE"""
        current_user = await check_aee_access(request)
        
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
        current_user = await check_aee_access(request)
        
        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")
        
        update_data = plano_update.model_dump(exclude_unset=True)
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
        """Exclui Plano AEE (apenas rascunhos)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'coordenador'])(request)
        
        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")
        
        if existing.get('status') not in ['rascunho']:
            raise HTTPException(status_code=400, detail="Apenas planos em rascunho podem ser excluídos")
        
        await db.planos_aee.delete_one({"id": plano_id})
        
        return {"message": "Plano AEE excluído com sucesso"}

    # ==================== ATENDIMENTOS AEE ====================

    @router.post("/atendimentos", response_model=AtendimentoAEE, status_code=status.HTTP_201_CREATED)
    async def create_atendimento_aee(atendimento_data: AtendimentoAEECreate, request: Request):
        """Registra novo atendimento AEE"""
        current_user = await check_aee_access(request)
        
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
        
        atendimento_obj = AtendimentoAEE(**atendimento_data.model_dump())
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
        current_user = await check_aee_access(request)
        
        existing = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
        
        update_data = atendimento_update.model_dump(exclude_unset=True)
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
        current_user = await check_aee_access(request)
        
        existing = await db.atendimentos_aee.find_one({"id": atendimento_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
        
        await db.atendimentos_aee.delete_one({"id": atendimento_id})
        
        return {"message": "Atendimento excluído com sucesso"}

    # ==================== EVOLUÇÃO/SÍNTESE ====================

    @router.post("/evolucoes")
    async def create_evolucao_aee(evolucao_data: dict, request: Request):
        """Registra síntese de evolução bimestral/semestral"""
        current_user = await check_aee_access(request)
        
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
        current_user = await check_aee_access(request)
        
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
                {"_id": 0, "full_name": 1, "birth_date": 1, "enrollment_number": 1}
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
                    "enrollment_number": student.get('enrollment_number') if student else None
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
        professor_aee_id: Optional[str] = None
    ):
        """Gera PDF do Diário AEE (individual ou completo)"""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
        
        current_user = await check_aee_access(request)
        
        # Busca dados do diário
        filter_planos = {"school_id": school_id, "academic_year": academic_year}
        if student_id:
            filter_planos['student_id'] = student_id
        if professor_aee_id:
            filter_planos['professor_aee_id'] = professor_aee_id
        if current_user.get('role') == 'professor':
            filter_planos['professor_aee_id'] = current_user.get('id')
        
        planos = await db.planos_aee.find(filter_planos, {"_id": 0}).to_list(100)
        
        if not planos:
            raise HTTPException(status_code=404, detail="Nenhum plano AEE encontrado")
        
        # Busca escola
        school = await db.schools.find_one({"id": school_id}, {"_id": 0, "name": 1})
        
        # Cria PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=14, spaceAfter=12, alignment=TA_CENTER)
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=11, spaceAfter=6, textColor=colors.darkblue)
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=9, spaceAfter=4)
        small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, spaceAfter=2)
        
        elements = []
        
        # Capa
        elements.append(Paragraph("DIÁRIO DE AEE", title_style))
        elements.append(Paragraph("Atendimento Educacional Especializado", styles['Heading3']))
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph(f"<b>Escola/Polo:</b> {school.get('name') if school else 'N/A'}", normal_style))
        elements.append(Paragraph(f"<b>Ano Letivo:</b> {academic_year}", normal_style))
        elements.append(Spacer(1, 1*cm))
        
        # Para cada plano/aluno
        for plano in planos:
            # Dados do aluno
            student = await db.students.find_one(
                {"id": plano.get('student_id')},
                {"_id": 0, "full_name": 1, "birth_date": 1, "enrollment_number": 1}
            )
            
            # Atendimentos
            atendimentos = await db.atendimentos_aee.find(
                {"plano_aee_id": plano['id']},
                {"_id": 0}
            ).sort("data", 1).to_list(500)
            
            # Ficha do aluno
            elements.append(PageBreak())
            elements.append(Paragraph(f"FICHA INDIVIDUAL - {student.get('full_name', 'N/A').upper()}", title_style))
            elements.append(Spacer(1, 0.3*cm))
            
            # Identificação
            elements.append(Paragraph("1. IDENTIFICAÇÃO", subtitle_style))
            id_data = [
                ["Nome:", student.get('full_name', 'N/A'), "Data Nasc.:", student.get('birth_date', 'N/A')],
                ["Matrícula:", student.get('enrollment_number', 'N/A'), "Público-Alvo:", plano.get('publico_alvo', 'N/A').replace('_', ' ').title()],
                ["Turma Origem:", plano.get('turma_origem_nome', 'N/A'), "Prof. Regente:", plano.get('professor_regente_nome', 'N/A')]
            ]
            t = Table(id_data, colWidths=[2.5*cm, 6*cm, 2.5*cm, 6*cm])
            t.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('BACKGROUND', (2, 0), (2, -1), colors.lightgrey),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.5*cm))
            
            # Cronograma
            elements.append(Paragraph("2. CRONOGRAMA DE ATENDIMENTO", subtitle_style))
            dias = ', '.join([d.title() for d in plano.get('dias_atendimento', [])])
            elements.append(Paragraph(f"<b>Dias:</b> {dias or 'N/D'}", normal_style))
            elements.append(Paragraph(f"<b>Horário:</b> {plano.get('horario_inicio', 'N/D')} às {plano.get('horario_fim', 'N/D')}", normal_style))
            elements.append(Paragraph(f"<b>Modalidade:</b> {plano.get('modalidade', 'N/D').replace('_', ' ').title()}", normal_style))
            elements.append(Paragraph(f"<b>Local:</b> {plano.get('local_atendimento', 'Sala de Recursos Multifuncionais')}", normal_style))
            elements.append(Spacer(1, 0.5*cm))
            
            # Objetivos do Plano
            elements.append(Paragraph("3. OBJETIVOS DO PLANO AEE", subtitle_style))
            objetivos = plano.get('objetivos', [])
            if objetivos:
                for i, obj in enumerate(objetivos, 1):
                    prazo_label = {'curto': 'Curto Prazo', 'medio': 'Médio Prazo', 'longo': 'Longo Prazo'}.get(obj.get('prazo', ''), '')
                    elements.append(Paragraph(f"{i}. [{prazo_label}] {obj.get('descricao', '')}", small_style))
            else:
                elements.append(Paragraph("Nenhum objetivo registrado.", small_style))
            elements.append(Spacer(1, 0.5*cm))
            
            # Registro de Atendimentos
            elements.append(Paragraph("4. REGISTRO DE ATENDIMENTOS", subtitle_style))
            if atendimentos:
                atend_header = ["Data", "Horário", "Presença", "Atividade Realizada", "Nível Apoio"]
                atend_data = [atend_header]
                for atend in atendimentos[-20:]:  # Últimos 20 atendimentos
                    presenca = "P" if atend.get('presente', True) else "F"
                    nivel = atend.get('nivel_apoio', '-')
                    if nivel:
                        nivel = nivel.replace('_', ' ').title()[:15]
                    atividade = atend.get('atividade_realizada', '-')[:50]
                    atend_data.append([
                        atend.get('data', '-'),
                        f"{atend.get('horario_inicio', '-')} - {atend.get('horario_fim', '-')}",
                        presenca,
                        atividade,
                        nivel
                    ])
                t = Table(atend_data, colWidths=[2*cm, 2.5*cm, 1.5*cm, 8*cm, 3*cm])
                t.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ]))
                elements.append(t)
            else:
                elements.append(Paragraph("Nenhum atendimento registrado.", small_style))
            elements.append(Spacer(1, 0.5*cm))
            
            # Estatísticas
            total = len(atendimentos)
            presencas = sum(1 for a in atendimentos if a.get('presente', True))
            carga = sum(a.get('duracao_minutos', 0) for a in atendimentos if a.get('presente', True))
            elements.append(Paragraph("5. RESUMO DO PERÍODO", subtitle_style))
            elements.append(Paragraph(f"Total de Atendimentos: {total} | Presenças: {presencas} | Ausências: {total - presencas}", normal_style))
            elements.append(Paragraph(f"Carga Horária Realizada: {round(carga/60, 1)} horas", normal_style))
        
        # Gera PDF
        doc.build(elements)
        buffer.seek(0)
        
        filename = f"diario_aee_{school_id[:8]}_{academic_year}.pdf"
        if student_id:
            filename = f"diario_aee_{student_id[:8]}_{academic_year}.pdf"
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
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
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "class_id": 1}
            )
            if student:
                turma = await db.classes.find_one({"id": student.get('class_id')}, {"_id": 0, "name": 1})
                estudantes.append({
                    "student_id": student.get('id'),
                    "full_name": student.get('full_name'),
                    "enrollment_number": student.get('enrollment_number'),
                    "turma_origem": turma.get('name') if turma else 'N/A',
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
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "class_id": 1, "disabilities": 1}
        ).to_list(100)
        
        for student in aee_students:
            turma = await db.classes.find_one({"id": student.get('class_id')}, {"_id": 0, "name": 1})
            estudantes.append({
                "student_id": student.get('id'),
                "full_name": student.get('full_name'),
                "enrollment_number": student.get('enrollment_number'),
                "turma_origem": turma.get('name') if turma else 'N/A',
                "publico_alvo": None,
                "modalidade": None,
                "dias_atendimento": [],
                "sem_plano": True
            })
        
        return estudantes

    return router
