"""
Módulo PDF do SIGESC - Utilitários compartilhados
Constantes, estilos, formatação e funções auxiliares usadas por todos os geradores de PDF.
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
import tempfile
import os
import hashlib

logger = logging.getLogger(__name__)

# URL do logotipo da prefeitura
LOGO_URL = "https://aprenderdigital.top/imagens/logotipo/logoprefeitura.jpg"

# Cache de logos em disco para evitar downloads repetidos
_logo_cache_dir = os.path.join(tempfile.gettempdir(), 'sigesc_logo_cache')
os.makedirs(_logo_cache_dir, exist_ok=True)
_logo_memory_cache = {}  # {(url_hash, width, height): Image}

# Tentar configurar locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')
    except:
        pass

# ===== ORDEM DOS COMPONENTES CURRICULARES =====

ORDEM_COMPONENTES_EDUCACAO_INFANTIL = [
    "O eu, o outro e nós",
    "Corpo, gestos e movimentos",
    "Escuta, fala, pensamento e imaginação",
    "Traço, sons, cores e formas",
    "Traços, sons, cores e formas",
    "Espaços, tempos, quantidades, relações e transformações",
    "Educação Ambiental e Clima",
    "Contação de Histórias e Iniciação Musical",
    "Arte e Cultura",
    "Higiene e Saúde",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Recreação, Esporte e Lazer",
]

ORDEM_COMPONENTES_ANOS_INICIAIS = [
    "Língua Portuguesa",
    "Arte",
    "Educação Física",
    "Matemática",
    "Ciências",
    "História",
    "Geografia",
    "Ensino Religioso",
    "Educação Ambiental e Clima",
    "Arte e Cultura",
    "Recreação, Esporte e Lazer",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Tecnologia e Informática",
    "Acompanhamento Pedagógico de Língua Portuguesa",
    "Acomp. Ped. de Língua Portuguesa",
    "Acompanhamento Pedagógico de Matemática",
    "Acomp. Ped. de Matemática",
]

ORDEM_COMPONENTES_ANOS_FINAIS = [
    "Língua Portuguesa",
    "Arte",
    "Educação Física",
    "Língua Inglesa",
    "Língua inglesa",
    "Inglês",
    "Matemática",
    "Ciências",
    "História",
    "Geografia",
    "Ensino Religioso",
    "Estudos Amazônicos",
    "Literatura e Redação",
    "Educação Ambiental e Clima",
    "Arte e Cultura",
    "Recreação, Esporte e Lazer",
    "Linguagem Recreativa com Práticas de Esporte e Lazer",
    "Tecnologia e Informática",
    "Acompanhamento Pedagógico de Língua Portuguesa",
    "Acomp. Ped. de Língua Portuguesa",
    "Acompanhamento Pedagógico de Matemática",
    "Acomp. Ped. de Matemática",
]

# ===== SISTEMA DE AVALIAÇÃO CONCEITUAL =====

CONCEITOS_EDUCACAO_INFANTIL = {
    'OD': {'valor': 10.0, 'descricao': 'Objetivo Desenvolvido'},
    'DP': {'valor': 7.5, 'descricao': 'Desenvolvido Parcialmente'},
    'ND': {'valor': 5.0, 'descricao': 'Não Desenvolvido'},
    'NT': {'valor': 0.0, 'descricao': 'Não Trabalhado'},
}

VALOR_PARA_CONCEITO = {
    10.0: 'OD',
    7.5: 'DP',
    5.0: 'ND',
    0.0: 'NT',
}

CONCEITOS_ANOS_INICIAIS = {
    'C': {'valor': 10.0, 'descricao': 'Consolidado'},
    'ED': {'valor': 7.5, 'descricao': 'Em Desenvolvimento'},
    'ND': {'valor': 5.0, 'descricao': 'Não Desenvolvido'},
}

VALOR_PARA_CONCEITO_ANOS_INICIAIS = {
    10.0: 'C',
    7.5: 'ED',
    5.0: 'ND',
}

SERIES_CONCEITUAIS_ANOS_INICIAIS = ['1º Ano', '2º Ano', '1º ano', '2º ano', '1 Ano', '2 Ano']

NIVEL_ENSINO_LABELS = {
    'educacao_infantil': 'EDUCAÇÃO INFANTIL',
    'fundamental_anos_iniciais': 'ENSINO FUNDAMENTAL',
    'fundamental_anos_finais': 'ENSINO FUNDAMENTAL',
    'ensino_medio': 'ENSINO MÉDIO',
    'eja': 'EJA - ANOS INICIAIS',
    'eja_final': 'EJA - ANOS FINAIS',
    'global': 'GLOBAL'
}

TURNOS_PT = {
    'morning': 'Matutino',
    'afternoon': 'Vespertino',
    'evening': 'Noturno',
    'full_time': 'Integral',
    'night': 'Noturno'
}

# ===== FUNÇÕES UTILITÁRIAS =====

def get_logo_image(width=2*cm, height=2*cm, logo_url=None):
    """Retorna o logotipo como Image do reportlab. Usa cache em disco."""
    url = logo_url if logo_url else LOGO_URL
    if not url:
        return None
    try:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_key = (url_hash, width, height)
        
        # Cache em memória (mais rápido)
        if cache_key in _logo_memory_cache:
            return _logo_memory_cache[cache_key]
        
        suffix = '.jpg' if '.jpg' in url.lower() or '.jpeg' in url.lower() else '.png'
        cache_path = os.path.join(_logo_cache_dir, f'{url_hash}{suffix}')
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                header = f.read(4)
            if not (header[:4] == b'\x89PNG' or header[:2] == b'\xff\xd8'):
                os.remove(cache_path)
        if not os.path.exists(cache_path):
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as response:
                content_type = response.headers.get('Content-Type', '')
                if 'image' not in content_type and 'octet-stream' not in content_type:
                    return None
                image_data = response.read()
                if not (image_data[:4] == b'\x89PNG' or image_data[:2] == b'\xff\xd8'):
                    return None
            with open(cache_path, 'wb') as f:
                f.write(image_data)
        img = Image(cache_path, width=width, height=height)
        _logo_memory_cache[cache_key] = img
        return img
    except Exception as e:
        logger.warning(f"Erro ao carregar logotipo de {url}: {e}")
        return None


def format_date_pt(d: date) -> str:
    """Formata data em português"""
    months = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
              'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    return f"{d.day} de {months[d.month - 1]} de {d.year}"


# Cache de estilos (evita recriar ParagraphStyles a cada PDF)
_styles_cache = None

def get_styles():
    """Retorna estilos personalizados para os documentos (com cache)"""
    global _styles_cache
    if _styles_cache is not None:
        return _styles_cache
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='MainTitle', parent=styles['Heading1'],
        fontSize=16, alignment=TA_CENTER, spaceAfter=20,
        textColor=colors.HexColor('#1e40af')
    ))
    styles.add(ParagraphStyle(
        name='SubTitle', parent=styles['Heading2'],
        fontSize=12, alignment=TA_CENTER, spaceAfter=10,
        textColor=colors.HexColor('#374151')
    ))
    styles.add(ParagraphStyle(
        name='CenterText', parent=styles['Normal'],
        fontSize=11, alignment=TA_CENTER, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name='JustifyText', parent=styles['Normal'],
        fontSize=11, alignment=TA_JUSTIFY, spaceAfter=12, leading=16
    ))
    styles.add(ParagraphStyle(
        name='SignatureText', parent=styles['Normal'],
        fontSize=10, alignment=TA_CENTER, spaceBefore=40
    ))
    _styles_cache = styles
    return styles


def is_serie_conceitual_anos_iniciais(grade_level):
    """Verifica se a série usa avaliação conceitual de Anos Iniciais (1º e 2º ano)."""
    if not grade_level:
        return False
    grade_lower = grade_level.lower()
    return any(serie.lower() in grade_lower for serie in SERIES_CONCEITUAIS_ANOS_INICIAIS)


def valor_para_conceito_fn(valor, grade_level=None):
    """Converte um valor numérico para o conceito correspondente."""
    if valor is None:
        return '-'
    if grade_level and is_serie_conceitual_anos_iniciais(grade_level):
        mapeamento = VALOR_PARA_CONCEITO_ANOS_INICIAIS
        conceito_minimo = 'ND'
    else:
        mapeamento = VALOR_PARA_CONCEITO
        conceito_minimo = 'NT'
    for v, conceito in sorted(mapeamento.items(), reverse=True):
        if valor >= v:
            return conceito
    return conceito_minimo


def conceito_para_valor(conceito):
    """Converte um conceito para seu valor numérico."""
    if conceito in CONCEITOS_EDUCACAO_INFANTIL:
        return CONCEITOS_EDUCACAO_INFANTIL[conceito]['valor']
    if conceito in CONCEITOS_ANOS_INICIAIS:
        return CONCEITOS_ANOS_INICIAIS[conceito]['valor']
    return None


def criar_legenda_conceitos(is_educacao_infantil=False, grade_level=None):
    """Cria uma tabela de legenda para os conceitos usados na avaliação."""
    elements = []
    is_anos_iniciais_conceitual = grade_level and is_serie_conceitual_anos_iniciais(grade_level)
    style_titulo = ParagraphStyle('LegendaTitulo', fontSize=8, fontName='Helvetica-Bold', alignment=TA_LEFT, spaceAfter=2)
    style_conceito = ParagraphStyle('LegendaConceito', fontSize=7, fontName='Helvetica', alignment=TA_LEFT)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph("LEGENDA:", style_titulo))
    if is_educacao_infantil:
        conceitos_data = [['OD', '=', 'Objetivo Desenvolvido'], ['DP', '=', 'Desenvolvido Parcialmente'], ['ND', '=', 'Não Desenvolvido'], ['NT', '=', 'Não Trabalhado']]
    elif is_anos_iniciais_conceitual:
        conceitos_data = [['C', '=', 'Consolidado'], ['ED', '=', 'Em Desenvolvimento'], ['ND', '=', 'Não Desenvolvido']]
    else:
        return []
    legenda_texto = '   •   '.join([f"{c[0]} = {c[2]}" for c in conceitos_data])
    elements.append(Paragraph(legenda_texto, style_conceito))
    return elements


def calcular_media_conceitual(notas):
    """Calcula a média conceitual (maior conceito alcançado nos bimestres)."""
    valores_validos = []
    for nota in notas:
        if nota is not None and isinstance(nota, (int, float)) and nota > 0:
            valores_validos.append(nota)
        elif isinstance(nota, str) and nota in CONCEITOS_EDUCACAO_INFANTIL:
            valores_validos.append(CONCEITOS_EDUCACAO_INFANTIL[nota]['valor'])
        elif isinstance(nota, str) and nota in CONCEITOS_ANOS_INICIAIS:
            valores_validos.append(CONCEITOS_ANOS_INICIAIS[nota]['valor'])
    if valores_validos:
        return max(valores_validos)
    return None


def formatar_nota_conceitual(valor, is_educacao_infantil=False, grade_level=None):
    """Formata uma nota. Se for Ed. Infantil ou 1º/2º ano, retorna conceito."""
    if valor is None:
        return '-'
    is_anos_iniciais_conceitual = grade_level and is_serie_conceitual_anos_iniciais(grade_level)
    if is_educacao_infantil or is_anos_iniciais_conceitual:
        return valor_para_conceito_fn(valor, grade_level)
    if isinstance(valor, (int, float)):
        return f"{valor:.1f}".replace('.', ',')
    return str(valor) if valor else '-'


def ordenar_componentes_educacao_infantil(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def get_ordem(course):
        nome = course.get('name', '')
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_EDUCACAO_INFANTIL):
            if nome_ordem.lower() in nome.lower() or nome.lower() in nome_ordem.lower():
                return i
        return len(ORDEM_COMPONENTES_EDUCACAO_INFANTIL) + ord(nome[0].lower()) if nome else 999
    return sorted(courses, key=get_ordem)


def ordenar_componentes_anos_iniciais(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def get_ordem(course):
        nome = course.get('name', '').strip()
        nome_lower = nome.lower()
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_ANOS_INICIAIS):
            if nome_ordem.lower() == nome_lower:
                return i
        return len(ORDEM_COMPONENTES_ANOS_INICIAIS) + ord(nome[0].lower()) if nome else 999
    return sorted(courses, key=get_ordem)


def ordenar_componentes_anos_finais(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def get_ordem(course):
        nome = course.get('name', '').strip()
        nome_lower = nome.lower()
        for i, nome_ordem in enumerate(ORDEM_COMPONENTES_ANOS_FINAIS):
            if nome_ordem.lower() == nome_lower:
                return i
        return len(ORDEM_COMPONENTES_ANOS_FINAIS) + ord(nome[0].lower()) if nome else 999
    return sorted(courses, key=get_ordem)


def ordenar_componentes_por_nivel(courses: List[Dict[str, Any]], nivel_ensino: str) -> List[Dict[str, Any]]:
    """Ordena os componentes curriculares de acordo com o nível de ensino."""
    if nivel_ensino == 'educacao_infantil':
        return ordenar_componentes_educacao_infantil(courses)
    elif nivel_ensino == 'fundamental_anos_iniciais':
        return ordenar_componentes_anos_iniciais(courses)
    elif nivel_ensino == 'fundamental_anos_finais':
        return ordenar_componentes_anos_finais(courses)
    else:
        return sorted(courses, key=lambda x: x.get('name', ''))


def inferir_nivel_ensino(class_info, enrollment=None):
    """Infere o nível de ensino a partir dos dados da turma e matrícula."""
    nivel_ensino = class_info.get('nivel_ensino') or class_info.get('education_level')
    if enrollment:
        grade_level = (enrollment.get('student_series') or class_info.get('grade_level', '')).lower()
    else:
        grade_level = class_info.get('grade_level', '').lower()
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
            nivel_ensino = 'fundamental_anos_iniciais'
    return nivel_ensino
