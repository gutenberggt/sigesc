"""
Geração de PDFs do módulo RH / Folha de Pagamento.
- Espelho Individual do Servidor
- Folha Consolidada por Escola
- Consolidado da Rede
- Relatório de Auditoria
"""

from io import BytesIO
from typing import Dict, Any, List, Optional
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from xml.sax.saxutils import escape as xml_escape

MONTHS = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
          'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

STATUS_LABELS = {
    'not_started': 'Não Iniciada', 'drafting': 'Em Preenchimento',
    'submitted': 'Enviada', 'under_analysis': 'Em Análise',
    'returned': 'Devolvida', 'approved': 'Aprovada',
    'closed': 'Fechada', 'reopened': 'Reaberta',
}

OCC_LABELS = {
    'falta': 'Falta', 'falta_justificada': 'Falta Justificada',
    'atestado': 'Atestado Médico', 'afastamento': 'Afastamento',
    'licenca': 'Licença', 'substituicao': 'Substituição',
    'hora_complementar': 'Hora Complementar', 'atraso': 'Atraso',
    'saida_antecipada': 'Saída Antecipada', 'outro': 'Outro',
}

FIELD_LABELS = {
    'worked_hours': 'Horas Trabalhadas', 'taught_classes': 'Aulas Ministradas',
    'classes_not_taught': 'Faltas', 'classes_replaced': 'Aulas Repostas',
    'extra_classes': 'Aulas Extras', 'complementary_hours': 'Horas Complementares',
    'complementary_reason': 'Motivo Complementar', 'complementary_type': 'Tipo Complementar',
    'absences': 'Faltas', 'justified_absences': 'Faltas Justificadas',
    'medical_leave_days': 'Dias Atestado', 'leave_days': 'Dias Afastamento',
    'observations': 'Observações',
}


def _safe(text):
    """Escapa texto para ReportLab"""
    if text is None:
        return ''
    return xml_escape(str(text))


def _build_header(elements, styles, title: str, subtitle: str, competency_label: str,
                   mantenedora: dict = None):
    """Cabeçalho padrão dos relatórios HR"""
    mant = mantenedora or {}
    mant_nome = mant.get('nome', 'Prefeitura Municipal de Floresta do Araguaia')
    mant_municipio = mant.get('municipio', 'Floresta do Araguaia')
    mant_estado = mant.get('estado', 'PA')

    header_style = ParagraphStyle('HRHeader', parent=styles['Normal'],
        fontSize=12, alignment=TA_CENTER, spaceAfter=2, fontName='Helvetica-Bold')
    sub_style = ParagraphStyle('HRSub', parent=styles['Normal'],
        fontSize=9, alignment=TA_CENTER, spaceAfter=1, textColor=colors.HexColor('#444444'))
    title_style = ParagraphStyle('HRTitle', parent=styles['Normal'],
        fontSize=11, alignment=TA_CENTER, spaceAfter=2, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1a365d'))

    elements.append(Paragraph(_safe(mant_nome.upper()), header_style))
    elements.append(Paragraph('Secretaria Municipal de Educação', sub_style))
    elements.append(Paragraph(f'{mant_municipio} - {mant_estado}', sub_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f'{title} - {competency_label}', title_style))
    if subtitle:
        elements.append(Paragraph(_safe(subtitle), sub_style))
    elements.append(Spacer(1, 4*mm))


def generate_espelho_individual_pdf(
    employee: Dict[str, Any],
    item: Dict[str, Any],
    occurrences: List[Dict[str, Any]],
    school: Dict[str, Any],
    competency: Dict[str, Any],
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """Gera PDF do espelho individual do servidor (contracheque de frequência)"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1*cm, bottomMargin=1*cm)
    elements = []
    styles = getSampleStyleSheet()

    month = competency.get('month', 1)
    year = competency.get('year', 2026)
    comp_label = f"{MONTHS[month] if 0 < month <= 12 else month}/{year}"

    _build_header(elements, styles, 'ESPELHO INDIVIDUAL DO SERVIDOR',
                  school.get('name', ''), comp_label, mantenedora)

    # Estilos
    label_s = ParagraphStyle('Label', parent=styles['Normal'], fontSize=7.5,
        textColor=colors.HexColor('#666666'), fontName='Helvetica')
    val_s = ParagraphStyle('Val', parent=styles['Normal'], fontSize=9,
        fontName='Helvetica-Bold')
    small_s = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8)
    small_bold = ParagraphStyle('SmallBold', parent=styles['Normal'], fontSize=8,
        fontName='Helvetica-Bold')

    # Dados do servidor
    info_data = [
        [Paragraph('NOME', label_s), Paragraph('MATRÍCULA', label_s),
         Paragraph('CARGO', label_s), Paragraph('VÍNCULO', label_s)],
        [Paragraph(_safe(employee.get('nome', 'N/A')), val_s),
         Paragraph(_safe(employee.get('matricula', 'N/A')), val_s),
         Paragraph(_safe(employee.get('cargo', 'N/A')), val_s),
         Paragraph(_safe(employee.get('tipo_vinculo', 'N/A')), val_s)],
    ]
    info_table = Table(info_data, colWidths=[7*cm, 3.5*cm, 3.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f4f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5*mm))

    # Carga horária e aulas
    section_style = ParagraphStyle('Section', parent=styles['Normal'], fontSize=10,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'),
        spaceBefore=4, spaceAfter=3)
    elements.append(Paragraph('CARGA HORÁRIA E AULAS', section_style))

    ch_data = [
        ['Carga Prevista', 'Horas Trabalhadas', 'Aulas Previstas', 'Aulas Ministradas',
         'Aulas N/ Cumpridas', 'Aulas Repostas', 'Aulas Extras'],
        [f"{item.get('expected_hours', 0)}h", f"{item.get('worked_hours', 0)}h",
         str(item.get('expected_classes', 0)), str(item.get('taught_classes', 0)),
         str(item.get('classes_not_taught', 0)), str(item.get('classes_replaced', 0)),
         str(item.get('extra_classes', 0))],
    ]
    ch_table = Table(ch_data, colWidths=[2.6*cm]*7)
    ch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(ch_table)
    elements.append(Spacer(1, 3*mm))

    # Horas complementares
    comp_hours = item.get('complementary_hours', 0)
    if comp_hours > 0:
        elements.append(Paragraph('HORAS COMPLEMENTARES', section_style))
        hc_data = [
            ['Quantidade', 'Tipo/Motivo', 'Período', 'Autorizado por'],
            [f"{comp_hours}h",
             _safe(item.get('complementary_type') or item.get('complementary_reason') or '-'),
             _safe(item.get('complementary_period') or '-'),
             _safe(item.get('complementary_authorized_by') or '-')],
        ]
        hc_table = Table(hc_data, colWidths=[2.5*cm, 7*cm, 4*cm, 4.5*cm])
        hc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ede9fe')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c4b5fd')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(hc_table)
        elements.append(Spacer(1, 3*mm))

    # Resumo de ausências
    elements.append(Paragraph('RESUMO DE AUSÊNCIAS', section_style))
    abs_data = [
        ['Faltas', 'Faltas Justificadas', 'Dias de Atestado', 'Dias de Afastamento/Licença', 'Total Ausências'],
        [str(item.get('absences', 0)), str(item.get('justified_absences', 0)),
         str(item.get('medical_leave_days', 0)), str(item.get('leave_days', 0)),
         str((item.get('absences', 0) or 0) + (item.get('justified_absences', 0) or 0) +
             (item.get('medical_leave_days', 0) or 0) + (item.get('leave_days', 0) or 0))],
    ]
    abs_table = Table(abs_data, colWidths=[3.6*cm]*5)
    abs_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fee2e2')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fca5a5')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(abs_table)
    elements.append(Spacer(1, 4*mm))

    # Ocorrências detalhadas
    active_occs = [o for o in occurrences if o.get('status') == 'active']
    if active_occs:
        elements.append(Paragraph('OCORRÊNCIAS DO MÊS', section_style))
        occ_header = ['Tipo', 'Período', 'Dias', 'Motivo/Justificativa', 'Doc.']
        occ_rows = [occ_header]
        for occ in active_occs:
            period = occ.get('start_date', '')
            if occ.get('end_date') and occ['end_date'] != occ.get('start_date'):
                period += f" a {occ['end_date']}"
            occ_rows.append([
                OCC_LABELS.get(occ.get('type', ''), occ.get('type', '')),
                period,
                str(occ.get('days', 0)),
                _safe((occ.get('reason') or occ.get('justification') or '-')[:80]),
                'Sim' if occ.get('document_url') else 'Não',
            ])

        occ_table = Table(occ_rows, colWidths=[3*cm, 3.5*cm, 1.5*cm, 8*cm, 2*cm])
        occ_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#93c5fd')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        # Destacar ocorrências sem documento
        for i, occ in enumerate(active_occs, 1):
            if not occ.get('document_url') and occ.get('type') in ('atestado', 'afastamento', 'licenca'):
                occ_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, i), (4, i), colors.red),
                    ('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'),
                ]))
        elements.append(occ_table)
        elements.append(Spacer(1, 3*mm))

    # Observações
    obs = item.get('observations')
    if obs:
        elements.append(Paragraph('OBSERVAÇÕES', section_style))
        elements.append(Paragraph(_safe(obs), small_s))
        elements.append(Spacer(1, 3*mm))

    # Validação
    if item.get('validation_notes'):
        elements.append(Paragraph('ALERTAS DE VALIDAÇÃO', section_style))
        elements.append(Paragraph(_safe(item['validation_notes']),
            ParagraphStyle('Alert', parent=styles['Normal'], fontSize=8,
                textColor=colors.HexColor('#b45309'))))
        elements.append(Spacer(1, 4*mm))

    # Assinaturas
    elements.append(Spacer(1, 10*mm))
    sig_data = [
        ['_' * 40, '', '_' * 40],
        ['Servidor(a)', '', 'Diretor(a) / Responsável'],
    ]
    sig_table = Table(sig_data, colWidths=[7*cm, 4*cm, 7*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sig_table)

    # Rodapé
    elements.append(Spacer(1, 5*mm))
    footer_s = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7,
        alignment=TA_CENTER, textColor=colors.HexColor('#999999'))
    elements.append(Paragraph(
        f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} - SIGESC',
        footer_s))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_folha_escola_pdf(
    school: Dict[str, Any],
    payroll: Dict[str, Any],
    items: List[Dict[str, Any]],
    competency: Dict[str, Any],
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """Gera PDF da folha consolidada por escola"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        rightMargin=1*cm, leftMargin=1*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    elements = []
    styles = getSampleStyleSheet()

    month = competency.get('month', 1)
    year = competency.get('year', 2026)
    comp_label = f"{MONTHS[month] if 0 < month <= 12 else month}/{year}"

    _build_header(elements, styles, 'FOLHA MENSAL DA ESCOLA',
                  school.get('name', ''), comp_label, mantenedora)

    status_label = STATUS_LABELS.get(payroll.get('status', ''), payroll.get('status', ''))
    info_s = ParagraphStyle('Info', parent=styles['Normal'], fontSize=8, alignment=TA_LEFT)
    elements.append(Paragraph(f'<b>Status da Folha:</b> {status_label} | <b>Total de Servidores:</b> {len(items)}', info_s))
    elements.append(Spacer(1, 3*mm))

    # Tabela de servidores
    header = ['Servidor', 'Matrícula', 'Cargo', 'CH Prev.', 'H. Trab.',
              'Aulas', 'H. Compl.', 'Faltas', 'Atest.', 'Afast.', 'Status']
    rows = [header]

    totals = {'expected': 0, 'worked': 0, 'compl': 0, 'faltas': 0, 'atest': 0, 'afast': 0}
    for it in items:
        taught = it.get('taught_classes', 0) or 0
        expected_c = it.get('expected_classes', 0) or 0
        status_icon = {'ok': 'OK', 'has_issues': 'PEND.', 'pending': '-'}.get(it.get('validation_status', ''), '-')

        totals['expected'] += it.get('expected_hours', 0) or 0
        totals['worked'] += it.get('worked_hours', 0) or 0
        totals['compl'] += it.get('complementary_hours', 0) or 0
        totals['faltas'] += it.get('absences', 0) or 0
        totals['atest'] += it.get('medical_leave_days', 0) or 0
        totals['afast'] += it.get('leave_days', 0) or 0

        rows.append([
            _safe((it.get('employee_name') or 'N/A')[:30]),
            _safe(it.get('employee_matricula') or '-'),
            _safe((it.get('employee_cargo') or '-')[:15]),
            f"{it.get('expected_hours', 0)}h",
            f"{it.get('worked_hours', 0)}h",
            f"{taught}/{expected_c}",
            f"{it.get('complementary_hours', 0)}h",
            str(it.get('absences', 0) or 0),
            str(it.get('medical_leave_days', 0) or 0),
            str(it.get('leave_days', 0) or 0),
            status_icon,
        ])

    # Linha de totais
    rows.append([
        'TOTAL', '', '', f"{totals['expected']}h", f"{totals['worked']}h",
        '', f"{totals['compl']}h", str(totals['faltas']),
        str(totals['atest']), str(totals['afast']), ''
    ])

    col_widths = [5*cm, 2.2*cm, 2.5*cm, 1.8*cm, 1.8*cm, 1.5*cm, 1.8*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')]),
        # Linha de totais
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    # Destacar linhas com pendência
    for i, it in enumerate(items, 1):
        if it.get('validation_status') == 'has_issues':
            table.setStyle(TableStyle([
                ('TEXTCOLOR', (-1, i), (-1, i), colors.HexColor('#b45309')),
                ('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold'),
            ]))
    elements.append(table)

    # Assinaturas
    elements.append(Spacer(1, 12*mm))
    sig_data = [
        ['_' * 35, '', '_' * 35, '', '_' * 35],
        ['Diretor(a)', '', 'Secretário(a) Escolar', '', 'Secretaria de Educação'],
    ]
    sig_table = Table(sig_data, colWidths=[6*cm, 2*cm, 6*cm, 2*cm, 6*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
    ]))
    elements.append(sig_table)

    elements.append(Spacer(1, 4*mm))
    footer_s = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=6.5,
        alignment=TA_CENTER, textColor=colors.HexColor('#999999'))
    elements.append(Paragraph(
        f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} - SIGESC', footer_s))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_consolidado_rede_pdf(
    payrolls: List[Dict[str, Any]],
    competency: Dict[str, Any],
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """Gera PDF consolidado de toda a rede"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        rightMargin=1*cm, leftMargin=1*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    elements = []
    styles = getSampleStyleSheet()

    month = competency.get('month', 1)
    year = competency.get('year', 2026)
    comp_label = f"{MONTHS[month] if 0 < month <= 12 else month}/{year}"

    _build_header(elements, styles, 'CONSOLIDADO DA REDE MUNICIPAL',
                  '', comp_label, mantenedora)

    header = ['Escola', 'Servidores', 'CH Prev.', 'H. Trab.', 'H. Compl.',
              'Faltas', 'Atest.', 'Afast.', 'Pendências', 'Status']
    rows = [header]

    grand_totals = {k: 0 for k in ['emps', 'expected', 'worked', 'compl', 'faltas', 'atest', 'afast', 'issues']}

    for p in payrolls:
        items = p.get('items', [])
        n_emps = len(items)
        expected = sum(i.get('expected_hours', 0) or 0 for i in items)
        worked = sum(i.get('worked_hours', 0) or 0 for i in items)
        compl = sum(i.get('complementary_hours', 0) or 0 for i in items)
        faltas = sum(i.get('absences', 0) or 0 for i in items)
        atest = sum(i.get('medical_leave_days', 0) or 0 for i in items)
        afast = sum(i.get('leave_days', 0) or 0 for i in items)
        issues = sum(1 for i in items if i.get('validation_status') == 'has_issues')

        grand_totals['emps'] += n_emps
        grand_totals['expected'] += expected
        grand_totals['worked'] += worked
        grand_totals['compl'] += compl
        grand_totals['faltas'] += faltas
        grand_totals['atest'] += atest
        grand_totals['afast'] += afast
        grand_totals['issues'] += issues

        rows.append([
            _safe((p.get('school_name') or 'N/A')[:35]),
            str(n_emps), f"{expected}h", f"{worked}h", f"{compl}h",
            str(faltas), str(atest), str(afast), str(issues),
            STATUS_LABELS.get(p.get('status', ''), p.get('status', '')),
        ])

    rows.append([
        'TOTAL REDE', str(grand_totals['emps']),
        f"{grand_totals['expected']}h", f"{grand_totals['worked']}h",
        f"{grand_totals['compl']}h", str(grand_totals['faltas']),
        str(grand_totals['atest']), str(grand_totals['afast']),
        str(grand_totals['issues']), ''
    ])

    col_widths = [6*cm, 2*cm, 2*cm, 2*cm, 2*cm, 1.8*cm, 1.8*cm, 1.8*cm, 2*cm, 3*cm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 8*mm))
    footer_s = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=6.5,
        alignment=TA_CENTER, textColor=colors.HexColor('#999999'))
    elements.append(Paragraph(
        f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} - SIGESC', footer_s))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_auditoria_pdf(
    logs: List[Dict[str, Any]],
    competency: Dict[str, Any],
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """Gera PDF do relatório de auditoria"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        rightMargin=1*cm, leftMargin=1*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    elements = []
    styles = getSampleStyleSheet()

    month = competency.get('month', 1)
    year = competency.get('year', 2026)
    comp_label = f"{MONTHS[month] if 0 < month <= 12 else month}/{year}"

    _build_header(elements, styles, 'RELATÓRIO DE AUDITORIA',
                  '', comp_label, mantenedora)

    info_s = ParagraphStyle('Info', parent=styles['Normal'], fontSize=8)
    elements.append(Paragraph(f'<b>Total de registros:</b> {len(logs)}', info_s))
    elements.append(Spacer(1, 3*mm))

    if not logs:
        elements.append(Paragraph('Nenhuma alteração registrada nesta competência.',
            ParagraphStyle('Empty', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER)))
    else:
        header = ['Data/Hora', 'Usuário', 'Ação', 'Campo', 'Valor Anterior', 'Valor Novo', 'Justificativa']
        rows = [header]
        for log in logs:
            ts = log.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts_str = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                ts_str = ts[:16] if ts else '-'

            changes = log.get('changes', [])
            action = log.get('action', '-')
            user_name = _safe(log.get('user_name', 'Sistema'))
            justification = _safe(log.get('justification', ''))

            if changes:
                for c in changes:
                    rows.append([
                        ts_str, user_name, action,
                        FIELD_LABELS.get(c.get('field', ''), c.get('field', '-')),
                        _safe(str(c.get('old_value', '-'))[:25]),
                        _safe(str(c.get('new_value', '-'))[:25]),
                        justification[:30] if justification else '-',
                    ])
            else:
                rows.append([ts_str, user_name, action, '-', '-', '-', justification[:30] or '-'])

        col_widths = [3*cm, 4*cm, 2.5*cm, 3.5*cm, 4*cm, 4*cm, 4*cm]
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6.5),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        elements.append(table)

    elements.append(Spacer(1, 6*mm))
    footer_s = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=6.5,
        alignment=TA_CENTER, textColor=colors.HexColor('#999999'))
    elements.append(Paragraph(
        f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} - SIGESC', footer_s))

    doc.build(elements)
    buffer.seek(0)
    return buffer
