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
import logging
from grade_calculator import calcular_resultado_final_aluno, determinar_resultado_documento, is_educacao_infantil

logger = logging.getLogger(__name__)
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


# Ordem personalizada dos componentes curriculares para Educação Infantil
ORDEM_COMPONENTES_EDUCACAO_INFANTIL = [
    "O eu, o outro e nós",
    "Corpo, gestos e movimentos",
    "Escuta, fala, pensamento e imaginação",
    "Traço, sons, cores e formas",
    "Traços, sons, cores e formas",  # Variação do nome
    "Espaços, tempos, quantidades, relações e transformações",
    "Educação Ambiental e Clima",
    "Contação de Histórias e Iniciação Musical",
    "Arte e Cultura",
    "Higiene e Saúde",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Recreação, Esporte e Lazer",  # Variação do nome
]

# ===== ORDEM DOS COMPONENTES - ENSINO FUNDAMENTAL ANOS INICIAIS =====
ORDEM_COMPONENTES_ANOS_INICIAIS = [
    "Língua Portuguesa",
    "Arte",
    "Arte e Cultura",
    "Educação Física",
    "Matemática",
    "Ciências",
    "História",
    "Geografia",
    "Ensino Religioso",
    "Recreação, Esporte e Lazer",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Tecnologia e Informática",
    "Acompanhamento Pedagógico de Língua Portuguesa",
    "Acomp. Ped. de Língua Portuguesa",
    "Acompanhamento Pedagógico de Matemática",
    "Acomp. Ped. de Matemática",
    "Educação Ambiental e Clima",
]

# ===== ORDEM DOS COMPONENTES - ENSINO FUNDAMENTAL ANOS FINAIS =====
ORDEM_COMPONENTES_ANOS_FINAIS = [
    "Língua Portuguesa",
    "Arte",
    "Arte e Cultura",
    "Educação Física",
    "Língua Inglesa",
    "Língua inglesa",  # Variação do nome (minúscula)
    "Inglês",  # Variação do nome
    "Matemática",
    "Ciências",
    "História",
    "Geografia",
    "Ensino Religioso",
    "Estudos Amazônicos",
    "Literatura e Redação",
    "Recreação, Esporte e Lazer",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Tecnologia e Informática",
    "Acompanhamento Pedagógico de Língua Portuguesa",
    "Acomp. Ped. de Língua Portuguesa",
    "Acompanhamento Pedagógico de Matemática",
    "Acomp. Ped. de Matemática",
    "Educação Ambiental e Clima",
]

# ===== SISTEMA DE AVALIAÇÃO CONCEITUAL - EDUCAÇÃO INFANTIL =====
# Conceitos e seus valores numéricos
CONCEITOS_EDUCACAO_INFANTIL = {
    'OD': {'valor': 10.0, 'descricao': 'Objetivo Desenvolvido'},
    'DP': {'valor': 7.5, 'descricao': 'Desenvolvido Parcialmente'},
    'ND': {'valor': 5.0, 'descricao': 'Não Desenvolvido'},
    'NT': {'valor': 0.0, 'descricao': 'Não Trabalhado'},
}

# Mapeamento inverso: valor para conceito
VALOR_PARA_CONCEITO = {
    10.0: 'OD',
    7.5: 'DP',
    5.0: 'ND',
    0.0: 'NT',
}

def valor_para_conceito(valor):
    """Converte um valor numérico para o conceito correspondente."""
    if valor is None:
        return '-'
    # Encontrar o conceito mais próximo
    for v, conceito in sorted(VALOR_PARA_CONCEITO.items(), reverse=True):
        if valor >= v:
            return conceito
    return 'NT'

def conceito_para_valor(conceito):
    """Converte um conceito para seu valor numérico."""
    if conceito in CONCEITOS_EDUCACAO_INFANTIL:
        return CONCEITOS_EDUCACAO_INFANTIL[conceito]['valor']
    return None

def calcular_media_conceitual(notas):
    """
    Calcula a média conceitual para Educação Infantil.
    A média é o MAIOR conceito alcançado nos 4 bimestres.
    """
    valores_validos = []
    for nota in notas:
        if nota is not None and isinstance(nota, (int, float)) and nota > 0:
            valores_validos.append(nota)
        elif isinstance(nota, str) and nota in CONCEITOS_EDUCACAO_INFANTIL:
            valores_validos.append(CONCEITOS_EDUCACAO_INFANTIL[nota]['valor'])
    
    if valores_validos:
        return max(valores_validos)  # Maior conceito alcançado
    return None

def formatar_nota_conceitual(valor, is_educacao_infantil=False):
    """
    Formata uma nota. Se for Educação Infantil, retorna o conceito.
    Caso contrário, retorna o valor numérico formatado.
    """
    if valor is None:
        return '-'
    if is_educacao_infantil:
        return valor_para_conceito(valor)
    if isinstance(valor, (int, float)):
        return f"{valor:.1f}".replace('.', ',')
    return str(valor) if valor else '-'

def ordenar_componentes_educacao_infantil(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena os componentes curriculares da Educação Infantil na ordem específica definida.
    Componentes não listados aparecem no final, em ordem alfabética.
    """
    def get_ordem(course):
        nome = course.get('name', '')
        # Procurar o nome na lista de ordem (ignorando case e variações)
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_EDUCACAO_INFANTIL):
            if nome_ordem.lower() in nome.lower() or nome.lower() in nome_ordem.lower():
                return i
        # Se não encontrar, colocar no final (ordem alfabética)
        return len(ORDEM_COMPONENTES_EDUCACAO_INFANTIL) + ord(nome[0].lower()) if nome else 999
    
    return sorted(courses, key=get_ordem)


def ordenar_componentes_anos_iniciais(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena os componentes curriculares do Ensino Fundamental Anos Iniciais na ordem específica definida.
    Componentes não listados aparecem no final, em ordem alfabética.
    """
    def get_ordem(course):
        nome = course.get('name', '').strip()
        nome_lower = nome.lower()
        
        # Primeiro, tentar match exato (ignorando case)
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_ANOS_INICIAIS):
            if nome_ordem.lower() == nome_lower:
                return i
        
        # Se não houver match exato, procurar match parcial
        # Mas apenas se o nome da lista estiver completamente contido no nome do componente
        # e o nome do componente não for significativamente maior
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_ANOS_INICIAIS):
            if nome_ordem.lower() == nome_lower:
                return i
        
        # Se não encontrar, colocar no final (ordem alfabética)
        return len(ORDEM_COMPONENTES_ANOS_INICIAIS) + ord(nome[0].lower()) if nome else 999
    
    return sorted(courses, key=get_ordem)


def ordenar_componentes_anos_finais(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena os componentes curriculares do Ensino Fundamental Anos Finais na ordem específica definida.
    Componentes não listados aparecem no final, em ordem alfabética.
    """
    def get_ordem(course):
        nome = course.get('name', '').strip()
        nome_lower = nome.lower()
        
        # Match exato (ignorando case)
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_ANOS_FINAIS):
            if nome_ordem.lower() == nome_lower:
                return i
        
        # Se não encontrar, colocar no final (ordem alfabética)
        return len(ORDEM_COMPONENTES_ANOS_FINAIS) + ord(nome[0].lower()) if nome else 999
    
    return sorted(courses, key=get_ordem)


def ordenar_componentes_por_nivel(courses: List[Dict[str, Any]], nivel_ensino: str) -> List[Dict[str, Any]]:
    """
    Ordena os componentes curriculares de acordo com o nível de ensino.
    """
    if nivel_ensino == 'educacao_infantil':
        return ordenar_componentes_educacao_infantil(courses)
    elif nivel_ensino == 'fundamental_anos_iniciais':
        return ordenar_componentes_anos_iniciais(courses)
    elif nivel_ensino == 'fundamental_anos_finais':
        return ordenar_componentes_anos_finais(courses)
    else:
        # Para outros níveis (EJA, etc.), ordenar alfabeticamente
        return sorted(courses, key=lambda x: x.get('name', ''))


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
    calendario_letivo: Dict[str, Any] = None
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
    
    # ===== DETERMINAR NÍVEL DE ENSINO =====
    # Mapa de níveis para exibição
    NIVEL_ENSINO_LABELS = {
        'educacao_infantil': 'EDUCAÇÃO INFANTIL',
        'fundamental_anos_iniciais': 'ENSINO FUNDAMENTAL - ANOS INICIAIS',
        'fundamental_anos_finais': 'ENSINO FUNDAMENTAL - ANOS FINAIS',
        'ensino_medio': 'ENSINO MÉDIO',
        'eja': 'EJA - ANOS INICIAIS',
        'eja_final': 'EJA - ANOS FINAIS'
    }
    
    # Inferir nível de ensino da turma
    nivel_ensino = class_info.get('nivel_ensino')
    grade_level = class_info.get('grade_level', '').lower()
    
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
    <b>{mant_nome}</b><br/>
    <font size="9">Secretaria Municipal de Educação</font><br/>
    {slogan_html}
    """
    
    header_right = f"""
    <font size="16" color="#1e40af"><b>BOLETIM ESCOLAR</b></font><br/>
    <font size="10">{nivel_ensino_label}</font>
    """
    
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    
    if logo:
        # Coluna do nível de ensino (header_right): 7.5cm
        header_table = Table([
            [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[3.2*cm, 7.3*cm, 7.5*cm])
    else:
        header_table = Table([
            [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
        ], colWidths=[10.5*cm, 7.5*cm])
    
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
    
    # Cabeçalho da tabela - Modelo simplificado
    # Para Educação Infantil, não tem coluna de Recuperação
    if is_educacao_infantil:
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
    
    # Ordenar componentes curriculares por nível de ensino
    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)
    
    # Obter o grade_level original (não lowercase) para buscar carga horária por série
    student_grade_level = class_info.get('grade_level', '')
    
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
        n1 = course_grades.get('b1', '')
        n2 = course_grades.get('b2', '')
        n3 = course_grades.get('b3', '')
        n4 = course_grades.get('b4', '')
        
        # Obter faltas - não temos faltas por período no formato atual
        # TODO: Integrar com sistema de frequência quando disponível
        total_faltas = 0
        
        total_geral_faltas += total_faltas
        
        # Calcular média/conceito
        valid_grades = []
        for g in [n1, n2, n3, n4]:
            if isinstance(g, (int, float)):
                valid_grades.append(g)
        
        if is_educacao_infantil:
            # Educação Infantil: média é o MAIOR conceito alcançado
            if valid_grades:
                media = max(valid_grades)
                media_str = valor_para_conceito(media)
            else:
                media_str = '-'
        else:
            # Outros níveis: média aritmética
            if valid_grades:
                media = sum(valid_grades) / len(valid_grades)
                media_str = f"{media:.1f}"
            else:
                media_str = ''
        
        # Formatar valores
        def fmt_grade(v):
            if is_educacao_infantil:
                return formatar_nota_conceitual(v, True) if isinstance(v, (int, float)) else (str(v) if v else '-')
            if isinstance(v, (int, float)):
                return f"{v:.1f}"
            return str(v) if v else ''
        
        def fmt_int(v):
            if isinstance(v, (int, float)):
                return str(int(v))
            return str(v) if v else ''
        
        # Marcar componentes optativos com "(Optativo)"
        course_name = course.get('name', 'N/A')
        if is_optativo:
            course_name = f"{course_name} (Optativo)"
        
        row = [
            course_name,
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
    elements.append(Spacer(1, 20))
    
    # ===== RESULTADO FINAL =====
    # Obter status da matrícula e dados para cálculo do resultado
    enrollment_status = enrollment.get('status', 'active')
    grade_level = class_info.get('grade_level', '')
    
    # Obter data fim do 4º bimestre do calendário
    data_fim_4bim = None
    if calendario_letivo:
        data_fim_4bim = calendario_letivo.get('bimestre_4_fim')
    
    # Preparar lista de médias por componente
    medias_por_componente = []
    for course in courses:
        is_optativo = course.get('optativo', False)
        course_grades = grades_by_course.get(course.get('id'), {})
        valid_grades = []
        for period in ['P1', 'P2', 'P3', 'P4']:
            g = course_grades.get(period, {}).get('grade')
            if isinstance(g, (int, float)):
                valid_grades.append(g)
        
        # Calcular média do componente
        media = sum(valid_grades) / len(valid_grades) if valid_grades else None
        
        medias_por_componente.append({
            'nome': course.get('name', 'N/A'),
            'media': media,
            'optativo': is_optativo
        })
    
    # Extrair regras de aprovação da mantenedora
    regras_aprovacao = {
        'media_aprovacao': mantenedora.get('media_aprovacao', 6.0) if mantenedora else 6.0,
        'frequencia_minima': mantenedora.get('frequencia_minima', 75.0) if mantenedora else 75.0,
        'aprovacao_com_dependencia': mantenedora.get('aprovacao_com_dependencia', False) if mantenedora else False,
        'max_componentes_dependencia': mantenedora.get('max_componentes_dependencia') if mantenedora else None,
        'cursar_apenas_dependencia': mantenedora.get('cursar_apenas_dependencia', False) if mantenedora else False,
        'qtd_componentes_apenas_dependencia': mantenedora.get('qtd_componentes_apenas_dependencia') if mantenedora else None,
    }
    
    # Calcular frequência do aluno baseada nos dias letivos e faltas
    frequencia_aluno = None
    if dias_letivos_ano and dias_letivos_ano > 0 and total_geral_faltas is not None:
        dias_presentes = dias_letivos_ano - total_geral_faltas
        frequencia_aluno = (dias_presentes / dias_letivos_ano) * 100
        # Garantir que a frequência não seja negativa
        frequencia_aluno = max(0, frequencia_aluno)
    
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
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.4*cm, height=1.6*cm, logo_url=logo_url)
    
    # Usar cidade/estado da mantenedora
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    
    # ===== DETERMINAR NÍVEL DE ENSINO =====
    # Mapa de níveis para exibição
    NIVEL_ENSINO_LABELS = {
        'educacao_infantil': 'EDUCAÇÃO INFANTIL',
        'fundamental_anos_iniciais': 'ENSINO FUNDAMENTAL - ANOS INICIAIS',
        'fundamental_anos_finais': 'ENSINO FUNDAMENTAL - ANOS FINAIS',
        'ensino_medio': 'ENSINO MÉDIO',
        'eja': 'EJA - ANOS INICIAIS',
        'eja_final': 'EJA - ANOS FINAIS'
    }
    
    # Inferir nível de ensino da turma
    nivel_ensino = class_info.get('nivel_ensino')
    grade_level = class_info.get('grade_level', '').lower()
    
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
    <b>{mant_nome}</b><br/>
    <font size="9">Secretaria Municipal de Educação</font><br/>
    {slogan_html}
    """
    
    header_right = f"""
    <font size="14" color="#1e40af"><b>FICHA INDIVIDUAL</b></font><br/>
    <font size="10">{nivel_ensino_label}</font>
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
    inep_number = student.get('inep_number', student.get('enrollment_number', 'N/A'))
    
    # Formatar data de nascimento
    birth_date = student.get('birth_date', 'N/A')
    if isinstance(birth_date, str) and '-' in birth_date:
        try:
            bd = datetime.strptime(birth_date.split('T')[0], '%Y-%m-%d')
            birth_date = bd.strftime('%d/%m/%Y')
        except:
            pass
    
    # Carga horária total da turma - considerando carga_horaria_por_serie
    def get_course_workload(course, grade_level):
        """Obtém a carga horária de um componente considerando a série do aluno"""
        carga_por_serie = course.get('carga_horaria_por_serie', {})
        if carga_por_serie and grade_level:
            return carga_por_serie.get(grade_level, course.get('carga_horaria', course.get('workload', 80)))
        return course.get('carga_horaria', course.get('workload', 80))
    
    total_carga_horaria = sum(get_course_workload(c, grade_level) for c in courses) if courses else 1200
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
    
    # DEBUG: Log para verificar mapeamento
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"PDF Boletim DEBUG: grades_by_course tem {len(grades_by_course)} entradas")
    for cid, g in grades_by_course.items():
        logger.info(f"PDF Boletim DEBUG: course_id={cid}, b1={g.get('b1')}, b2={g.get('b2')}")
    
    # Verificar se é Educação Infantil (avaliação conceitual)
    is_educacao_infantil = nivel_ensino == 'educacao_infantil'
    
    if is_educacao_infantil:
        # EDUCAÇÃO INFANTIL: Tabela simplificada com conceitos
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
    
    def fmt_grade_conceitual(v):
        """Formata nota como conceito para Educação Infantil"""
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return valor_para_conceito(v)
        return str(v) if v else '-'
    
    def fmt_int(v):
        """Formata número inteiro"""
        if v is None:
            return '-'
        if isinstance(v, (int, float)):
            return str(int(v))
        return str(v) if v else '-'
    
    # Ordenar componentes curriculares por nível de ensino
    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)
    
    # Obter o grade_level original para buscar carga horária por série
    student_grade_level = class_info.get('grade_level', '')
    
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
        
        # Marcar componentes optativos com "(Optativo)" - igual ao Boletim
        if is_optativo:
            course_name = f"{course_name} (Optativo)"
        
        grade = grades_by_course.get(course_id, {})
        
        # DEBUG: Log para cada componente
        logger.info(f"PDF Boletim DEBUG: Componente {course_name} (ID: {course_id}), nota encontrada: {bool(grade)}, b1={grade.get('b1')}")
        
        # Notas bimestrais
        b1 = grade.get('b1')
        b2 = grade.get('b2')
        b3 = grade.get('b3')
        b4 = grade.get('b4')
        
        # Faltas
        att = attendance_data.get(course_id, {})
        total_faltas = att.get('absences', 0)
        
        # Frequência do componente
        freq_componente = att.get('frequency_percentage', 100.0)
        
        if is_educacao_infantil:
            # EDUCAÇÃO INFANTIL: Conceitos e maior conceito como média
            valid_grades = [g for g in [b1, b2, b3, b4] if isinstance(g, (int, float))]
            if valid_grades:
                conceito_final = valor_para_conceito(max(valid_grades))
            else:
                conceito_final = '-'
            
            row = [
                course_name,
                str(carga_horaria),
                fmt_grade_conceitual(b1),
                fmt_grade_conceitual(b2),
                fmt_grade_conceitual(b3),
                fmt_grade_conceitual(b4),
                conceito_final,
                fmt_int(total_faltas),
                f"{freq_componente:.2f}".replace('.', ',')
            ]
        else:
            # OUTROS NÍVEIS: Processo ponderado completo
            # Recuperações por semestre
            rec_s1 = grade.get('rec_s1', grade.get('recovery'))
            rec_s2 = grade.get('rec_s2')
            
            # Processo ponderado
            b1_pond = (b1 or 0) * 2
            b2_pond = (b2 or 0) * 3
            b3_pond = (b3 or 0) * 2
            b4_pond = (b4 or 0) * 3
            
            # Total de pontos e média
            total_pontos = b1_pond + b2_pond + b3_pond + b4_pond
            media_anual = total_pontos / 10 if total_pontos > 0 else 0
            
            row = [
                course_name,
                str(carga_horaria),
                fmt_grade(b1), fmt_grade(b2), fmt_grade(rec_s1),
                fmt_grade(b3), fmt_grade(b4), fmt_grade(rec_s2),
                fmt_grade(b1_pond), fmt_grade(b2_pond), fmt_grade(b3_pond), fmt_grade(b4_pond),
                fmt_grade(total_pontos),
                fmt_grade(media_anual),
                fmt_int(total_faltas),
                f"{freq_componente:.2f}".replace('.', ',')
            ]
        table_data.append(row)
    
    # Larguras das colunas
    if is_educacao_infantil:
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
    
    # Estilo da tabela - diferente para Educação Infantil
    if is_educacao_infantil:
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
        
        # Verificar se tem notas válidas
        valid_grades = [g for g in [b1, b2, b3, b4] if isinstance(g, (int, float))]
        
        # Calcular média do componente (média ponderada)
        if valid_grades:
            b1 = b1 or 0
            b2 = b2 or 0
            b3 = b3 or 0
            b4 = b4 or 0
            total = (b1 * 2) + (b2 * 3) + (b3 * 2) + (b4 * 3)
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
        'media_aprovacao': mantenedora.get('media_aprovacao', 6.0) if mantenedora else 6.0,
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


def generate_certificado_pdf(
    student: Dict[str, Any],
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    enrollment: Dict[str, Any],
    academic_year: int,
    course_name: str = "Ensino Fundamental",
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera o Certificado de Conclusão em PDF.
    Usa imagem de fundo do servidor FTP e brasão da mantenedora.
    Uso exclusivo para turmas do 9º Ano e EJA 4ª Etapa.
    """
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm, mm
    import urllib.request
    import tempfile
    import os
    
    buffer = BytesIO()
    
    # Página em paisagem (landscape)
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    
    # ========== IMAGEM DE FUNDO ==========
    background_url = "https://aprenderdigital.top/imagens/certificado/certificado_1.jpg"
    
    try:
        # Baixar a imagem de fundo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            urllib.request.urlretrieve(background_url, tmp_file.name)
            # Desenhar imagem de fundo ocupando toda a página
            c.drawImage(tmp_file.name, 0, 0, width=width, height=height)
            # Limpar arquivo temporário
            os.unlink(tmp_file.name)
    except Exception as e:
        # Se falhar ao carregar a imagem, continua sem fundo
        logger.warning(f"Não foi possível carregar imagem de fundo do certificado: {e}")
    
    # ========== BRASÃO COMO MARCA D'ÁGUA (CENTRALIZADO, 70% ALTURA, 20% OPACIDADE) ==========
    brasao_url = mantenedora.get('brasao_url') if mantenedora else None
    brasao_tmp_path = None  # Guardar caminho para reutilizar
    
    if brasao_url:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_brasao:
                urllib.request.urlretrieve(brasao_url, tmp_brasao.name)
                brasao_tmp_path = tmp_brasao.name  # Guardar para usar depois
                
                # Calcular tamanho: 70% da altura da página
                brasao_height = height * 0.70
                brasao_width = brasao_height  # Manter proporção quadrada inicialmente
                
                # Centralizar horizontalmente e verticalmente
                brasao_x = (width - brasao_width) / 2
                brasao_y = (height - brasao_height) / 2
                
                # Aplicar transparência de 80% (opacidade 20%)
                c.saveState()
                c.setFillAlpha(0.20)  # 20% de opacidade = 80% de transparência
                c.setStrokeAlpha(0.20)
                
                # Desenhar o brasão como marca d'água
                c.drawImage(brasao_tmp_path, brasao_x, brasao_y, 
                           width=brasao_width, height=brasao_height, 
                           preserveAspectRatio=True, mask='auto')
                
                c.restoreState()  # Restaurar opacidade normal para o texto
                
        except Exception as e:
            logger.warning(f"Não foi possível carregar brasão da mantenedora: {e}")
    
    # ========== DADOS DO ALUNO ==========
    student_name = student.get('full_name', 'N/A').upper()
    birth_date = student.get('birth_date', 'N/A')
    nationality = student.get('nationality', 'BRASILEIRA').upper()
    birth_city = student.get('birth_city', '').upper()
    birth_state = student.get('birth_state', 'PA').upper()
    father_name = student.get('father_name', '').upper()
    mother_name = student.get('mother_name', '').upper()
    
    # Filiação
    parents = []
    if mother_name:
        parents.append(mother_name)
    if father_name:
        parents.append(father_name)
    filiation = ' e '.join(parents) if parents else 'N/A'
    
    # Naturalidade completa
    naturalidade = f"{birth_city} - {birth_state}" if birth_city else birth_state
    
    # Dados da escola
    school_name = school.get('name', 'ESCOLA MUNICIPAL').upper()
    
    # Resolução de autorização da escola (pode vir do cadastro da escola)
    resolucao = school.get('regulamentacao', 'Resolução n° 272 de 21 de maio de 2020 - CEE/PA')
    
    # Determinar o nível de ensino para o certificado
    grade_level = class_info.get('grade_level', '')
    education_level = class_info.get('education_level', '')
    
    if 'eja' in education_level.lower() or '4' in str(grade_level):
        curso_completo = "Ensino Fundamental - Educação de Jovens e Adultos (EJA)"
    else:
        curso_completo = "Ensino Fundamental"
    
    # ========== CORES ==========
    dark_blue = colors.HexColor('#1a365d')
    black = colors.black
    
    # ========== CABEÇALHO ==========
    # Centro deslocado para a direita (por causa do texto vertical "CERTIFICADO" no fundo)
    center_x = width / 2 + 1.5*cm
    y_position = height - 2.5*cm
    
    # ========== BRASÃO NO CANTO SUPERIOR DIREITO (SEM TRANSPARÊNCIA) ==========
    if brasao_tmp_path:
        try:
            brasao_small_size = 3.52*cm  # 2.2cm + 60% = 3.52cm
            brasao_small_x = width - 5.5*cm  # Ajustado para o novo tamanho
            brasao_small_y = height - 5*cm   # Ajustado para o novo tamanho
            c.drawImage(brasao_tmp_path, brasao_small_x, brasao_small_y, 
                       width=brasao_small_size, height=brasao_small_size, 
                       preserveAspectRatio=True, mask='auto')
        except Exception as e:
            logger.warning(f"Não foi possível desenhar brasão no canto: {e}")
    
    # Textos do cabeçalho (centralizados) - Fontes aumentadas em 3 pontos
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(center_x, y_position, "REPÚBLICA FEDERATIVA DO BRASIL")
    
    y_position -= 14
    c.setFont("Helvetica", 11)
    c.drawCentredString(center_x, y_position, "GOVERNO DO ESTADO DO PARÁ")
    
    y_position -= 14
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(center_x, y_position, "PREFEITURA MUNICIPAL DE FLORESTA DO ARAGUAIA")
    
    y_position -= 14
    c.setFont("Helvetica", 11)
    c.drawCentredString(center_x, y_position, "SECRETARIA MUNICIPAL DE EDUCAÇÃO")
    
    # ========== NOME DA ESCOLA ==========
    y_position -= 34  # +10 (mais 1 espaço)
    c.setFillColor(dark_blue)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(center_x, y_position, school_name)
    
    # ========== AUTORIZAÇÃO LEGAL ==========
    y_position -= 18
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawCentredString(center_x, y_position, f"Autorização - {resolucao}")
    
    # ========== CORPO DO CERTIFICADO ==========
    y_position -= 42  # +10 (mais 1 espaço)
    
    # "Conferimos o presente certificado a"
    c.setFillColor(black)
    c.setFont("Helvetica", 13)
    c.drawCentredString(center_x, y_position, "Conferimos o presente certificado a")
    
    # Nome do aluno (destaque)
    y_position -= 26
    c.setFillColor(dark_blue)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(center_x, y_position, student_name)
    
    # Filiação
    y_position -= 24
    c.setFillColor(black)
    c.setFont("Helvetica", 12)
    c.drawCentredString(center_x, y_position, f"filho(a) de: {filiation}")
    
    # Linha com nacionalidade, naturalidade e nascimento
    y_position -= 18
    c.setFont("Helvetica", 12)
    info_line = f"Nacionalidade: {nationality}        Naturalidade: {naturalidade}        Nascido(a) em: {birth_date}"
    c.drawCentredString(center_x, y_position, info_line)
    
    # ========== TEXTO DE CONCLUSÃO ==========
    y_position -= 32
    
    # Criar texto de conclusão
    text_lines = [
        f"Por haver concluído em {academic_year}, o {curso_completo}, com aprovação em todos os Componentes",
        "Curriculares para gozar de todos os direitos, regalias e prerrogativas concedidas aos portadores, pela Legislação",
        "de Ensino em vigor no País."
    ]
    
    c.setFont("Helvetica", 12)
    for line in text_lines:
        c.drawCentredString(center_x, y_position, line)
        y_position -= 15
    
    # ========== DATA ==========
    y_position -= 38  # +20 (mais 2 espaços)
    today = format_date_pt(date.today())
    city = school.get('municipio', 'Floresta do Araguaia')
    state = school.get('estado', 'PA')
    
    c.setFont("Helvetica", 12)
    c.drawCentredString(center_x, y_position, f"{city} - {state}, {today}.")
    
    # ========== ÁREA DE ASSINATURAS ==========
    # As linhas de assinatura já estão na imagem de fundo
    # Apenas posicionar os textos de identificação se necessário
    
    # Limpar arquivo temporário do brasão
    if brasao_tmp_path:
        try:
            os.unlink(brasao_tmp_path)
        except:
            pass
    
    # Finalizar
    c.save()
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


def generate_livro_promocao_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    students_data: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    academic_year: int,
    mantenedora: Dict[str, Any] = None
) -> BytesIO:
    """
    Gera o PDF do Livro de Promoção para uma turma.
    Formato baseado no modelo de Floresta do Araguaia, similar à Ficha Individual.
    
    O documento é dividido em múltiplas páginas:
    - Página 1: 1º e 2º Bimestre + Recuperação 1º Semestre
    - Página 2: 3º e 4º Bimestre + Recuperação 2º Semestre + Total/Média/Resultado
    
    Args:
        school: Dados da escola
        class_info: Dados da turma
        students_data: Lista com dados dos alunos (incluindo notas e resultado)
        courses: Lista de componentes curriculares
        academic_year: Ano letivo
        mantenedora: Dados da mantenedora (opcional)
    
    Returns:
        BytesIO: Buffer com o PDF gerado
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    
    buffer = BytesIO()
    mantenedora = mantenedora or {}
    
    # Criar documento em paisagem
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8*cm,
        rightMargin=0.8*cm,
        topMargin=0.8*cm,
        bottomMargin=0.8*cm
    )
    
    elements = []
    
    # ===== ESTILOS =====
    info_style = ParagraphStyle('InfoStyle', fontSize=7, leading=9)
    header_style_text = ParagraphStyle('HeaderText', fontSize=10, alignment=TA_LEFT, leading=14)
    header_style_right = ParagraphStyle('HeaderRight', fontSize=10, alignment=TA_RIGHT, leading=16)
    small_text = ParagraphStyle('SmallText', fontSize=7, alignment=TA_LEFT)
    
    # ===== DADOS DA MANTENEDORA =====
    mant_municipio = mantenedora.get('municipio', 'Floresta do Araguaia')
    mant_estado = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mant_municipio}')
    slogan = mantenedora.get('slogan', '')
    logo_url = mantenedora.get('logotipo_url')
    logo = get_logo_image(width=2.4*cm, height=1.6*cm, logo_url=logo_url)
    
    # ===== DADOS DA TURMA =====
    escola_nome = school.get('name', 'Escola Municipal')
    turma_nome = class_info.get('name', 'Turma')
    grade_level = class_info.get('grade_level', '')
    shift_raw = class_info.get('shift', '')
    
    TURNOS_PT = {
        'morning': 'MATUTINO',
        'afternoon': 'VESPERTINO', 
        'evening': 'NOTURNO',
        'full_time': 'INTEGRAL',
        'night': 'NOTURNO'
    }
    turno = TURNOS_PT.get(shift_raw, shift_raw.upper() if shift_raw else 'N/A')
    
    # Ordenar componentes
    nivel_ensino = class_info.get('education_level', '')
    courses_ordenados = ordenar_componentes_por_nivel(courses, nivel_ensino)
    num_components = len(courses_ordenados)
    
    if num_components == 0:
        courses_ordenados = [{'id': 'placeholder', 'name': 'Componente'}]
        num_components = 1
    
    # Abreviações dos componentes
    def abreviar_componente(nome):
        abreviacoes = {
            'Língua Portuguesa': 'Lin. Port.',
            'Arte': 'Arte',
            'Educação Física': 'Ed. Fís.',
            'Língua Inglesa': 'Lin. Ingl.',
            'Inglês': 'Lin. Ingl.',
            'Matemática': 'Mat.',
            'Ciências': 'Ciênc.',
            'História': 'Hist.',
            'Geografia': 'Geo.',
            'Ensino Religioso': 'Ed. Rel.',
            'Educação Ambiental e Clima': 'Ed. A. Cl.',
            'Estudos Amazônicos': 'Est. Amaz.',
            'Literatura e Redação': 'Lit. e red.',
            'Recreação e Lazer': 'R. E. Laz.',
            'Recreação, Esporte e Lazer': 'R. E. Laz.',
            'Linguagem Recreativa com Práticas de Esporte e Lazer': 'R. E. Laz.',
            'Arte e Cultura': 'Art. e Cul.',
            'Tecnologia da Informação': 'Tec. Inf.',
            'Tecnologia e Informática': 'Tec. Inf.',
            'Acompanhamento Pedagógico de Língua Portuguesa': 'APL Port.',
            'Acompanhamento Pedagógico de Matemática': 'AP Mat.',
            'Acomp. Ped. de Língua Portuguesa': 'APL Port.',
            'Acomp. Ped. de Matemática': 'AP Mat.',
            'Contação de Histórias e Iniciação Musical': 'Cont. Hist.',
            'Corpo, gestos e movimentos': 'Corp. Gest.',
            'Escuta, fala, pensamento e imaginação': 'Esc. Fala',
            'Espaços, tempos, quantidades, relações e transformações': 'Esp. Temp.',
            'Higiene e Saúde': 'Hig. Saúde',
            'O eu, o outro e nós': 'Eu Out. Nós',
            'Traço, sons, cores e formas': 'Traç. Sons'
        }
        return abreviacoes.get(nome, nome[:10] + '.' if len(nome) > 10 else nome)
    
    comp_names = [abreviar_componente(c.get('name', '')) for c in courses_ordenados]
    
    # ===== FUNÇÃO PARA CRIAR CABEÇALHO =====
    def criar_cabecalho(pagina_num, total_paginas):
        header_elements = []
        
        # Linha 1: Logo + Nome da Mantenedora + Título
        slogan_html = f'<font size="8" color="#666666">"{slogan}"</font>' if slogan else ''
        header_text = f"""
        <b>{mant_nome}</b><br/>
        <font size="9">Secretaria Municipal de Educação</font><br/>
        {slogan_html}
        """
        
        header_right = f"""
        <font size="14" color="#1e40af"><b>LIVRO DE PROMOÇÃO</b></font><br/>
        <font size="10">ANO LETIVO: {academic_year}</font>
        """
        
        if logo:
            header_table = Table([
                [logo, Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
            ], colWidths=[3*cm, 14*cm, 10*cm])
        else:
            header_table = Table([
                [Paragraph(header_text, header_style_text), Paragraph(header_right, header_style_right)]
            ], colWidths=[15*cm, 12*cm])
        
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
        ]))
        header_elements.append(header_table)
        header_elements.append(Spacer(1, 5))
        
        # Linha 2: Escola + Ano Letivo
        info_row1 = Table([
            [
                Paragraph(f"<b>ESCOLA:</b> {escola_nome}", info_style),
                Paragraph(f"<b>PÁGINA:</b> {pagina_num:02d}/{total_paginas:02d}", info_style),
            ]
        ], colWidths=[23*cm, 4*cm])
        info_row1.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        header_elements.append(info_row1)
        
        # Linha 3: Turma, Série, Turno
        info_row2 = Table([
            [
                Paragraph(f"<b>TURMA:</b> {turma_nome}", info_style),
                Paragraph(f"<b>ANO/ETAPA:</b> {grade_level}", info_style),
                Paragraph(f"<b>TURNO:</b> {turno}", info_style),
            ]
        ], colWidths=[12*cm, 8*cm, 7*cm])
        info_row2.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        header_elements.append(info_row2)
        header_elements.append(Spacer(1, 8))
        
        return header_elements
    
    # ===== FUNÇÃO PARA FORMATAR NOTA =====
    def fmt_grade(v):
        if v is None:
            return ''
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
        return str(v) if v else ''
    
    # ===== PÁGINA 1: 1º SEMESTRE (1º Bim, 2º Bim, Rec 1º Sem) =====
    elements.extend(criar_cabecalho(1, 2))
    
    # Cabeçalho da tabela - Página 1
    # Estrutura: N° | Nome | Sexo | [1º BIM: componentes] | [2º BIM: componentes] | [REC 1º SEM: componentes]
    header_row1_p1 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p1.extend(['NOTAS 1º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['NOTAS 2º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p1.extend(['RECUPERAÇÃO 1º SEMESTRE'] + [''] * (num_components - 1))
    
    header_row2_p1 = ['', '', '']
    header_row2_p1.extend(comp_names)  # 1º Bim
    header_row2_p1.extend(comp_names)  # 2º Bim
    header_row2_p1.extend(comp_names)  # Rec 1º Sem
    
    table_data_p1 = [header_row1_p1, header_row2_p1]
    
    # Dados dos alunos - Página 1
    for idx, student in enumerate(students_data, 1):
        row = [
            str(idx),
            student.get('studentName', '')[:30],
            student.get('sex', '-')
        ]
        
        grades = student.get('grades', {})
        
        # 1º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b1')))
        
        # 2º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b2')))
        
        # Recuperação 1º Semestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('rec1')))
        
        table_data_p1.append(row)
    
    # Calcular larguras - Página 1
    largura_disponivel = 27 * cm
    largura_num = 0.7 * cm
    largura_nome = 4.5 * cm
    largura_sexo = 0.7 * cm
    largura_restante = largura_disponivel - largura_num - largura_nome - largura_sexo
    largura_por_nota = largura_restante / (num_components * 3)
    largura_por_nota = max(largura_por_nota, 0.6 * cm)
    
    col_widths_p1 = [largura_num, largura_nome, largura_sexo]
    col_widths_p1.extend([largura_por_nota] * (num_components * 3))
    
    # Criar tabela Página 1
    table_p1 = Table(table_data_p1, colWidths=col_widths_p1, repeatRows=2)
    
    # Estilo da tabela
    style_p1 = [
        # Cabeçalho linha 1
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Cabeçalho linha 2
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        
        # Corpo
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, -1), 'LEFT'),  # Nome alinhado à esquerda
        
        # Grid e bordas
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Linhas verticais mais grossas entre blocos
        ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),  # Após Sexo
        ('LINEAFTER', (2 + num_components, 0), (2 + num_components, -1), 1.5, colors.black),  # Após 1º Bim
        ('LINEAFTER', (2 + num_components * 2, 0), (2 + num_components * 2, -1), 1.5, colors.black),  # Após 2º Bim
        ('LINEAFTER', (2 + num_components * 3, 0), (2 + num_components * 3, -1), 1.5, colors.black),  # Após Rec 1º Sem
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        
        # Span para cabeçalhos de seção
        ('SPAN', (3, 0), (3 + num_components - 1, 0)),  # 1º Bim
        ('SPAN', (3 + num_components, 0), (3 + num_components * 2 - 1, 0)),  # 2º Bim
        ('SPAN', (3 + num_components * 2, 0), (3 + num_components * 3 - 1, 0)),  # Rec 1º Sem
        
        # Cores alternadas nas linhas
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]
    
    table_p1.setStyle(TableStyle(style_p1))
    elements.append(table_p1)
    
    # ===== PÁGINA 2: 2º SEMESTRE + RESULTADO =====
    elements.append(PageBreak())
    elements.extend(criar_cabecalho(2, 2))
    
    # Cabeçalho da tabela - Página 2
    header_row1_p2 = ['N°', 'NOME DO ALUNO', 'S']
    header_row1_p2.extend(['NOTAS 3º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['NOTAS 4º BIMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['RECUPERAÇÃO 2º SEMESTRE'] + [''] * (num_components - 1))
    header_row1_p2.extend(['TOTAL', 'MÉDIA', 'RESULTADO'])
    
    header_row2_p2 = ['', '', '']
    header_row2_p2.extend(comp_names)  # 3º Bim
    header_row2_p2.extend(comp_names)  # 4º Bim
    header_row2_p2.extend(comp_names)  # Rec 2º Sem
    header_row2_p2.extend(['PTS', 'FINAL', ''])
    
    table_data_p2 = [header_row1_p2, header_row2_p2]
    
    # Dados dos alunos - Página 2
    for idx, student in enumerate(students_data, 1):
        row = [
            str(idx),
            student.get('studentName', '')[:30],
            student.get('sex', '-')
        ]
        
        grades = student.get('grades', {})
        
        # 3º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b3')))
        
        # 4º Bimestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('b4')))
        
        # Recuperação 2º Semestre
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            row.append(fmt_grade(grade_info.get('rec2')))
        
        # Calcular Total de Pontos (soma de todas as médias finais)
        total_pontos = 0
        medias_validas = []
        for course in courses_ordenados:
            course_id = course.get('id', '')
            grade_info = grades.get(course_id, {})
            media = grade_info.get('finalAverage')
            if isinstance(media, (int, float)):
                total_pontos += media
                medias_validas.append(media)
        
        # Média geral
        media_geral = total_pontos / len(medias_validas) if medias_validas else 0
        
        row.append(f"{total_pontos:.1f}".replace('.', ',') if total_pontos > 0 else '-')
        row.append(f"{media_geral:.1f}".replace('.', ',') if media_geral > 0 else '-')
        
        # Resultado
        resultado = student.get('result', 'CURSANDO')
        row.append(resultado[:12])
        
        table_data_p2.append(row)
    
    # Calcular larguras - Página 2 (3 colunas extras: Total, Média, Resultado)
    largura_total = 1.0 * cm
    largura_media = 1.0 * cm
    largura_resultado = 1.8 * cm
    largura_restante_p2 = largura_disponivel - largura_num - largura_nome - largura_sexo - largura_total - largura_media - largura_resultado
    largura_por_nota_p2 = largura_restante_p2 / (num_components * 3)
    largura_por_nota_p2 = max(largura_por_nota_p2, 0.55 * cm)
    
    col_widths_p2 = [largura_num, largura_nome, largura_sexo]
    col_widths_p2.extend([largura_por_nota_p2] * (num_components * 3))
    col_widths_p2.extend([largura_total, largura_media, largura_resultado])
    
    # Criar tabela Página 2
    table_p2 = Table(table_data_p2, colWidths=col_widths_p2, repeatRows=2)
    
    # Estilo da tabela Página 2
    style_p2 = [
        # Cabeçalho linha 1
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Cabeçalho linha 2
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        
        # Corpo
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, -1), 'LEFT'),
        
        # Grid e bordas
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Linhas verticais mais grossas entre blocos
        ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),  # Após Sexo
        ('LINEAFTER', (2 + num_components, 0), (2 + num_components, -1), 1.5, colors.black),  # Após 3º Bim
        ('LINEAFTER', (2 + num_components * 2, 0), (2 + num_components * 2, -1), 1.5, colors.black),  # Após 4º Bim
        ('LINEAFTER', (2 + num_components * 3, 0), (2 + num_components * 3, -1), 1.5, colors.black),  # Após Rec 2º Sem
        ('LINEAFTER', (2 + num_components * 3 + 1, 0), (2 + num_components * 3 + 1, -1), 1.5, colors.black),  # Após Total
        ('LINEAFTER', (2 + num_components * 3 + 2, 0), (2 + num_components * 3 + 2, -1), 1.5, colors.black),  # Após Média
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        
        # Span para cabeçalhos de seção
        ('SPAN', (3, 0), (3 + num_components - 1, 0)),  # 3º Bim
        ('SPAN', (3 + num_components, 0), (3 + num_components * 2 - 1, 0)),  # 4º Bim
        ('SPAN', (3 + num_components * 2, 0), (3 + num_components * 3 - 1, 0)),  # Rec 2º Sem
        
        # Cores alternadas nas linhas
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]
    
    # Colorir resultado baseado no valor
    col_resultado = len(col_widths_p2) - 1
    for row_idx, student in enumerate(students_data, 2):
        resultado = student.get('result', 'CURSANDO')
        if 'APROVADO' in resultado or 'PROMOVIDO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#c8e6c9')))
            style_p2.append(('TEXTCOLOR', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#1b5e20')))
            style_p2.append(('FONTNAME', (col_resultado, row_idx), (col_resultado, row_idx), 'Helvetica-Bold'))
        elif 'REPROVADO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#ffcdd2')))
            style_p2.append(('TEXTCOLOR', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#b71c1c')))
            style_p2.append(('FONTNAME', (col_resultado, row_idx), (col_resultado, row_idx), 'Helvetica-Bold'))
        elif 'DESISTENTE' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#e0e0e0')))
        elif 'TRANSFERIDO' in resultado:
            style_p2.append(('BACKGROUND', (col_resultado, row_idx), (col_resultado, row_idx), colors.HexColor('#fff9c4')))
    
    table_p2.setStyle(TableStyle(style_p2))
    elements.append(table_p2)
    
    # ===== RODAPÉ COM ASSINATURAS =====
    elements.append(Spacer(1, 20))
    
    # Data e local
    today = datetime.now()
    data_extenso = f"{mant_municipio} - {mant_estado}, {today.day} de {['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'][today.month - 1]} de {today.year}"
    
    footer_style = ParagraphStyle('FooterStyle', fontSize=9, alignment=TA_CENTER)
    elements.append(Paragraph(data_extenso, footer_style))
    elements.append(Spacer(1, 30))
    
    # Assinaturas
    assinatura_data = [
        ['_' * 40, '_' * 40],
        ['Secretário(a)', 'Diretor(a)']
    ]
    assinatura_table = Table(assinatura_data, colWidths=[10*cm, 10*cm])
    assinatura_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, 1), 5),
    ]))
    elements.append(assinatura_table)
    
    # Rodapé com informações de geração
    elements.append(Spacer(1, 15))
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    elements.append(Paragraph(rodape_info, small_text))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
