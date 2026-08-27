"""Módulo PDF - Ficha Individual do Aluno"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from grade_calculator import determinar_resultado_documento
from pdf.utils import (
    get_logo_image, format_date_pt, get_styles, is_serie_conceitual_anos_iniciais,
    valor_para_conceito_fn as valor_para_conceito, formatar_nota_conceitual,
    ordenar_componentes_por_nivel, criar_legenda_conceitos, inferir_nivel_ensino,
    NIVEL_ENSINO_LABELS
)
from utils.client_time import local_now, local_today

_CONTINGENCY_RESULT_COLORS = {
    'CURSANDO': '#2563eb',
    'EM ANDAMENTO': '#2563eb',
    'PROMOVIDO(A)': '#16a34a',
    'CONCLUIU A ETAPA': '#16a34a',
    'APROVADO': '#16a34a',
    'APROVADO COM DEPENDÊNCIA': '#ca8a04',
    'EM DEPENDÊNCIA': '#7c3aed',
    'REPROVADO': '#dc2626',
    'REPROVADO POR FREQUÊNCIA': '#991b1b',
    'TRANSFERIDO': '#2563eb',
    'DESISTENTE': '#6b7280',
    'FALECIDO': '#6b7280',
}


def generate_ficha_individual_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    enrollment: Dict[str, Any],
    academic_year: int,
    grades: List[Dict[str, Any]] = None,
    courses: List[Dict[str, Any]] = None,
    attendance_data: Dict[str, Any] = None,
    mantenedora: Dict[str, Any] = None,
    calendario_letivo: Dict[str, Any] = None,
    resultado_override: str | None = None,
    data_emissao_override: date | None = None,
) -> BytesIO:
    """
    Gera a Ficha Individual do Aluno em PDF - Modelo Floresta do Araguaia.

    ``resultado_override`` e ``data_emissao_override`` existem exclusivamente para
    emissão documental de contingência. Quando ambos são ``None`` o fluxo oficial
    permanece idêntico ao comportamento histórico.
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
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.5*cm, height=3*cm, logo_url=logo_url)

    # Usar cidade/estado da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')

    # ===== DETERMINAR NÍVEL DE ENSINO =====
    # Mapa de níveis para exibição
    NIVEL_ENSINO_LABELS = {
        'educacao_infantil': 'EDUCAÇÃO INFANTIL',
        'fundamental_anos_iniciais': 'ENSINO FUNDAMENTAL',
        'fundamental_anos_finais': 'ENSINO FUNDAMENTAL',
        'ensino_medio': 'ENSINO MÉDIO',
        'eja': 'EJA - ANOS INICIAIS',
        'eja_final': 'EJA - ANOS FINAIS',
        'global': 'GLOBAL'
    }

    # Inferir nível de ensino da turma
    # Nota: O campo pode ser 'nivel_ensino' ou 'education_level' dependendo da versão
    nivel_ensino = class_info.get('nivel_ensino') or class_info.get('education_level')
    # Para turmas multisseriadas, usar student_series da matrícula do aluno
    grade_level = (enrollment.get('student_series') or class_info.get('grade_level', '')).lower()

    # Se não tem nivel_ensino definido, inferir pelo grade_level
    if not nivel_ensino:
        if any(x in grade_level for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
            nivel_ensino = 'educacao_infantil'
        elif any(x in grade_level for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
            nivel_ensino = 'fundamental_anos_iniciais'
        elif any(x in grade_level for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
            nivel_ensino = 'fundamental_anos_finais'
        elif any(x in grade_level for x in ['eja', 'etapa']):
            if any(x in grade_level for x in ['3', '4', 'final']):
                nivel_ensino = 'eja_final'
            else:
                nivel_ensino = 'eja'
        else:
            nivel_ensino = 'fundamental_anos_iniciais'  # Fallback

    nivel_ensino_label = NIVEL_ENSINO_LABELS.get(nivel_ensino, 'ENSINO FUNDAMENTAL')

    # Buscar slogan da mantenedora
    slogan = mantenedora.get('slogan', '') if mantenedora else ''
    slogan_html = f'<font size="8" color="#666666">"{slogan}"</font>' if slogan else ''

    header_text = f"""
    <font size="11"><b>{mant_nome.upper()}</b></font><br/>
    <font size="9"><i>{mantenedora.get('secretaria', 'Secretaria Municipal de Educação')}</i></font><br/>
    {slogan_html}
    """

    header_right = f"""
    <font size="14" color="#1e40af"><b>FICHA INDIVIDUAL</b></font><br/>
    <font size="10">{nivel_ensino_label}</font>
    """

    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)

    if logo:
        # Layout: [Brasão | Texto Prefeitura | Título Ficha]
        header_table = Table([
            [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[3*cm, 9*cm, 7*cm])
    else:
        header_table = Table([
            [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[10*cm, 9*cm])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (1, 0), (1, 0), 10),
        ('LINEAFTER', (0, 0), (0, 0), 1, colors.black),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 5))

    # ===== INFORMAÇÕES DO ALUNO E ESCOLA =====
    school_name = school.get('name', 'Escola Municipal')
    if school.get('tipo_unidade') == 'anexa' and school.get('anexa_a'):
        school_name = f"{school_name} - ANEXA A {school.get('anexa_a')}"
    grade_level = enrollment.get('student_series') or class_info.get('grade_level', 'N/A')
    class_name = class_info.get('name', 'N/A')

    TURNOS_PT = {
        'morning': 'Matutino',
        'afternoon': 'Vespertino',
        'evening': 'Noturno',
        'full_time': 'Integral',
        'night': 'Noturno'
    }
    shift_raw = class_info.get('shift', 'N/A')
    shift = TURNOS_PT.get(shift_raw, shift_raw)

    student_name = student.get('full_name', 'N/A').upper()
    student_sex = student.get('sex', 'N/A')
    inep_number = student.get('inep_code', student.get('inep_number', 'N/A'))

    birth_date = student.get('birth_date', 'N/A')
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = bd.strftime('%d/%m/%Y')
        except Exception:
            pass

    def get_course_workload(course, grade_level):
        carga_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_por_serie and grade_level:
            return carga_por_serie.get(grade_level, course.get('carga_horaria', course.get('workload', 80)))
        return course.get('carga_horaria', course.get('workload', 80))

    is_escola_integral = school.get('atendimento_integral', False) if school else False

    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            total_carga_horaria = 1400
        else:
            total_carga_horaria = 800
    else:
        total_carga_horaria = sum(get_course_workload(c, grade_level) for c in courses) if courses else 1200

    dias_letivos = 200
    if calendario_letivo:
        calc = calendario_letivo.get('dias_letivos_calculados')
        if calc and isinstance(calc, (int, float)) and calc > 0:
            dias_letivos = int(calc)
        else:
            dias_letivos = calendario_letivo.get('dias_letivos_previstos', 200) or 200

    meta_freq = attendance_data.get('_meta', {})
    faltas_regular = meta_freq.get('faltas_regular', 0)
    faltas_por_componente = meta_freq.get('faltas_por_componente', {})

    carga_regular = 0
    carga_integral = 0
    for course in courses:
        atendimento = course.get('atendimento_programa')
        ch = get_course_workload(course, grade_level) or 0
        if atendimento == 'atendimento_integral':
            carga_integral += ch
        else:
            carga_regular += ch

    total_faltas_integral = sum(faltas_por_componente.values())

    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            horas_faltadas = (faltas_regular * 4) + total_faltas_integral
            percentual_faltas = (horas_faltadas / total_carga_horaria) * 100 if total_carga_horaria > 0 else 0
            frequencia_anual = 100 - percentual_faltas
        else:
            horas_faltadas = faltas_regular * 4
            percentual_faltas = (horas_faltadas / total_carga_horaria) * 100 if total_carga_horaria > 0 else 0
            frequencia_anual = 100 - percentual_faltas
    else:
        freq_total = 0
        freq_count = 0
        for course in courses:
            course_id = course.get('id')
            att = attendance_data.get(course_id, {})
            if att.get('frequency_percentage') is not None:
                freq_total += att.get('frequency_percentage', 100)
                freq_count += 1
        frequencia_anual = freq_total / freq_count if freq_count > 0 else 100.0

    frequencia_anual = max(0, min(100, frequencia_anual))

    info_style = ParagraphStyle('InfoStyle', fontSize=7, leading=9)
    info_style_bold = ParagraphStyle('InfoStyleBold', fontSize=7, leading=9, fontName='Helvetica-Bold')

    info_row1 = Table([
        [
            Paragraph(f"<b>NOME DA ESCOLA:</b> {school_name}", info_style),
            Paragraph(f"<b>ANO LETIVO:</b> {academic_year}", info_style),
        ]
    ], colWidths=[16.0*cm, 3.0*cm])
    info_row1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row1)

    info_row2 = Table([
        [
            Paragraph(f"<b>NOME DO ESTUDANTE:</b> {student_name}", info_style),
            Paragraph(f"<b>SEXO:</b> {student_sex}", info_style),
            Paragraph(f"<b>Nº INEP:</b> {inep_number}", info_style),
        ]
    ], colWidths=[13.0*cm, 2.5*cm, 3.5*cm])
    info_row2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row2)

    info_row3 = Table([
        [
            Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", info_style),
            Paragraph(f"<b>TURMA:</b> {class_name}", info_style),
            Paragraph(f"<b>TURNO:</b> {shift}", info_style),
            Paragraph(f"<b>C.H.:</b> {total_carga_horaria}h", info_style),
            Paragraph(f"<b>DIAS LET.:</b> {dias_letivos}", info_style),
            Paragraph(f"<b>NASC.:</b> {birth_date}", info_style),
        ]
    ], colWidths=[3.5*cm, 6.0*cm, 2.5*cm, 2.0*cm, 2.5*cm, 2.5*cm])
    info_row3.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_row3)

    freq_style = ParagraphStyle('FreqStyle', fontSize=8, alignment=TA_RIGHT)
    elements.append(Paragraph(f"<b>FREQUÊNCIA ANUAL: {frequencia_anual:.2f}%</b>", freq_style))
    elements.append(Spacer(1, 8))

    grades_by_course = {}
    for grade in grades:
        course_id = grade.get('course_id')
        grades_by_course[course_id] = grade

    is_educacao_infantil = nivel_ensino == 'educacao_infantil'
    is_anos_iniciais_conceitual = is_serie_conceitual_anos_iniciais(grade_level)
    usa_conceito = is_educacao_infantil or is_anos_iniciais_conceitual

    if usa_conceito:
        header_row1 = [
            'COMPONENTES\nCURRICULARES',
            'C.H.',
            '1º Bim.',
            '2º Bim.',
            '3º Bim.',
            '4º Bim.',
            'CONCEITO\nFINAL',
            'FALTAS',
            '%\nFREQ'
        ]
        table_data = [header_row1]
    else:
        header_row1 = [
            'COMPONENTES\nCURRICULARES',
            'C.H.',
            '1º SEMESTRE', '', '',
            '2º SEMESTRE', '', '',
            'PROC. PONDERADO', '', '', '',
            'TOTAL\nPONTOS',
            'MÉDIA\nANUAL',
            'FALTAS',
            '%\nFREQ'
        ]
        header_row2 = [
            '', '',
            '1º', '2º', 'REC',
            '3º', '4º', 'REC',
            '1ºx2', '2ºx3', '3ºx2', '4ºx3',
            '', '', '', ''
        ]
        table_data = [header_row1, header_row2]

    def fmt_grade(v):
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
        return str(v) if v else '-'

    def fmt_grade_conceitual(v, gl=None):
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return valor_para_conceito(v, gl)
        return str(v) if v else '-'

    def fmt_int(v):
        if v is None or v == '-':
            return '-'
        if isinstance(v, (int, float)):
            return str(int(v))
        return str(v) if v else '-'

    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)
    student_grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')

    for course in courses:
        course_id = course.get('id')
        course_name = course.get('name', 'N/A')
        is_optativo = course.get('optativo', False)

        carga_horaria_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_horaria_por_serie and student_grade_level:
            carga_horaria = carga_horaria_por_serie.get(student_grade_level, course.get('carga_horaria', course.get('workload', 80)))
        else:
            carga_horaria = course.get('carga_horaria', course.get('workload', 80))

        if is_optativo:
            course_name = f"{course_name} (Optativo)"

        course_name_p = Paragraph(course_name, ParagraphStyle('CourseName', fontSize=8, leading=10))
        grade = grades_by_course.get(course_id, {})
        b1 = grade.get('b1')
        b2 = grade.get('b2')
        b3 = grade.get('b3')
        b4 = grade.get('b4')

        att = attendance_data.get(course_id, {})
        atendimento_programa = course.get('atendimento_programa')

        if nivel_ensino == 'fundamental_anos_iniciais':
            if atendimento_programa == 'atendimento_integral':
                total_faltas = meta_freq.get('faltas_por_componente', {}).get(course_id, 0)
            elif course_name == 'Língua Portuguesa':
                total_faltas = meta_freq.get('faltas_regular', 0)
            else:
                total_faltas = '-'
        else:
            total_faltas = att.get('absences', 0)

        if nivel_ensino == 'fundamental_anos_iniciais':
            freq_componente_str = '-'
        else:
            freq_componente = att.get('frequency_percentage', 100.0)
            freq_componente_str = f"{freq_componente:.2f}".replace('.', ',')

        if usa_conceito:
            valid_grades = [g for g in [b1, b2, b3, b4] if isinstance(g, (int, float))]
            if valid_grades:
                conceito_final = valor_para_conceito(max(valid_grades), student_grade_level)
            else:
                conceito_final = '-'

            row = [
                course_name_p,
                str(carga_horaria),
                fmt_grade_conceitual(b1, student_grade_level),
                fmt_grade_conceitual(b2, student_grade_level),
                fmt_grade_conceitual(b3, student_grade_level),
                fmt_grade_conceitual(b4, student_grade_level),
                conceito_final,
                fmt_int(total_faltas),
                freq_componente_str
            ]
        else:
            rec_s1 = grade.get('rec_s1', grade.get('recovery'))
            rec_s2 = grade.get('rec_s2')

            b1_orig = b1
            b2_orig = b2
            b3_orig = b3
            b4_orig = b4

            b1_calc = b1 if isinstance(b1, (int, float)) else 0
            b2_calc = b2 if isinstance(b2, (int, float)) else 0
            b3_calc = b3 if isinstance(b3, (int, float)) else 0
            b4_calc = b4 if isinstance(b4, (int, float)) else 0

            if rec_s1 is not None and isinstance(rec_s1, (int, float)):
                if b1_calc < b2_calc:
                    if rec_s1 > b1_calc:
                        b1_calc = rec_s1
                elif b2_calc < b1_calc:
                    if rec_s1 > b2_calc:
                        b2_calc = rec_s1
                else:
                    if rec_s1 > b2_calc:
                        b2_calc = rec_s1

            if rec_s2 is not None and isinstance(rec_s2, (int, float)):
                if b3_calc < b4_calc:
                    if rec_s2 > b3_calc:
                        b3_calc = rec_s2
                elif b4_calc < b3_calc:
                    if rec_s2 > b4_calc:
                        b4_calc = rec_s2
                else:
                    if rec_s2 > b4_calc:
                        b4_calc = rec_s2

            b1_pond = b1_calc * 2
            b2_pond = b2_calc * 3
            b3_pond = b3_calc * 2
            b4_pond = b4_calc * 3

            total_pontos = b1_pond + b2_pond + b3_pond + b4_pond
            media_anual = total_pontos / 10 if total_pontos > 0 else 0

            row = [
                course_name_p,
                str(carga_horaria),
                fmt_grade(b1_orig), fmt_grade(b2_orig), fmt_grade(rec_s1),
                fmt_grade(b3_orig), fmt_grade(b4_orig), fmt_grade(rec_s2),
                fmt_grade(b1_pond), fmt_grade(b2_pond), fmt_grade(b3_pond), fmt_grade(b4_pond),
                fmt_grade(total_pontos),
                fmt_grade(media_anual),
                fmt_int(total_faltas),
                freq_componente_str
            ]
        table_data.append(row)

    if usa_conceito:
        col_widths = [
            7.5*cm,
            1.0*cm,
            1.5*cm,
            1.5*cm,
            1.5*cm,
            1.5*cm,
            1.5*cm,
            1.0*cm,
            1.5*cm
        ]
    else:
        col_widths = [
            6.75*cm,
            0.75*cm,
            0.75*cm, 0.75*cm, 0.75*cm,
            0.75*cm, 0.75*cm, 0.75*cm,
            0.85*cm, 0.85*cm, 0.85*cm, 0.85*cm,
            1.0*cm,
            0.95*cm,
            0.85*cm,
            1.0*cm
        ]

    grades_table = Table(table_data, colWidths=col_widths)

    if usa_conceito:
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]
    else:
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 1), 6),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#eff6ff')),
            ('SPAN', (0, 0), (0, 1)),
            ('SPAN', (1, 0), (1, 1)),
            ('SPAN', (2, 0), (4, 0)),
            ('SPAN', (5, 0), (7, 0)),
            ('SPAN', (8, 0), (11, 0)),
            ('SPAN', (12, 0), (12, 1)),
            ('SPAN', (13, 0), (13, 1)),
            ('SPAN', (14, 0), (14, 1)),
            ('SPAN', (15, 0), (15, 1)),
            ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 2), (-1, -1), 7),
            ('ALIGN', (1, 2), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 2), (0, -1), 'LEFT'),
            ('VALIGN', (0, 2), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]

    grades_table.setStyle(TableStyle(style_commands))
    elements.append(grades_table)

    if usa_conceito:
        legenda_elements = criar_legenda_conceitos(
            is_educacao_infantil=is_educacao_infantil,
            grade_level=student_grade_level
        )
        elements.extend(legenda_elements)

    elements.append(Spacer(1, 5))

    enrollment_status = enrollment.get('status', 'active')
    _student_status = (student.get('status') or '').lower()
    _STUDENT_TERMINAL = {'transferred', 'transferido', 'transferencia',
                         'dropout', 'desistente', 'desistencia',
                         'deceased', 'falecido', 'falecimento'}
    if _student_status in _STUDENT_TERMINAL:
        enrollment_status = _student_status

    calendario_letivo = calendario_letivo or {}
    data_fim_4bim = calendario_letivo.get('bimestre_4_fim')

    medias_por_componente = []
    for course in courses:
        is_optativo = course.get('optativo', False)
        course_id = course.get('id')
        grade = grades_by_course.get(course_id, {})
        b1 = grade.get('b1')
        b2 = grade.get('b2')
        b3 = grade.get('b3')
        b4 = grade.get('b4')
        rec_s1 = grade.get('rec_s1')
        rec_s2 = grade.get('rec_s2')

        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0

        if rec_s1 is not None and isinstance(rec_s1, (int, float)):
            if b1_val < b2_val:
                if rec_s1 > b1_val:
                    b1_val = rec_s1
            elif b2_val < b1_val:
                if rec_s1 > b2_val:
                    b2_val = rec_s1
            else:
                if rec_s1 > b2_val:
                    b2_val = rec_s1

        if rec_s2 is not None and isinstance(rec_s2, (int, float)):
            if b3_val < b4_val:
                if rec_s2 > b3_val:
                    b3_val = rec_s2
            elif b4_val < b3_val:
                if rec_s2 > b4_val:
                    b4_val = rec_s2
            else:
                if rec_s2 > b4_val:
                    b4_val = rec_s2

        valid_grades = [g for g in [b1, b2, b3, b4] if isinstance(g, (int, float))]
        if valid_grades:
            total = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
            media = total / 10
        else:
            media = None

        has_b4 = b4 is not None
        has_all_bims = all(g is not None for g in [b1, b2, b3, b4])
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])

        medias_por_componente.append({
            'nome': course.get('name', 'N/A'),
            'media': media,
            'optativo': is_optativo,
            'atendimento_programa': course.get('atendimento_programa') or '',
            'has_b4': has_b4,
            'has_all_bims': has_all_bims,
            'has_any_grade': has_any_grade
        })

    regras_aprovacao = {
        'media_aprovacao': mantenedora.get('media_aprovacao', 5.0) if mantenedora else 5.0,
        'frequencia_minima': mantenedora.get('frequencia_minima', 75.0) if mantenedora else 75.0,
        'aprovacao_com_dependencia': mantenedora.get('aprovacao_com_dependencia', False) if mantenedora else False,
        'max_componentes_dependencia': mantenedora.get('max_componentes_dependencia') if mantenedora else None,
        'cursar_apenas_dependencia': mantenedora.get('cursar_apenas_dependencia', False) if mantenedora else False,
        'qtd_componentes_apenas_dependencia': mantenedora.get('qtd_componentes_apenas_dependencia') if mantenedora else None,
    }

    resultado_calc = determinar_resultado_documento(
        enrollment_status=enrollment_status,
        grade_level=grade_level,
        nivel_ensino=nivel_ensino,
        data_fim_4bim=data_fim_4bim,
        medias_por_componente=medias_por_componente,
        regras_aprovacao=regras_aprovacao,
        frequencia_aluno=frequencia_anual
    )

    if resultado_override is None:
        resultado = resultado_calc['resultado']
        resultado_color = colors.HexColor(resultado_calc['cor'])
    else:
        resultado = str(resultado_override).strip().upper()
        override_color = _CONTINGENCY_RESULT_COLORS.get(resultado)
        if override_color is None:
            raise ValueError(f"Resultado de contingência inválido: {resultado}")
        resultado_color = colors.HexColor(override_color)

    obs_style = ParagraphStyle('ObsStyle', fontSize=7, fontName='Helvetica-Oblique')
    result_style = ParagraphStyle('ResultStyle', fontSize=10, alignment=TA_CENTER)

    obs_result_table = Table([
        [
            Paragraph("Este Documento não possui emendas nem rasuras.", obs_style),
            Table([
                [
                    Paragraph(f"<b>RESULTADO:</b>", result_style),
                    Paragraph(f"<b><font color='{resultado_color.hexval()}'>{resultado}</font></b>", result_style)
                ]
            ], colWidths=[3.5*cm, 5*cm])
        ]
    ], colWidths=[10.5*cm, 8.5*cm])
    obs_result_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOX', (1, 0), (1, 0), 1, colors.black),
    ]))
    elements.append(obs_result_table)
    elements.append(Spacer(1, 10))

    emission_date = data_emissao_override or local_today()
    today = format_date_pt(emission_date)
    city = mant_municipio
    state = mant_estado

    date_style = ParagraphStyle('DateStyle', fontSize=8, alignment=TA_LEFT)
    elements.append(Paragraph(f"{city} - {state}, {today}.", date_style))
    elements.append(Spacer(1, 5))

    obs_line_style = ParagraphStyle('ObsLineStyle', fontSize=8)
    elements.append(Paragraph("<b>OBS.:</b> _______________________________________________", obs_line_style))
    elements.append(Spacer(1, 15))

    sig_data = [
        ['_' * 30, '_' * 30],
        ['SECRETÁRIO(A)', 'DIRETOR(A)']
    ]

    sig_table = Table(sig_data, colWidths=[9*cm, 9*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 1), (-1, 1), 3),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
