"""
Gerador de PDF do Plano AEE (Atendimento Educacional Especializado).

Design simplificado e impressível:
  - Cabeçalho institucional (mesma estrutura do PDF de frequência)
  - Identificação do estudante + plano
  - Seções: Elegibilidade, Articulação com Sala Comum, Linha de Base,
    Cronograma, Barreiras, Objetivos, Recursos, Avaliação, Observações
  - Suporte a arrays de BarreiraAEE / ObjetivoAEE / RecursoAcessibilidade
"""
import io
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    from pdf_generator import get_logo_image  # type: ignore
except ImportError:
    get_logo_image = None


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

FREQUENCIA_REVISAO_LABELS = {
    'mensal': 'Mensal',
    'bimestral': 'Bimestral',
    'trimestral': 'Trimestral',
    'semestral': 'Semestral',
}

DIAS_LABELS = {
    'segunda': 'Segunda', 'terca': 'Terça', 'quarta': 'Quarta',
    'quinta': 'Quinta', 'sexta': 'Sexta',
}


def _label(value, mapping):
    if not value:
        return '-'
    return mapping.get(value, value)


def _render_list_of_dicts(arr, style):
    """Converte uma lista de dicts (barreiras/objetivos/recursos) em Paragraph multilinha."""
    if not arr:
        return Paragraph('<i>(não informado)</i>', style)
    lines = []
    for idx, item in enumerate(arr, 1):
        if isinstance(item, dict):
            tipo = item.get('tipo') or item.get('prazo')
            desc = item.get('descricao') or ''
            tipo_str = f'<b>[{tipo.upper()}]</b> ' if tipo else ''
            lines.append(f'{idx}. {tipo_str}{desc}')
        else:
            lines.append(f'{idx}. {item}')
    return Paragraph('<br/>'.join(lines), style)


def generate_plano_aee_pdf(plano: dict, student: dict, school: dict, mantenedora: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.2*cm, bottomMargin=1.5*cm,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        title="Plano de Atendimento Educacional Especializado"
    )

    normal = ParagraphStyle('NormalAEE', fontSize=9, leading=12, fontName='Helvetica')
    label = ParagraphStyle('LabelAEE', fontSize=8, leading=10, fontName='Helvetica-Bold',
                           textColor=colors.Color(0.25, 0.25, 0.25))
    value_style = ParagraphStyle('ValueAEE', fontSize=9, leading=12, fontName='Helvetica')
    section = ParagraphStyle('SectionAEE', fontSize=11, leading=15,
                             fontName='Helvetica-Bold',
                             textColor=colors.Color(0.15, 0.35, 0.6), spaceBefore=6)
    title = ParagraphStyle('TitleAEE', fontSize=14, leading=17,
                           fontName='Helvetica-Bold', alignment=1)

    elements = []

    # === Cabeçalho institucional ===
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
        'InstAEE', fontSize=9, alignment=0, leading=12, fontName='Helvetica'
    )
    slogan_html = (
        f'<br/><font size="7" color="#666666"><i>"{mant_slogan}"</i></font>' if mant_slogan else ''
    )
    instit_html = (
        f'<font size="10"><b>{mant_nome.upper()}</b></font><br/>'
        f'<font size="8"><i>{mant_sec}</i></font>'
        f'{slogan_html}'
    )
    escola_html = f'<b>{(school or {}).get("name", "ESCOLA").upper()}</b>'

    if logo:
        header = Table(
            [[logo, Paragraph(instit_html, institucional_style), Paragraph(escola_html, value_style)]],
            colWidths=[2.6*cm, 8*cm, 7.5*cm]
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
            colWidths=[10*cm, 8*cm]
        )
        header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, 0), 'MIDDLE')]))
    elements.append(header)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('PLANO DE ATENDIMENTO EDUCACIONAL ESPECIALIZADO', title))
    elements.append(Spacer(1, 10))

    # === 1. Identificação do Estudante ===
    elements.append(Paragraph('1. IDENTIFICAÇÃO DO ESTUDANTE', section))
    ident_rows = [
        [Paragraph('Aluno(a):', label),
         Paragraph(student.get('full_name') or '-', value_style),
         Paragraph('Matrícula:', label),
         Paragraph(str(student.get('enrollment_number') or '-'), value_style)],
        [Paragraph('Ano Letivo:', label),
         Paragraph(str(plano.get('academic_year') or '-'), value_style),
         Paragraph('Status do Plano:', label),
         Paragraph((plano.get('status') or '-').title(), value_style)],
        [Paragraph('Data Elaboração:', label),
         Paragraph(plano.get('data_elaboracao') or '-', value_style),
         Paragraph('Período Vigência:', label),
         Paragraph(plano.get('periodo_vigencia') or '-', value_style)],
    ]
    ident_table = Table(ident_rows, colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
    ident_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(ident_table)

    # === 2. Elegibilidade ===
    elements.append(Paragraph('2. ELEGIBILIDADE', section))
    eleg = [
        [Paragraph('Público-alvo:', label),
         Paragraph(_label(plano.get('publico_alvo'), PUBLICO_ALVO_LABELS), value_style)],
        [Paragraph('Critério:', label),
         Paragraph(plano.get('criterio_elegibilidade') or '-', value_style)],
    ]
    eleg_t = Table(eleg, colWidths=[3*cm, 15*cm])
    eleg_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(eleg_t)

    # === 3. Articulação com Sala Comum ===
    elements.append(Paragraph('3. ARTICULAÇÃO COM SALA COMUM', section))
    artic = [
        [Paragraph('Escola Origem:', label),
         Paragraph(plano.get('escola_origem_nome') or '-', value_style),
         Paragraph('Turma Origem:', label),
         Paragraph(plano.get('turma_origem_nome') or '-', value_style)],
        [Paragraph('Professor Regente:', label),
         Paragraph(plano.get('professor_regente_nome') or '-', value_style),
         Paragraph('Prof. AEE:', label),
         Paragraph(plano.get('professor_aee_nome') or '-', value_style)],
        [Paragraph('Orientações à Sala Comum:', label),
         Paragraph(plano.get('orientacoes_sala_comum') or '-', value_style, ),
         '', ''],
        [Paragraph('Combinados c/ Regente:', label),
         Paragraph(plano.get('combinados_professor_regente') or '-', value_style), '', ''],
        [Paragraph('Adequações Curriculares:', label),
         Paragraph(plano.get('adequacoes_curriculares') or '-', value_style), '', ''],
        [Paragraph('Adaptações por Componente:', label),
         Paragraph(plano.get('adaptacoes_por_componente') or '-', value_style), '', ''],
    ]
    artic_t = Table(artic, colWidths=[3.5*cm, 6*cm, 3*cm, 5.5*cm])
    artic_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('SPAN', (1, 2), (3, 2)),
        ('SPAN', (1, 3), (3, 3)),
        ('SPAN', (1, 4), (3, 4)),
        ('SPAN', (1, 5), (3, 5)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(artic_t)

    # === 4. Linha de Base ===
    elements.append(Paragraph('4. LINHA DE BASE (PERFIL DO ESTUDANTE)', section))
    linha = [
        [Paragraph('Situação Atual:', label),
         Paragraph(plano.get('linha_base_situacao_atual') or '-', value_style)],
        [Paragraph('Potencialidades:', label),
         Paragraph(plano.get('linha_base_potencialidades') or '-', value_style)],
        [Paragraph('Dificuldades:', label),
         Paragraph(plano.get('linha_base_dificuldades') or '-', value_style)],
        [Paragraph('Comunicação:', label),
         Paragraph(plano.get('linha_base_comunicacao') or '-', value_style)],
    ]
    linha_t = Table(linha, colWidths=[3.5*cm, 14.5*cm])
    linha_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(linha_t)

    # === 5. Cronograma de Atendimento ===
    elements.append(Paragraph('5. CRONOGRAMA DE ATENDIMENTO', section))
    dias_pt = ', '.join([DIAS_LABELS.get(d, d) for d in (plano.get('dias_atendimento') or [])]) or '-'
    cron = [
        [Paragraph('Modalidade:', label),
         Paragraph(_label(plano.get('modalidade'), MODALIDADE_LABELS), value_style),
         Paragraph('Carga Horária Semanal:', label),
         Paragraph(str(plano.get('carga_horaria_semanal') or '-'), value_style)],
        [Paragraph('Dias:', label),
         Paragraph(dias_pt, value_style),
         Paragraph('Horário:', label),
         Paragraph(f"{plano.get('horario_inicio') or '--:--'} às {plano.get('horario_fim') or '--:--'}", value_style)],
        [Paragraph('Local:', label),
         Paragraph(plano.get('local_atendimento') or '-', value_style), '', ''],
    ]
    cron_t = Table(cron, colWidths=[3*cm, 5.5*cm, 4*cm, 5.5*cm])
    cron_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('SPAN', (1, 2), (3, 2)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(cron_t)

    # === 6-8. Barreiras / Objetivos / Recursos ===
    for title_, key in [
        ('6. BARREIRAS IDENTIFICADAS', 'barreiras'),
        ('7. OBJETIVOS DO PLANO', 'objetivos'),
        ('8. RECURSOS DE ACESSIBILIDADE', 'recursos_acessibilidade'),
    ]:
        elements.append(KeepTogether([
            Paragraph(title_, section),
            _render_list_of_dicts(plano.get(key), normal),
        ]))

    # === 9. Avaliação e Monitoramento ===
    elements.append(Paragraph('9. AVALIAÇÃO E MONITORAMENTO', section))
    monit = [
        [Paragraph('Indicadores de Progresso:', label),
         Paragraph(plano.get('indicadores_progresso') or '-', value_style)],
        [Paragraph('Frequência de Revisão:', label),
         Paragraph(_label(plano.get('frequencia_revisao'), FREQUENCIA_REVISAO_LABELS), value_style)],
        [Paragraph('Critérios de Ajuste:', label),
         Paragraph(plano.get('criterios_ajuste') or '-', value_style)],
        [Paragraph('Próxima Revisão:', label),
         Paragraph(plano.get('data_revisao') or '-', value_style)],
    ]
    monit_t = Table(monit, colWidths=[4*cm, 14*cm])
    monit_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(monit_t)

    # === Rodapé: assinatura ===
    elements.append(Spacer(1, 28))
    sign_style = ParagraphStyle('SignAEE', fontSize=8, alignment=1, fontName='Helvetica')
    sign = Table([
        [Paragraph('_______________________________<br/>Professor(a) AEE', sign_style),
         Paragraph('_______________________________<br/>Direção da Escola', sign_style)]
    ], colWidths=[9*cm, 9*cm])
    elements.append(sign)

    doc.build(elements)
    return buffer.getvalue()
