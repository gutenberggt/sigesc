"""
Módulo para geração de documentos PDF do SIGESC
- Boletim Escolar
- Declaração de Matrícula
- Declaração de Frequência
- Ficha Individual
- Impressão em Lote (consolidado)
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import locale
import urllib.request
import tempfile
import os

# URL do logotipo da prefeitura
LOGO_URL = "https://aprenderdigital.top/imagens/logotipo/logoprefeitura.jpg"

# Tentar configurar locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')
    except:
        pass


def get_logo_image(width=2*cm, height=2*cm, logo_url=None):
    """
    Baixa e retorna o logotipo como um objeto Image do reportlab.
    Se logo_url não for fornecido, usa a URL padrão.
    Retorna None se não conseguir baixar.
    """
    url = logo_url if logo_url else LOGO_URL
    
    if not url:
        return None
    
    try:
        # Baixar a imagem
        with urllib.request.urlopen(url, timeout=5) as response:
            image_data = response.read()
        
        # Salvar em arquivo temporário
        suffix = '.jpg' if '.jpg' in url.lower() or '.jpeg' in url.lower() else '.png'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(image_data)
        temp_file.close()
        
        # Criar objeto Image
        logo = Image(temp_file.name, width=width, height=height)
        
        return logo
    except Exception as e:
        print(f"Erro ao carregar logotipo de {url}: {e}")
        return None


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
    academic_year: str,
    mantenedora: Dict[str, Any] = None
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
        mantenedora: Dados da mantenedora (logotipo, cidade, estado)
    
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
    mantenedora = mantenedora or {}
    
    # ===== CABEÇALHO =====
    # Usar logotipo da mantenedora se disponível
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.7*cm, height=1.8*cm, logo_url=logo_url)
    
    # Usar dados da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    header_text = f"""
    <b>{mant_nome}</b><br/>
    <font size="9">Secretaria Municipal de Educação</font><br/>
    <font size="8" color="#666666">"Cuidar do povo é nossa prioridade"</font>
    """
    
    header_right = """
    <font size="16" color="#1e40af"><b>BOLETIM ESCOLAR</b></font><br/>
    <font size="10">ENSINO FUNDAMENTAL</font>
    """
    
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    
    if logo:
        header_table = Table([
            [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[3.2*cm, 8.5*cm, 6.3*cm])  # Texto +1cm para melhor estética
    else:
        header_table = Table([
            [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[10*cm, 8*cm])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 10),  # Padding extra no texto
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
    
    # Cabeçalho da tabela - Modelo com Carga Horária e Faltas por bimestre
    header_row1 = [
        'COMPONENTES\nCURRICULARES',
        'CH',  # Carga Horária Anual
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
    total_carga_horaria = 0
    
    for course in courses:
        course_grades = grades_by_course.get(course.get('id'), {})
        
        # Obter carga horária do componente
        carga_horaria = course.get('workload', '')
        if carga_horaria:
            total_carga_horaria += carga_horaria
        
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
            fmt_int(carga_horaria) if carga_horaria else '',
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
    
    # Adicionar linha de total de carga horária
    total_row = [
        'TOTAL GERAL',
        fmt_int(total_carga_horaria) if total_carga_horaria else '',
        '', '', '', '', '', '', '', '', '', ''
    ]
    table_data.append(total_row)
    
    # Larguras das colunas (Componentes Curriculares + CH)
    col_widths = [4.2*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 0.8*cm, 1.1*cm, 1.1*cm, 1.0*cm]
    
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
    purpose: str = "fins comprobatórios",
    mantenedora: Dict[str, Any] = None
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
        mantenedora: Dados da mantenedora (logotipo, cidade, estado)
    
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
    mantenedora = mantenedora or {}
    
    # Usar logotipo da mantenedora se disponível
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=3.75*cm, height=2.5*cm, logo_url=logo_url)
    if logo:
        logo_table = Table([[logo]], colWidths=[16*cm])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(logo_table)
        elements.append(Spacer(1, 10))
    
    # Usar dados da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    # Cabeçalho - usar nome da mantenedora
    elements.append(Paragraph(mant_nome.upper(), styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    elements.append(Paragraph(f"Endereço: {school.get('address', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Tel: {school.get('phone', 'N/A')}", styles['CenterText']))
    elements.append(Spacer(1, 30))
    
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
    
    # Data e local - usar município da mantenedora
    today = format_date_pt(date.today())
    city = mant_municipio  # Usar município da mantenedora
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
    period: str = "ano letivo",
    mantenedora: Dict[str, Any] = None
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
        mantenedora: Dados da mantenedora (logotipo, cidade, estado)
    
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
    mantenedora = mantenedora or {}
    
    # Usar logotipo da mantenedora se disponível
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=3.75*cm, height=2.5*cm, logo_url=logo_url)
    if logo:
        logo_table = Table([[logo]], colWidths=[16*cm])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(logo_table)
        elements.append(Spacer(1, 10))
    
    # Usar dados da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    # Cabeçalho - usar nome da mantenedora
    elements.append(Paragraph(mant_nome.upper(), styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    elements.append(Paragraph(f"Endereço: {school.get('address', 'N/A')}", styles['CenterText']))
    elements.append(Paragraph(f"Tel: {school.get('phone', 'N/A')}", styles['CenterText']))
    elements.append(Spacer(1, 30))
    
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
    
    # Data e local - usar município da mantenedora
    today = format_date_pt(date.today())
    city = mant_municipio  # Usar município da mantenedora
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
    academic_year: int,
    grades: List[Dict[str, Any]] = None,
    courses: List[Dict[str, Any]] = None,
    attendance_data: Dict[str, Any] = None,
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera a Ficha Individual do Aluno em PDF - Modelo Floresta do Araguaia.
    
    Args:
        student: Dados do aluno
        school: Dados da escola
        class_info: Dados da turma
        enrollment: Dados da matrícula
        academic_year: Ano letivo
        grades: Lista de notas do aluno por componente
        courses: Lista de componentes curriculares
        attendance_data: Dados de frequência por componente
        mantenedora: Dados da mantenedora (logotipo, cidade, estado)
    
    Returns:
        BytesIO com o PDF gerado
    """
    from reportlab.platypus import KeepTogether
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.8*cm,
        leftMargin=0.8*cm,
        topMargin=0.8*cm,
        bottomMargin=0.8*cm
    )
    
    elements = []
    grades = grades or []
    courses = courses or []
    attendance_data = attendance_data or {}
    mantenedora = mantenedora or {}
    
    # ===== CABEÇALHO =====
    # Usar logotipo da mantenedora se disponível
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.4*cm, height=1.6*cm, logo_url=logo_url)
    
    # Usar cidade/estado da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    header_text = f"""
    <b>{mant_nome}</b><br/>
    <font size="9">Secretaria Municipal de Educação</font><br/>
    <font size="8" color="#666666">"Cuidar do povo é nossa prioridade"</font>
    """
    
    header_right = """
    <font size="14" color="#1e40af"><b>FICHA INDIVIDUAL</b></font><br/>
    <font size="10">ENSINO FUNDAMENTAL</font>
    """
    
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    
    if logo:
        header_table = Table([
            [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[3*cm, 9*cm, 7*cm])  # Texto +1cm para melhor estética
    else:
        header_table = Table([
            [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[10*cm, 9*cm])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (1, 0), (1, 0), 10),  # Padding extra no texto
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 5))
    
    # ===== INFORMAÇÕES DO ALUNO E ESCOLA =====
    school_name = school.get('name', 'Escola Municipal')
    grade_level = class_info.get('grade_level', 'N/A')
    class_name = class_info.get('name', 'N/A')
    shift = class_info.get('shift', 'N/A')
    student_name = student.get('full_name', 'N/A').upper()
    student_sex = student.get('sex', 'N/A')
    inep_number = student.get('inep_number', student.get('enrollment_number', 'N/A'))
    student_id_num = student.get('id', 'N/A')[:12] if student.get('id') else 'N/A'
    
    # Formatar data de nascimento
    birth_date = student.get('birth_date', 'N/A')
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = bd.strftime('%d/%m/%Y')
        except:
            pass
    
    # Carga horária total da turma
    total_carga_horaria = sum(c.get('carga_horaria', c.get('workload', 80)) for c in courses) if courses else 1200
    dias_letivos = 200
    
    # Calcular frequência anual média
    freq_total = 0
    freq_count = 0
    for course in courses:
        course_id = course.get('id')
        att = attendance_data.get(course_id, {})
        if att.get('frequency_percentage'):
            freq_total += att.get('frequency_percentage', 100)
            freq_count += 1
    frequencia_anual = freq_total / freq_count if freq_count > 0 else 100.0
    
    # Linha 1: Escola, Nome do Aluno
    info_style = ParagraphStyle('InfoStyle', fontSize=7, leading=9)
    info_style_bold = ParagraphStyle('InfoStyleBold', fontSize=7, leading=9, fontName='Helvetica-Bold')
    
    info_row1 = Table([
        [
            Paragraph(f"<b>NOME DA ESCOLA:</b> {school_name}", info_style),
            Paragraph(f"<b>ANO LETIVO:</b> {academic_year}", info_style),
        ]
    ], colWidths=[13*cm, 6*cm])
    info_row1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row1)
    
    # Linha 2: Nome aluno, sexo, INEP, ID
    info_row2 = Table([
        [
            Paragraph(f"<b>NOME DO(A) ALUNO(A):</b> {student_name}", info_style),
            Paragraph(f"<b>SEXO:</b> {student_sex}", info_style),
            Paragraph(f"<b>Nº INEP:</b> {inep_number}", info_style),
            Paragraph(f"<b>ID:</b> {student_id_num}", info_style),
        ]
    ], colWidths=[8*cm, 2*cm, 4.5*cm, 4.5*cm])
    info_row2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row2)
    
    # Linha 3: Ano/Etapa, Turma, Turno, Carga Horária, Dias Letivos, Data Nascimento
    info_row3 = Table([
        [
            Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", info_style),
            Paragraph(f"<b>TURMA:</b> {class_name}", info_style),
            Paragraph(f"<b>TURNO:</b> {shift}", info_style),
            Paragraph(f"<b>C.H.:</b> {total_carga_horaria}h", info_style),
            Paragraph(f"<b>DIAS LET.:</b> {dias_letivos}", info_style),
            Paragraph(f"<b>NASC.:</b> {birth_date}", info_style),
        ]
    ], colWidths=[3*cm, 3*cm, 3.5*cm, 2.5*cm, 3*cm, 4*cm])
    info_row3.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row3)
    
    # Linha 4: Frequência anual
    freq_style = ParagraphStyle('FreqStyle', fontSize=8, alignment=TA_RIGHT)
    elements.append(Paragraph(f"<b>FREQUÊNCIA ANUAL: {frequencia_anual:.2f}%</b>", freq_style))
    elements.append(Spacer(1, 8))
    
    # ===== TABELA DE NOTAS =====
    # Criar mapa de notas por componente
    grades_by_course = {}
    for grade in grades:
        course_id = grade.get('course_id')
        grades_by_course[course_id] = grade
    
    # Cabeçalho da tabela de notas - Modelo Ficha Individual
    # Estrutura: Componente | CH | 1º Sem (1º, 2º, Rec, Falt) | 2º Sem (3º, 4º, Rec, Falt) | Resultado (1ºx2, 2ºx3, 3ºx2, 4ºx3, Total, Média, Faltas, %Freq)
    
    # Cabeçalho principal (primeira linha)
    header_row1 = [
        'COMPONENTES\nCURRICULARES',
        'C.H.',
        '1º SEMESTRE', '', '', '',
        '2º SEMESTRE', '', '', '',
        'PROC. PONDERADO', '', '', '',
        'TOTAL\nPONTOS',
        'MÉDIA\nANUAL',
        'FALTAS',
        '%\nFREQ'
    ]
    
    # Cabeçalho secundário (segunda linha)
    header_row2 = [
        '', '',
        '1º', '2º', 'REC', 'FLT',
        '3º', '4º', 'REC', 'FLT',
        '1ºx2', '2ºx3', '3ºx2', '4ºx3',
        '', '', '', ''
    ]
    
    table_data = [header_row1, header_row2]
    
    def fmt_grade(v):
        """Formata nota como string"""
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
        return str(v) if v else '-'
    
    def fmt_int(v):
        """Formata número inteiro"""
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return str(int(v))
        return str(v) if v else '-'
    
    for course in courses:
        course_id = course.get('id')
        course_name = course.get('name', 'N/A')
        carga_horaria = course.get('carga_horaria', course.get('workload', 80))
        
        grade = grades_by_course.get(course_id, {})
        
        # Notas bimestrais
        b1 = grade.get('b1')
        b2 = grade.get('b2')
        b3 = grade.get('b3')
        b4 = grade.get('b4')
        
        # Recuperações por semestre
        rec_s1 = grade.get('rec_s1', grade.get('recovery'))
        rec_s2 = grade.get('rec_s2')
        
        # Faltas por semestre (assumindo distribuição igual)
        att = attendance_data.get(course_id, {})
        total_faltas = att.get('absences', 0)
        faltas_s1 = total_faltas // 2
        faltas_s2 = total_faltas - faltas_s1
        
        # Processo ponderado
        b1_pond = (b1 or 0) * 2
        b2_pond = (b2 or 0) * 3
        b3_pond = (b3 or 0) * 2
        b4_pond = (b4 or 0) * 3
        
        # Total de pontos e média
        total_pontos = b1_pond + b2_pond + b3_pond + b4_pond
        media_anual = total_pontos / 10 if total_pontos > 0 else 0
        
        # Frequência do componente
        freq_componente = att.get('frequency_percentage', 100.0)
        
        row = [
            course_name,
            str(carga_horaria),
            fmt_grade(b1), fmt_grade(b2), fmt_grade(rec_s1), fmt_int(faltas_s1),
            fmt_grade(b3), fmt_grade(b4), fmt_grade(rec_s2), fmt_int(faltas_s2),
            fmt_grade(b1_pond), fmt_grade(b2_pond), fmt_grade(b3_pond), fmt_grade(b4_pond),
            fmt_grade(total_pontos),
            fmt_grade(media_anual),
            fmt_int(total_faltas),
            f"{freq_componente:.2f}".replace('.', ',')
        ]
        table_data.append(row)
    
    # Larguras das colunas (Componentes Curriculares 25% maior: 3.5 * 1.25 = 4.375 ~ 4.4)
    col_widths = [
        4.4*cm,  # Componente (25% maior)
        0.65*cm,  # CH
        0.65*cm, 0.65*cm, 0.65*cm, 0.65*cm,  # 1º Sem
        0.65*cm, 0.65*cm, 0.65*cm, 0.65*cm,  # 2º Sem
        0.75*cm, 0.75*cm, 0.75*cm, 0.75*cm,  # Proc. Pond.
        0.9*cm,    # Total
        0.85*cm,  # Média
        0.75*cm,  # Faltas
        0.9*cm     # %Freq
    ]
    
    grades_table = Table(table_data, colWidths=col_widths)
    
    # Estilo da tabela
    style_commands = [
        # Cabeçalho principal - primeira linha
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 1), 6),
        ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 1), 'MIDDLE'),
        
        # Cabeçalho secundário
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#eff6ff')),
        
        # Merge células do cabeçalho
        ('SPAN', (0, 0), (0, 1)),  # Componentes
        ('SPAN', (1, 0), (1, 1)),  # CH
        ('SPAN', (2, 0), (5, 0)),  # 1º Semestre
        ('SPAN', (6, 0), (9, 0)),  # 2º Semestre
        ('SPAN', (10, 0), (13, 0)),  # Proc. Ponderado
        ('SPAN', (14, 0), (14, 1)),  # Total
        ('SPAN', (15, 0), (15, 1)),  # Média
        ('SPAN', (16, 0), (16, 1)),  # Faltas
        ('SPAN', (17, 0), (17, 1)),  # %Freq
        
        # Corpo da tabela
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 2), (-1, -1), 7),
        ('ALIGN', (1, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 2), (0, -1), 'LEFT'),
        ('VALIGN', (0, 2), (-1, -1), 'MIDDLE'),
        
        # Grid
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        
        # Padding
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        
        # Alternar cores das linhas
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
    ]
    
    grades_table.setStyle(TableStyle(style_commands))
    elements.append(grades_table)
    elements.append(Spacer(1, 5))
    
    # ===== OBSERVAÇÃO =====
    obs_style = ParagraphStyle('ObsStyle', fontSize=7, fontName='Helvetica-Oblique')
    elements.append(Paragraph("Este Documento não possui emendas nem rasuras.", obs_style))
    elements.append(Spacer(1, 10))
    
    # ===== RODAPÉ =====
    # Data e local - usar município da mantenedora
    today = format_date_pt(date.today())
    city = mant_municipio  # Usar município da mantenedora
    state = mant_estado  # Usar estado da mantenedora
    
    date_style = ParagraphStyle('DateStyle', fontSize=8, alignment=TA_LEFT)
    elements.append(Paragraph(f"{city} - {state}, {today}.", date_style))
    elements.append(Spacer(1, 5))
    
    # Observações livres
    obs_line_style = ParagraphStyle('ObsLineStyle', fontSize=8)
    elements.append(Paragraph("<b>OBS.:</b> _______________________________________________", obs_line_style))
    elements.append(Spacer(1, 15))
    
    # Assinaturas
    sig_data = [
        ['_' * 25, '_' * 25, '_' * 25],
        ['AUX. DE SECRETARIA', 'SECRETÁRIO(A)', 'DIRETOR(A)']
    ]
    
    sig_table = Table(sig_data, colWidths=[6*cm, 6*cm, 6*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 1), (-1, 1), 3),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 10))
    
    # Resultado final
    # Calcular se aprovado ou reprovado
    if grades:
        medias = []
        for course in courses:
            course_id = course.get('id')
            grade = grades_by_course.get(course_id, {})
            b1 = grade.get('b1') or 0
            b2 = grade.get('b2') or 0
            b3 = grade.get('b3') or 0
            b4 = grade.get('b4') or 0
            total = (b1 * 2) + (b2 * 3) + (b3 * 2) + (b4 * 3)
            media = total / 10
            medias.append(media)
        
        if medias:
            media_geral = sum(medias) / len(medias)
            if media_geral >= 5 and frequencia_anual >= 75:
                resultado = "APROVADO"
                resultado_color = colors.HexColor('#16a34a')
            else:
                resultado = "REPROVADO"
                resultado_color = colors.HexColor('#dc2626')
        else:
            resultado = "EM ANDAMENTO"
            resultado_color = colors.HexColor('#2563eb')
    else:
        resultado = "EM ANDAMENTO"
        resultado_color = colors.HexColor('#2563eb')
    
    result_style = ParagraphStyle('ResultStyle', fontSize=10, alignment=TA_CENTER)
    result_table = Table([
        [
            Paragraph(f"<b>RESULTADO:</b>", result_style),
            Paragraph(f"<b><font color='{resultado_color.hexval()}'>{resultado}</font></b>", result_style)
        ]
    ], colWidths=[4*cm, 6*cm])
    result_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(result_table)
    
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
    
    # Logotipo centralizado
    logo = get_logo_image(width=3.75*cm, height=2.5*cm)  # Largura 50% maior para não deformar
    if logo:
        logo_table = Table([[logo]], colWidths=[16*cm])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(logo_table)
        elements.append(Spacer(1, 10))
    
    # Cabeçalho
    elements.append(Paragraph("PREFEITURA MUNICIPAL DE FLORESTA DO ARAGUAIA", styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['Subtitle']))
    elements.append(Spacer(1, 30))
    
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


def generate_class_details_pdf(
    class_info: Dict[str, Any],
    school: Dict[str, Any],
    teachers: List[Dict[str, Any]],
    students: List[Dict[str, Any]],
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera PDF com detalhes da turma incluindo:
    - Dados cadastrais da turma
    - Professores alocados
    - Lista de alunos com responsáveis
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    styles.add(ParagraphStyle(
        name='TitleMain',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.HexColor('#1e40af')
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        alignment=TA_LEFT,
        spaceBefore=15,
        spaceAfter=10,
        textColor=colors.HexColor('#1e3a5f'),
        borderPadding=5
    ))
    styles.add(ParagraphStyle(
        name='NormalText',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_LEFT,
        spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name='SmallText',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_LEFT
    ))
    styles.add(ParagraphStyle(
        name='CenterText',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER
    ))
    
    elements = []
    
    # Cabeçalho com logo
    header_data = []
    logo = None
    
    # Tentar carregar logo da mantenedora
    if mantenedora and mantenedora.get('logo_url'):
        logo = get_logo_image(width=2.5*cm, height=2.5*cm, logo_url=mantenedora.get('logo_url'))
    
    if not logo:
        logo = get_logo_image(width=2.5*cm, height=2.5*cm)
    
    # Texto do cabeçalho
    mantenedora_nome = mantenedora.get('nome', 'Secretaria Municipal de Educação') if mantenedora else 'Secretaria Municipal de Educação'
    city = mantenedora.get('cidade', 'Município') if mantenedora else 'Município'
    state = mantenedora.get('estado', 'PA') if mantenedora else 'PA'
    
    header_text = f"""<b>{mantenedora_nome}</b><br/>
    {city} - {state}<br/>
    <b>{school.get('name', 'Escola')}</b>"""
    
    header_style = ParagraphStyle(
        name='HeaderStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        leading=14
    )
    
    if logo:
        header_data = [[logo, Paragraph(header_text, header_style)]]
        header_table = Table(header_data, colWidths=[3*cm, 14*cm])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(header_table)
    else:
        elements.append(Paragraph(header_text, header_style))
    
    elements.append(Spacer(1, 15))
    
    # Título
    elements.append(Paragraph(f"DETALHES DA TURMA: {class_info.get('name', '')}", styles['TitleMain']))
    elements.append(Spacer(1, 10))
    
    # Dados da Turma
    elements.append(Paragraph("📋 DADOS DA TURMA", styles['SectionTitle']))
    
    # Mapeamento de níveis de ensino
    education_levels = {
        'educacao_infantil': 'Educação Infantil',
        'fundamental_anos_iniciais': 'Ensino Fundamental - Anos Iniciais',
        'fundamental_anos_finais': 'Ensino Fundamental - Anos Finais',
        'eja': 'EJA - Educação de Jovens e Adultos'
    }
    
    # Mapeamento de turnos
    shifts = {
        'morning': 'Manhã',
        'afternoon': 'Tarde',
        'evening': 'Noite',
        'full_time': 'Integral'
    }
    
    class_data = [
        ['Nome:', class_info.get('name', '-'), 'Ano Letivo:', str(class_info.get('academic_year', '-'))],
        ['Escola:', school.get('name', '-'), 'Turno:', shifts.get(class_info.get('shift'), class_info.get('shift', '-'))],
        ['Nível de Ensino:', education_levels.get(class_info.get('education_level'), class_info.get('education_level', '-')), 'Série/Etapa:', class_info.get('grade_level', '-')],
    ]
    
    class_table = Table(class_data, colWidths=[3*cm, 6*cm, 3*cm, 5*cm])
    class_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e0e7ff')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#e0e7ff')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(class_table)
    elements.append(Spacer(1, 15))
    
    # Professores Alocados
    elements.append(Paragraph("👨‍🏫 PROFESSOR(ES) ALOCADO(S)", styles['SectionTitle']))
    
    if teachers:
        teacher_data = [['Nome', 'Componente Curricular', 'Celular']]
        for teacher in teachers:
            teacher_data.append([
                teacher.get('nome', '-'),
                teacher.get('componente', '-') or '-',
                teacher.get('celular', '-') or '-'
            ])
        
        teacher_table = Table(teacher_data, colWidths=[7*cm, 6*cm, 4*cm])
        teacher_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dcfce7')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(teacher_table)
    else:
        elements.append(Paragraph("Nenhum professor alocado", styles['NormalText']))
    
    elements.append(Spacer(1, 15))
    
    # Lista de Alunos
    elements.append(Paragraph(f"👥 ALUNOS MATRICULADOS ({len(students)})", styles['SectionTitle']))
    
    if students:
        student_data = [['#', 'Aluno', 'Data Nasc.', 'Responsável', 'Celular']]
        
        for idx, student in enumerate(students, 1):
            # Formatar data de nascimento
            birth_date = student.get('birth_date', '')
            if birth_date:
                try:
                    if isinstance(birth_date, str):
                        date_obj = datetime.strptime(birth_date, '%Y-%m-%d')
                        birth_date = date_obj.strftime('%d/%m/%Y')
                except:
                    pass
            
            student_data.append([
                str(idx),
                student.get('full_name', '-'),
                birth_date or '-',
                student.get('guardian_name', '-') or '-',
                student.get('guardian_phone', '-') or '-'
            ])
        
        student_table = Table(student_data, colWidths=[1*cm, 6.5*cm, 2.5*cm, 4.5*cm, 2.5*cm])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]))
        elements.append(student_table)
    else:
        elements.append(Paragraph("Nenhum aluno matriculado", styles['NormalText']))
    
    elements.append(Spacer(1, 20))
    
    # Rodapé com data de geração
    today = datetime.now().strftime('%d/%m/%Y às %H:%M')
    elements.append(Paragraph(f"Documento gerado em {today}", styles['SmallText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
