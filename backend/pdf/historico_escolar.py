"""
Módulo de geração de PDF do Histórico Escolar.
Layout inspirado no modelo oficial da SEMED.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import logging

logger = logging.getLogger(__name__)

# Componentes curriculares organizados por área de conhecimento
COMPONENTES_BNCC = {
    "Linguagens": [
        "Língua Portuguesa",
        "Arte",
        "Educação Física",
        "Língua Inglesa"
    ],
    "Matemática": [
        "Matemática"
    ],
    "Ciências da Natureza": [
        "Ciências"
    ],
    "Ciências Humanas": [
        "História",
        "Geografia",
        "Ensino Religioso"
    ]
}

COMPONENTES_DIVERSIFICADA = [
    "Ed. Ambiental e Clima",
    "Estudos Amazônicos",
    "Literatura e Redação",
    "Acomp. Pedagógico",
    "Recreação, Esporte e Lazer",
    "Arte e Cultura",
    "Tecnologia e Informática"
]

SERIES = ["1º", "2º", "3º", "4º", "5º", "6º", "7º", "8º", "9º"]
CICLOS = [
    {"nome": "CICLO I", "series": ["1º", "2º", "3º"]},
    {"nome": "CICLO II", "series": ["4º", "5º"]},
    {"nome": "CICLO III", "series": ["6º", "7º"]},
    {"nome": "CICLO IV", "series": ["8º", "9º"]}
]


def get_logo_image(width=1.8*cm, height=1.8*cm, logo_url=None):
    """Tenta carregar logo da mantenedora."""
    if logo_url:
        try:
            import urllib.request
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            urllib.request.urlretrieve(logo_url, tmp.name)
            return Image(tmp.name, width=width, height=height)
        except Exception:
            pass
    return None


def generate_historico_escolar_pdf(student, school, mantenedora, history, **kwargs):
    """Gera o PDF do Histórico Escolar."""
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.2*cm,
        rightMargin=1.2*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    width, height = A4
    usable_width = width - 2.4*cm
    
    styles = getSampleStyleSheet()
    
    # Estilos customizados
    style_center = ParagraphStyle('Center', parent=styles['Normal'], alignment=TA_CENTER, fontSize=7, leading=9)
    style_center_bold = ParagraphStyle('CenterBold', parent=styles['Normal'], alignment=TA_CENTER, fontSize=7, leading=9, fontName='Helvetica-Bold')
    style_center_title = ParagraphStyle('CenterTitle', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10, leading=12, fontName='Helvetica-Bold')
    style_left = ParagraphStyle('Left', parent=styles['Normal'], alignment=TA_LEFT, fontSize=6.5, leading=8)
    style_left_bold = ParagraphStyle('LeftBold', parent=styles['Normal'], alignment=TA_LEFT, fontSize=6.5, leading=8, fontName='Helvetica-Bold')
    style_small = ParagraphStyle('Small', parent=styles['Normal'], alignment=TA_CENTER, fontSize=5.5, leading=7)
    style_obs = ParagraphStyle('Obs', parent=styles['Normal'], alignment=TA_LEFT, fontSize=6, leading=8)
    style_header_inst = ParagraphStyle('HeaderInst', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, leading=10, fontName='Helvetica-Bold')
    style_header_sec = ParagraphStyle('HeaderSec', parent=styles['Normal'], alignment=TA_CENTER, fontSize=7, leading=9, fontName='Helvetica-Oblique')
    
    elements = []
    mantenedora = mantenedora or {}
    records = history.get('records', [])
    records_map = {r.get('serie', ''): r for r in records}
    
    # ===== CABEÇALHO =====
    mant_nome = mantenedora.get('nome', 'Prefeitura Municipal')
    mant_secretaria = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')
    
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    logo = get_logo_image(width=1.5*cm, height=1.5*cm, logo_url=logo_url)
    
    header_data = [[
        logo if logo else '',
        Paragraph(f"<b>{mant_nome.upper()}</b><br/><i>{mant_secretaria}</i><br/>HISTÓRICO ESCOLAR", style_center)
    ]]
    header_table = Table(header_data, colWidths=[2*cm, usable_width - 2*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3*mm))
    
    # ===== DADOS DO ALUNO =====
    nome = (student.get('full_name') or '').upper()
    pai = (student.get('father_name') or '').upper()
    mae = (student.get('mother_name') or '').upper()
    nascimento = student.get('birth_date') or ''
    if nascimento and '-' in str(nascimento):
        parts = str(nascimento).split('-')
        nascimento = f"{parts[2]}/{parts[1]}/{parts[0]}"
    cpf = str(student.get('cpf') or '')
    naturalidade = str(student.get('birth_city') or '')
    uf_nasc = str(student.get('birth_state') or '')
    inep = str(student.get('inep_code') or '')
    rg = str(student.get('rg') or '')
    
    school_name = (school.get('name') or 'Escola Municipal').upper() if school else 'ESCOLA MUNICIPAL'
    school_city = (school.get('city') or school.get('municipio') or '') if school else ''
    school_uf = (school.get('state') or school.get('uf') or 'PA') if school else 'PA'
    
    # Tabela de dados pessoais
    p = lambda t: Paragraph(t, style_left)
    pb = lambda t: Paragraph(t, style_left_bold)
    
    student_data = [
        [pb('Nome do Aluno:'), p(nome), pb('Data Nasc.:'), p(nascimento)],
        [pb('Pai:'), p(pai), pb('CPF:'), p(cpf)],
        [pb('Mãe:'), p(mae), pb('RG:'), p(rg)],
        [pb('Naturalidade:'), p(f"{naturalidade} - {uf_nasc}"), pb('Cód. INEP:'), p(inep)],
    ]
    
    col_w = [2.2*cm, usable_width/2 - 2.2*cm, 2.2*cm, usable_width/2 - 2.2*cm]
    student_table = Table(student_data, colWidths=col_w)
    student_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.93)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.93, 0.93, 0.93)),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 2*mm))
    
    # ===== TABELA PRINCIPAL DE COMPONENTES/NOTAS =====
    # Cabeçalho: Amparo Legal | Área | Componente | 1º 2º 3º | 4º 5º | 6º 7º | 8º 9º
    
    # Colunas de notas: uma por série
    note_col_w = 1.35*cm
    area_col_w = 1.8*cm
    comp_col_w = usable_width - area_col_w - (note_col_w * 9)
    if comp_col_w < 2.5*cm:
        note_col_w = 1.2*cm
        comp_col_w = usable_width - area_col_w - (note_col_w * 9)
    
    col_widths = [area_col_w, comp_col_w] + [note_col_w] * 9
    
    ps = lambda t: Paragraph(t, style_small)
    pc = lambda t: Paragraph(t, style_center)
    pcb = lambda t: Paragraph(t, style_center_bold)
    
    # Header row com ciclos
    header_row1 = [
        pcb('ÁREA DE<br/>CONHECIMENTO'),
        pcb('COMPONENTES<br/>CURRICULARES'),
        pcb('CICLO I'), '', '',
        pcb('CICLO II'), '',
        pcb('CICLO III'), '',
        pcb('CICLO IV'), ''
    ]
    
    header_row2 = [
        '', '',
        pcb('1º'), pcb('2º'), pcb('3º'),
        pcb('4º'), pcb('5º'),
        pcb('6º'), pcb('7º'),
        pcb('8º'), pcb('9º')
    ]
    
    data_rows = [header_row1, header_row2]
    
    # Linhas dos componentes BNCC
    bncc_label = "BASE NACIONAL COMUM CURRICULAR"
    first_bncc = True
    total_bncc_rows = sum(len(comps) for comps in COMPONENTES_BNCC.values())
    bncc_start_row = 2  # after 2 header rows
    
    for area, componentes in COMPONENTES_BNCC.items():
        for i, comp in enumerate(componentes):
            notas = []
            for s in SERIES:
                rec = records_map.get(s, {})
                grades = rec.get('grades', {})
                # Busca por nome exato ou similar
                nota = grades.get(comp, '')
                if not nota:
                    # Tentar buscar por nome normalizado
                    comp_lower = comp.lower()
                    for k, v in grades.items():
                        if k.lower() == comp_lower or comp_lower in k.lower():
                            nota = v
                            break
                notas.append(pc(str(nota) if nota else ''))
            
            area_cell = pcb(area.upper()) if i == 0 else ''
            row = [area_cell, ps(comp)] + notas
            data_rows.append(row)
    
    # Separador "Parte Diversificada"
    div_row = [pcb('PARTE<br/>DIVERSIFICADA'), '', '', '', '', '', '', '', '', '', '']
    data_rows.append(div_row)
    div_row_idx = len(data_rows) - 1
    
    # Componentes diversificados
    for comp in COMPONENTES_DIVERSIFICADA:
        notas = []
        for s in SERIES:
            rec = records_map.get(s, {})
            grades = rec.get('grades', {})
            nota = grades.get(comp, '')
            if not nota:
                comp_lower = comp.lower()
                for k, v in grades.items():
                    if k.lower() == comp_lower or comp_lower in k.lower():
                        nota = v
                        break
            notas.append(pc(str(nota) if nota else ''))
        
        row = ['', ps(comp)] + notas
        data_rows.append(row)
    
    # Linha de Carga Horária Anual
    ch_row = [pcb('CARGA HORÁRIA ANUAL'), '']
    for s in SERIES:
        rec = records_map.get(s, {})
        ch = rec.get('carga_horaria', '')
        ch_row.append(pc(str(ch) if ch else ''))
    data_rows.append(ch_row)
    ch_row_idx = len(data_rows) - 1
    
    # Linha de Resultado
    res_row = [pcb('RESULTADO'), '']
    for s in SERIES:
        rec = records_map.get(s, {})
        resultado = rec.get('resultado', '')
        res_row.append(pc(str(resultado).upper() if resultado else ''))
    data_rows.append(res_row)
    res_row_idx = len(data_rows) - 1
    
    # Linha de Ano Letivo
    ano_row = [pcb('ANO LETIVO'), '']
    for s in SERIES:
        rec = records_map.get(s, {})
        ano = rec.get('ano_letivo', '')
        ano_row.append(pc(str(ano) if ano else ''))
    data_rows.append(ano_row)
    ano_row_idx = len(data_rows) - 1
    
    # Linha de Escola
    esc_row = [pcb('ESTABELECIMENTO'), '']
    for s in SERIES:
        rec = records_map.get(s, {})
        escola = rec.get('escola', '')
        esc_row.append(ps(str(escola).upper() if escola else ''))
    data_rows.append(esc_row)
    esc_row_idx = len(data_rows) - 1
    
    # Linha Cidade/UF
    city_row = [pcb('CIDADE / UF'), '']
    for s in SERIES:
        rec = records_map.get(s, {})
        cidade = rec.get('cidade', '')
        uf = rec.get('uf', '')
        city_row.append(ps(f"{cidade}/{uf}" if cidade else ''))
    data_rows.append(city_row)
    city_row_idx = len(data_rows) - 1
    
    # Criar tabela
    main_table = Table(data_rows, colWidths=col_widths, repeatRows=2)
    
    # Estilo da tabela
    table_style = [
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 1),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ('FONTSIZE', (0, 0), (-1, -1), 6),
        
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 1), colors.Color(0.85, 0.85, 0.85)),
        ('SPAN', (0, 0), (0, 1)),  # Área de Conhecimento
        ('SPAN', (1, 0), (1, 1)),  # Componentes
        ('SPAN', (2, 0), (4, 0)),  # CICLO I
        ('SPAN', (5, 0), (6, 0)),  # CICLO II
        ('SPAN', (7, 0), (8, 0)),  # CICLO III
        ('SPAN', (9, 0), (10, 0)),  # CICLO IV
        
        # Parte Diversificada header
        ('SPAN', (0, div_row_idx), (1, div_row_idx)),
        ('BACKGROUND', (0, div_row_idx), (-1, div_row_idx), colors.Color(0.9, 0.9, 0.9)),
        
        # Carga Horária, Resultado, Ano, Escola, Cidade rows
        ('SPAN', (0, ch_row_idx), (1, ch_row_idx)),
        ('SPAN', (0, res_row_idx), (1, res_row_idx)),
        ('SPAN', (0, ano_row_idx), (1, ano_row_idx)),
        ('SPAN', (0, esc_row_idx), (1, esc_row_idx)),
        ('SPAN', (0, city_row_idx), (1, city_row_idx)),
        ('BACKGROUND', (0, ch_row_idx), (1, ch_row_idx), colors.Color(0.93, 0.93, 0.93)),
        ('BACKGROUND', (0, res_row_idx), (1, res_row_idx), colors.Color(0.93, 0.93, 0.93)),
        ('BACKGROUND', (0, ano_row_idx), (1, ano_row_idx), colors.Color(0.93, 0.93, 0.93)),
        ('BACKGROUND', (0, esc_row_idx), (1, esc_row_idx), colors.Color(0.93, 0.93, 0.93)),
        ('BACKGROUND', (0, city_row_idx), (1, city_row_idx), colors.Color(0.93, 0.93, 0.93)),
    ]
    
    # Merge vertical das áreas BNCC
    row_idx = 2  # start after headers
    for area, componentes in COMPONENTES_BNCC.items():
        n = len(componentes)
        if n > 1:
            table_style.append(('SPAN', (0, row_idx), (0, row_idx + n - 1)))
        row_idx += n
    
    main_table.setStyle(TableStyle(table_style))
    elements.append(main_table)
    elements.append(Spacer(1, 3*mm))
    
    # ===== OBSERVAÇÕES =====
    obs_text = history.get('observations', '')
    media_aprov = history.get('media_aprovacao', 6.0)
    
    obs_content = f"""<b>Observações:</b> Média de Aprovação: {media_aprov}<br/>
    APV = Aprovado | REP = Reprovado | DIS = Dispensado | E = Em andamento<br/>
    {obs_text if obs_text else ''}<br/><br/>
    <b>Legenda:</b><br/>
    C - Consolidado (7,1 – 10,0) | ED - Em Desenvolvimento (3,1 – 7,0) | ND - Não Desenvolvido (0 – 3,0)<br/><br/>
    LDBN N° 9394/96, RESOLUÇÃO CEE-PA nº 001/2010."""
    
    elements.append(Paragraph(obs_content, style_obs))
    elements.append(Spacer(1, 8*mm))
    
    # ===== DATA E LOCAL =====
    mant_city = mantenedora.get('cidade', mantenedora.get('city', ''))
    mant_uf = mantenedora.get('uf', mantenedora.get('state', 'PA'))
    
    from datetime import datetime
    now = datetime.now()
    meses = ['', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    data_extenso = f"{mant_city} - {mant_uf}, {now.day} de {meses[now.month]} de {now.year}."
    
    elements.append(Paragraph(data_extenso, style_center))
    elements.append(Spacer(1, 12*mm))
    
    # ===== ASSINATURAS =====
    sig_data = [
        ['_' * 35, '', '_' * 35],
        [Paragraph('Secretário(a)', style_center), '', Paragraph('Diretor(a)', style_center)]
    ]
    sig_table = Table(sig_data, colWidths=[usable_width * 0.4, usable_width * 0.2, usable_width * 0.4])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
