"""Módulo PDF - Livro de Promoção"""
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from pdf.utils import get_logo_image, ordenar_componentes_por_nivel

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
    
    # Criar documento em paisagem
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8*cm,
        rightMargin=0.8*cm,
        topMargin=0.8*cm,
        bottomMargin=0.8*cm
    )
    
    elements = []
    
    # ===== ESTILOS =====
    info_style = ParagraphStyle('InfoStyle', fontSize=7, leading=9)
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    small_text = ParagraphStyle('SmallText', fontSize=7, alignment=TA_LEFT)
    
    # ===== DADOS DA MANTENEDORA =====
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    slogan = mantenedora.get('slogan', '')
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    # Tamanho reduzido em 40% (2.4cm -> 1.44cm, 1.6cm -> 0.96cm)
    logo = get_logo_image(width=1.44*cm, height=0.96*cm, logo_url=logo_url)
    
    # ===== DADOS DA TURMA =====
    escola_nome = school.get('name', 'Escola Municipal')
    turma_nome = class_info.get('name', 'Turma')
    grade_level = class_info.get('grade_level', '')
    shift_raw = class_info.get('shift', '')
    
    TURNOS_PT = {
        'morning': 'MATUTINO',
        'afternoon': 'VESPERTINO', 
        'evening': 'NOTURNO',
        'full_time': 'INTEGRAL',
        'night': 'NOTURNO'
    }
    turno = TURNOS_PT.get(shift_raw, shift_raw.upper() if shift_raw else 'N/A')
    
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
            'Língua Portuguesa': 'Lin. Port.',
            'Arte': 'Arte',
            'Educação Física': 'Ed. Fís.',
            'Língua Inglesa': 'Lin. Ingl.',
            'Inglês': 'Lin. Ingl.',
            'Matemática': 'Mat.',
            'Ciências': 'Ciênc.',
            'História': 'Hist.',
            'Geografia': 'Geo.',
            'Ensino Religioso': 'Ed. Rel.',
            'Educação Ambiental e Clima': 'Ed. A. Cl.',
            'Estudos Amazônicos': 'Est. Amaz.',
            'Literatura e Redação': 'Lit. e red.',
            'Recreação e Lazer': 'R. E. Laz.',
            'Recreação, Esporte e Lazer': 'R. E. Laz.',
            'Linguagem Recreativa com Práticas de Esporte e Lazer': 'R. E. Laz.',
            'Arte e Cultura': 'Art. e Cul.',
            'Tecnologia da Informação': 'Tec. Inf.',
            'Tecnologia e Informática': 'Tec. Inf.',
            'Acompanhamento Pedagógico de Língua Portuguesa': 'APL Port.',
            'Acompanhamento Pedagógico de Matemática': 'AP Mat.',
            'Acomp. Ped. de Língua Portuguesa': 'APL Port.',
            'Acomp. Ped. de Matemática': 'AP Mat.',
            'Contação de Histórias e Iniciação Musical': 'Cont. Hist.',
            'Corpo, gestos e movimentos': 'Corp. Gest.',
            'Escuta, fala, pensamento e imaginação': 'Esc. Fala',
            'Espaços, tempos, quantidades, relações e transformações': 'Esp. Temp.',
            'Higiene e Saúde': 'Hig. Saúde',
            'O eu, o outro e nós': 'Eu Out. Nós',
            'Traço, sons, cores e formas': 'Traç. Sons'
        }
        return abreviacoes.get(nome, nome[:10] + '.' if len(nome) > 10 else nome)
    
    comp_names = [abreviar_componente(c.get('name', '')) for c in courses_ordenados]
    
    # ===== FUNÇÃO PARA CRIAR CABEÇALHO =====
    def criar_cabecalho(pagina_num, total_paginas):
        header_elements = []
        
        # Linha 1: Logo + Nome da Mantenedora + Título
        slogan_html = f'<font size="8" color="#666666">"{slogan}"</font>' if slogan else ''
        header_text = f"""
        <b>{mant_nome}</b><br/>
        <font size="9">{mantenedora.get('secretaria', 'Secretaria Municipal de Educação')}</font><br/>
        {slogan_html}
        """
        
        header_right = f"""
        <font size="14" color="#1e40af"><b>LIVRO DE PROMOÇÃO</b></font><br/>
        <font size="10">ANO LETIVO: {academic_year}</font>
        """
        
        if logo:
            header_table = Table([
                [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
            ], colWidths=[3*cm, 14*cm, 10*cm])
        else:
            header_table = Table([
                [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
            ], colWidths=[15*cm, 12*cm])
        
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
        ]))
        header_elements.append(header_table)
        header_elements.append(Spacer(1, 5))
        
        # Linha 2: Escola + Ano Letivo
        info_row1 = Table([
            [
                Paragraph(f"<b>ESCOLA:</b> {escola_nome}", info_style),
                Paragraph(f"<b>PÁGINA:</b> {pagina_num:02d}/{total_paginas:02d}", info_style),
            ]
        ], colWidths=[23*cm, 4*cm])
        info_row1.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        header_elements.append(info_row1)
        
        # Linha 3: Turma, Série, Turno
        info_row2 = Table([
            [
                Paragraph(f"<b>TURMA:</b> {turma_nome}", info_style),
                Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", info_style),
                Paragraph(f"<b>TURNO:</b> {turno}", info_style),
            ]
        ], colWidths=[12*cm, 8*cm, 7*cm])
        info_row2.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        header_elements.append(info_row2)
        header_elements.append(Spacer(1, 8))
        
        return header_elements
    
    # ===== FUNÇÃO PARA FORMATAR NOTA =====
    def fmt_grade(v):
        if v is None:
            return ''
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
        return str(v) if v else ''
    
    # ===== PÁGINA 1: 1º SEMESTRE (1º Bim, 2º Bim, Rec 1º Sem) =====
    elements.extend(criar_cabecalho(1, 2))
    
    # Cabeçalho da tabela - Página 1
    # Estrutura: N° | Nome | Sexo | [1º BIM: componentes] | [2º BIM: componentes] | [REC 1º SEM: componentes]
    header_row1_p1 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p1.extend(['NOTAS 1º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['NOTAS 2º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['RECUPERAÇÃO 1º SEMESTRE'] + [''] * (num_components - 1))
    
    header_row2_p1 = ['', '', '']
    header_row2_p1.extend(comp_names)  # 1º Bim
    header_row2_p1.extend(comp_names)  # 2º Bim
    header_row2_p1.extend(comp_names)  # Rec 1º Sem
    
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
    elements.extend(criar_cabecalho(2, 2))
    
    # Cabeçalho da tabela - Página 2
    header_row1_p2 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p2.extend(['NOTAS 3º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['NOTAS 4º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['RECUPERAÇÃO 2º SEMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['TOTAL', 'MÉDIA', 'RESULTADO'])
    
    header_row2_p2 = ['', '', '']
    header_row2_p2.extend(comp_names)  # 3º Bim
    header_row2_p2.extend(comp_names)  # 4º Bim
    header_row2_p2.extend(comp_names)  # Rec 2º Sem
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
    
    # ===== RODAPÉ COM ASSINATURAS =====
    elements.append(Spacer(1, 20))
    
    # Data e local
    today = datetime.now()
    data_extenso = f"{mant_municipio} - {mant_estado}, {today.day} de {['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'][today.month - 1]} de {today.year}"
    
    footer_style = ParagraphStyle('FooterStyle', fontSize=9, alignment=TA_CENTER)
    elements.append(Paragraph(data_extenso, footer_style))
    elements.append(Spacer(1, 30))
    
    # Assinaturas
    assinatura_data = [
        ['_' * 40, '_' * 40],
        ['Secretário(a)', 'Diretor(a)']
    ]
    assinatura_table = Table(assinatura_data, colWidths=[10*cm, 10*cm])
    assinatura_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, 1), 5),
    ]))
    elements.append(assinatura_table)
    
    # Rodapé com informações de geração
    elements.append(Spacer(1, 15))
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    elements.append(Paragraph(rodape_info, small_text))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

