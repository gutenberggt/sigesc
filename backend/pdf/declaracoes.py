"""Módulo PDF - Declarações (Matrícula, Transferência, Frequência)"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from pdf.utils import get_logo_image, format_date_pt, get_styles

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
    # Margem superior reduzida em 60% (3cm -> 1.2cm)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5*cm,
        leftMargin=2.5*cm,
        topMargin=1.2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    mantenedora = mantenedora or {}
    
    # Usar logotipo da mantenedora se disponível
    # Tamanho reduzido em 40% (3.75cm -> 2.25cm, 2.5cm -> 1.5cm)
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=3*cm, height=3.5*cm, logo_url=logo_url)
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
    
    # Montar endereço completo da escola a partir dos campos de localização
    endereco_partes = []
    if school.get('logradouro'):
        endereco_partes.append(school.get('logradouro'))
    if school.get('numero'):
        endereco_partes.append(f"nº {school.get('numero')}")
    if school.get('complemento'):
        endereco_partes.append(school.get('complemento'))
    if school.get('bairro'):
        endereco_partes.append(school.get('bairro'))
    if school.get('municipio'):
        endereco_partes.append(school.get('municipio'))
    if school.get('estado'):
        endereco_partes.append(f"- {school.get('estado')}")
    if school.get('cep'):
        endereco_partes.append(f"CEP: {school.get('cep')}")
    
    endereco = ', '.join(endereco_partes) if endereco_partes else ''
    
    # Montar telefone da escola
    telefone = ''
    if school.get('ddd_telefone') and school.get('telefone'):
        telefone = f"({school.get('ddd_telefone')}) {school.get('telefone')}"
    elif school.get('telefone'):
        telefone = school.get('telefone')
    
    # Cabeçalho - usar nome da mantenedora
    elements.append(Paragraph(mant_nome.upper(), styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    
    # Endereço e telefone da escola (deixar em branco se não tiver)
    if endereco:
        elements.append(Paragraph(f"Endereço: {endereco}", styles['CenterText']))
    if telefone:
        elements.append(Paragraph(f"Tel: {telefone}", styles['CenterText']))
    elements.append(Spacer(1, 30))
    
    # Título
    elements.append(Paragraph("DECLARAÇÃO DE MATRÍCULA", styles['MainTitle']))
    elements.append(Spacer(1, 30))
    
    # Corpo do texto
    student_name = student.get('full_name', 'N/A')
    birth_date = student.get('birth_date', 'N/A')
    display_grade = enrollment.get('student_series') or class_info.get('grade_level') or class_info.get('name', 'N/A')
    
    # Mapeamento de turnos para português
    TURNOS_PT = {
        'morning': 'Matutino',
        'afternoon': 'Vespertino',
        'evening': 'Noturno',
        'full_time': 'Integral',
        'night': 'Noturno'
    }
    shift_raw = class_info.get('shift', 'N/A')
    shift = TURNOS_PT.get(shift_raw, shift_raw)
    
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
    cursando o <b>{display_grade}</b>, no turno <b>{shift}</b>, 
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
    
    # Assinatura - apenas Secretário(a) Escolar (removido Diretor)
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer



def generate_declaracao_transferencia_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    enrollment: Dict[str, Any],
    class_info: Dict[str, Any],
    academic_year: str,
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera o PDF da Declaração de Transferência
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5*cm,
        leftMargin=2.5*cm,
        topMargin=1.2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    mantenedora = mantenedora or {}
    
    # Logotipo
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=3*cm, height=3.5*cm, logo_url=logo_url)
    if logo:
        logo_table = Table([[logo]], colWidths=[16*cm])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(logo_table)
        elements.append(Spacer(1, 10))
    
    # Dados da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    # Endereço da escola
    endereco_partes = []
    if school.get('logradouro'):
        endereco_partes.append(school.get('logradouro'))
    if school.get('numero'):
        endereco_partes.append(f"nº {school.get('numero')}")
    if school.get('complemento'):
        endereco_partes.append(school.get('complemento'))
    if school.get('bairro'):
        endereco_partes.append(school.get('bairro'))
    if school.get('municipio'):
        endereco_partes.append(school.get('municipio'))
    if school.get('estado'):
        endereco_partes.append(f"- {school.get('estado')}")
    if school.get('cep'):
        endereco_partes.append(f"CEP: {school.get('cep')}")
    endereco = ', '.join(endereco_partes) if endereco_partes else ''
    
    # Telefone da escola
    telefone = ''
    if school.get('ddd_telefone') and school.get('telefone'):
        telefone = f"({school.get('ddd_telefone')}) {school.get('telefone')}"
    elif school.get('telefone'):
        telefone = school.get('telefone')
    
    # Cabeçalho
    elements.append(Paragraph(mant_nome.upper(), styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    
    if endereco:
        elements.append(Paragraph(f"Endereço: {endereco}", styles['CenterText']))
    if telefone:
        elements.append(Paragraph(f"Tel: {telefone}", styles['CenterText']))
    elements.append(Spacer(1, 30))
    
    # Título
    elements.append(Paragraph("DECLARAÇÃO DE TRANSFERÊNCIA", styles['MainTitle']))
    elements.append(Spacer(1, 30))
    
    # Dados do aluno
    student_name = student.get('full_name', 'N/A')
    birth_date = student.get('birth_date', 'N/A')
    display_grade = enrollment.get('student_series') or class_info.get('grade_level') or class_info.get('name', 'N/A')
    mother_name = student.get('mother_name') or 'Não informado'
    father_name = student.get('father_name') or 'Não informado'
    
    TURNOS_PT = {
        'morning': 'Matutino',
        'afternoon': 'Vespertino',
        'evening': 'Noturno',
        'full_time': 'Integral',
        'night': 'Noturno'
    }
    shift_raw = class_info.get('shift', 'N/A')
    shift = TURNOS_PT.get(shift_raw, shift_raw)
    
    reg_number = enrollment.get('registration_number', 'N/A')
    
    # Formatar data de nascimento
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = format_date_pt(bd.date())
        except:
            pass
    
    # Corpo do texto
    text1 = f"""
    Declaramos, para os devidos fins de transferência, que <b>{student_name}</b>, 
    nascido(a) em <b>{birth_date}</b>, filho(a) de <b>{mother_name}</b> e 
    <b>{father_name}</b>, esteve regularmente matriculado(a) nesta Unidade de Ensino 
    no ano letivo de <b>{academic_year}</b>, cursando o <b>{display_grade}</b>, 
    no turno <b>{shift}</b>, sob o número de matrícula <b>{reg_number}</b>.
    """
    elements.append(Paragraph(text1, styles['JustifyText']))
    elements.append(Spacer(1, 15))
    
    text2 = f"""
    O(A) referido(a) aluno(a) está sendo transferido(a) desta instituição a pedido 
    de seu responsável legal, nada constando que o(a) desabone em termos de conduta 
    e aproveitamento escolar.
    """
    elements.append(Paragraph(text2, styles['JustifyText']))
    elements.append(Spacer(1, 15))
    
    text3 = f"""
    Informamos que o <b>Histórico Escolar</b> do(a) aluno(a) será emitido e 
    disponibilizado em até <b>30 (trinta) dias</b> a contar da data desta declaração.
    """
    elements.append(Paragraph(text3, styles['JustifyText']))
    elements.append(Spacer(1, 20))
    
    text4 = """
    Por ser expressão da verdade, firmamos a presente declaração.
    """
    elements.append(Paragraph(text4, styles['JustifyText']))
    elements.append(Spacer(1, 50))
    
    # Data e local
    today = format_date_pt(date.today())
    city = mant_municipio
    elements.append(Paragraph(f"{city}, {today}.", styles['CenterText']))
    elements.append(Spacer(1, 60))
    
    # Assinatura - Secretário(a) Escolar
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    
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
    # Margem superior reduzida em 60% (3cm -> 1.2cm)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5*cm,
        leftMargin=2.5*cm,
        topMargin=1.2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    elements = []
    mantenedora = mantenedora or {}
    
    # Usar logotipo da mantenedora se disponível
    # Tamanho reduzido em 40% (3.75cm -> 2.25cm, 2.5cm -> 1.5cm)
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=3*cm, height=3.5*cm, logo_url=logo_url)
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
    
    # Montar endereço completo da escola a partir dos campos de localização
    endereco_partes = []
    if school.get('logradouro'):
        endereco_partes.append(school.get('logradouro'))
    if school.get('numero'):
        endereco_partes.append(f"nº {school.get('numero')}")
    if school.get('complemento'):
        endereco_partes.append(school.get('complemento'))
    if school.get('bairro'):
        endereco_partes.append(school.get('bairro'))
    if school.get('municipio'):
        endereco_partes.append(school.get('municipio'))
    if school.get('estado'):
        endereco_partes.append(f"- {school.get('estado')}")
    if school.get('cep'):
        endereco_partes.append(f"CEP: {school.get('cep')}")
    
    endereco = ', '.join(endereco_partes) if endereco_partes else ''
    
    # Montar telefone da escola
    telefone = ''
    if school.get('ddd_telefone') and school.get('telefone'):
        telefone = f"({school.get('ddd_telefone')}) {school.get('telefone')}"
    elif school.get('telefone'):
        telefone = school.get('telefone')
    
    # Cabeçalho - usar nome da mantenedora
    elements.append(Paragraph(mant_nome.upper(), styles['CenterText']))
    elements.append(Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", styles['CenterText']))
    elements.append(Paragraph(school.get('name', 'Escola Municipal'), styles['MainTitle']))
    
    # Endereço e telefone da escola (deixar em branco se não tiver)
    if endereco:
        elements.append(Paragraph(f"Endereço: {endereco}", styles['CenterText']))
    if telefone:
        elements.append(Paragraph(f"Tel: {telefone}", styles['CenterText']))
    elements.append(Spacer(1, 20))
    
    # Título
    elements.append(Paragraph("DECLARAÇÃO DE FREQUÊNCIA", styles['MainTitle']))
    elements.append(Spacer(1, 20))
    
    # Dados de frequência
    total_days = attendance_data.get('total_days', 0)
    present_days = attendance_data.get('present_days', 0)
    absent_days = attendance_data.get('absent_days', 0)
    frequency = attendance_data.get('frequency_percentage', 0)
    
    # Corpo do texto
    student_name = student.get('full_name', 'N/A')
    display_grade = enrollment.get('student_series') or class_info.get('grade_level') or class_info.get('name', 'N/A')
    
    # Mapeamento de turnos para português
    TURNOS_PT = {
        'morning': 'Matutino',
        'afternoon': 'Vespertino',
        'evening': 'Noturno',
        'full_time': 'Integral',
        'night': 'Noturno'
    }
    shift_raw = class_info.get('shift', 'N/A')
    shift = TURNOS_PT.get(shift_raw, shift_raw)
    
    reg_number = enrollment.get('registration_number', 'N/A')
    
    text = f"""
    Declaramos, para os devidos fins, que <b>{student_name}</b>, 
    matriculado(a) nesta Unidade de Ensino sob o número <b>{reg_number}</b>, 
    cursando o <b>{display_grade}</b>, turno <b>{shift}</b>, 
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
    
    # Assinatura - apenas Secretário(a) Escolar (removido Diretor)
    elements.append(Paragraph("_" * 50, styles['CenterText']))
    elements.append(Paragraph("Secretário(a) Escolar", styles['CenterText']))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
