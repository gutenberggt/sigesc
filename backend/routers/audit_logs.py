"""Router de Auditoria — tenant-scoped e fail-closed (MT-1)."""

from datetime import datetime
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from auth_middleware import AuthMiddleware
from utils.client_time import local_now


router = APIRouter(tags=["Auditoria"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura as rotas de auditoria no banco canônico do SIGESC."""

    async def _require_audit_access(request: Request) -> tuple[dict, str]:
        user = await AuthMiddleware.require_permission(
            db, 'nav-audit-logs-button', ['super_admin']
        )(request)
        tenant_id = str(
            user.get('active_mantenedora_id') or user.get('mantenedora_id') or ''
        ).strip()
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    'code': 'AUDIT_TENANT_REQUIRED',
                    'message': 'Selecione uma mantenedora para visualizar a auditoria.',
                },
            )
        return user, tenant_id

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
        search: Optional[str] = None,
    ):
        """Lista somente eventos atribuíveis à mantenedora operacional ativa."""
        _, tenant_id = await _require_audit_access(request)
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
            'search': search,
        }
        filters = {key: value for key, value in filters.items() if value is not None}
        logs, total = await audit_service.get_logs(
            filters, skip, limit, tenant_id=tenant_id
        )
        return {'items': logs, 'total': total, 'skip': skip, 'limit': limit}

    @router.get("/audit-logs/user/{user_id}")
    async def get_user_audit_logs(
        user_id: str, request: Request, limit: int = 20
    ):
        _, tenant_id = await _require_audit_access(request)
        logs = await audit_service.get_user_activity(
            user_id, limit, tenant_id=tenant_id
        )
        return {'items': logs}

    @router.get("/audit-logs/document/{collection}/{document_id}")
    async def get_document_audit_history(
        collection: str, document_id: str, request: Request
    ):
        _, tenant_id = await _require_audit_access(request)
        logs = await audit_service.get_document_history(
            collection, document_id, tenant_id=tenant_id
        )
        return {'items': logs}

    @router.get("/audit-logs/critical")
    async def get_critical_audit_events(
        request: Request, hours: int = 24
    ):
        _, tenant_id = await _require_audit_access(request)
        logs = await audit_service.get_critical_events(
            hours, tenant_id=tenant_id
        )
        return {'items': logs, 'hours': hours}

    @router.get("/audit-logs/stats")
    async def get_audit_stats(request: Request, days: int = 7):
        _, tenant_id = await _require_audit_access(request)
        return await audit_service.get_stats(days=days, tenant_id=tenant_id)

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
        """Gera PDF dos logs visíveis exclusivamente no tenant ativo."""
        _, tenant_id = await _require_audit_access(request)
        max_rows = 2000
        filters = {
            'user_id': user_id,
            'user_role': user_role,
            'school_id': school_id,
            'collection': collection,
            'action': action,
            'category': category,
            'start_date': start_date,
            'end_date': end_date,
            'academic_year': academic_year,
            'search': search,
        }
        filters = {key: value for key, value in filters.items() if value is not None}
        logs, total = await audit_service.get_logs(
            filters, skip=0, limit=max_rows, tenant_id=tenant_id
        )

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from pdf.utils import get_logo_image

        action_labels = {
            'login': 'Login',
            'logout': 'Logout',
            'create': 'Criação',
            'update': 'Alteração',
            'delete': 'Exclusão',
            'export': 'Exportação',
            'import': 'Importação',
            'approve': 'Aprovação',
            'reject': 'Rejeição',
        }
        collection_labels = {
            'users': 'Usuários',
            'students': 'Estudantes',
            'grades': 'Notas',
            'attendance': 'Frequência',
            'content_entries': 'Conteúdos',
            'staff': 'Servidores(as)',
            'schools': 'Escolas',
            'classes': 'Turmas',
            'courses': 'Componentes',
            'enrollments': 'Matrículas',
            'school_assignments': 'Lotações',
            'teacher_assignments': 'Alocações',
            'mantenedora': 'Mantenedora',
            'calendario_letivo': 'Calendário',
        }

        def _fmt_dt(value):
            if not value:
                return '-'
            try:
                return datetime.fromisoformat(
                    str(value).replace('Z', '+00:00')
                ).strftime('%d/%m/%Y %H:%M')
            except Exception:
                return str(value)

        # Cabeçalho institucional também é tenant-scoped: nunca usa a primeira
        # mantenedora como fallback.
        mantenedora = await db.mantenedoras.find_one(
            {'id': tenant_id}, {'_id': 0}
        )
        if not mantenedora:
            mantenedora = await db['mantenedora'].find_one(
                {'id': tenant_id}, {'_id': 0}
            )
        mantenedora = mantenedora or {}
        municipio = mantenedora.get('municipio', 'Município')
        estado = mantenedora.get('estado', '')
        nome = mantenedora.get('nome', 'Mantenedora')
        secretaria = mantenedora.get('secretaria', 'Secretaria de Educação')
        slogan = mantenedora.get('slogan', '')
        logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
        logo = get_logo_image(width=2.3 * cm, height=2.7 * cm, logo_url=logo_url)

        escola_nome = None
        if school_id:
            school = await db.schools.find_one(
                {'id': school_id, 'mantenedora_id': tenant_id},
                {'_id': 0, 'name': 1},
            )
            escola_nome = (school or {}).get('name')

        usuario_ctx = None
        if user_id:
            target_user = await db.users.find_one(
                {'id': user_id, 'mantenedora_id': tenant_id},
                {'_id': 0, 'full_name': 1, 'name': 1, 'email': 1, 'role': 1},
            )
            if target_user:
                role_labels = {
                    'super_admin': 'Super Administrador',
                    'admin': 'Administrador(a)',
                    'gerente': 'Gerente',
                    'secretario': 'Secretário(a)',
                    'coordenador': 'Coordenador(a)',
                    'professor': 'Professor(a)',
                    'auxiliar_secretaria': 'Auxiliar de Secretaria',
                    'diretor': 'Diretor(a)',
                }
                role_label = role_labels.get(
                    target_user.get('role'), target_user.get('role') or ''
                )
                user_name = (
                    target_user.get('full_name')
                    or target_user.get('name')
                    or target_user.get('email')
                    or '-'
                )
                usuario_ctx = user_name + (
                    f" — {role_label}" if role_label else ''
                )

        styles = getSampleStyleSheet()
        cell = ParagraphStyle('cell', parent=styles['Normal'], fontSize=7, leading=9)
        left_style = ParagraphStyle('hleft', fontSize=10, alignment=TA_LEFT, leading=13)
        right_style = ParagraphStyle('hright', fontSize=10, alignment=TA_RIGHT, leading=15)
        ctx_style = ParagraphStyle('ctx', parent=styles['Normal'], fontSize=8, leading=11)

        data = [['Data/Hora', 'Usuário', 'Ação', 'Descrição', 'Tempo']]
        for log in logs:
            tempo_dias = log.get('tempo_dias')
            tempo = (
                f"{tempo_dias} dia{'s' if tempo_dias != 1 else ''}"
                if isinstance(tempo_dias, int)
                else '-'
            )
            acao = action_labels.get(log.get('action'), log.get('action') or '-')
            colecao = collection_labels.get(
                log.get('collection'), log.get('collection') or ''
            )
            data.append([
                Paragraph(escape(_fmt_dt(log.get('timestamp_local') or log.get('timestamp'))), cell),
                Paragraph(escape(log.get('user_name') or log.get('user_email') or '-'), cell),
                Paragraph(f"{escape(acao)}<br/><font size=6 color='#888888'>{escape(colecao)}</font>", cell),
                Paragraph(escape(log.get('description') or '-'), cell),
                Paragraph(escape(tempo), cell),
            ])

        if len(data) == 1:
            data.append([
                Paragraph('-', cell),
                Paragraph('-', cell),
                Paragraph('-', cell),
                Paragraph('Nenhum registro encontrado para os filtros informados.', cell),
                Paragraph('-', cell),
            ])

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=12 * mm,
        )

        uf = f" - {estado}" if estado else ''
        slogan_html = (
            f'<br/><font size="8" color="#666666"><i>"{escape(slogan)}"</i></font>'
            if slogan
            else ''
        )
        header_left = (
            f'<font size="12"><b>{escape(nome.upper())}</b></font><br/>'
            f'<font size="9"><i>{escape(secretaria)}</i></font><br/>'
            f'<font size="8" color="#555555">{escape(municipio + uf)}</font>'
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
        ]))

        context_parts = []
        if escola_nome:
            context_parts.append(f'<b>Escola:</b> {escape(escola_nome)}')
        if usuario_ctx:
            context_parts.append(f'<b>Usuário:</b> {escape(usuario_ctx)}')
        if start_date or end_date:
            context_parts.append(
                f"<b>Período:</b> {escape(start_date or '...')} a {escape(end_date or '...')}"
            )
        context_parts.append(f'<b>Gerado em:</b> {local_now().strftime("%d/%m/%Y %H:%M")}')
        context_parts.append(
            f"<b>Registros:</b> {len(logs)} de {total}"
            + (f" (limitado a {max_rows})" if total > max_rows else '')
        )

        elements = [
            head_table,
            Table([['']], colWidths=[26.8 * cm], style=TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#1e40af')),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ])),
            Spacer(1, 4),
            Paragraph(' &nbsp;|&nbsp; '.join(context_parts), ctx_style),
            Spacer(1, 6),
        ]

        table = Table(
            data,
            colWidths=[28 * mm, 45 * mm, 32 * mm, 150 * mm, 22 * mm],
            repeatRows=1,
        )
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
        document.build(elements)
        buffer.seek(0)

        filename = f"logs_auditoria_{local_now().strftime('%Y%m%d_%H%M')}.pdf"
        return StreamingResponse(
            buffer,
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    return router
