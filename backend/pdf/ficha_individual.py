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
    calendario_letivo: Dict[str, Any] = None
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
        calendario_letivo: Dados do calendário letivo (para data fim do 4º bimestre)
    
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
    grade_level = enrollment.get('student_series') or class_info.get('grade_level', 'N/A')
    class_name = class_info.get('name', 'N/A')
    
    # Mapeamento de turnos para português
    TURNOS_PT = {
        'morning': 'Matutino',
        'afternoon': 'Vespertino',
        'evening': 'Noturno',
        'full_time': 'Integral',
        'night': 'Noturno'
    }
    shift_raw = class_info.get('shift', 'N/A')
    shift = TURNOS_PT.get(shift_raw, shift_raw)  # Traduz ou mantém o valor original
    
    student_name = student.get('full_name', 'N/A').upper()
    student_sex = student.get('sex', 'N/A')
    inep_number = student.get('inep_code', student.get('inep_number', 'N/A'))
    
    # Formatar data de nascimento
    birth_date = student.get('birth_date', 'N/A')
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = bd.strftime('%d/%m/%Y')
        except:
            pass
    
    # Carga horária total da turma - considerando carga_horaria_por_serie e escola integral
    def get_course_workload(course, grade_level):
        """Obtém a carga horária de um componente considerando a série do aluno"""
        carga_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_por_serie and grade_level:
            return carga_por_serie.get(grade_level, course.get('carga_horaria', course.get('workload', 80)))
        return course.get('carga_horaria', course.get('workload', 80))
    
    # Verificar se é escola integral
    is_escola_integral = school.get('atendimento_integral', False) if school else False
    
    # Calcular carga horária total baseada no nível de ensino e tipo de escola
    # Para Anos Iniciais:
    # - Escola Regular: 800 horas (200 dias × 4h)
    # - Escola Integral: 1400 horas (800h base + 600h componentes extras)
    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            # Escola Integral: soma todos os componentes (base + extras)
            # Base: 800h (Língua Portuguesa, Arte, Ed. Física, Matemática, Ciências, História, Geografia, Ens. Religioso, Ed. Ambiental)
            # Extras: 600h (Arte e Cultura=160, Recreação=80, Tecnologia=40, Acomp. LP=160, Acomp. Mat=160)
            total_carga_horaria = 1400
        else:
            # Escola Regular: 800 horas
            total_carga_horaria = 800
    else:
        # Para outros níveis, soma a carga horária dos componentes
        total_carga_horaria = sum(get_course_workload(c, grade_level) for c in courses) if courses else 1200
    
    # Buscar dias letivos do calendário (calculados a partir dos períodos bimestrais)
    dias_letivos = 200  # Valor padrão
    if calendario_letivo:
        # Priorizar dias_letivos_calculados (soma dos bimestres), senão usar dias_letivos_previstos
        dias_letivos = calendario_letivo.get('dias_letivos_calculados') or calendario_letivo.get('dias_letivos_previstos', 200)
    
    # ===== CÁLCULO DE FREQUÊNCIA PARA ANOS INICIAIS =====
    # Obter metadados de frequência
    meta_freq = attendance_data.get('_meta', {})
    faltas_regular = meta_freq.get('faltas_regular', 0)
    faltas_por_componente = meta_freq.get('faltas_por_componente', {})
    
    # Calcular carga horária por tipo (Regular vs Escola Integral)
    carga_regular = 0
    carga_integral = 0
    for course in courses:
        atendimento = course.get('atendimento_programa')
        ch = get_course_workload(course, grade_level)
        if atendimento == 'atendimento_integral':
            carga_integral += ch
        else:
            carga_regular += ch
    
    # Somar faltas dos componentes integrais
    total_faltas_integral = sum(faltas_por_componente.values())
    
    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            # ESCOLA INTEGRAL:
            # Fórmula: ((Faltas Regular × 4) + Faltas Integral) / CH Total × 100 = % FALTAS
            # CH Total = carga_regular (800) + carga_integral (600) = 1400
            horas_faltadas = (faltas_regular * 4) + total_faltas_integral
            percentual_faltas = (horas_faltadas / total_carga_horaria) * 100 if total_carga_horaria > 0 else 0
            frequencia_anual = 100 - percentual_faltas
        else:
            # ESCOLA REGULAR:
            # Fórmula: (Faltas × 4 / CH Total) × 100 = % FALTAS
            # CH Total = 800
            horas_faltadas = faltas_regular * 4
            percentual_faltas = (horas_faltadas / total_carga_horaria) * 100 if total_carga_horaria > 0 else 0
            frequencia_anual = 100 - percentual_faltas
    else:
        # Outros níveis - frequência padrão
        freq_total = 0
        freq_count = 0
        for course in courses:
            course_id = course.get('id')
            att = attendance_data.get(course_id, {})
            if att.get('frequency_percentage') is not None:
                freq_total += att.get('frequency_percentage', 100)
                freq_count += 1
        frequencia_anual = freq_total / freq_count if freq_count > 0 else 100.0
    
    # Garantir que frequência não seja negativa
    frequencia_anual = max(0, min(100, frequencia_anual))
    
    # Linha 1: Escola, Nome do Aluno
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
    
    # Linha 2: Nome aluno, sexo, INEP
    info_row2 = Table([
        [
            Paragraph(f"<b>NOME DO(A) ALUNO(A):</b> {student_name}", info_style),
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
    
    # Verificar se é Educação Infantil (avaliação conceitual)
    is_educacao_infantil = nivel_ensino == 'educacao_infantil'
    
    # Verificar se é 1º ou 2º ano (avaliação conceitual específica)
    is_anos_iniciais_conceitual = is_serie_conceitual_anos_iniciais(grade_level)
    
    # Usar avaliação conceitual para Educação Infantil OU 1º/2º ano
    usa_conceito = is_educacao_infantil or is_anos_iniciais_conceitual
    
    if usa_conceito:
        # EDUCAÇÃO INFANTIL ou 1º/2º ANO: Tabela simplificada com conceitos
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
        # OUTROS NÍVEIS: Tabela completa com processo ponderado
        # Cabeçalho da tabela de notas - Modelo Ficha Individual
        # Estrutura: Componente | CH | 1º Sem (1º, 2º, Rec) | 2º Sem (3º, 4º, Rec) | Resultado (1ºx2, 2ºx3, 3ºx2, 4ºx3, Total, Média, Faltas, %Freq)
        
        # Cabeçalho principal (primeira linha)
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
        
        # Cabeçalho secundário (segunda linha)
        header_row2 = [
            '', '',
            '1º', '2º', 'REC',
            '3º', '4º', 'REC',
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
    
    def fmt_grade_conceitual(v, gl=None):
        """Formata nota como conceito para Educação Infantil ou 1º/2º Ano"""
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return valor_para_conceito(v, gl)
        return str(v) if v else '-'
    
    def fmt_int(v):
        """Formata número inteiro"""
        if v is None or v == '-':
            return '-'
        if isinstance(v, (int, float)):
            return str(int(v))
        return str(v) if v else '-'
    
    # Ordenar componentes curriculares por nível de ensino
    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)
    
    # Obter o grade_level do ALUNO para buscar carga horária por série
    # Para turmas multisseriadas, priorizar student_series da matrícula
    student_grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')
    
    for course in courses:
        course_id = course.get('id')
        course_name = course.get('name', 'N/A')
        is_optativo = course.get('optativo', False)
        
        # Obter carga horária - prioriza carga_horaria_por_serie baseado na série do aluno
        carga_horaria_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_horaria_por_serie and student_grade_level:
            carga_horaria = carga_horaria_por_serie.get(student_grade_level, course.get('carga_horaria', course.get('workload', 80)))
        else:
            carga_horaria = course.get('carga_horaria', course.get('workload', 80))
        
        if is_optativo:
            course_name = f"{course_name} (Optativo)"
        
        course_name_p = Paragraph(course_name, ParagraphStyle('CourseName', fontSize=8, leading=10))
        
        grade = grades_by_course.get(course_id, {})
        
        # Notas bimestrais
        b1 = grade.get('b1')
        b2 = grade.get('b2')
        b3 = grade.get('b3')
        b4 = grade.get('b4')
        
        # Faltas - Lógica especial para Anos Iniciais
        att = attendance_data.get(course_id, {})
        atendimento_programa = course.get('atendimento_programa')
        
        if nivel_ensino == 'fundamental_anos_iniciais':
            # Anos Iniciais: lógica especial de exibição de faltas
            if atendimento_programa == 'atendimento_integral':
                # Componente de Escola Integral: mostrar faltas individuais
                total_faltas = meta_freq.get('faltas_por_componente', {}).get(course_id, 0)
            elif course_name == 'Língua Portuguesa':
                # Língua Portuguesa: mostrar TODAS as faltas regulares
                total_faltas = meta_freq.get('faltas_regular', 0)
            else:
                # Outros componentes regulares: não mostrar faltas (só em LP)
                total_faltas = '-'
        else:
            # Outros níveis: usar faltas do attendance_data
            total_faltas = att.get('absences', 0)
        
        # Frequência do componente
        # Para Anos Iniciais, a frequência é exibida apenas no campo "FREQUÊNCIA ANUAL"
        # Na coluna % FREQ, mostrar apenas "-"
        if nivel_ensino == 'fundamental_anos_iniciais':
            freq_componente_str = '-'
        else:
            freq_componente = att.get('frequency_percentage', 100.0)
            freq_componente_str = f"{freq_componente:.2f}".replace('.', ',')
        
        if usa_conceito:
            # EDUCAÇÃO INFANTIL ou 1º/2º ANO: Conceitos e maior conceito como média
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
            # OUTROS NÍVEIS: Processo ponderado completo
            # Recuperações por semestre
            rec_s1 = grade.get('rec_s1', grade.get('recovery'))
            rec_s2 = grade.get('rec_s2')
            
            # Valores originais para exibição
            b1_orig = b1
            b2_orig = b2
            b3_orig = b3
            b4_orig = b4
            
            # Valores para cálculo (após aplicar recuperação)
            b1_calc = b1 if isinstance(b1, (int, float)) else 0
            b2_calc = b2 if isinstance(b2, (int, float)) else 0
            b3_calc = b3 if isinstance(b3, (int, float)) else 0
            b4_calc = b4 if isinstance(b4, (int, float)) else 0
            
            # Aplicar lógica de recuperação do 1º semestre
            # A recuperação substitui a menor nota entre B1 e B2
            # Se as notas forem iguais, substitui a de maior peso (B2 tem peso 3)
            if rec_s1 is not None and isinstance(rec_s1, (int, float)):
                if b1_calc < b2_calc:
                    # B1 é menor, substitui B1 se recuperação for maior
                    if rec_s1 > b1_calc:
                        b1_calc = rec_s1
                elif b2_calc < b1_calc:
                    # B2 é menor, substitui B2 se recuperação for maior
                    if rec_s1 > b2_calc:
                        b2_calc = rec_s1
                else:
                    # Notas iguais, substitui a de maior peso (B2 tem peso 3)
                    if rec_s1 > b2_calc:
                        b2_calc = rec_s1
            
            # Aplicar lógica de recuperação do 2º semestre
            # A recuperação substitui a menor nota entre B3 e B4
            # Se as notas forem iguais, substitui a de maior peso (B4 tem peso 3)
            if rec_s2 is not None and isinstance(rec_s2, (int, float)):
                if b3_calc < b4_calc:
                    # B3 é menor, substitui B3 se recuperação for maior
                    if rec_s2 > b3_calc:
                        b3_calc = rec_s2
                elif b4_calc < b3_calc:
                    # B4 é menor, substitui B4 se recuperação for maior
                    if rec_s2 > b4_calc:
                        b4_calc = rec_s2
                else:
                    # Notas iguais, substitui a de maior peso (B4 tem peso 3)
                    if rec_s2 > b4_calc:
                        b4_calc = rec_s2
            
            # Processo ponderado (com notas já substituídas pela recuperação)
            b1_pond = b1_calc * 2
            b2_pond = b2_calc * 3
            b3_pond = b3_calc * 2
            b4_pond = b4_calc * 3
            
            # Total de pontos e média
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
    
    # Larguras das colunas
    if usa_conceito:
        # Educação Infantil: 9 colunas - Total: 19cm
        col_widths = [
            7.5*cm,   # Componente
            1.0*cm,   # CH
            1.5*cm,   # 1º Bim
            1.5*cm,   # 2º Bim
            1.5*cm,   # 3º Bim
            1.5*cm,   # 4º Bim
            1.5*cm,   # Conceito Final
            1.0*cm,   # Faltas
            1.5*cm    # %Freq
        ]
    else:
        # Outros níveis: 16 colunas - Total: 19cm
        col_widths = [
            6.75*cm,  # Componente (mantido)
            0.75*cm,  # CH
            0.75*cm, 0.75*cm, 0.75*cm,  # 1º Sem (1º, 2º, REC)
            0.75*cm, 0.75*cm, 0.75*cm,  # 2º Sem (3º, 4º, REC)
            0.85*cm, 0.85*cm, 0.85*cm, 0.85*cm,  # Proc. Pond.
            1.0*cm,   # Total
            0.95*cm,  # Média
            0.85*cm,  # Faltas
            1.0*cm    # %Freq
        ]
    
    grades_table = Table(table_data, colWidths=col_widths)
    
    # Estilo da tabela - diferente para conceitual vs notas
    if usa_conceito:
        # Educação Infantil: tabela simples sem merge de cabeçalho
        style_commands = [
            # Cabeçalho
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            
            # Corpo da tabela
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            
            # Padding
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            
            # Alternar cores das linhas
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]
    else:
        # Outros níveis: tabela completa com merge de cabeçalho
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
            ('SPAN', (2, 0), (4, 0)),  # 1º Semestre (3 colunas)
            ('SPAN', (5, 0), (7, 0)),  # 2º Semestre (3 colunas)
            ('SPAN', (8, 0), (11, 0)),  # Proc. Ponderado (4 colunas)
            ('SPAN', (12, 0), (12, 1)),  # Total
            ('SPAN', (13, 0), (13, 1)),  # Média
            ('SPAN', (14, 0), (14, 1)),  # Faltas
            ('SPAN', (15, 0), (15, 1)),  # %Freq
            
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
    
    # ===== LEGENDA DE CONCEITOS (para Ed. Infantil e 1º/2º ano) =====
    if usa_conceito:
        legenda_elements = criar_legenda_conceitos(
            is_educacao_infantil=is_educacao_infantil,
            grade_level=student_grade_level
        )
        elements.extend(legenda_elements)
    
    elements.append(Spacer(1, 5))
    
    # ===== CALCULAR RESULTADO =====
    # Obter status da matrícula e dados para cálculo do resultado
    enrollment_status = enrollment.get('status', 'active')
    
    # Obter data fim do 4º bimestre do calendário
    calendario_letivo = calendario_letivo or {}
    data_fim_4bim = calendario_letivo.get('bimestre_4_fim')
    
    # Preparar lista de médias por componente
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
        
        # Valores para cálculo (aplicando recuperação)
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        # Aplicar lógica de recuperação do 1º semestre
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
        
        # Aplicar lógica de recuperação do 2º semestre
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
        
        # Verificar se tem notas válidas
        valid_grades = [g for g in [b1, b2, b3, b4] if isinstance(g, (int, float))]
        
        # Calcular média do componente (média ponderada com notas após recuperação)
        if valid_grades:
            total = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
            media = total / 10
        else:
            media = None
        
        medias_por_componente.append({
            'nome': course.get('name', 'N/A'),
            'media': media,
            'optativo': is_optativo
        })
    
    # Extrair regras de aprovação da mantenedora
    regras_aprovacao = {
        'media_aprovacao': mantenedora.get('media_aprovacao', 5.0) if mantenedora else 5.0,
        'frequencia_minima': mantenedora.get('frequencia_minima', 75.0) if mantenedora else 75.0,
        'aprovacao_com_dependencia': mantenedora.get('aprovacao_com_dependencia', False) if mantenedora else False,
        'max_componentes_dependencia': mantenedora.get('max_componentes_dependencia') if mantenedora else None,
        'cursar_apenas_dependencia': mantenedora.get('cursar_apenas_dependencia', False) if mantenedora else False,
        'qtd_componentes_apenas_dependencia': mantenedora.get('qtd_componentes_apenas_dependencia') if mantenedora else None,
    }
    
    # Calcular resultado usando a nova função que considera a data do 4º bimestre
    resultado_calc = determinar_resultado_documento(
        enrollment_status=enrollment_status,
        grade_level=grade_level,
        nivel_ensino=nivel_ensino,
        data_fim_4bim=data_fim_4bim,
        medias_por_componente=medias_por_componente,
        regras_aprovacao=regras_aprovacao,
        frequencia_aluno=frequencia_anual
    )
    
    resultado = resultado_calc['resultado']
    resultado_color = colors.HexColor(resultado_calc['cor'])
    
    # ===== LINHA COM OBSERVAÇÃO E RESULTADO =====
    obs_style = ParagraphStyle('ObsStyle', fontSize=7, fontName='Helvetica-Oblique')
    result_style = ParagraphStyle('ResultStyle', fontSize=10, alignment=TA_CENTER)
    
    # Tabela com observação à esquerda e resultado à direita
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
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

