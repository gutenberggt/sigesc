"""Módulo PDF - Objetos de Conhecimento"""
from io import BytesIO
from datetime import datetime, date
from collections import OrderedDict
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as canvas_module
from pdf.utils import get_logo_image, format_date_pt, get_styles

def generate_learning_objects_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    records: List[Dict[str, Any]],
    bimestre: int,
    academic_year: int,
    period_start: str,
    period_end: str,
    teacher_name: str = "",
    mantenedora: Dict[str, Any] = None,
    dias_previstos: int = 0
) -> BytesIO:
    """Gera PDF do relatório de Objetos de Conhecimento por bimestre"""
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
    
    def safe(val, default=''):
        if val is None:
            return default
        return str(val)
    
    page_width = A4[0] - 3*cm  # largura útil
    
    # Estilos
    info_style = ParagraphStyle('LOInfo', fontSize=8, leading=10, alignment=0)
    content_style = ParagraphStyle('LOContent', fontSize=8, leading=10, alignment=0)
    content_bold = ParagraphStyle('LOContentBold', fontSize=8, leading=10, alignment=0, fontName='Helvetica-Bold')
    small_center = ParagraphStyle('LOSmallCenter', fontSize=8, leading=10, alignment=1)
    
    meses_pt = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    
    def fmt_date(date_str):
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{d.day} de {meses_pt[d.month - 1]} de {d.year}"
        except:
            return date_str
    
    # Ajuste #6: Formato de data DD/MM (sem ano)
    def fmt_date_short(date_str):
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{d.day:02d}/{d.month:02d}"
        except:
            return date_str
    
    # Tradução de nível e turno
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
    
    education_level = class_info.get('education_level', '')
    nivel = niveis.get(education_level, education_level)
    turno = turnos.get(class_info.get('shift', ''), class_info.get('shift', ''))
    serie = class_info.get('grade', class_info.get('grade_level', class_info.get('name', '')))
    is_infantil = education_level == 'educacao_infantil'
    is_dias = education_level in ('educacao_infantil', 'fundamental_anos_iniciais', 'eja')
    label_componente = 'Campo de Experiência' if is_infantil else 'Componente Curricular'
    
    # Totais para o cabeçalho
    total_registros = len(records)
    dates_aulas = {}
    for r in sorted(records, key=lambda x: safe(x.get('date'))):
        dt = safe(r.get('date'))
        if dt not in dates_aulas:
            dates_aulas[dt] = r.get('number_of_classes', 1) or 1
    total_aulas = sum(dates_aulas.values())
    dias_registrados = len(dates_aulas)  # Cada data única = 1 dia registrado
    
    # === CABEÇALHO INSTITUCIONAL (Ajuste #1: Brasão maior, posicionado à esquerda) ===
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.5*cm, height=2.8*cm, logo_url=logo_url)
    
    mant_nome = mantenedora.get('nome', '')
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    
    header_right_html = (
        f"<b>{safe(mant_nome)}</b><br/>"
        f"{school.get('name', '').upper()}<br/><br/>"
        f"<b><font size=\"12\">REGISTRO DE OBJETOS DE CONHECIMENTO</font></b><br/>"
        f"{bimestre}º Bimestre - Ano Letivo {academic_year}<br/>"
        f"Período: {fmt_date(period_start)} a {fmt_date(period_end)}"
    )
    header_text_style = ParagraphStyle('LOHeaderRight', fontSize=9, leading=12, alignment=TA_CENTER)
    
    if logo:
        header_data = [[logo, Paragraph(header_right_html, header_text_style)]]
        header_table = Table(header_data, colWidths=[3.5*cm, page_width - 3.5*cm])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
    else:
        header_data = [[Paragraph(header_right_html, header_text_style)]]
        header_table = Table(header_data, colWidths=[page_width])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    
    # === INFORMAÇÕES DA TURMA ===
    col_w = page_width / 4
    if is_dias:
        # Anos Iniciais / Ed. Infantil: "Dias Previstos" e "Dias Registrados"
        info_data = [
            [
                Paragraph(f"<b>Turma:</b> {safe(class_info.get('name'))}", info_style),
                Paragraph(f"<b>Série/Ano:</b> {safe(serie)}", info_style),
                Paragraph(f"<b>Turno:</b> {safe(turno)}", info_style),
                Paragraph(f"<b>Nível:</b> {safe(nivel)}", info_style),
            ],
            [
                Paragraph(f"<b>Professor(a):</b> {safe(teacher_name)}", info_style),
                '',
                Paragraph(f"<b>Dias Previstos:</b> {dias_previstos}", info_style),
                Paragraph(f"<b>Dias Registrados:</b> {dias_registrados}", info_style),
            ]
        ]
    else:
        # Anos Finais / EJA: manter original
        info_data = [
            [
                Paragraph(f"<b>Turma:</b> {safe(class_info.get('name'))}", info_style),
                Paragraph(f"<b>Série/Ano:</b> {safe(serie)}", info_style),
                Paragraph(f"<b>Turno:</b> {safe(turno)}", info_style),
                Paragraph(f"<b>Nível:</b> {safe(nivel)}", info_style),
            ],
            [
                Paragraph(f"<b>Professor(a):</b> {safe(teacher_name)}", info_style),
                '',
                Paragraph(f"<b>Total de Registros:</b> {total_registros}", info_style),
                Paragraph(f"<b>Total de Aulas:</b> {total_aulas}", info_style),
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
        # Ajuste #4 e #5: Mesclar células abaixo de Turma e Série/Ano para Professor(a)
        ('SPAN', (0, 1), (1, 1)),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    # === TABELA DE CONTEÚDOS (agrupado por data) ===
    if is_dias:
        # Anos Iniciais / Ed. Infantil: 4 colunas (sem AULAS), COMPONENTE mais larga
        table_header = [
            Paragraph('<b>DATA</b>', small_center),
            Paragraph(f'<b>{label_componente.upper()}</b>', content_bold),
            Paragraph('<b>CONTEÚDO / OBJETO DE CONHECIMENTO</b>', content_bold),
            Paragraph('<b>PRÁTICAS PEDAGÓGICAS</b>', content_bold),
        ]
    else:
        # Anos Finais / EJA: 5 colunas (com AULAS)
        table_header = [
            Paragraph('<b>DATA</b>', small_center),
            Paragraph(f'<b>{label_componente.upper()}</b>', content_bold),
            Paragraph('<b>CONTEÚDO / OBJETO DE CONHECIMENTO</b>', content_bold),
            Paragraph('<b>PRÁTICAS PEDAGÓGICAS</b>', content_bold),
            Paragraph('<b>AULAS</b>', small_center),
        ]
    
    table_data = [table_header]
    
    # Agrupar registros por data em ordem cronológica
    from collections import OrderedDict
    records_by_date = OrderedDict()
    for r in sorted(records, key=lambda x: safe(x.get('date'))):
        dt = safe(r.get('date'))
        if dt not in records_by_date:
            records_by_date[dt] = []
        records_by_date[dt].append(r)
    
    for dt, day_records in records_by_date.items():
        # 1. Enumerar componentes
        componentes = []
        for i, r in enumerate(day_records, 1):
            componentes.append(f"{i}. {safe(r.get('course_name', ''), '-')}")
        
        # 2. Conteúdos únicos (sem repetir)
        seen_conteudos = []
        for r in day_records:
            c = safe(r.get('content', ''), '').strip()
            if c and c not in seen_conteudos:
                seen_conteudos.append(c)
        
        # 3. Metodologias únicas (sem repetir)
        seen_metodologias = []
        for r in day_records:
            m = safe(r.get('methodology', ''), '').strip()
            if m and m not in seen_metodologias:
                seen_metodologias.append(m)
        
        # 4. Aulas: valor registrado (não soma dos componentes)
        aulas_dia = day_records[0].get('number_of_classes', 1) or 1
        
        if is_dias:
            # Sem coluna AULAS
            row = [
                Paragraph(fmt_date_short(dt), small_center),
                Paragraph('<br/>'.join(componentes), content_style),
                Paragraph('<br/>'.join(seen_conteudos) if seen_conteudos else '-', content_style),
                Paragraph('<br/>'.join(seen_metodologias) if seen_metodologias else '-', content_style),
            ]
        else:
            row = [
                Paragraph(fmt_date_short(dt), small_center),
                Paragraph('<br/>'.join(componentes), content_style),
                Paragraph('<br/>'.join(seen_conteudos) if seen_conteudos else '-', content_style),
                Paragraph('<br/>'.join(seen_metodologias) if seen_metodologias else '-', content_style),
                Paragraph(str(aulas_dia), small_center),
            ]
        table_data.append(row)
    
    if len(table_data) == 1:
        empty_cols = 4 if is_dias else 5
        empty_row = [''] * empty_cols
        empty_row[2] = Paragraph('Nenhum registro encontrado para este bimestre.', content_style)
        table_data.append(empty_row)
    
    # Larguras das colunas
    is_anos_iniciais = education_level == 'fundamental_anos_iniciais'
    if is_dias:
        # Anos Iniciais / Ed. Infantil: 4 colunas (sem AULAS)
        conteudo_original = page_width - 9.5*cm
        conteudo_w_full = conteudo_original * 0.75
        metodologia_w_full = 3*cm + conteudo_original * 0.25
        
        conteudo_w = conteudo_w_full * (2/3)
        metodologia_w = metodologia_w_full * (2/3)
        # Espaço extra: 1/3 de cada coluna + coluna AULAS (1.5cm)
        extra = (conteudo_w_full - conteudo_w) + (metodologia_w_full - metodologia_w) + 1.5*cm
        componente_w = 3.5*cm + extra
        
        if is_anos_iniciais:
            # Anos Iniciais: COMPONENTE reduzida a 2/3, o 1/3 vai para CONTEÚDO
            reducao = componente_w * (1/3)
            componente_w = componente_w * (2/3)
            conteudo_w = conteudo_w + reducao
        
        col_widths = [1.5*cm, componente_w, conteudo_w, metodologia_w]
    else:
        # Anos Finais / EJA: 5 colunas (com AULAS) - layout original
        conteudo_original = page_width - 9.5*cm
        conteudo_w = conteudo_original * 0.75
        metodologia_w = 3*cm + conteudo_original * 0.25
        col_widths = [1.5*cm, 3.5*cm, conteudo_w, metodologia_w, 1.5*cm]
    
    content_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    content_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.5)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        *[('BACKGROUND', (0, i), (-1, i), colors.Color(0.97, 0.97, 0.97))
          for i in range(2, len(table_data), 2)],
    ]))
    
    elements.append(content_table)
    elements.append(Spacer(1, 20))
    
    # === RODAPÉ: Local, data e assinaturas ===
    today = datetime.now()
    elements.append(Paragraph(
        f"{mant_municipio} - {mant_estado}, {format_date_pt(today.date())}",
        small_center
    ))
    elements.append(Spacer(1, 30))
    
    sig_data = [
        ['_' * 45, '_' * 45],
        [
            Paragraph('Professor(a)', small_center),
            Paragraph('Coordenador(a) Pedagógico(a)', small_center)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[page_width / 2] * 2)
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
    ]))
    elements.append(sig_table)
    
    # Ajuste #10: Numeração de página "Página X de Y"
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
                self.drawCentredString(
                    A4[0] / 2,
                    1 * cm,
                    f"Página {i + 1} de {num_pages}"
                )
                canvas_module.Canvas.showPage(self)
            canvas_module.Canvas.save(self)
    
    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer

