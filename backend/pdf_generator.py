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
    Gera o PDF do Boletim Escolar
    
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
    elements.append(Paragraph(f"CNPJ: {school.get('cnpj', 'N/A')} - Tel: {school.get('phone', 'N/A')}", styles['CenterText']))
    elements.append(Spacer(1, 20))
    
    # Título do documento
    elements.append(Paragraph("BOLETIM ESCOLAR", styles['MainTitle']))
    elements.append(Paragraph(f"Ano Letivo: {academic_year}", styles['SubTitle']))
    elements.append(Spacer(1, 15))
    
    # Dados do aluno
    student_data = [
        ['Aluno(a):', student.get('full_name', 'N/A')],
        ['Matrícula:', enrollment.get('registration_number', 'N/A')],
        ['Turma:', class_info.get('name', 'N/A')],
        ['Turno:', class_info.get('shift', 'N/A')],
        ['Nascimento:', student.get('birth_date', 'N/A')]
    ]
    
    student_table = Table(student_data, colWidths=[4*cm, 12*cm])
    student_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 20))
    
    # Tabela de notas
    # Criar mapa de notas por disciplina
    grades_by_course = {}
    for grade in grades:
        course_id = grade.get('course_id')
        if course_id not in grades_by_course:
            grades_by_course[course_id] = {}
        period = grade.get('period', 'P1')
        grades_by_course[course_id][period] = grade
    
    # Cabeçalho da tabela de notas
    header = ['Disciplina', '1º Bim', '2º Bim', '3º Bim', '4º Bim', 'Rec 1', 'Rec 2', 'Média', 'Situação']
    table_data = [header]
    
    for course in courses:
        course_grades = grades_by_course.get(course.get('id'), {})
        
        # Obter notas de cada período
        n1 = course_grades.get('P1', {}).get('grade', '-')
        n2 = course_grades.get('P2', {}).get('grade', '-')
        n3 = course_grades.get('P3', {}).get('grade', '-')
        n4 = course_grades.get('P4', {}).get('grade', '-')
        rec1 = course_grades.get('REC1', {}).get('grade', '-')
        rec2 = course_grades.get('REC2', {}).get('grade', '-')
        
        # Calcular média (simplificado)
        valid_grades = []
        for g in [n1, n2, n3, n4]:
            if isinstance(g, (int, float)):
                valid_grades.append(g)
        
        if valid_grades:
            media = sum(valid_grades) / len(valid_grades)
            media_str = f"{media:.1f}"
            situacao = 'Aprovado' if media >= 6 else 'Em Recuperação' if media >= 4 else 'Reprovado'
        else:
            media_str = '-'
            situacao = '-'
        
        # Formatar notas
        def fmt(v):
            if isinstance(v, (int, float)):
                return f"{v:.1f}"
            return str(v) if v else '-'
        
        row = [
            course.get('name', 'N/A'),
            fmt(n1), fmt(n2), fmt(n3), fmt(n4),
            fmt(rec1), fmt(rec2),
            media_str,
            situacao
        ]
        table_data.append(row)
    
    # Criar tabela
    col_widths = [4*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 2.5*cm]
    grades_table = Table(table_data, colWidths=col_widths)
    grades_table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Corpo
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        
        # Alternar cores das linhas
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
    ]))
    elements.append(grades_table)
    elements.append(Spacer(1, 30))
    
    # Legenda
    elements.append(Paragraph(
        "<b>Legenda:</b> Média para aprovação: 6,0 | Rec = Recuperação",
        styles['Normal']
    ))
    elements.append(Spacer(1, 40))
    
    # Data e assinatura
    today = format_date_pt(date.today())
    city = school.get('city', 'Município')
    elements.append(Paragraph(f"{city}, {today}", styles['CenterText']))
    elements.append(Spacer(1, 40))
    
    # Linha de assinatura
    sig_data = [['_' * 40, '_' * 40]]
    sig_names = [['Secretário(a) Escolar', 'Diretor(a)']]
    
    sig_table = Table(sig_data + sig_names, colWidths=[8*cm, 8*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
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
