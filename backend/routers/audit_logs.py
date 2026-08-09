"""
Router para Auditoria.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone, timedelta
from io import BytesIO

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Auditoria"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/audit-logs")
    async def list_audit_logs(
        request: Request,
        skip: int = 0,
        limit: int = 50,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        school_id: Optional[str] = None,
        collection: Optional[str] = None,
        action: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        academic_year: Optional[int] = None,
        search: Optional[str] = None
    ):
        """
        Lista logs de auditoria com filtros.
        Apenas admin e SEMED 3 podem visualizar.
        """
        current_user = await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        filters = {
            'user_id': user_id,
            'user_role': user_role,
            'school_id': school_id,
            'collection': collection,
            'action': action,
            'category': category,
            'severity': severity,
            'start_date': start_date,
            'end_date': end_date,
            'academic_year': academic_year,
            'search': search
        }

        # Remove filtros vazios
        filters = {k: v for k, v in filters.items() if v is not None}

        logs, total = await audit_service.get_logs(filters, skip, limit)

        return {
            'items': logs,
            'total': total,
            'skip': skip,
            'limit': limit
        }


    @router.get("/audit-logs/user/{user_id}")
    async def get_user_audit_logs(user_id: str, request: Request, limit: int = 20):
        """Retorna atividades recentes de um usuário específico"""
        current_user = await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        logs = await audit_service.get_user_activity(user_id, limit)
        return {'items': logs}


    @router.get("/audit-logs/pdf")
    async def export_audit_logs_pdf(
        request: Request,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        school_id: Optional[str] = None,
        collection: Optional[str] = None,
        action: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        academic_year: Optional[int] = None,
        search: Optional[str] = None,
    ):
        """Gera um PDF (streaming) dos logs de auditoria conforme os filtros atuais.

        Memória controlada: limita a exportação a MAX_ROWS registros e transmite via stream.
        Colunas: Data/Hora, Usuário, Ação, Descrição, Tempo (dias do 1º salvamento).
        """
        await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        MAX_ROWS = 2000
        filters = {
            'user_id': user_id, 'user_role': user_role, 'school_id': school_id,
            'collection': collection, 'action': action, 'category': category,
            'start_date': start_date, 'end_date': end_date,
            'academic_year': academic_year, 'search': search,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        logs, total = await audit_service.get_logs(filters, skip=0, limit=MAX_ROWS)

        action_labels = {
            'login': 'Login', 'logout': 'Logout', 'create': 'Criação', 'update': 'Alteração',
            'delete': 'Exclusão', 'export': 'Exportação', 'import': 'Importação',
            'approve': 'Aprovação', 'reject': 'Rejeição',
        }
        collection_labels = {
            'users': 'Usuários', 'students': 'Alunos(as)', 'grades': 'Notas',
            'attendance': 'Frequência', 'content_entries': 'Conteúdos', 'staff': 'Servidores(as)',
            'schools': 'Escolas', 'classes': 'Turmas', 'courses': 'Componentes',
            'enrollments': 'Matrículas', 'school_assignments': 'Lotações',
            'teacher_assignments': 'Alocações', 'mantenedora': 'Mantenedora',
            'calendario_letivo': 'Calendário',
        }

        def _fmt_dt(ts):
            try:
                d = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                return d.strftime('%d/%m/%Y %H:%M')
            except Exception:
                return str(ts or '-')

        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm, cm
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from pdf.utils import get_logo_image

        # ===== Dados institucionais (mantenedora / escola / usuário filtrado) =====
        _mant_scope = request.headers.get('X-Mantenedora-Id')
        mantenedora = await db['mantenedora'].find_one({}, {'_id': 0})
        if not mantenedora and _mant_scope:
            mantenedora = await db['mantenedoras'].find_one({'id': _mant_scope}, {'_id': 0})
        if not mantenedora:
            mantenedora = await db['mantenedoras'].find_one({}, {'_id': 0})
        mantenedora = mantenedora or {}
        mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
        mant_estado = mantenedora.get('estado', 'PA')
        mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
        mant_secretaria = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')
        mant_slogan = mantenedora.get('slogan', '')
        logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
        logo = get_logo_image(width=2.3 * cm, height=2.7 * cm, logo_url=logo_url)

        escola_nome = None
        if school_id:
            _sc = await db.schools.find_one({'id': school_id}, {'_id': 0, 'name': 1})
            escola_nome = (_sc or {}).get('name')
        usuario_ctx = None
        if user_id:
            _u = await db.users.find_one({'id': user_id}, {'_id': 0, 'full_name': 1, 'name': 1, 'email': 1, 'role': 1})
            if _u:
                role_labels = {
                    'super_admin': 'Super Administrador', 'admin': 'Administrador(a)',
                    'gerente': 'Gerente', 'secretario': 'Secretário(a)', 'coordenador': 'Coordenador(a)',
                    'professor': 'Professor(a)', 'auxiliar_secretaria': 'Auxiliar de Secretaria',
                    'diretor': 'Diretor(a)',
                }
                _rl = role_labels.get(_u.get('role'), _u.get('role') or '')
                usuario_ctx = f"{_u.get('full_name') or _u.get('name') or _u.get('email')}" + (f" — {_rl}" if _rl else '')

        styles = getSampleStyleSheet()
        cell = ParagraphStyle('cell', parent=styles['Normal'], fontSize=7, leading=9)
        left_style = ParagraphStyle('hleft', fontSize=10, alignment=TA_LEFT, leading=13)
        right_style = ParagraphStyle('hright', fontSize=10, alignment=TA_RIGHT, leading=15)
        ctx_style = ParagraphStyle('ctx', parent=styles['Normal'], fontSize=8, leading=11)
        small = ParagraphStyle('s', parent=styles['Normal'], fontSize=8, textColor=colors.grey)

        header = ['Data/Hora', 'Usuário', 'Ação', 'Descrição', 'Tempo']
        data = [header]
        for lg in logs:
            td = lg.get('tempo_dias')
            tempo = f"{td} dia{'s' if td != 1 else ''}" if isinstance(td, int) else '-'
            acao = f"{action_labels.get(lg.get('action'), lg.get('action') or '-')}"
            colls = collection_labels.get(lg.get('collection'), lg.get('collection') or '')
            data.append([
                Paragraph(_fmt_dt(lg.get('timestamp')), cell),
                Paragraph((lg.get('user_name') or lg.get('user_email') or '-'), cell),
                Paragraph(f"{acao}<br/><font size=6 color='#888888'>{colls}</font>", cell),
                Paragraph((lg.get('description') or '-'), cell),
                Paragraph(tempo, cell),
            ])

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=landscape(A4),
            leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=12 * mm,
        )

        # ===== Cabeçalho institucional (brasão | mantenedora/secretaria | título) =====
        slogan_html = f'<br/><font size="8" color="#666666"><i>"{mant_slogan}"</i></font>' if mant_slogan else ''
        header_left = (
            f'<font size="12"><b>{mant_nome.upper()}</b></font><br/>'
            f'<font size="9"><i>{mant_secretaria}</i></font><br/>'
            f'<font size="8" color="#555555">{mant_municipio} - {mant_estado}</font>'
            f'{slogan_html}'
        )
        header_right = (
            '<font size="15" color="#1e40af"><b>LOGS DE AUDITORIA</b></font><br/>'
            '<font size="9" color="#555555">Rastreamento de alterações no sistema</font>'
        )
        if logo:
            head_table = Table(
                [[logo, Paragraph(header_left, left_style), Paragraph(header_right, right_style)]],
                colWidths=[2.8 * cm, 15 * cm, 9 * cm],
            )
        else:
            head_table = Table(
                [[Paragraph(header_left, left_style), Paragraph(header_right, right_style)]],
                colWidths=[17.8 * cm, 9 * cm],
            )
        head_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (1 if logo else 0, 0), (1 if logo else 0, 0), 10),
            ('LINEAFTER', (0, 0), (0, 0), 0.8, colors.HexColor('#1e40af')) if logo else ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white),
        ]))

        gen_at = datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M')
        ctx_parts = []
        if escola_nome:
            ctx_parts.append(f'<b>Escola:</b> {escola_nome}')
        if usuario_ctx:
            ctx_parts.append(f'<b>Usuário:</b> {usuario_ctx}')
        if start_date or end_date:
            ctx_parts.append(f"<b>Período:</b> {start_date or '...'} a {end_date or '...'}")
        ctx_parts.append(f'<b>Gerado em:</b> {gen_at}')
        ctx_parts.append(f"<b>Registros:</b> {len(logs)} de {total}"
                         + (f" (limitado a {MAX_ROWS})" if total > MAX_ROWS else ''))

        elements = [
            head_table,
            Table([['']], colWidths=[26.8 * cm], style=TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#1e40af')),
                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ])),
            Spacer(1, 4),
            Paragraph(' &nbsp;|&nbsp; '.join(ctx_parts), ctx_style),
            Spacer(1, 6),
        ]
        col_widths = [28 * mm, 45 * mm, 32 * mm, 150 * mm, 22 * mm]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(table)
        doc.build(elements)
        buf.seek(0)

        filename = f"logs_auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return StreamingResponse(
            buf, media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    @router.get("/audit-logs/document/{collection}/{document_id}")
    async def get_document_audit_history(collection: str, document_id: str, request: Request):
        """Retorna histórico de alterações de um documento específico"""
        current_user = await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        logs = await audit_service.get_document_history(collection, document_id)
        return {'items': logs}


    @router.get("/audit-logs/critical")
    async def get_critical_audit_events(request: Request, hours: int = 24):
        """Retorna eventos críticos das últimas X horas"""
        current_user = await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        logs = await audit_service.get_critical_events(hours)
        return {'items': logs, 'hours': hours}


    @router.get("/audit-logs/stats")
    async def get_audit_stats(request: Request, days: int = 7):
        """Retorna estatísticas de auditoria"""
        current_user = await AuthMiddleware.require_permission(db, 'nav-audit-logs-button', ['super_admin'])(request)

        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Estatísticas por ação
        pipeline_action = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$action', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]

        # Estatísticas por coleção
        pipeline_collection = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$collection', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]

        # Estatísticas por usuário
        pipeline_user = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': {'id': '$user_id', 'email': '$user_email'}, 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]

        # Estatísticas por severidade
        pipeline_severity = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$severity', 'count': {'$sum': 1}}}
        ]

        by_action = await db.audit_logs.aggregate(pipeline_action).to_list(length=20)
        by_collection = await db.audit_logs.aggregate(pipeline_collection).to_list(length=20)
        by_user = await db.audit_logs.aggregate(pipeline_user).to_list(length=10)
        by_severity = await db.audit_logs.aggregate(pipeline_severity).to_list(length=5)

        total = await db.audit_logs.count_documents({'timestamp': {'$gte': cutoff}})

        return {
            'period_days': days,
            'total_events': total,
            'by_action': by_action,
            'by_collection': by_collection,
            'by_user': by_user,
            'by_severity': by_severity
        }

    return router
