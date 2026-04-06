"""Módulo PDF - Boletim Escolar"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from grade_calculator import calcular_resultado_final_aluno, determinar_resultado_documento, is_educacao_infantil
from pdf.utils import (
    get_logo_image, format_date_pt, get_styles, is_serie_conceitual_anos_iniciais,
    valor_para_conceito_fn as valor_para_conceito, formatar_nota_conceitual,
    ordenar_componentes_por_nivel, criar_legenda_conceitos, inferir_nivel_ensino,
    NIVEL_ENSINO_LABELS
)

def generate_boletim_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    enrollment: Dict[str, Any],
    class_info: Dict[str, Any],
    grades: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    academic_year: str,
    mantenedora: Dict[str, Any] = None,
    dias_letivos_ano: int = 200,
    calendario_letivo: Dict[str, Any] = None,
    attendance_data: Dict[str, Any] = None
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
        dias_letivos_ano: Total de dias letivos no ano (para cálculo de frequência)
        calendario_letivo: Dados do calendário letivo (para data fim do 4º bimestre)
        attendance_data: Dados de frequência do aluno
    
    Returns:
        BytesIO com o PDF gerado
    """
    from reportlab.platypus import KeepTogether
    
    # Inicializar attendance_data se não fornecido
    if attendance_data is None:
        attendance_data = {}
    
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
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.5*cm, height=3*cm, logo_url=logo_url)
    
    # Usar dados da mantenedora
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
    <font size="9"><i>Secretaria Municipal de Educação</i></font><br/>
    {slogan_html}
    """
    
    header_right = f"""
    <font size="16" color="#1e40af"><b>BOLETIM ESCOLAR</b></font><br/>
    <font size="10">{nivel_ensino_label}</font>
    """
    
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    
    if logo:
        # Layout: [Brasão | Texto Prefeitura | Título Boletim]
        header_table = Table([
            [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[3*cm, 8*cm, 7*cm])
    else:
        header_table = Table([
            [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[10.5*cm, 7.5*cm])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 10),
        ('LINEAFTER', (0, 0), (0, 0), 1, colors.black),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    
    # ===== INFORMAÇÕES DA ESCOLA E ALUNO =====
    school_name = school.get('name', 'Escola Municipal')
    grade_level = enrollment.get('student_series') or class_info.get('grade_level', 'N/A')
    class_name = class_info.get('name', 'N/A')
    student_number = enrollment.get('registration_number', student.get('enrollment_number', '1'))
    student_name = student.get('full_name', 'N/A').upper()
    
    # Linha 1: Escola, Ano Letivo e Ano/Etapa
    info_row1 = Table([
        [
            Paragraph(f"<b>Nome/escola:</b> {school_name}", ParagraphStyle('Info', fontSize=7)),
            Paragraph(f"<b>ANO LETIVO:</b> {academic_year}", ParagraphStyle('Info', fontSize=7, alignment=TA_CENTER)),
            Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", ParagraphStyle('Info', fontSize=7, alignment=TA_CENTER))
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
    
    # Linha 2: Nome do aluno e Turma
    info_row2 = Table([
        [
            Paragraph(f"<b>NOME:</b> {student_name}", ParagraphStyle('Info', fontSize=7)),
            Paragraph(f"<b>TURMA:</b> {class_name}", ParagraphStyle('Info', fontSize=7, alignment=TA_CENTER))
        ]
    ], colWidths=[10*cm, 8*cm])
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
    # As notas vêm no formato: {course_id, b1, b2, b3, b4, ...}
    grades_by_course = {}
    for grade in grades:
        course_id = grade.get('course_id')
        grades_by_course[course_id] = grade
    
    # Verificar se é Educação Infantil (avaliação conceitual)
    is_educacao_infantil = nivel_ensino == 'educacao_infantil'
    
    # Obter o grade_level do ALUNO (não da turma) para buscar carga horária por série
    # Para turmas multisseriadas, priorizar student_series da matrícula
    student_grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')
    
    # Verificar se é 1º ou 2º ano (avaliação conceitual específica)
    is_anos_iniciais_conceitual = is_serie_conceitual_anos_iniciais(student_grade_level)
    
    # Usar avaliação conceitual para Educação Infantil OU 1º/2º ano
    usa_conceito = is_educacao_infantil or is_anos_iniciais_conceitual
    
    # Cabeçalho da tabela - Modelo simplificado
    # Para Educação Infantil e 1º/2º ano, não tem coluna de Recuperação
    if usa_conceito:
        header_row1 = [
            'COMPONENTES CURRICULARES',
            'CH',
            '1º Bim.',
            '2º Bim.',
            '3º Bim.',
            '4º Bim.',
            'Faltas',
            'Conceito'
        ]
    else:
        header_row1 = [
            'COMPONENTES CURRICULARES',
            'CH',
            '1º Bim.',
            '2º Bim.',
            '3º Bim.',
            '4º Bim.',
            'Faltas',
            'Média'
        ]
    
    table_data = [header_row1]
    
    total_geral_faltas = 0
    total_carga_horaria = 0
    
    # Verificar se é escola integral
    is_escola_integral = school.get('atendimento_integral', False) if school else False
    
    # Ordenar componentes curriculares por nível de ensino
    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)
    
    for course in courses:
        course_grades = grades_by_course.get(course.get('id'), {})
        is_optativo = course.get('optativo', False)
        
        # Obter carga horária do componente - prioriza carga_horaria_por_serie
        carga_horaria_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_horaria_por_serie and student_grade_level:
            # Busca carga horária específica para a série do aluno
            carga_horaria = carga_horaria_por_serie.get(student_grade_level, course.get('workload', ''))
        else:
            carga_horaria = course.get('workload', '')
        
        if carga_horaria:
            total_carga_horaria += carga_horaria
        
        # Obter notas diretamente do registro (formato: b1, b2, b3, b4)
        n1 = course_grades.get('b1')
        n2 = course_grades.get('b2')
        n3 = course_grades.get('b3')
        n4 = course_grades.get('b4')
        
        # Obter recuperações
        rec_s1 = course_grades.get('rec_s1')
        rec_s2 = course_grades.get('rec_s2')
        
        # Aplicar lógica de recuperação do 1º semestre
        # A recuperação substitui a menor nota entre B1 e B2
        # Se as notas forem iguais, substitui a de maior peso (B2 tem peso 3)
        if rec_s1 is not None and isinstance(rec_s1, (int, float)):
            b1_val = n1 if isinstance(n1, (int, float)) else 0
            b2_val = n2 if isinstance(n2, (int, float)) else 0
            
            if b1_val < b2_val:
                # B1 é menor, substitui B1 se recuperação for maior
                if rec_s1 > b1_val:
                    n1 = rec_s1
            elif b2_val < b1_val:
                # B2 é menor, substitui B2 se recuperação for maior
                if rec_s1 > b2_val:
                    n2 = rec_s1
            else:
                # Notas iguais, substitui a de maior peso (B2 tem peso 3)
                if rec_s1 > b2_val:
                    n2 = rec_s1
        
        # Aplicar lógica de recuperação do 2º semestre
        # A recuperação substitui a menor nota entre B3 e B4
        # Se as notas forem iguais, substitui a de maior peso (B4 tem peso 3)
        if rec_s2 is not None and isinstance(rec_s2, (int, float)):
            b3_val = n3 if isinstance(n3, (int, float)) else 0
            b4_val = n4 if isinstance(n4, (int, float)) else 0
            
            if b3_val < b4_val:
                # B3 é menor, substitui B3 se recuperação for maior
                if rec_s2 > b3_val:
                    n3 = rec_s2
            elif b4_val < b3_val:
                # B4 é menor, substitui B4 se recuperação for maior
                if rec_s2 > b4_val:
                    n4 = rec_s2
            else:
                # Notas iguais, substitui a de maior peso (B4 tem peso 3)
                if rec_s2 > b4_val:
                    n4 = rec_s2
        
        # ===== FALTAS - MESMA LÓGICA DA FICHA INDIVIDUAL =====
        meta_freq = attendance_data.get('_meta', {})
        atendimento_programa = course.get('atendimento_programa')
        course_id = course.get('id')
        course_name_atual = course.get('name', 'N/A')
        
        if nivel_ensino == 'fundamental_anos_iniciais':
            # Anos Iniciais: lógica especial de exibição de faltas
            if atendimento_programa == 'atendimento_integral':
                # Componente de Escola Integral: mostrar faltas individuais
                total_faltas = meta_freq.get('faltas_por_componente', {}).get(course_id, 0)
            elif course_name_atual == 'Língua Portuguesa':
                # Língua Portuguesa: mostrar TODAS as faltas regulares
                total_faltas = meta_freq.get('faltas_regular', 0)
            else:
                # Outros componentes regulares: não mostrar faltas (só em LP)
                total_faltas = '-'
        else:
            # Outros níveis: usar faltas do attendance_data
            att = attendance_data.get(course_id, {})
            total_faltas = att.get('absences', 0)
        
        # Somar faltas para o total (apenas valores numéricos)
        if isinstance(total_faltas, (int, float)):
            total_geral_faltas += total_faltas
        
        # Calcular média/conceito
        if usa_conceito:
            # Educação Infantil ou 1º/2º ano: média é o MAIOR conceito alcançado
            valid_grades = [g for g in [n1, n2, n3, n4] if isinstance(g, (int, float))]
            if valid_grades:
                media = max(valid_grades)
                media_str = valor_para_conceito(media, student_grade_level)
            else:
                media_str = '-'
        else:
            # FÓRMULA PONDERADA: (B1×2 + B2×3 + B3×2 + B4×3) / 10
            b1_val = n1 if isinstance(n1, (int, float)) else 0
            b2_val = n2 if isinstance(n2, (int, float)) else 0
            b3_val = n3 if isinstance(n3, (int, float)) else 0
            b4_val = n4 if isinstance(n4, (int, float)) else 0
            
            total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
            media = total_pontos / 10
            media_str = f"{media:.1f}".replace('.', ',')
        
        # Formatar valores
        def fmt_grade(v):
            if usa_conceito:
                return formatar_nota_conceitual(v, is_educacao_infantil, student_grade_level) if isinstance(v, (int, float)) else (str(v) if v else '-')
            if isinstance(v, (int, float)):
                return f"{v:.1f}".replace('.', ',')
            return str(v) if v else ''
        
        def fmt_int(v):
            if v is None or v == '-':
                return '-'
            if isinstance(v, (int, float)):
                return str(int(v))
            return str(v) if v else '-'
        
        # Marcar componentes optativos com "(Optativo)"
        course_name = course.get('name', 'N/A')
        if is_optativo:
            course_name = f"{course_name} (Optativo)"
        
        course_name_p = Paragraph(course_name, ParagraphStyle('CourseName', fontSize=8, leading=10))
        
        row = [
            course_name_p,
            fmt_int(carga_horaria) if carga_horaria else '',
            fmt_grade(n1),
            fmt_grade(n2),
            fmt_grade(n3),
            fmt_grade(n4),
            fmt_int(total_faltas) if total_faltas else '',
            media_str
        ]
        table_data.append(row)
    
    # Adicionar linha de total de carga horária (todos os componentes)
    total_row = [
        'TOTAL GERAL',
        str(total_carga_horaria) if total_carga_horaria else '',
        '', '', '', '',
        str(total_geral_faltas) if total_geral_faltas else '',
        ''
    ]
    table_data.append(total_row)
    
    # Larguras das colunas (8 colunas simplificadas)
    # Total: 18cm para alinhar com a tabela de informações do aluno
    # COMPONENTES CURRICULARES: 8.6cm (aumentada para alinhar)
    col_widths = [8.6*cm, 1.0*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm]
    
    grades_table = Table(table_data, colWidths=col_widths)
    grades_table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        
        # Corpo
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        
        # Linha de total
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e5e7eb')),
        
        # Grid
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        
        # Padding
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        
        # Alternar cores das linhas (exceto total)
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fafb')]),
    ]))
    elements.append(grades_table)
    
    # ===== LEGENDA DE CONCEITOS (para Ed. Infantil e 1º/2º ano) =====
    if usa_conceito:
        legenda_elements = criar_legenda_conceitos(
            is_educacao_infantil=is_educacao_infantil,
            grade_level=student_grade_level
        )
        elements.extend(legenda_elements)
    
    elements.append(Spacer(1, 20))
    
    # ===== AJUSTAR CARGA HORÁRIA TOTAL PARA ANOS INICIAIS =====
    # Para Anos Iniciais, a carga horária total depende se é escola integral ou regular
    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            # Escola Integral: 1400 horas
            # (800h base + 600h extras: Arte/Cultura=160, Recreação=80, Tecnologia=40, Acomp.LP=160, Acomp.Mat=160)
            total_carga_horaria = 1400
        else:
            # Escola Regular: 800 horas (200 dias × 4h/dia)
            total_carga_horaria = 800
    
    # ===== RESULTADO FINAL =====
    # Obter status da matrícula e dados para cálculo do resultado
    enrollment_status = enrollment.get('status', 'active')
    grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')
    
    # Obter data fim do 4º bimestre do calendário
    data_fim_4bim = None
    if calendario_letivo:
        data_fim_4bim = calendario_letivo.get('bimestre_4_fim')
    
    # Preparar lista de médias por componente (usando fórmula ponderada com recuperação)
    medias_por_componente = []
    for course in courses:
        is_optativo = course.get('optativo', False)
        course_id = course.get('id')
        course_grades = grades_by_course.get(course_id, {})
        
        # Obter notas bimestrais
        b1 = course_grades.get('b1')
        b2 = course_grades.get('b2')
        b3 = course_grades.get('b3')
        b4 = course_grades.get('b4')
        rec_s1 = course_grades.get('rec_s1')
        rec_s2 = course_grades.get('rec_s2')
        
        # Valores para cálculo
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
        
        # Calcular média ponderada: (B1×2 + B2×3 + B3×2 + B4×3) / 10
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        # IMPORTANTE: média 0.0 é válida e deve ser tratada como reprovação
        # Só usar None quando não há nenhuma nota registrada
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
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
    
    # ===== CALCULAR FREQUÊNCIA (MESMA LÓGICA DA FICHA INDIVIDUAL) =====
    meta_freq = attendance_data.get('_meta', {})
    faltas_regular = meta_freq.get('faltas_regular', 0)
    faltas_por_componente = meta_freq.get('faltas_por_componente', {})
    total_faltas_integral = sum(faltas_por_componente.values())
    
    if nivel_ensino == 'fundamental_anos_iniciais':
        if is_escola_integral:
            # Escola Integral: 1400h
            ch_total = 1400
            horas_faltadas = (faltas_regular * 4) + total_faltas_integral
        else:
            # Escola Regular: 800h
            ch_total = 800
            horas_faltadas = faltas_regular * 4
        
        percentual_faltas = (horas_faltadas / ch_total) * 100 if ch_total > 0 else 0
        frequencia_aluno = 100 - percentual_faltas
        frequencia_aluno = max(0, min(100, frequencia_aluno))
    else:
        # Outros níveis: cálculo padrão baseado em dias letivos
        if dias_letivos_ano and dias_letivos_ano > 0 and total_geral_faltas is not None:
            dias_presentes = dias_letivos_ano - total_geral_faltas
            frequencia_aluno = (dias_presentes / dias_letivos_ano) * 100
            frequencia_aluno = max(0, frequencia_aluno)
        else:
            frequencia_aluno = None
    
    # Calcular resultado usando a nova função que considera a data do 4º bimestre
    resultado_calc = determinar_resultado_documento(
        enrollment_status=enrollment_status,
        grade_level=grade_level,
        nivel_ensino=nivel_ensino,
        data_fim_4bim=data_fim_4bim,
        medias_por_componente=medias_por_componente,
        regras_aprovacao=regras_aprovacao,
        frequencia_aluno=frequencia_aluno
    )
    
    resultado = resultado_calc['resultado']
    resultado_color = colors.HexColor(resultado_calc['cor'])
    
    # Estilos do resultado (fonte original, largura +20%)
    result_style = ParagraphStyle('Result', fontSize=12, alignment=TA_LEFT)
    result_value_style = ParagraphStyle('ResultValue', fontSize=14, alignment=TA_LEFT, textColor=resultado_color)
    
    result_table = Table([
        [
            Paragraph("<b>RESULTADO:</b>", result_style),
            Paragraph(f"<b>{resultado}</b>", result_value_style)
        ]
    ], colWidths=[3.6*cm, 14.4*cm])  # Largura da coluna RESULTADO +20% (3cm -> 3.6cm)
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

