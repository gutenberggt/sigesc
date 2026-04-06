"""Módulo PDF - Relatório de Frequência por Bimestre"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from pdf.utils import get_logo_image, format_date_pt, get_styles

def generate_relatorio_frequencia_bimestre_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    course_info: Dict[str, Any],
    students_attendance: List[Dict[str, Any]],
    bimestre: int,
    academic_year: int,
    period_start: str,
    period_end: str,
    attendance_days: List[str],
    aulas_previstas: int = 0,
    aulas_ministradas: int = 0,
    teacher_name: str = "",
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera o PDF do Relatório de Frequência por Bimestre
    """
    buffer = BytesIO()
    
    from reportlab.lib.pagesizes import landscape
    page_width, page_height = landscape(A4)
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    styles = get_styles()
    elements = []
    mantenedora = mantenedora or {}
    
    # Estilos com espaçamento simples
    small_text = ParagraphStyle(
        'SmallText',
        parent=styles['CenterText'],
        fontSize=8,
        leading=9
    )
    
    small_text_left = ParagraphStyle(
        'SmallTextLeft',
        parent=styles['CenterText'],
        fontSize=8,
        leading=9,
        alignment=0  # LEFT
    )
    
    tiny_text = ParagraphStyle(
        'TinyText',
        parent=styles['CenterText'],
        fontSize=6,
        leading=7
    )
    
    tiny_text_left = ParagraphStyle(
        'TinyTextLeft',
        parent=styles['CenterText'],
        fontSize=6,
        leading=7,
        alignment=0  # LEFT
    )
    
    # Brasão da mantenedora (70% da largura anterior: 1.5cm * 0.7 = 1.05cm)
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=1.05*cm, height=0.7*cm, logo_url=logo_url)
    
    # Meses abreviados em português
    meses_pt = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    meses_abrev = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN',
                   'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']
    
    # Formatação de datas
    def format_date_short(date_str):
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{d.day} de {meses_pt[d.month - 1]}"
        except:
            return date_str
    
    def format_day_month(date_str):
        """Retorna dia na primeira linha e mês abreviado na segunda"""
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{d.day:02d}\n{meses_abrev[d.month - 1]}"
        except:
            return date_str
    
    # Dados da turma
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    periodo_texto = f"De {format_date_short(period_start)} a {format_date_short(period_end)}"
    
    turnos = {'morning': 'MATUTINO', 'afternoon': 'VESPERTINO', 'night': 'NOTURNO', 'full_time': 'INTEGRAL'}
    turno = turnos.get(class_info.get('shift', ''), class_info.get('shift', '').upper())
    
    niveis = {
        'fundamental_anos_iniciais': 'ENSINO FUNDAMENTAL - ANOS INICIAIS',
        'fundamental_anos_finais': 'ENSINO FUNDAMENTAL - ANOS FINAIS',
        'eja': 'EJA - ANOS INICIAIS',
        'eja_final': 'EJA - ANOS FINAIS',
        'educacao_infantil': 'EDUCAÇÃO INFANTIL',
        'ensino_medio': 'ENSINO MÉDIO',
        'global': 'GLOBAL'
    }
    education_level = class_info.get('education_level', '')
    nivel = niveis.get(education_level, education_level.upper())
    
    is_anos_finais = education_level in ('fundamental_anos_finais', 'eja_final')
    
    # Níveis que usam "DIAS" ao invés de "AULAS"
    is_dias = education_level in ('educacao_infantil', 'fundamental_anos_iniciais', 'eja')
    label_previstas = "DIAS PREVISTOS" if is_dias else "AULAS PREVISTAS"
    label_ministradas = "DIAS REGISTRADOS" if is_dias else "AULAS MINISTRADAS"
    
    serie = class_info.get('grade', class_info.get('grade_level', class_info.get('name', '')))
    
    # Título: se Anos Finais e tem componente, usa nome do componente
    componente_nome = ''
    titulo_frequencia = f"FREQUÊNCIA - {bimestre}º BIMESTRE DE {academic_year}"
    if is_anos_finais and course_info:
        componente_nome = course_info.get('name', '')
        titulo_frequencia = f"{componente_nome.upper()} - {bimestre}º BIMESTRE DE {academic_year}"
    
    # === CABEÇALHO ===
    header_data = []
    col1 = logo if logo else Paragraph(mant_municipio.upper(), small_text)
    header_row1 = [
        col1,
        Paragraph(f"<b>{school.get('name', 'ESCOLA').upper()}</b>", styles['CenterText']),
        Paragraph(f"<b>{titulo_frequencia}</b>", styles['CenterText'])
    ]
    header_data.append(header_row1)
    
    header_row2 = ['', Paragraph(periodo_texto, small_text), '']
    header_data.append(header_row2)
    
    header_table = Table(header_data, colWidths=[3*cm, 14*cm, 10*cm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, 0), (0, 1)),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 5))
    
    # === INFORMAÇÕES DA TURMA (4 colunas x 2 linhas) ===
    col_w = (page_width - 2*cm) / 4
    
    if is_anos_finais:
        info_data = [
            [
                Paragraph(f"<b>COMPONENTE:</b> {componente_nome}", small_text_left),
                Paragraph(f"<b>SÉRIE/ANO:</b> {serie}", small_text_left),
                Paragraph(f"<b>TURMA:</b> {class_info.get('name', '')}", small_text_left),
                Paragraph(f"<b>TURNO:</b> {turno}", small_text_left),
            ],
            [
                Paragraph(f"<b>NÍVEL:</b> {nivel}", small_text_left),
                Paragraph(f"<b>{label_previstas}:</b> {aulas_previstas}", small_text_left),
                Paragraph(f"<b>PROFESSOR(A):</b> {teacher_name}", small_text_left),
                Paragraph(f"<b>{label_ministradas}:</b> {aulas_ministradas}", small_text_left),
            ]
        ]
    else:
        info_data = [
            [
                Paragraph(f"<b>SÉRIE/ANO:</b> {serie}", small_text_left),
                Paragraph(f"<b>TURMA:</b> {class_info.get('name', '')}", small_text_left),
                Paragraph(f"<b>TURNO:</b> {turno}", small_text_left),
                Paragraph(f"<b>NÍVEL:</b> {nivel}", small_text_left),
            ],
            [
                Paragraph(f"<b>{label_previstas}:</b> {aulas_previstas}", small_text_left),
                Paragraph(f"<b>PROFESSOR(A):</b> {teacher_name}", small_text_left),
                Paragraph(f"<b>{label_ministradas}:</b> {aulas_ministradas}", small_text_left),
                '',
            ]
        ]
    
    info_table = Table(info_data, colWidths=[col_w] * 4)
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.Color(0.8, 0.8, 0.8)),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5))
    
    # === TABELA DE FREQUÊNCIA ===
    # Estilo para cabeçalho de data (dia + mês em duas linhas)
    header_date_style = ParagraphStyle(
        'HeaderDate',
        parent=styles['CenterText'],
        fontSize=5,
        leading=6,
        alignment=1  # CENTER
    )
    
    header_row = ['Nº', 'NOME']
    
    for day_str in attendance_days:
        try:
            d = datetime.strptime(day_str, '%Y-%m-%d')
            day_text = f"{d.day:02d}<br/>{d.month:02d}"
        except:
            day_text = day_str
        header_row.append(Paragraph(day_text, header_date_style))
    
    header_row.extend(['FALTAS', 'PRESEN.'])
    
    table_data = [header_row]
    
    for idx, student in enumerate(students_attendance, 1):
        row = [
            str(idx),
            Paragraph(student.get('name', '')[:40], tiny_text_left)
        ]
        
        attendance_by_date = student.get('attendance_by_date', {})
        faltas = 0
        presencas = 0
        
        for day_str in attendance_days:
            status = attendance_by_date.get(day_str, '')
            if status == 'present':
                row.append('P')
                presencas += 1
            elif status == 'absent':
                row.append('F')
                faltas += 1
            elif status == 'justified':
                row.append('J')
                presencas += 1
            else:
                row.append('')
        
        row.extend([str(faltas), str(presencas)])
        table_data.append(row)
    
    # Larguras das colunas — colunas de data ajustadas para 2 caracteres
    num_days = len(attendance_days)
    num_width = 0.6*cm
    nome_width = 5*cm
    day_width = 0.45*cm  # Largura para 2 caracteres
    falta_width = 0.9*cm
    presen_width = 0.9*cm
    
    # Verificar se cabe na página, senão reduzir proporcionalmente
    total_days_width = day_width * num_days
    available_width = page_width - 2*cm - num_width - nome_width - falta_width - presen_width
    if total_days_width > available_width:
        day_width = available_width / max(num_days, 1)
    
    col_widths = [num_width, nome_width] + [day_width] * num_days + [falta_width, presen_width]
    
    freq_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    freq_table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 5),
        
        # Corpo
        ('FONTSIZE', (0, 1), (-1, -1), 6),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Nº
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Nome à esquerda
        ('ALIGN', (2, 1), (-1, -1), 'CENTER'),  # Dias e totais
        
        # Bordas
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Espaçamento simples
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 1),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (1, 1), (1, -1), 3),  # Nomes com padding extra à esquerda
        
        # Cores alternadas
        *[('BACKGROUND', (0, i), (-1, i), colors.Color(0.97, 0.97, 0.97)) 
          for i in range(2, len(table_data), 2)],
    ]))
    
    elements.append(freq_table)
    elements.append(Spacer(1, 15))
    
    # Rodapé
    today = datetime.now()
    local_data = f"{mant_municipio} - {mantenedora.get('estado', 'PA')}, {format_date_pt(today.date())}"
    elements.append(Paragraph(local_data, small_text))
    elements.append(Spacer(1, 20))
    
    # Assinaturas
    assinatura_data = [
        ['_' * 40, '_' * 40],
        ['Assinatura do(a) Professor(a)', 'Assinatura do(a) Coordenador(a)']
    ]
    assinatura_table = Table(assinatura_data, colWidths=[12*cm, 12*cm])
    assinatura_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, 1), 5),
    ]))
    elements.append(assinatura_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

