"""
Módulo para geração de documentos PDF do SIGESC
- Boletim Escolar
- Declaração de Matrícula
- Declaração de Frequência
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import locale

# Tentar configurar locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')
    except:
        pass


def format_date_pt(d: date) -> str:
    """Formata data em português"""
    months = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
              'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    return f"{d.day} de {months[d.month - 1]} de {d.year}"


def get_styles():
    """Retorna estilos personalizados para os documentos"""
    styles = getSampleStyleSheet()
    
    # Título principal
    styles.add(ParagraphStyle(
        name='MainTitle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.HexColor('#1e40af')
    ))
    
    # Subtítulo
    styles.add(ParagraphStyle(
        name='SubTitle',
        parent=styles['Heading2'],
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=10,
        textColor=colors.HexColor('#374151')
    ))
    
    # Texto normal centralizado
    styles.add(ParagraphStyle(
        name='CenterText',
        parent=styles['Normal'],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=6
    ))
    
    # Texto justificado
    styles.add(ParagraphStyle(
        name='JustifyText',
        parent=styles['Normal'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
        leading=16
    ))
    
    # Texto para assinatura
    styles.add(ParagraphStyle(
        name='SignatureText',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        spaceBefore=40
    ))
    
    return styles


def generate_boletim_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    enrollment: Dict[str, Any],
    class_info: Dict[str, Any],
    grades: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    academic_year: str
) -> BytesIO:
    """
    Gera o PDF do Boletim Escolar - Modelo Floresta do Araguaia
    
    Args:
        student: Dados do aluno
        school: Dados da escola
        enrollment: Dados da matrícula
        class_info: Dados da turma
        grades: Lista de notas do aluno
        courses: Lista de disciplinas
        academic_year: Ano letivo
    
    Returns:
        BytesIO com o PDF gerado
    """
    from reportlab.platypus import KeepTogether
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    
    # ===== CABEÇALHO =====
    # Criar tabela do cabeçalho com logo à esquerda e título à direita
    header_left = """
    <b>Prefeitura Mun. de Floresta do Araguaia - PA</b><br/>
    <font size="9">Secretaria Municipal de Educação</font><br/>
    <font size="8" color="#666666">"Cuidar do povo é nosso amor"</font>
    """
    
    header_right = """
    <font size="16" color="#1e40af"><b>BOLETIM ESCOLAR</b></font><br/>
    <font size="10">ENSINO FUNDAMENTAL</font>
    """
    
    header_style_left = ParagraphStyle('HeaderLeft', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    
    header_table = Table([
        [Paragraph(header_left, header_style_left), Paragraph(header_right, header_style_right)]
    ], colWidths=[10*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    
    # ===== INFORMAÇÕES DA ESCOLA E ALUNO =====
    school_name = school.get('name', 'Escola Municipal')
    grade_level = class_info.get('grade_level', 'N/A')
    class_name = class_info.get('name', 'N/A')
    student_number = enrollment.get('registration_number', student.get('enrollment_number', '1'))
    student_name = student.get('full_name', 'N/A').upper()
    
    # Linha 1: Escola e Ano Letivo
    info_row1 = Table([
        [
            Paragraph(f"<b>Nome/escola:</b> {school_name}", ParagraphStyle('Info', fontSize=9)),
            Paragraph(f"<b>ANO LETIVO:</b> {academic_year}", ParagraphStyle('Info', fontSize=9, alignment=TA_CENTER)),
            Paragraph(f"<b>N°</b> {student_number}", ParagraphStyle('Info', fontSize=9, alignment=TA_RIGHT))
        ]
    ], colWidths=[10*cm, 4*cm, 4*cm])
    info_row1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_row1)
    
    # Linha 2: Nome do aluno, Ano/Etapa e Turma
    info_row2 = Table([
        [
            Paragraph(f"<b>NOME:</b> {student_name}", ParagraphStyle('Info', fontSize=9)),
            Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", ParagraphStyle('Info', fontSize=9, alignment=TA_CENTER)),
            Paragraph(f"<b>TURMA:</b> {class_name}", ParagraphStyle('Info', fontSize=9, alignment=TA_CENTER))
        ]
    ], colWidths=[10*cm, 4*cm, 4*cm])
    info_row2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_row2)
    elements.append(Spacer(1, 15))
    
    # ===== TABELA DE NOTAS E FALTAS =====
    # Criar mapa de notas por disciplina
    grades_by_course = {}
    for grade in grades:
        course_id = grade.get('course_id')
        if course_id not in grades_by_course:
            grades_by_course[course_id] = {}
        period = grade.get('period', 'P1')
        grades_by_course[course_id][period] = grade
    
    # Cabeçalho da tabela - Modelo com Faltas por bimestre
    header_row1 = [
        'COMPONENTES\nCURRICULARES',
        '1ª', 'Faltas',
        '2°', 'Faltas',
        '3°', 'Faltas',
        '4°', 'Faltas',
        'Total de\npontos',
        'Total de\nfaltas',
        'Média'
    ]
    
    table_data = [header_row1]
    
    total_geral_pontos = 0
    total_geral_faltas = 0
    
    for course in courses:
        course_grades = grades_by_course.get(course.get('id'), {})
        
        # Obter notas e faltas de cada período
        n1 = course_grades.get('P1', {}).get('grade', '')
        f1 = course_grades.get('P1', {}).get('absences', '')
        n2 = course_grades.get('P2', {}).get('grade', '')
        f2 = course_grades.get('P2', {}).get('absences', '')
        n3 = course_grades.get('P3', {}).get('grade', '')
        f3 = course_grades.get('P3', {}).get('absences', '')
        n4 = course_grades.get('P4', {}).get('grade', '')
        f4 = course_grades.get('P4', {}).get('absences', '')
        
        # Calcular total de pontos e faltas
        valid_grades = []
        for g in [n1, n2, n3, n4]:
            if isinstance(g, (int, float)):
                valid_grades.append(g)
        
        total_pontos = sum(valid_grades) if valid_grades else 0
        
        valid_faltas = []
        for f in [f1, f2, f3, f4]:
            if isinstance(f, (int, float)):
                valid_faltas.append(f)
        total_faltas = sum(valid_faltas) if valid_faltas else 0
        
        # Calcular média
        if valid_grades:
            media = total_pontos / len(valid_grades)
            media_str = f"{media:.1f}"
        else:
            media_str = ''
        
        # Formatar valores
        def fmt_grade(v):
            if isinstance(v, (int, float)):
                return f"{v:.1f}"
            return str(v) if v else ''
        
        def fmt_int(v):
            if isinstance(v, (int, float)):
                return str(int(v))
            return str(v) if v else ''
        
        row = [
            course.get('name', 'N/A'),
            fmt_grade(n1), fmt_int(f1),
            fmt_grade(n2), fmt_int(f2),
            fmt_grade(n3), fmt_int(f3),
            fmt_grade(n4), fmt_int(f4),
            f"{total_pontos:.1f}" if total_pontos else '',
            fmt_int(total_faltas) if total_faltas else '',
            media_str
        ]
        table_data.append(row)
        
        total_geral_faltas += total_faltas
    
    # Larguras das colunas
    col_widths = [4*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.9*cm, 1.3*cm, 1.3*cm, 1.2*cm]
    
    grades_table = Table(table_data, colWidths=col_widths)
    grades_table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        
        # Corpo
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        
        # Grid
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        
        # Padding
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        
        # Alternar cores das linhas
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
    ]))
    elements.append(grades_table)
    elements.append(Spacer(1, 20))
    
    # ===== RESULTADO FINAL =====
    # Calcular resultado geral do aluno
    all_medias = []
    for course in courses:
        course_grades = grades_by_course.get(course.get('id'), {})
        valid_grades = []
        for period in ['P1', 'P2', 'P3', 'P4']:
            g = course_grades.get(period, {}).get('grade')
            if isinstance(g, (int, float)):
                valid_grades.append(g)
        if valid_grades:
            all_medias.append(sum(valid_grades) / len(valid_grades))
    
    if all_medias:
        media_geral = sum(all_medias) / len(all_medias)
        if media_geral >= 6:
            resultado = "APROVADO"
            resultado_color = colors.HexColor('#16a34a')  # Verde
        elif media_geral >= 4:
            resultado = "EM RECUPERAÇÃO"
            resultado_color = colors.HexColor('#ca8a04')  # Amarelo
        else:
            resultado = "REPROVADO"
            resultado_color = colors.HexColor('#dc2626')  # Vermelho
    else:
        resultado = "EM ANDAMENTO"
        resultado_color = colors.HexColor('#2563eb')  # Azul
    
    result_style = ParagraphStyle('Result', fontSize=12, alignment=TA_LEFT)
    result_value_style = ParagraphStyle('ResultValue', fontSize=14, alignment=TA_LEFT, textColor=resultado_color)
    
    result_table = Table([
        [
            Paragraph("<b>RESULTADO:</b>", result_style),
            Paragraph(f"<b>{resultado}</b>", result_value_style)
        ]
    ], colWidths=[3*cm, 15*cm])
    result_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(result_table)
    elements.append(Spacer(1, 30))
    
    # ===== ASSINATURAS =====
    sig_data = [
        ['_' * 35, '_' * 35],
        ['SECRETÁRIO(A)', 'DIRETOR(A)']
    ]
    
    sig_table = Table(sig_data, colWidths=[8.5*cm, 8.5*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, 1), 9),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 1), (-1, 1), 5),
    ]))
    elements.append(sig_table)
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_declaracao_matricula_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    enrollment: Dict[str, Any],
    class_info: Dict[str, Any],
    academic_year: str,
    purpose: str = "fins comprobatórios"
) -> BytesIO:
    """
    Gera o PDF da Declaração de Matrícula
    
    Args:
        student: Dados do aluno
        school: Dados da escola
        enrollment: Dados da matrícula
        class_info: Dados da turma
        academic_year: Ano letivo
        purpose: Finalidade da declaração
    
    Returns:
        BytesIO com o PDF gerado
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5*cm,
        leftMargin=2.5*cm,
        topMargin=3*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    
    # Cabeçalho
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    elements.append(Paragraph(f"CNPJ: {school.get('cnpj', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Endereço: {school.get('address', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Tel: {school.get('phone', 'N/A')}", styles['CenterText']))
    elements.append(Spacer(1, 40))
    
    # Título
    elements.append(Paragraph("DECLARAÇÃO DE MATRÍCULA", styles['MainTitle']))
    elements.append(Spacer(1, 30))
    
    # Corpo do texto
    student_name = student.get('full_name', 'N/A')
    birth_date = student.get('birth_date', 'N/A')
    class_name = class_info.get('name', 'N/A')
    shift = class_info.get('shift', 'N/A')
    reg_number = enrollment.get('registration_number', 'N/A')
    
    # Formatar data de nascimento
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = format_date_pt(bd.date())
        except:
            pass
    
    text = f"""
    Declaramos, para os devidos {purpose}, que <b>{student_name}</b>, 
    nascido(a) em <b>{birth_date}</b>, encontra-se regularmente matriculado(a) 
    nesta Unidade de Ensino no ano letivo de <b>{academic_year}</b>, 
    cursando a turma <b>{class_name}</b>, no turno <b>{shift}</b>, 
    sob o número de matrícula <b>{reg_number}</b>.
    """
    
    elements.append(Paragraph(text, styles['JustifyText']))
    elements.append(Spacer(1, 20))
    
    text2 = """
    Por ser expressão da verdade, firmamos a presente declaração.
    """
    elements.append(Paragraph(text2, styles['JustifyText']))
    elements.append(Spacer(1, 50))
    
    # Data e local
    today = format_date_pt(date.today())
    city = school.get('city', 'Município')
    elements.append(Paragraph(f"{city}, {today}.", styles['CenterText']))
    elements.append(Spacer(1, 60))
    
    # Assinatura
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Diretor(a)", styles['CenterText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_declaracao_frequencia_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    enrollment: Dict[str, Any],
    class_info: Dict[str, Any],
    attendance_data: Dict[str, Any],
    academic_year: str,
    period: str = "ano letivo"
) -> BytesIO:
    """
    Gera o PDF da Declaração de Frequência
    
    Args:
        student: Dados do aluno
        school: Dados da escola
        enrollment: Dados da matrícula
        class_info: Dados da turma
        attendance_data: Dados de frequência {total_days, present_days, absent_days, frequency_percentage}
        academic_year: Ano letivo
        period: Período de referência
    
    Returns:
        BytesIO com o PDF gerado
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5*cm,
        leftMargin=2.5*cm,
        topMargin=3*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    
    # Cabeçalho
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    elements.append(Paragraph(f"CNPJ: {school.get('cnpj', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Endereço: {school.get('address', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Tel: {school.get('phone', 'N/A')}", styles['CenterText']))
    elements.append(Spacer(1, 40))
    
    # Título
    elements.append(Paragraph("DECLARAÇÃO DE FREQUÊNCIA", styles['MainTitle']))
    elements.append(Spacer(1, 30))
    
    # Dados de frequência
    total_days = attendance_data.get('total_days', 0)
    present_days = attendance_data.get('present_days', 0)
    absent_days = attendance_data.get('absent_days', 0)
    frequency = attendance_data.get('frequency_percentage', 0)
    
    # Corpo do texto
    student_name = student.get('full_name', 'N/A')
    class_name = class_info.get('name', 'N/A')
    shift = class_info.get('shift', 'N/A')
    reg_number = enrollment.get('registration_number', 'N/A')
    
    text = f"""
    Declaramos, para os devidos fins, que <b>{student_name}</b>, 
    matriculado(a) nesta Unidade de Ensino sob o número <b>{reg_number}</b>, 
    cursando a turma <b>{class_name}</b>, turno <b>{shift}</b>, 
    no ano letivo de <b>{academic_year}</b>, apresenta a seguinte situação de frequência 
    referente ao {period}:
    """
    
    elements.append(Paragraph(text, styles['JustifyText']))
    elements.append(Spacer(1, 20))
    
    # Tabela de frequência
    freq_data = [
        ['Total de dias letivos:', f'{total_days} dias'],
        ['Dias de presença:', f'{present_days} dias'],
        ['Dias de ausência:', f'{absent_days} dias'],
        ['Percentual de frequência:', f'{frequency:.1f}%'],
    ]
    
    freq_table = Table(freq_data, colWidths=[6*cm, 5*cm])
    freq_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0f2fe')),
    ]))
    elements.append(freq_table)
    elements.append(Spacer(1, 30))
    
    # Situação
    if frequency >= 75:
        situacao = "FREQUÊNCIA REGULAR"
        cor = colors.HexColor('#166534')
    else:
        situacao = "FREQUÊNCIA IRREGULAR (abaixo de 75%)"
        cor = colors.HexColor('#dc2626')
    
    elements.append(Paragraph(
        f"<b>Situação:</b> <font color='{cor.hexval()}'>{situacao}</font>",
        styles['CenterText']
    ))
    elements.append(Spacer(1, 30))
    
    text2 = """
    Por ser expressão da verdade, firmamos a presente declaração.
    """
    elements.append(Paragraph(text2, styles['JustifyText']))
    elements.append(Spacer(1, 50))
    
    # Data e local
    today = format_date_pt(date.today())
    city = school.get('city', 'Município')
    elements.append(Paragraph(f"{city}, {today}.", styles['CenterText']))
    elements.append(Spacer(1, 60))
    
    # Assinatura
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Diretor(a)", styles['CenterText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_ficha_individual_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    enrollment: Dict[str, Any],
    academic_year: int
) -> BytesIO:
    """
    Gera a Ficha Individual do Aluno em PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    
    # Cabeçalho
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    elements.append(Spacer(1, 20))
    
    # Título
    elements.append(Paragraph("FICHA INDIVIDUAL DO ALUNO", styles['MainTitle']))
    elements.append(Paragraph(f"Ano Letivo: {academic_year}", styles['CenterText']))
    elements.append(Spacer(1, 20))
    
    # Dados do Aluno
    elements.append(Paragraph("DADOS PESSOAIS", styles['Subtitle']))
    elements.append(Spacer(1, 10))
    
    dados_pessoais = [
        ['Nome Completo:', student.get('full_name', 'N/A')],
        ['Data de Nascimento:', student.get('birth_date', 'N/A')],
        ['Naturalidade:', f"{student.get('city_of_birth', 'N/A')} - {student.get('state_of_birth', 'N/A')}"],
        ['Sexo:', student.get('sex', 'N/A')],
        ['CPF:', student.get('cpf', 'N/A')],
        ['RG:', student.get('rg', 'N/A')],
        ['NIS:', student.get('nis', 'N/A')],
    ]
    
    table = Table(dados_pessoais, colWidths=[5*cm, 12*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    
    # Dados de Matrícula
    elements.append(Paragraph("DADOS DE MATRÍCULA", styles['Subtitle']))
    elements.append(Spacer(1, 10))
    
    dados_matricula = [
        ['Nº Matrícula:', enrollment.get('registration_number', student.get('enrollment_number', 'N/A'))],
        ['Turma:', class_info.get('name', 'N/A')],
        ['Série/Ano:', class_info.get('grade_level', 'N/A')],
        ['Turno:', class_info.get('shift', 'N/A')],
        ['Escola:', school.get('name', 'N/A')],
    ]
    
    table2 = Table(dados_matricula, colWidths=[5*cm, 12*cm])
    table2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(table2)
    elements.append(Spacer(1, 20))
    
    # Filiação
    elements.append(Paragraph("FILIAÇÃO", styles['Subtitle']))
    elements.append(Spacer(1, 10))
    
    filiacao = [
        ['Pai:', student.get('father_name', 'N/A')],
        ['Mãe:', student.get('mother_name', 'N/A')],
        ['Responsável:', student.get('guardian_name', 'N/A')],
        ['Tel. Responsável:', student.get('guardian_phone', 'N/A')],
    ]
    
    table3 = Table(filiacao, colWidths=[5*cm, 12*cm])
    table3.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(table3)
    elements.append(Spacer(1, 20))
    
    # Endereço
    elements.append(Paragraph("ENDEREÇO", styles['Subtitle']))
    elements.append(Spacer(1, 10))
    
    endereco = [
        ['Endereço:', student.get('address', 'N/A')],
        ['Bairro:', student.get('neighborhood', 'N/A')],
        ['Cidade/UF:', f"{student.get('city', 'N/A')} - {student.get('state', 'N/A')}"],
        ['CEP:', student.get('zip_code', 'N/A')],
    ]
    
    table4 = Table(endereco, colWidths=[5*cm, 12*cm])
    table4.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(table4)
    elements.append(Spacer(1, 30))
    
    # Data e local
    today = format_date_pt(date.today())
    city = school.get('city', school.get('municipio', 'Município'))
    elements.append(Paragraph(f"{city}, {today}.", styles['CenterText']))
    elements.append(Spacer(1, 40))
    
    # Assinatura
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_certificado_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    enrollment: Dict[str, Any],
    academic_year: int,
    course_name: str = "Ensino Fundamental"
) -> BytesIO:
    """
    Gera o Certificado de Conclusão em PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=3*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    
    # Cabeçalho
    elements.append(Paragraph("PREFEITURA MUNICIPAL", styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['Subtitle']))
    elements.append(Spacer(1, 40))
    
    # Título do Certificado
    cert_style = ParagraphStyle(
        'CertTitle',
        parent=styles['MainTitle'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30
    )
    elements.append(Paragraph("CERTIFICADO", cert_style))
    elements.append(Spacer(1, 30))
    
    # Corpo do Certificado
    student_name = student.get('full_name', 'N/A').upper()
    birth_date = student.get('birth_date', 'N/A')
    grade_level = class_info.get('grade_level', 'N/A')
    
    # Determinar o nível com base na série
    if '9' in str(grade_level):
        nivel = "Anos Finais do Ensino Fundamental"
    elif '5' in str(grade_level):
        nivel = "Anos Iniciais do Ensino Fundamental"
    else:
        nivel = "Ensino Fundamental"
    
    text = f"""
    Certificamos que <b>{student_name}</b>, nascido(a) em <b>{birth_date}</b>,
    concluiu com aproveitamento o <b>{nivel}</b>, nesta Unidade de Ensino,
    no ano letivo de <b>{academic_year}</b>, estando apto(a) a prosseguir seus estudos.
    """
    
    elements.append(Paragraph(text, styles['JustifyText']))
    elements.append(Spacer(1, 40))
    
    # Data e local
    today = format_date_pt(date.today())
    city = school.get('city', school.get('municipio', 'Município'))
    state = school.get('state', school.get('estado', 'PA'))
    elements.append(Paragraph(f"{city} - {state}, {today}.", styles['CenterText']))
    elements.append(Spacer(1, 60))
    
    # Assinaturas
    sig_data = [
        ['_' * 30, '_' * 30],
        ['Secretário(a) Escolar', 'Diretor(a)'],
    ]
    
    sig_table = Table(sig_data, colWidths=[8*cm, 8*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, 1), 5),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 40))
    
    # Registro
    reg_number = enrollment.get('registration_number', student.get('enrollment_number', 'N/A'))
    elements.append(Paragraph(f"Registro nº: {reg_number}", styles['SmallText']))
    elements.append(Paragraph(f"Livro: _____ Folha: _____", styles['SmallText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
