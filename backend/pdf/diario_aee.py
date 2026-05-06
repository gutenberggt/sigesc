"""
Gerador de PDF do Diário AEE - Visão Consolidada.

Estrutura (espelhando a tela):
  - Cabeçalho institucional (brasão + mantenedora + secretaria) | Escola
  - Título: "DIÁRIO DE AEE - VISÃO CONSOLIDADA"
  - Info: Escola | Turma AEE | Professor AEE | Ano Letivo
  - KPIs: Estudantes | Atendimentos | Planos Ativos | Carga Horária
  - Grade de Atendimentos (Segunda a Sexta)
  - Fichas Individuais (uma por aluno)
"""
from io import BytesIO
from typing import Dict, Any, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

try:
    from pdf.utils import get_logo_image
except ImportError:
    get_logo_image = None


DIAS_ORDEM = ['segunda', 'terca', 'quarta', 'quinta', 'sexta']
DIAS_LABELS = {
    'segunda': 'Segunda', 'terca': 'Terça', 'quarta': 'Quarta',
    'quinta': 'Quinta', 'sexta': 'Sexta',
}
PUBLICO_ALVO_LABELS = {
    'deficiencia_fisica': 'Deficiência Física',
    'deficiencia_intelectual': 'Deficiência Intelectual',
    'deficiencia_visual': 'Deficiência Visual',
    'deficiencia_auditiva': 'Deficiência Auditiva',
    'surdocegueira': 'Surdocegueira',
    'transtorno_espectro_autista': 'Transtorno do Espectro Autista',
    'altas_habilidades': 'Altas Habilidades/Superdotação',
    'deficiencia_multipla': 'Deficiência Múltipla',
}
MODALIDADE_LABELS = {
    'individual': 'Individual',
    'pequeno_grupo': 'Pequeno Grupo',
    'coensino': 'Coensino',
    'mista': 'Mista',
}


def _label(value, mapping):
    if not value:
        return '-'
    return mapping.get(value, str(value).replace('_', ' ').title())


def _build_header(mantenedora: Dict[str, Any], school: Dict[str, Any]):
    mant_nome = (mantenedora or {}).get('nome') or 'Prefeitura Municipal'
    mant_sec = (mantenedora or {}).get('secretaria', 'Secretaria Municipal de Educação')
    mant_slogan = (mantenedora or {}).get('slogan', '')
    logo = None
    if get_logo_image:
        logo_url = (mantenedora or {}).get('brasao_url') or (mantenedora or {}).get('logotipo_url')
        try:
            logo = get_logo_image(width=2.2*cm, height=2.2*cm, logo_url=logo_url)
        except Exception:
            logo = None

    institucional_style = ParagraphStyle(
        'InstDiario', fontSize=9, alignment=0, leading=12, fontName='Helvetica',
    )
    value_style = ParagraphStyle(
        'ValDiario', fontSize=9, leading=12, fontName='Helvetica', alignment=1,
    )
    slogan_html = (
        f'<br/><font size="7" color="#666666"><i>"{mant_slogan}"</i></font>' if mant_slogan else ''
    )
    instit_html = (
        f'<font size="10"><b>{mant_nome}</b></font><br/>'
        f'<font size="8"><i>{mant_sec}</i></font>'
        f'{slogan_html}'
    )
    escola_html = f'<b>{(school or {}).get("name", "Escola")}</b>'

    if logo:
        header = Table(
            [[logo, Paragraph(instit_html, institucional_style), Paragraph(escola_html, value_style)]],
            colWidths=[2.6*cm, 8*cm, 7.5*cm],
        )
        header.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ]))
    else:
        header = Table(
            [[Paragraph(instit_html, institucional_style), Paragraph(escola_html, value_style)]],
            colWidths=[10*cm, 8*cm],
        )
        header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, 0), 'MIDDLE')]))
    return header


def _build_kpis(total_estudantes: int, total_atendimentos: int,
                planos_ativos: int, carga_horaria_horas: float):
    kpi_label = ParagraphStyle(
        'KPILabel', fontSize=8, leading=10, fontName='Helvetica',
        alignment=1, textColor=colors.Color(0.3, 0.3, 0.3),
    )
    kpi_big = ParagraphStyle(
        'KPIBig', fontSize=18, leading=22, fontName='Helvetica-Bold', alignment=1,
    )

    def cell(number, label, bg, fg):
        num_style = ParagraphStyle('KPINum', parent=kpi_big, textColor=fg)
        return [[Paragraph(str(number), num_style)], [Paragraph(label, kpi_label)]]

    # Cores aproximando os cards da tela
    blue_bg = colors.Color(0.90, 0.95, 1.00)
    blue_fg = colors.Color(0.13, 0.45, 0.85)
    green_bg = colors.Color(0.90, 0.97, 0.92)
    green_fg = colors.Color(0.15, 0.65, 0.28)
    purple_bg = colors.Color(0.96, 0.93, 1.00)
    purple_fg = colors.Color(0.55, 0.30, 0.85)
    orange_bg = colors.Color(1.00, 0.96, 0.88)
    orange_fg = colors.Color(0.95, 0.55, 0.10)

    col1 = Table(cell(total_estudantes, 'Estudantes', blue_bg, blue_fg))
    col1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), blue_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, blue_fg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    col2 = Table(cell(total_atendimentos, 'Atendimentos', green_bg, green_fg))
    col2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), green_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, green_fg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    col3 = Table(cell(planos_ativos, 'Planos Ativos', purple_bg, purple_fg))
    col3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), purple_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, purple_fg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    col4 = Table(cell(f'{carga_horaria_horas}h', 'Carga Horária', orange_bg, orange_fg))
    col4.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), orange_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, orange_fg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    kpis_table = Table([[col1, col2, col3, col4]], colWidths=[4.5*cm]*4)
    kpis_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    return kpis_table


def _build_grade_atendimentos(grade_horarios: Dict[str, List[Dict[str, Any]]]):
    """Grade semanal Segunda-Sexta com alunos e horários."""
    header_style = ParagraphStyle(
        'GridHead', fontSize=9, fontName='Helvetica-Bold', alignment=0,
        textColor=colors.Color(0.2, 0.2, 0.2), leading=11,
    )
    student_style = ParagraphStyle(
        'GridStudent', fontSize=8, fontName='Helvetica-Bold', alignment=0, leading=10,
    )
    time_style = ParagraphStyle(
        'GridTime', fontSize=7, fontName='Helvetica', alignment=0,
        textColor=colors.Color(0.4, 0.4, 0.4), leading=9,
    )

    header_row = [Paragraph(DIAS_LABELS[d], header_style) for d in DIAS_ORDEM]
    cells_row = []
    for dia in DIAS_ORDEM:
        slots = grade_horarios.get(dia, [])
        if not slots:
            cells_row.append(Paragraph('<font color="#888888">-</font>', time_style))
        else:
            parts = []
            for s in slots:
                nome = (s.get('student_name') or '')[:24]
                h_ini = s.get('horario_inicio') or '--:--'
                h_fim = s.get('horario_fim') or '--:--'
                parts.append(f'<b>{nome}</b><br/>'
                             f'<font size="7" color="#666666">{h_ini} - {h_fim}</font>')
            cells_row.append(Paragraph('<br/><br/>'.join(parts), student_style))

    grade = Table([header_row, cells_row], colWidths=[3.6*cm]*5)
    grade.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.Color(0.6, 0.6, 0.6)),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return grade


def _build_ficha_individual(ficha: Dict[str, Any], subtitle: ParagraphStyle,
                            label: ParagraphStyle, value: ParagraphStyle,
                            small: ParagraphStyle):
    """Monta a ficha individual de um aluno."""
    plano = ficha['plano']
    student = ficha['student']
    atendimentos = ficha['atendimentos']
    stats = ficha['estatisticas']

    out = []
    out.append(Paragraph(f"Ficha Individual — {student.get('full_name') or 'N/A'}",
                         subtitle))
    out.append(Spacer(1, 6))

    # Identificação
    ident = [
        [Paragraph('Aluno(a):', label),
         Paragraph(student.get('full_name') or '-', value),
         Paragraph('Matrícula:', label),
         Paragraph(str(student.get('enrollment_number') or '-'), value)],
        [Paragraph('Data Nasc.:', label),
         Paragraph(student.get('birth_date') or '-', value),
         Paragraph('Público-Alvo:', label),
         Paragraph(_label(plano.get('publico_alvo'), PUBLICO_ALVO_LABELS), value)],
        [Paragraph('Turma Origem:', label),
         Paragraph(plano.get('turma_origem_nome') or '-', value),
         Paragraph('Prof. Regente:', label),
         Paragraph(plano.get('professor_regente_nome') or '-', value)],
        [Paragraph('Prof. AEE:', label),
         Paragraph(plano.get('professor_aee_nome') or '-', value),
         Paragraph('Status:', label),
         Paragraph((plano.get('status') or '-').title(), value)],
    ]
    ident_t = Table(ident, colWidths=[2.5*cm, 6*cm, 2.5*cm, 6*cm])
    ident_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.96, 0.96, 0.96)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.96, 0.96, 0.96)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    out.append(ident_t)
    out.append(Spacer(1, 10))

    # Cronograma
    out.append(Paragraph('CRONOGRAMA DE ATENDIMENTO', subtitle))
    dias_txt = ', '.join(DIAS_LABELS.get(d, d) for d in (plano.get('dias_atendimento') or [])) or '-'
    cron = [
        [Paragraph('Dias:', label), Paragraph(dias_txt, value),
         Paragraph('Horário:', label),
         Paragraph(f"{plano.get('horario_inicio') or '--:--'} às {plano.get('horario_fim') or '--:--'}", value)],
        [Paragraph('Modalidade:', label),
         Paragraph(_label(plano.get('modalidade'), MODALIDADE_LABELS), value),
         Paragraph('Local:', label),
         Paragraph(plano.get('local_atendimento') or 'Sala de Recursos Multifuncionais', value)],
    ]
    cron_t = Table(cron, colWidths=[2.5*cm, 6*cm, 2.5*cm, 6*cm])
    cron_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.96, 0.96, 0.96)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.96, 0.96, 0.96)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    out.append(cron_t)
    out.append(Spacer(1, 10))

    # Objetivos
    out.append(Paragraph('OBJETIVOS DO PLANO AEE', subtitle))
    objetivos = plano.get('objetivos') or []
    if objetivos:
        obj_lines = []
        prazo_label = {'curto': 'Curto Prazo', 'medio': 'Médio Prazo', 'longo': 'Longo Prazo'}
        for i, obj in enumerate(objetivos, 1):
            pz = prazo_label.get(obj.get('prazo', ''), obj.get('prazo', ''))
            desc = obj.get('descricao', '')
            obj_lines.append(f'{i}. <b>[{pz}]</b> {desc}')
        out.append(Paragraph('<br/>'.join(obj_lines), small))
    else:
        out.append(Paragraph('<i>Nenhum objetivo registrado.</i>', small))
    out.append(Spacer(1, 10))

    # Registro de Atendimentos
    out.append(Paragraph('REGISTRO DE ATENDIMENTOS', subtitle))
    if atendimentos:
        atend_header = ['Data', 'Horário', 'Presença', 'Atividade Realizada', 'Nível Apoio']
        rows = [atend_header]
        for a in atendimentos[-30:]:
            presenca = 'P' if a.get('presente', True) else 'F'
            nivel = (a.get('nivel_apoio') or '-').replace('_', ' ').title()[:15]
            atividade = (a.get('atividade_realizada') or '-')[:60]
            rows.append([
                a.get('data', '-'),
                f"{a.get('horario_inicio', '-')} - {a.get('horario_fim', '-')}",
                presenca,
                atividade,
                nivel,
            ])
        t = Table(rows, colWidths=[2*cm, 2.8*cm, 1.6*cm, 7.6*cm, 3*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.15, 0.30, 0.55)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.75, 0.75, 0.75)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.Color(0.97, 0.97, 0.97)]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        out.append(t)
    else:
        out.append(Paragraph('<i>Nenhum atendimento registrado.</i>', small))
    out.append(Spacer(1, 10))

    # Resumo
    out.append(Paragraph('RESUMO DO PERÍODO', subtitle))
    resumo = [[
        Paragraph(f"<b>Total:</b> {stats.get('total_atendimentos', 0)}", small),
        Paragraph(f"<b>Presenças:</b> {stats.get('presencas', 0)}", small),
        Paragraph(f"<b>Ausências:</b> {stats.get('ausencias', 0)}", small),
        Paragraph(f"<b>Frequência:</b> {stats.get('frequencia_percentual', 0)}%", small),
        Paragraph(f"<b>C.H. Realizada:</b> {stats.get('carga_horaria_realizada_horas', 0)}h", small),
    ]]
    resumo_t = Table(resumo, colWidths=[3.4*cm]*5)
    resumo_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('BACKGROUND', (0, 0), (-1, -1), colors.Color(0.97, 0.98, 1.0)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    out.append(resumo_t)
    return out


def generate_diario_aee_pdf(
    school: Dict[str, Any],
    mantenedora: Dict[str, Any],
    academic_year: int,
    turma_aee_nome: str,
    professor_aee_nome: str,
    fichas: List[Dict[str, Any]],
    grade_horarios: Dict[str, List[Dict[str, Any]]],
    total_atendimentos: int,
    planos_ativos: int,
    carga_horaria_horas: float,
    periodo_label: str = None,
    data_inicio: str = None,
    data_fim: str = None,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.2*cm, bottomMargin=1.5*cm,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        title='Diário AEE - Visão Consolidada',
    )

    # Estilos
    title = ParagraphStyle('TitleDiario', fontSize=14, leading=17,
                           fontName='Helvetica-Bold', alignment=1, spaceAfter=4)
    subtitle = ParagraphStyle('SubtitleDiario', fontSize=11, leading=15,
                              fontName='Helvetica-Bold',
                              textColor=colors.Color(0.15, 0.35, 0.6),
                              spaceBefore=4, spaceAfter=4)
    label = ParagraphStyle('LabelDiario', fontSize=8, leading=10,
                           fontName='Helvetica-Bold',
                           textColor=colors.Color(0.25, 0.25, 0.25))
    value = ParagraphStyle('ValDiario2', fontSize=9, leading=12,
                           fontName='Helvetica')
    small = ParagraphStyle('SmallDiario', fontSize=8.5, leading=11,
                           fontName='Helvetica')

    elements = []

    # === Cabeçalho institucional ===
    elements.append(_build_header(mantenedora, school))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('DIÁRIO DE AEE - VISÃO CONSOLIDADA', title))
    elements.append(Paragraph('<font size="9" color="#555555">Atendimento Educacional Especializado</font>',
                              ParagraphStyle('SubDiario', fontSize=9, alignment=1)))
    elements.append(Spacer(1, 10))

    # === Info geral ===
    periodo_txt = '-'
    if periodo_label and (data_inicio or data_fim):
        di_fmt = data_inicio or ''
        df_fmt = data_fim or ''
        # YYYY-MM-DD -> dd/mm/aaaa
        def _br(s):
            try:
                from datetime import datetime as _d
                return _d.strptime(s, '%Y-%m-%d').strftime('%d/%m/%Y')
            except Exception:
                return s or '-'
        periodo_txt = f"{periodo_label} ({_br(di_fmt)} a {_br(df_fmt)})"
    elif periodo_label:
        periodo_txt = periodo_label
    elif data_inicio or data_fim:
        periodo_txt = f"{data_inicio or '?'} a {data_fim or '?'}"
    else:
        periodo_txt = 'Ano completo'

    info = [
        [Paragraph('Escola/Polo:', label),
         Paragraph((school or {}).get('name') or '-', value),
         Paragraph('Ano Letivo:', label),
         Paragraph(str(academic_year), value)],
        [Paragraph('Turma AEE:', label),
         Paragraph(turma_aee_nome or '-', value),
         Paragraph('Prof. AEE:', label),
         Paragraph(professor_aee_nome or '-', value)],
        [Paragraph('Período:', label),
         Paragraph(periodo_txt, value),
         Paragraph('', label),
         Paragraph('', value)],
    ]
    info_t = Table(info, colWidths=[2.8*cm, 7*cm, 2.5*cm, 6.3*cm])
    info_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.96, 0.96, 0.96)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.96, 0.96, 0.96)),
        ('SPAN', (1, 2), (3, 2)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_t)
    elements.append(Spacer(1, 10))

    # === KPIs ===
    elements.append(_build_kpis(
        total_estudantes=len(fichas),
        total_atendimentos=total_atendimentos,
        planos_ativos=planos_ativos,
        carga_horaria_horas=carga_horaria_horas,
    ))
    elements.append(Spacer(1, 12))

    # === Grade de Atendimentos ===
    elements.append(Paragraph('GRADE DE ATENDIMENTOS', subtitle))
    elements.append(_build_grade_atendimentos(grade_horarios))
    elements.append(Spacer(1, 8))

    # === Fichas Individuais ===
    if fichas:
        for ficha in fichas:
            elements.append(PageBreak())
            elements.extend(_build_ficha_individual(ficha, subtitle, label, value, small))

    doc.build(elements)
    return buffer.getvalue()
