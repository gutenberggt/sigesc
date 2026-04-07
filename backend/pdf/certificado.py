"""Módulo PDF - Certificado de Conclusão"""
from io import BytesIO
from datetime import datetime, date
from typing import List, Dict, Any
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
import urllib.request
import tempfile
import os
import logging
from pdf.utils import get_logo_image, format_date_pt

logger = logging.getLogger(__name__)

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
    display_grade_level = enrollment.get('student_series') or grade_level
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
    c.drawCentredString(center_x, y_position, (mantenedora.get('secretaria', 'SECRETARIA MUNICIPAL DE EDUCAÇÃO') if mantenedora else 'SECRETARIA MUNICIPAL DE EDUCAÇÃO').upper())
    
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

