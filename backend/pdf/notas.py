"""Módulo PDF - Relatório de Notas"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as canvas_module
from pdf.utils import get_logo_image, format_date_pt, get_styles

def generate_grades_report_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    course: Dict[str, Any],
    students_data: List[Dict[str, Any]],
    bimestres: List[int],
    academic_year: int,
    grade_level: str = "",
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """Gera PDF do relatório de notas por turma e componente"""
    from reportlab.pdfgen import canvas as canvas_module

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=2*cm
    )

    styles = get_styles()
    elements = []
    mantenedora = mantenedora or {}
    page_width = A4[0] - 3*cm

    def safe(val, default=''):
        if val is None:
            return default
        return str(val)

    # Estilos
    info_style = ParagraphStyle('GRInfo', fontSize=8, leading=10, alignment=0)
    content_style = ParagraphStyle('GRContent', fontSize=7, leading=9, alignment=0)
    content_bold = ParagraphStyle('GRContentBold', fontSize=7, leading=9, alignment=0, fontName='Helvetica-Bold')
    small_center = ParagraphStyle('GRSmallCenter', fontSize=7, leading=9, alignment=1)
    header_text_style = ParagraphStyle('GRHeader', fontSize=9, leading=12, alignment=TA_CENTER)

    # Detecta tipo de avaliação
    SERIES_INFANTIL = ['berçário', 'maternal', 'pré', 'creche', 'jardim']
    SERIES_CONCEITUAL = ['1º ano', '2º ano', '1 ano', '2 ano']
    gl = grade_level.lower() if grade_level else ''
    nivel = class_info.get('education_level', '')

    is_infantil = nivel == 'educacao_infantil' or any(s in gl for s in SERIES_INFANTIL)
    is_conceitual = is_infantil or any(s in gl for s in SERIES_CONCEITUAL)

    VALOR_CONCEITO_INFANTIL = {10.0: 'OD', 7.5: 'DP', 5.0: 'ND', 0.0: 'NT'}
    VALOR_CONCEITO_ANOS = {10.0: 'C', 7.5: 'ED', 5.0: 'ND'}

    def format_grade(val):
        if val is None:
            return '-'
        try:
            v = float(val)
            if is_infantil:
                return VALOR_CONCEITO_INFANTIL.get(v, str(val))
            if is_conceitual:
                return VALOR_CONCEITO_ANOS.get(v, str(val))
            return f"{v:.1f}" if v != int(v) else str(int(v))
        except (ValueError, TypeError):
            return str(val)

    # Tradução
    niveis = {
        'fundamental_anos_iniciais': 'Ensino Fundamental - Anos Iniciais',
        'fundamental_anos_finais': 'Ensino Fundamental - Anos Finais',
        'eja': 'EJA - Anos Iniciais',
        'eja_final': 'EJA - Anos Finais',
        'educacao_infantil': 'Educação Infantil',
        'ensino_medio': 'Ensino Médio',
        'global': 'Global'
    }
    turnos = {'morning': 'Matutino', 'afternoon': 'Vespertino', 'night': 'Noturno', 'full_time': 'Integral'}
    nivel_label = niveis.get(nivel, nivel)
    turno = turnos.get(class_info.get('shift', ''), class_info.get('shift', ''))

    bimestres_str = ', '.join([f'{b}º' for b in sorted(bimestres)])

    # === CABEÇALHO ===
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.5*cm, height=2.8*cm, logo_url=logo_url)

    mant_nome = mantenedora.get('nome', '')
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')

    header_html = (
        f"<b>{safe(mant_nome)}</b><br/>"
        f"{school.get('name', '').upper()}<br/><br/>"
        f"<b><font size=\"12\">RELATÓRIO DE NOTAS</font></b><br/>"
        f"{bimestres_str} Bimestre(s) - Ano Letivo {academic_year}"
    )

    if logo:
        header_data = [[logo, Paragraph(header_html, header_text_style)]]
        header_table = Table(header_data, colWidths=[3.5*cm, page_width - 3.5*cm])
    else:
        header_data = [[Paragraph(header_html, header_text_style)]]
        header_table = Table(header_data, colWidths=[page_width])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))

    # === INFO TABLE ===
    col_w = page_width / 4
    serie = grade_level or class_info.get('grade_level', class_info.get('name', ''))
    info_data = [
        [
            Paragraph(f"<b>Turma:</b> {safe(class_info.get('name'))}", info_style),
            Paragraph(f"<b>Série/Ano:</b> {safe(serie)}", info_style),
            Paragraph(f"<b>Turno:</b> {safe(turno)}", info_style),
            Paragraph(f"<b>Nível:</b> {safe(nivel_label)}", info_style),
        ],
        [
            Paragraph(f"<b>Componente:</b> {safe(course.get('name'))}", info_style),
            '',
            Paragraph(f"<b>Total de Alunos:</b> {len(students_data)}", info_style),
            Paragraph(f"<b>Tipo:</b> {'Conceitual' if is_conceitual else 'Numérica'}", info_style),
        ]
    ]
    info_table = Table(info_data, colWidths=[col_w]*4)
    info_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.3, colors.Color(0.7, 0.7, 0.7)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), colors.Color(0.96, 0.96, 0.96)),
        ('SPAN', (0, 1), (1, 1)),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # === TABELA DE NOTAS ===
    # Cabeçalho dinâmico baseado nos bimestres selecionados
    header_cells = [
        Paragraph('<b>Nº</b>', small_center),
        Paragraph('<b>ALUNO(A)</b>', content_bold),
    ]
    for b in sorted(bimestres):
        header_cells.append(Paragraph(f'<b>B{b}</b>', small_center))

    # Recuperações e média final se todos bimestres
    show_rec_s1 = 1 in bimestres and 2 in bimestres
    show_rec_s2 = 3 in bimestres and 4 in bimestres
    show_final = len(bimestres) == 4

    if show_rec_s1:
        header_cells.append(Paragraph('<b>Rec S1</b>', small_center))
    if show_rec_s2:
        header_cells.append(Paragraph('<b>Rec S2</b>', small_center))
    if show_final:
        header_cells.append(Paragraph('<b>Rec Final</b>', small_center))
        header_cells.append(Paragraph('<b>Média</b>', small_center))
        header_cells.append(Paragraph('<b>Situação</b>', small_center))

    table_data = [header_cells]

    # Dados dos alunos
    status_map = {
        'aprovado': 'Aprovado',
        'reprovado': 'Reprovado',
        'cursando': 'Cursando',
        'recuperacao': 'Recuperação',
        'conselho': 'Conselho',
    }

    for idx, s in enumerate(students_data, 1):
        row = [
            Paragraph(str(idx), small_center),
            Paragraph(safe(s.get('full_name')), content_style),
        ]
        for b in sorted(bimestres):
            row.append(Paragraph(format_grade(s.get(f'b{b}')), small_center))

        if show_rec_s1:
            row.append(Paragraph(format_grade(s.get('rec_s1')), small_center))
        if show_rec_s2:
            row.append(Paragraph(format_grade(s.get('rec_s2')), small_center))
        if show_final:
            row.append(Paragraph(format_grade(s.get('recovery')), small_center))
            row.append(Paragraph(format_grade(s.get('final_average')), small_center))
            sit = status_map.get(s.get('status', ''), s.get('status', ''))
            row.append(Paragraph(safe(sit), small_center))

        table_data.append(row)

    if len(table_data) == 1:
        empty_row = ['', Paragraph('Nenhum aluno encontrado.', content_style)]
        empty_row.extend([''] * (len(header_cells) - 2))
        table_data.append(empty_row)

    # Larguras das colunas
    num_w = 0.8*cm
    name_w_base = page_width - num_w
    grade_col_count = len(header_cells) - 2  # excluindo Nº e Nome
    grade_col_w = 1.4*cm
    name_w = name_w_base - (grade_col_count * grade_col_w)
    if name_w < 4*cm:
        name_w = 4*cm
        grade_col_w = (page_width - num_w - name_w) / max(grade_col_count, 1)

    col_widths = [num_w, name_w] + [grade_col_w] * grade_col_count

    content_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.5)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]
    # Cores alternadas
    for i in range(2, len(table_data), 2):
        table_style_cmds.append(('BACKGROUND', (0, i), (-1, i), colors.Color(0.97, 0.97, 0.97)))

    content_table.setStyle(TableStyle(table_style_cmds))
    elements.append(content_table)
    elements.append(Spacer(1, 15))

    # Legenda de conceitos (se aplicável)
    if is_conceitual:
        elements.append(Paragraph('<b>LEGENDA:</b>', content_bold))
        elements.append(Spacer(1, 3))
        if is_infantil:
            elements.append(Paragraph('OD = Objetivo Desenvolvido | DP = Desenvolvido Parcialmente | ND = Não Desenvolvido | NT = Não Trabalhado', content_style))
        else:
            elements.append(Paragraph('C = Consolidado | ED = Em Desenvolvimento | ND = Não Desenvolvido', content_style))
        elements.append(Spacer(1, 10))

    # === RODAPÉ ===
    today = datetime.now()
    elements.append(Paragraph(
        f"{mant_municipio} - {mant_estado}, {format_date_pt(today.date())}",
        ParagraphStyle('GRDate', fontSize=8, leading=10, alignment=1)
    ))
    elements.append(Spacer(1, 30))

    sig_center = ParagraphStyle('GRSigCenter', fontSize=8, leading=10, alignment=1)
    sig_data = [
        ['_' * 45, '_' * 45],
        [Paragraph('Professor(a)', sig_center), Paragraph('Coordenador(a) Pedagógico(a)', sig_center)]
    ]
    sig_table = Table(sig_data, colWidths=[page_width / 2] * 2)
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
    ]))
    elements.append(sig_table)

    # Numeração de página
    class NumberedCanvas(canvas_module.Canvas):
        def __init__(self, *args, **kwargs):
            canvas_module.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []
        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()
        def save(self):
            num_pages = len(self._saved_page_states)
            for i, state in enumerate(self._saved_page_states):
                self.__dict__.update(state)
                self.setFont("Helvetica", 8)
                self.drawCentredString(A4[0] / 2, 1 * cm, f"Página {i + 1} de {num_pages}")
                canvas_module.Canvas.showPage(self)
            canvas_module.Canvas.save(self)

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer