"""Módulo PDF - Livro de Promoção"""
import copy
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf.utils import get_logo_image, ordenar_componentes_por_nivel


class VerticalText(Flowable):
    """Flowable que desenha texto rotacionado 90° (vertical, de baixo para cima)."""
    def __init__(self, text, font='Helvetica-Bold', size=6, text_color=colors.white):
        Flowable.__init__(self)
        self.text = text
        self.font = font
        self.size = size
        self.text_color = text_color
        self.width = size + 4
        self.height = stringWidth(text, font, size) + 6

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFont(self.font, self.size)
        canvas.setFillColor(self.text_color)
        canvas.rotate(90)
        canvas.drawString(3, -self.size - 1, self.text)
        canvas.restoreState()

def generate_livro_promocao_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    students_data: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    academic_year: int,
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera o PDF do Livro de Promoção para uma turma.
    Formato baseado no modelo de Floresta do Araguaia, similar à Ficha Individual.
    
    O documento é dividido em múltiplas páginas:
    - Página 1: 1º e 2º Bimestre + Recuperação 1º Semestre
    - Página 2: 3º e 4º Bimestre + Recuperação 2º Semestre + Total/Média/Resultado
    
    Args:
        school: Dados da escola
        class_info: Dados da turma
        students_data: Lista com dados dos alunos (incluindo notas e resultado)
        courses: Lista de componentes curriculares
        academic_year: Ano letivo
        mantenedora: Dados da mantenedora (opcional)
    
    Returns:
        BytesIO: Buffer com o PDF gerado
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    
    buffer = BytesIO()
    mantenedora = mantenedora or {}
    
    # Dados pré-calculados para cabeçalho e rodapé
    today = datetime.now()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    secretaria = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')
    slogan = mantenedora.get('slogan', '')
    data_extenso = f"{mant_municipio} - {mant_estado}, {today.day} de {meses[today.month - 1]} de {today.year}"
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    escola_nome = school.get('name', 'Escola Municipal')
    turma_nome = class_info.get('name', 'Turma')
    grade_level = class_info.get('grade_level', '')
    shift_raw = class_info.get('shift', '')
    TURNOS_PT = {
        'morning': 'MATUTINO', 'afternoon': 'VESPERTINO',
        'evening': 'NOTURNO', 'full_time': 'INTEGRAL', 'night': 'NOTURNO'
    }
    turno = TURNOS_PT.get(shift_raw, shift_raw.upper() if shift_raw else 'N/A')
    
    # Variável mutável para total de páginas (preenchida após 1ª passagem)
    page_total = [0]
    
    def draw_header_footer(canvas_obj, doc_obj):
        """Desenha cabeçalho e rodapé em TODAS as páginas."""
        canvas_obj.saveState()
        page_num = doc_obj.page
        total = page_total[0] if page_total[0] > 0 else '??'
        page_w, page_h = landscape(A4)
        mx = 0.8 * cm
        
        # ===== CABEÇALHO =====
        y = page_h - 0.6 * cm
        canvas_obj.setFont('Helvetica-Bold', 10)
        canvas_obj.drawString(mx, y, mant_nome.upper())
        y -= 12
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawString(mx, y, secretaria)
        if slogan:
            y -= 10
            canvas_obj.setFont('Helvetica-Oblique', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(mx, y, f'"{slogan}"')
            canvas_obj.setFillColor(colors.black)
        
        # Título à direita
        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.setFillColor(colors.HexColor('#1e40af'))
        canvas_obj.drawRightString(page_w - mx, page_h - 0.7 * cm, 'LIVRO DE PROMOÇÃO')
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont('Helvetica', 10)
        canvas_obj.drawRightString(page_w - mx, page_h - 1.2 * cm, f'ANO LETIVO: {academic_year}')
        
        # Caixa: ESCOLA | PÁGINA
        box_y = page_h - 2.2 * cm
        box_h = 0.4 * cm
        canvas_obj.setStrokeColor(colors.black)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.rect(mx, box_y, page_w - 2 * mx, box_h, stroke=1, fill=0)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawString(mx + 3, box_y + 3, 'ESCOLA:')
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(mx + 3 + stringWidth('ESCOLA: ', 'Helvetica-Bold', 7), box_y + 3, escola_nome)
        pag_text = f'PÁGINA: {page_num:02d}/{total:02d}' if isinstance(total, int) else f'PÁGINA: {page_num:02d}/{total}'
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawRightString(page_w - mx - 3, box_y + 3, pag_text)
        
        # Caixa: TURMA | ANO/ETAPA | TURNO
        box_y2 = box_y - box_h
        canvas_obj.rect(mx, box_y2, page_w - 2 * mx, box_h, stroke=1, fill=0)
        third = (page_w - 2 * mx) / 3
        canvas_obj.line(mx + third, box_y2, mx + third, box_y2 + box_h)
        canvas_obj.line(mx + 2 * third, box_y2, mx + 2 * third, box_y2 + box_h)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawString(mx + 3, box_y2 + 3, 'TURMA:')
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(mx + 3 + stringWidth('TURMA: ', 'Helvetica-Bold', 7), box_y2 + 3, turma_nome)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawString(mx + third + 3, box_y2 + 3, 'ANO/ETAPA:')
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(mx + third + 3 + stringWidth('ANO/ETAPA: ', 'Helvetica-Bold', 7), box_y2 + 3, grade_level)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawString(mx + 2 * third + 3, box_y2 + 3, 'TURNO:')
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(mx + 2 * third + 3 + stringWidth('TURNO: ', 'Helvetica-Bold', 7), box_y2 + 3, turno)
        
        # ===== RODAPÉ (somente na última página) =====
        is_last_page = isinstance(total, int) and page_num == total
        if is_last_page:
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.setFillColor(colors.black)
            canvas_obj.drawCentredString(page_w / 2, 3.8 * cm, data_extenso)
            
            line_y = 2.6 * cm
            center_left = page_w / 2 - 5 * cm
            center_right = page_w / 2 + 5 * cm
            half_line = 4 * cm
            canvas_obj.setLineWidth(0.5)
            canvas_obj.line(center_left - half_line, line_y, center_left + half_line, line_y)
            canvas_obj.line(center_right - half_line, line_y, center_right + half_line, line_y)
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.drawCentredString(center_left, line_y - 12, 'Secretário(a)')
            canvas_obj.drawCentredString(center_right, line_y - 12, 'Diretor(a)')
            
            canvas_obj.setFont('Helvetica', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(mx, 0.6 * cm, rodape_info)
        
        canvas_obj.restoreState()
    
    # Criar documento em paisagem
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8*cm,
        rightMargin=0.8*cm,
        topMargin=3.0*cm,
        bottomMargin=4.2*cm
    )
    
    elements = []
    
    # ===== ESTILOS =====
    small_text = ParagraphStyle('SmallText', fontSize=7, alignment=TA_LEFT)
    
    # Ordenar componentes
    nivel_ensino = class_info.get('education_level', '')
    courses_ordenados = ordenar_componentes_por_nivel(courses, nivel_ensino)
    num_components = len(courses_ordenados)
    
    if num_components == 0:
        courses_ordenados = [{'id': 'placeholder', 'name': 'Componente'}]
        num_components = 1
    
    # Abreviações dos componentes
    def abreviar_componente(nome):
        abreviacoes = {
            'língua portuguesa': 'L. PORT.',
            'arte': 'ARTE',
            'educação física': 'ED. FÍS.',
            'língua inglesa': 'L. ING.',
            'inglês': 'L. ING.',
            'matemática': 'MAT.',
            'ciências': 'CIÊN.',
            'história': 'HIST.',
            'geografia': 'GEOG.',
            'ensino religioso': 'ENS. REL.',
            'educação ambiental e clima': 'ED. AMB. CLI.',
            'estudos amazônicos': 'EST. AMAZ.',
            'literatura e redação': 'LIT. E RED.',
            'recreação e lazer': 'REC. ESP. LAZ.',
            'recreação, esporte e lazer': 'REC. ESP. LAZ.',
            'linguagem recreativa com práticas de esporte e lazer': 'REC. ESP. LAZ.',
            'arte e cultura': 'ART. E CULT.',
            'tecnologia da informação': 'TEC. E INFO.',
            'tecnologia e informática': 'TEC. E INFO.',
            'acompanhamento pedagógico de língua portuguesa': 'AC. PED. L. PORT.',
            'acompanhamento pedagógico de matemática': 'AC. PED. MAT.',
            'acomp. ped. de língua portuguesa': 'AC. PED. L. PORT.',
            'acomp. ped. de matemática': 'AC. PED. MAT.',
        }
        nome_lower = (nome or '').lower().strip()
        # Match exato
        if nome_lower in abreviacoes:
            return abreviacoes[nome_lower]
        # Match parcial
        for key, abbr in abreviacoes.items():
            if nome_lower.startswith(key) or key.startswith(nome_lower):
                return abbr
        return (nome[:12] + '.').upper() if len(nome) > 12 else nome.upper()
    
    comp_names = [abreviar_componente(c.get('name', '')) for c in courses_ordenados]
    
    # Criar VerticalText para cada componente (para uso nos headers da tabela)
    def make_vertical_comp(name):
        return VerticalText(name, font='Helvetica-Bold', size=6, text_color=colors.white)
    
    # ===== FUNÇÃO PARA FORMATAR NOTA =====
    def fmt_grade(v):
        if v is None:
            return ''
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
        return str(v) if v else ''
    
    # ===== PÁGINA 1: 1º SEMESTRE (1º Bim, 2º Bim, Rec 1º Sem) =====
    
    # Cabeçalho da tabela - Página 1
    # Estrutura: N° | Nome | Sexo | [1º BIM: componentes] | [2º BIM: componentes] | [REC 1º SEM: componentes]
    header_row1_p1 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p1.extend(['NOTAS 1º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['NOTAS 2º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['RECUPERAÇÃO 1º SEMESTRE'] + [''] * (num_components - 1))
    
    header_row2_p1 = ['', '', '']
    header_row2_p1.extend([make_vertical_comp(n) for n in comp_names])  # 1º Bim
    header_row2_p1.extend([make_vertical_comp(n) for n in comp_names])  # 2º Bim
    header_row2_p1.extend([make_vertical_comp(n) for n in comp_names])  # Rec 1º Sem
    
    table_data_p1 = [header_row1_p1, header_row2_p1]
    
    # Dados dos alunos - Página 1
    for idx, student in enumerate(students_data, 1):
        row = [
            str(idx),
            student.get('studentName', '')[:30],
            student.get('sex', '-')
        ]
        
        grades = student.get('grades', {})
        
        # 1º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b1')))
        
        # 2º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b2')))
        
        # Recuperação 1º Semestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('rec1')))
        
        table_data_p1.append(row)
    
    # Calcular larguras - Página 1
    largura_disponivel = 27 * cm
    largura_num = 0.7 * cm
    largura_nome = 4.5 * cm
    largura_sexo = 0.7 * cm
    largura_restante = largura_disponivel - largura_num - largura_nome - largura_sexo
    largura_por_nota = largura_restante / (num_components * 3)
    largura_por_nota = max(largura_por_nota, 0.6 * cm)
    
    col_widths_p1 = [largura_num, largura_nome, largura_sexo]
    col_widths_p1.extend([largura_por_nota] * (num_components * 3))
    
    # Criar tabela Página 1
    table_p1 = Table(table_data_p1, colWidths=col_widths_p1, repeatRows=2)
    
    # Estilo da tabela
    style_p1 = [
        # Cabeçalho linha 1
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Cabeçalho linha 2
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        
        # Corpo
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, -1), 'LEFT'),  # Nome alinhado à esquerda
        
        # Grid e bordas
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Linhas verticais mais grossas entre blocos
        ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),  # Após Sexo
        ('LINEAFTER', (2 + num_components, 0), (2 + num_components, -1), 1.5, colors.black),  # Após 1º Bim
        ('LINEAFTER', (2 + num_components * 2, 0), (2 + num_components * 2, -1), 1.5, colors.black),  # Após 2º Bim
        ('LINEAFTER', (2 + num_components * 3, 0), (2 + num_components * 3, -1), 1.5, colors.black),  # Após Rec 1º Sem
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        
        # Span para cabeçalhos de seção
        ('SPAN', (3, 0), (3 + num_components - 1, 0)),  # 1º Bim
        ('SPAN', (3 + num_components, 0), (3 + num_components * 2 - 1, 0)),  # 2º Bim
        ('SPAN', (3 + num_components * 2, 0), (3 + num_components * 3 - 1, 0)),  # Rec 1º Sem
        
        # Cores alternadas nas linhas
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]
    
    table_p1.setStyle(TableStyle(style_p1))
    elements.append(table_p1)
    
    # ===== PÁGINA 2: 2º SEMESTRE + RESULTADO =====
    elements.append(PageBreak())
    
    # Cabeçalho da tabela - Página 2
    header_row1_p2 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p2.extend(['NOTAS 3º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['NOTAS 4º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['RECUPERAÇÃO 2º SEMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['TOTAL', 'MÉDIA', 'RESULTADO'])
    
    header_row2_p2 = ['', '', '']
    header_row2_p2.extend([make_vertical_comp(n) for n in comp_names])  # 3º Bim
    header_row2_p2.extend([make_vertical_comp(n) for n in comp_names])  # 4º Bim
    header_row2_p2.extend([make_vertical_comp(n) for n in comp_names])  # Rec 2º Sem
    header_row2_p2.extend(['PTS', 'FINAL', ''])
    
    table_data_p2 = [header_row1_p2, header_row2_p2]
    
    # Dados dos alunos - Página 2
    for idx, student in enumerate(students_data, 1):
        row = [
            str(idx),
            student.get('studentName', '')[:30],
            student.get('sex', '-')
        ]
        
        grades = student.get('grades', {})
        
        # 3º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b3')))
        
        # 4º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b4')))
        
        # Recuperação 2º Semestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('rec2')))
        
        # Calcular Total de Pontos (soma de todas as médias finais)
        total_pontos = 0
        medias_validas = []
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            media = grade_info.get('finalAverage')
            if isinstance(media, (int, float)):
                total_pontos += media
                medias_validas.append(media)
        
        # Média geral
        media_geral = total_pontos / len(medias_validas) if medias_validas else 0
        
        row.append(f"{total_pontos:.1f}".replace('.', ',') if total_pontos > 0 else '-')
        row.append(f"{media_geral:.1f}".replace('.', ',') if media_geral > 0 else '-')
        
        # Resultado
        resultado = student.get('result', 'CURSANDO')
        row.append(resultado[:12])
        
        table_data_p2.append(row)
    
    # Calcular larguras - Página 2 (3 colunas extras: Total, Média, Resultado)
    largura_total = 1.0 * cm
    largura_media = 1.0 * cm
    largura_resultado = 1.8 * cm
    largura_restante_p2 = largura_disponivel - largura_num - largura_nome - largura_sexo - largura_total - largura_media - largura_resultado
    largura_por_nota_p2 = largura_restante_p2 / (num_components * 3)
    largura_por_nota_p2 = max(largura_por_nota_p2, 0.55 * cm)
    
    col_widths_p2 = [largura_num, largura_nome, largura_sexo]
    col_widths_p2.extend([largura_por_nota_p2] * (num_components * 3))
    col_widths_p2.extend([largura_total, largura_media, largura_resultado])
    
    # Criar tabela Página 2
    table_p2 = Table(table_data_p2, colWidths=col_widths_p2, repeatRows=2)
    
    # Estilo da tabela Página 2
    style_p2 = [
        # Cabeçalho linha 1
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Cabeçalho linha 2
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        
        # Corpo
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, -1), 'LEFT'),
        
        # Grid e bordas
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Linhas verticais mais grossas entre blocos
        ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),  # Após Sexo
        ('LINEAFTER', (2 + num_components, 0), (2 + num_components, -1), 1.5, colors.black),  # Após 3º Bim
        ('LINEAFTER', (2 + num_components * 2, 0), (2 + num_components * 2, -1), 1.5, colors.black),  # Após 4º Bim
        ('LINEAFTER', (2 + num_components * 3, 0), (2 + num_components * 3, -1), 1.5, colors.black),  # Após Rec 2º Sem
        ('LINEAFTER', (2 + num_components * 3 + 1, 0), (2 + num_components * 3 + 1, -1), 1.5, colors.black),  # Após Total
        ('LINEAFTER', (2 + num_components * 3 + 2, 0), (2 + num_components * 3 + 2, -1), 1.5, colors.black),  # Após Média
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        
        # Span para cabeçalhos de seção
        ('SPAN', (3, 0), (3 + num_components - 1, 0)),  # 3º Bim
        ('SPAN', (3 + num_components, 0), (3 + num_components * 2 - 1, 0)),  # 4º Bim
        ('SPAN', (3 + num_components * 2, 0), (3 + num_components * 3 - 1, 0)),  # Rec 2º Sem
        
        # Cores alternadas nas linhas
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]
    
    # Colorir resultado baseado no valor
    col_resultado = len(col_widths_p2) - 1
    for row_idx, student in enumerate(students_data, 2):
        resultado = student.get('result', 'CURSANDO')
        if 'APROVADO' in resultado or 'PROMOVIDO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#c8e6c9')))
            style_p2.append(('TEXTCOLOR', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#1b5e20')))
            style_p2.append(('FONTNAME', (col_resultado, row_idx), (col_resultado, row_idx), 'Helvetica-Bold'))
        elif 'REPROVADO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#ffcdd2')))
            style_p2.append(('TEXTCOLOR', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#b71c1c')))
            style_p2.append(('FONTNAME', (col_resultado, row_idx), (col_resultado, row_idx), 'Helvetica-Bold'))
        elif 'DESISTENTE' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#e0e0e0')))
        elif 'TRANSFERIDO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#fff9c4')))
    
    table_p2.setStyle(TableStyle(style_p2))
    elements.append(table_p2)
    
    # === Build em 2 passagens: 1ª conta páginas, 2ª gera com total correto ===
    # 1ª passagem: contar páginas (usa deep copy para não mutar os elementos originais)
    count_buffer = BytesIO()
    count_doc = SimpleDocTemplate(count_buffer, pagesize=landscape(A4),
        leftMargin=0.8*cm, rightMargin=0.8*cm, topMargin=3.0*cm, bottomMargin=4.2*cm)
    count_doc.build(copy.deepcopy(elements), onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    page_total[0] = count_doc.page
    
    # 2ª passagem: gerar PDF final com total de páginas correto
    doc.build(elements, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    buffer.seek(0)
    return buffer

