"""Módulo PDF - Detalhes da Turma"""
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from xml.sax.saxutils import escape as xml_escape
from pdf.utils import get_logo_image

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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from xml.sax.saxutils import escape as xml_escape

    buffer = BytesIO()

    # Cores do tema
    PRIMARY = colors.HexColor('#1e3a5f')
    PRIMARY_LIGHT = colors.HexColor('#e8edf3')
    ACCENT = colors.HexColor('#2563eb')
    SECTION_BG = colors.HexColor('#1e3a5f')
    ROW_ALT = colors.HexColor('#f8fafc')
    BORDER = colors.HexColor('#cbd5e1')
    TEXT_DARK = colors.HexColor('#1e293b')
    TEXT_MUTED = colors.HexColor('#64748b')

    page_width = A4[0]
    usable_width = page_width - 3*cm  # margens

    def footer_handler(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(TEXT_MUTED)
        today = datetime.now().strftime('%d/%m/%Y às %H:%M')
        canvas.drawString(1.5*cm, 1*cm, f"Documento gerado em {today}")
        canvas.drawRightString(page_width - 1.5*cm, 1*cm, f"Página {doc.page}")
        # Linha fina no footer
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(1.5*cm, 1.3*cm, page_width - 1.5*cm, 1.3*cm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=0.75*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    elements = []

    # ===== CABEÇALHO =====
    logo = None
    if mantenedora and mantenedora.get('brasao_url'):
        logo = get_logo_image(width=2*cm, height=2*cm, logo_url=mantenedora.get('brasao_url'))
    if not logo and mantenedora and mantenedora.get('logotipo_url'):
        logo = get_logo_image(width=2*cm, height=2*cm, logo_url=mantenedora.get('logotipo_url'))
    if not logo:
        logo = get_logo_image(width=2*cm, height=2*cm)

    mantenedora_nome = mantenedora.get('nome', 'Secretaria Municipal de Educação') if mantenedora else 'Secretaria Municipal de Educação'
    school_name = xml_escape(school.get('name', 'Escola'))

    header_style = ParagraphStyle('HeaderInst', fontSize=9, alignment=TA_CENTER, leading=13, textColor=TEXT_DARK)

    header_text = f"""<b>{xml_escape(mantenedora_nome.upper())}</b><br/>
    {xml_escape((mantenedora.get('secretaria', 'Secretaria Municipal de Educação') if mantenedora else 'Secretaria Municipal de Educação').upper())}<br/>
    <b>{school_name}</b>"""

    if logo:
        header_data = [[logo, Paragraph(header_text, header_style)]]
        header_table = Table(header_data, colWidths=[2.5*cm, usable_width - 2.5*cm])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(header_table)
    else:
        elements.append(Paragraph(header_text, header_style))

    # Linha divisória
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceAfter=8))

    # ===== TÍTULO =====
    title_style = ParagraphStyle('DocTitle', fontSize=13, alignment=TA_CENTER, textColor=PRIMARY, fontName='Helvetica-Bold', spaceAfter=4)
    elements.append(Paragraph(f"DETALHES DA TURMA", title_style))

    class_name = xml_escape(class_info.get('name', ''))
    subtitle_style = ParagraphStyle('DocSubtitle', fontSize=11, alignment=TA_CENTER, textColor=ACCENT, fontName='Helvetica-Bold', spaceAfter=12)
    elements.append(Paragraph(class_name, subtitle_style))

    # ===== HELPER: Cabeçalho de seção =====
    def section_header(text):
        s = ParagraphStyle('SectionHdr', fontSize=9, fontName='Helvetica-Bold', textColor=colors.white, leading=12)
        data = [[Paragraph(text, s)]]
        t = Table(data, colWidths=[usable_width])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), SECTION_BG),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('ROUNDEDCORNERS', [3, 3, 0, 0]),
        ]))
        return t

    # ===== DADOS DA TURMA =====
    elements.append(section_header("DADOS DA TURMA"))

    education_levels = {
        'educacao_infantil': 'Educação Infantil',
        'fundamental_anos_iniciais': 'Ens. Fundamental - Anos Iniciais',
        'fundamental_anos_finais': 'Ens. Fundamental - Anos Finais',
        'eja': 'EJA - Anos Iniciais',
        'eja_final': 'EJA - Anos Finais',
        'ensino_medio': 'Ensino Médio',
        'global': 'Global'
    }
    shifts = {
        'morning': 'Manhã', 'afternoon': 'Tarde',
        'evening': 'Noite', 'full_time': 'Integral'
    }
    atendimentos = {
        'regular': 'Regular', 'atendimento_integral': 'Escola Integral',
        'aee': 'AEE', '': '-'
    }

    label_style = ParagraphStyle('LabelCell', fontSize=8, fontName='Helvetica-Bold', textColor=TEXT_DARK)
    value_style = ParagraphStyle('ValueCell', fontSize=8.5, textColor=TEXT_DARK)

    def make_field(label, value):
        return [Paragraph(label, label_style), Paragraph(xml_escape(str(value or '-')), value_style)]

    nivel = education_levels.get(class_info.get('education_level') or class_info.get('nivel_ensino', ''), class_info.get('education_level', '-'))
    turno = shifts.get(class_info.get('shift'), class_info.get('shift', '-'))
    atendimento = atendimentos.get(class_info.get('atendimento_programa', ''), class_info.get('atendimento_programa', '-'))

    fields_data = [
        make_field('Nome:', class_info.get('name', '-')) + make_field('Ano Letivo:', str(class_info.get('academic_year', '-'))),
        make_field('Escola:', school.get('name', '-')) + make_field('Turno:', turno),
        make_field('Nível de Ensino:', nivel) + make_field('Série/Etapa:', class_info.get('grade_level', '-')),
        make_field('Atendimento:', atendimento) + make_field('Alunos Matriculados:', str(len(students))),
    ]

    col_w = [2.8*cm, 5.8*cm, 2.8*cm, usable_width - 11.4*cm]
    fields_table = Table(fields_data, colWidths=col_w)
    fields_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), PRIMARY_LIGHT),
        ('BACKGROUND', (2, 0), (2, -1), PRIMARY_LIGHT),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(fields_table)
    elements.append(Spacer(1, 12))

    # ===== PROFESSORES =====
    elements.append(section_header("PROFESSOR(ES) ALOCADO(S)"))

    th_style = ParagraphStyle('THCell', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_LEFT)
    td_style = ParagraphStyle('TDCell', fontSize=8, textColor=TEXT_DARK, leading=10)

    if teachers:
        t_header = [
            Paragraph('Nome', th_style),
            Paragraph('Componente Curricular', th_style),
            Paragraph('Celular', th_style)
        ]
        t_data = [t_header]
        for teacher in teachers:
            t_data.append([
                Paragraph(xml_escape(teacher.get('nome', '-')), td_style),
                Paragraph(xml_escape(teacher.get('componente', '-') or '-'), td_style),
                Paragraph(xml_escape(teacher.get('celular', '-') or '-'), td_style)
            ])

        t_table = Table(t_data, colWidths=[6*cm, usable_width - 10*cm, 4*cm])
        t_styles = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(t_data)):
            if i % 2 == 0:
                t_styles.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
        t_table.setStyle(TableStyle(t_styles))
        elements.append(t_table)
    else:
        no_data_style = ParagraphStyle('NoData', fontSize=9, textColor=TEXT_MUTED, alignment=TA_CENTER)
        elements.append(Paragraph("Nenhum professor alocado", no_data_style))

    elements.append(Spacer(1, 12))

    # ===== ALUNOS MATRICULADOS =====
    elements.append(section_header(f"ALUNOS MATRICULADOS ({len(students)})"))

    if students:
        s_header = [
            Paragraph('#', ParagraphStyle('THNum', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER)),
            Paragraph('Aluno(a)', th_style),
            Paragraph('Data Nasc.', th_style),
            Paragraph('Responsável', th_style),
            Paragraph('Celular', th_style)
        ]
        s_data = [s_header]

        for idx, student in enumerate(students, 1):
            birth_date = student.get('birth_date', '')
            if birth_date:
                try:
                    if isinstance(birth_date, str) and '-' in birth_date:
                        parts = birth_date.split('T')[0].split('-')
                        if len(parts) == 3:
                            birth_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
                except:
                    pass

            num_style = ParagraphStyle('TDNum', fontSize=8, textColor=TEXT_DARK, alignment=TA_CENTER)
            s_data.append([
                Paragraph(str(idx), num_style),
                Paragraph(xml_escape(student.get('full_name', '-')), td_style),
                Paragraph(xml_escape(str(birth_date or '-')), td_style),
                Paragraph(xml_escape(student.get('guardian_name', '-') or '-'), td_style),
                Paragraph(xml_escape(student.get('guardian_phone', '-') or '-'), td_style)
            ])

        s_table = Table(s_data, colWidths=[1*cm, 6*cm, 2.2*cm, usable_width - 12.8*cm, 2.6*cm], repeatRows=1)
        s_styles = [
            ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(s_data)):
            if i % 2 == 0:
                s_styles.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
        s_table.setStyle(TableStyle(s_styles))
        elements.append(s_table)
    else:
        no_data_style = ParagraphStyle('NoData2', fontSize=9, textColor=TEXT_MUTED, alignment=TA_CENTER)
        elements.append(Paragraph("Nenhum aluno matriculado", no_data_style))

    # Gerar PDF
    doc.build(elements, onFirstPage=footer_handler, onLaterPages=footer_handler)
    buffer.seek(0)
    return buffer

