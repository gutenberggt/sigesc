"""
Módulo de geração de PDF do Histórico Escolar.
Layout moderno e elegante com cantos arredondados.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import logging

logger = logging.getLogger(__name__)

# === Paleta de cores moderna ===
PRIMARY = colors.Color(0.12, 0.25, 0.42)       # Azul escuro elegante
PRIMARY_LIGHT = colors.Color(0.18, 0.35, 0.55)  # Azul médio
ACCENT = colors.Color(0.16, 0.50, 0.45)         # Teal/verde escuro
HEADER_BG = colors.Color(0.12, 0.25, 0.42)      # Fundo cabeçalho tabela
HEADER_BG2 = colors.Color(0.22, 0.38, 0.58)     # Fundo sub-cabeçalho
ROW_ALT = colors.Color(0.95, 0.97, 1.0)         # Linhas alternadas
ROW_WHITE = colors.white
SECTION_BG = colors.Color(0.88, 0.93, 0.98)     # Fundo seções especiais
BORDER_COLOR = colors.Color(0.78, 0.82, 0.88)   # Bordas suaves
LABEL_BG = colors.Color(0.93, 0.95, 0.98)       # Fundo labels
TEXT_DARK = colors.Color(0.15, 0.15, 0.15)
TEXT_MED = colors.Color(0.35, 0.35, 0.35)
FOOTER_LINE = colors.Color(0.12, 0.25, 0.42)

# Componentes curriculares
COMPONENTES_BNCC = {
    "Linguagens": ["Língua Portuguesa", "Arte", "Educação Física", "Língua Inglesa"],
    "Matemática": ["Matemática"],
    "Ciências da Natureza": ["Ciências"],
    "Ciências Humanas": ["História", "Geografia", "Ensino Religioso"]
}
COMPONENTES_DIVERSIFICADA = [
    "Ed. Ambiental e Clima", "Estudos Amazônicos", "Literatura e Redação"
]
CAMPOS_INTEGRADORES = [
    "Acomp. Pedagógico", "Recreação, Esporte e Lazer", "Arte e Cultura", "Tecnologia e Informática"
]
SERIES = ["1º", "2º", "3º", "4º", "5º", "6º", "7º", "8º", "9º"]


def get_logo_image(width=1.5*cm, height=1.5*cm, logo_url=None):
    """Tenta carregar logo da mantenedora."""
    if not logo_url:
        return None
    try:
        import urllib.request
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        urllib.request.urlretrieve(logo_url, tmp.name)
        return Image(tmp.name, width=width, height=height)
    except Exception:
        return None


def build_header(uw, mantenedora, logo_url):
    """Constrói o cabeçalho com Table nativa (fundo colorido confiável)."""
    mant_nome = mantenedora.get('nome', 'Prefeitura Municipal')
    mant_secretaria = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')

    # Endereço
    end_parts = []
    if mantenedora.get('logradouro'):
        addr = mantenedora['logradouro']
        if mantenedora.get('numero'):
            addr += f", {mantenedora['numero']}"
        if mantenedora.get('complemento'):
            addr += f" - {mantenedora['complemento']}"
        end_parts.append(addr)
    if mantenedora.get('bairro'):
        end_parts.append(mantenedora['bairro'])
    city_state = []
    if mantenedora.get('municipio'):
        city_state.append(mantenedora['municipio'])
    if mantenedora.get('estado'):
        city_state.append(mantenedora['estado'])
    if city_state:
        end_parts.append(' - '.join(city_state))
    if mantenedora.get('cep'):
        end_parts.append(f"CEP: {mantenedora['cep']}")
    if mantenedora.get('telefone'):
        end_parts.append(f"Tel: {mantenedora['telefone']}")
    mant_endereco = '  |  '.join(end_parts) if end_parts else ''

    s_black_bold_lg = ParagraphStyle('hdr_lg', fontName='Helvetica-Bold', fontSize=11, leading=13, alignment=TA_LEFT, textColor=TEXT_DARK)
    s_black_bold = ParagraphStyle('hdr_sec', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=TA_LEFT, textColor=TEXT_DARK)
    s_black_bold_title = ParagraphStyle('hdr_title', fontName='Helvetica-Bold', fontSize=13, leading=15, alignment=TA_RIGHT, textColor=TEXT_DARK)
    s_black_sub = ParagraphStyle('hdr_sub', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_RIGHT, textColor=TEXT_MED)
    s_addr = ParagraphStyle('hdr_addr', fontName='Helvetica-Bold', fontSize=6, leading=8, alignment=TA_CENTER, textColor=TEXT_DARK)

    logo = get_logo_image(width=1.5*cm, height=1.5*cm, logo_url=logo_url)

    # Linha principal: Logo | Nome+Secretaria | Título
    left_content = [
        Paragraph(mant_nome.upper(), s_black_bold_lg),
        Paragraph(mant_secretaria, s_black_bold),
    ]
    right_content = [
        Paragraph('HISTÓRICO ESCOLAR', s_black_bold_title),
        Paragraph('Ensino Fundamental', s_black_sub),
    ]

    logo_w = 2 * cm if logo else 0
    right_w = 6.5 * cm
    left_w = uw - logo_w - right_w

    if logo:
        main_row = [[logo, left_content, right_content]]
        col_widths = [logo_w, left_w, right_w]
    else:
        main_row = [[left_content, right_content]]
        col_widths = [uw - right_w, right_w]

    main_table = Table(main_row, colWidths=col_widths, rowHeights=[1.6 * cm])
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (0, 0), 8),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 8),
    ]
    main_table.setStyle(TableStyle(style_cmds))

    # Linha de endereço
    addr_row = [[Paragraph(mant_endereco, s_addr)]]
    addr_table = Table(addr_row, colWidths=[uw], rowHeights=[0.55 * cm])
    addr_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LABEL_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))

    # Wrapper table para unir as duas linhas com cantos arredondados
    wrapper_data = [[main_table], [addr_table]]
    wrapper = Table(wrapper_data, colWidths=[uw])
    wrapper.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    return wrapper


def generate_historico_escolar_pdf(student, school, mantenedora, history, **kwargs):
    """Gera o PDF do Histórico Escolar com layout moderno."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1 * cm, rightMargin=1 * cm,
        topMargin=0.8 * cm, bottomMargin=0.8 * cm
    )
    width, height = A4
    uw = width - 2 * cm  # usable width

    # === Estilos ===
    def make_style(name, size=6.5, bold=False, align=TA_LEFT, color=TEXT_DARK, leading=None):
        return ParagraphStyle(
            name, fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=size, leading=leading or size + 2.5,
            alignment=align, textColor=color
        )

    s_label = make_style('lbl', 6, bold=True, color=PRIMARY)
    s_value = make_style('val', 6.5)
    s_center = make_style('ctr', 6, align=TA_CENTER)
    s_center_b = make_style('ctrb', 6, bold=True, align=TA_CENTER, color=colors.white)
    s_center_dark = make_style('ctrd', 6, bold=True, align=TA_CENTER, color=PRIMARY)
    s_small = make_style('sm', 5.5, align=TA_CENTER)
    s_small_b = make_style('smb', 5.5, bold=True, align=TA_CENTER, color=PRIMARY)
    s_obs = make_style('obs', 6, leading=8.5)
    s_obs_b = make_style('obsb', 6, bold=True, color=PRIMARY, leading=8.5)
    s_footer = make_style('ftr', 7, align=TA_CENTER, color=TEXT_MED)
    s_sig = make_style('sig', 7, align=TA_CENTER, color=TEXT_DARK)
    s_area = make_style('area', 5.5, bold=True, align=TA_CENTER, color=PRIMARY)
    s_comp = make_style('comp', 5.5, align=TA_LEFT)
    s_nota = make_style('nota', 6, align=TA_CENTER, color=TEXT_DARK)

    mantenedora = mantenedora or {}
    records = history.get('records', [])
    records_map = {r.get('serie', ''): r for r in records}

    elements = []

    # ===== CABEÇALHO COM BANNER =====
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    elements.append(build_header(uw, mantenedora, logo_url))
    elements.append(Spacer(1, 3 * mm))

    # ===== DADOS DO ALUNO (caixa arredondada) =====
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

    p_lbl = lambda t: Paragraph(t, s_label)
    p_val = lambda t: Paragraph(t, s_value)

    student_data = [
        [p_lbl('ALUNO(A)'), p_val(nome), p_lbl('NASCIMENTO'), p_val(nascimento)],
        [p_lbl('FILIAÇÃO'), p_val(f"Pai: {pai}"), p_lbl('CPF'), p_val(cpf)],
        [p_lbl(''), p_val(f"Mãe: {mae}"), p_lbl('RG'), p_val(rg)],
        [p_lbl('NATURALIDADE'), p_val(f"{naturalidade} - {uf_nasc}"), p_lbl('CÓD. INEP'), p_val(inep)],
        [p_lbl('ESCOLA'), p_val(school_name), '', ''],
    ]

    lbl_w = 2 * cm
    val_w = uw / 2 - lbl_w
    student_table = Table(student_data, colWidths=[lbl_w, val_w, lbl_w, val_w])
    student_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (0, -1), LABEL_BG),
        ('BACKGROUND', (2, 0), (2, -1), LABEL_BG),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, BORDER_COLOR),
        ('LINEBELOW', (0, -1), (-1, -1), 0.3, BORDER_COLOR),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('SPAN', (1, 4), (3, 4)),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 2.5 * mm))

    # ===== TABELA PRINCIPAL =====
    note_col_w = (uw - 1.6 * cm - 2.8 * cm) / 9
    area_col_w = 1.6 * cm
    comp_col_w = 2.8 * cm

    col_widths = [area_col_w, comp_col_w] + [note_col_w] * 9

    pc = lambda t: Paragraph(t, s_nota)
    pcb = lambda t: Paragraph(t, s_center_b)
    pcd = lambda t: Paragraph(t, s_center_dark)
    pa = lambda t: Paragraph(t, s_area)
    pcomp = lambda t: Paragraph(t, s_comp)
    psm = lambda t: Paragraph(t, s_small)
    psmb = lambda t: Paragraph(t, s_small_b)

    # Header com ciclos
    header1 = [
        pcb('ÁREA'), pcb('COMPONENTE'),
        pcb('CICLO I'), '', '', pcb('CICLO II'), '', pcb('CICLO III'), '', pcb('CICLO IV'), ''
    ]
    header2 = [
        '', '',
        pcb('1º'), pcb('2º'), pcb('3º'), pcb('4º'), pcb('5º'), pcb('6º'), pcb('7º'), pcb('8º'), pcb('9º')
    ]
    data_rows = [header1, header2]

    # BNCC rows
    for area, componentes in COMPONENTES_BNCC.items():
        for i, comp in enumerate(componentes):
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
            area_cell = pa(area.upper()) if i == 0 else ''
            data_rows.append([area_cell, pcomp(comp)] + notas)

    # Parte diversificada header
    div_row = [pcd('PARTE DIVERSIFICADA'), '', '', '', '', '', '', '', '', '', '']
    data_rows.append(div_row)
    div_idx = len(data_rows) - 1

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
        data_rows.append(['', pcomp(comp)] + notas)

    # Campos personalizados da Parte Diversificada (só exibir se preenchidos)
    custom_diversificada = history.get('custom_diversificada', [])
    for custom in custom_diversificada:
        title = (custom.get('title') or '').strip()
        if not title:
            continue
        notas = []
        for s in SERIES:
            rec = records_map.get(s, {})
            grades = rec.get('grades', {})
            nota = grades.get(title, '')
            notas.append(pc(str(nota) if nota else ''))
        data_rows.append(['', pcomp(title)] + notas)

    # Campos Integradores Curricular I (dispensados de notas)
    ci_row = [pcd('CAMPOS INTEGRADORES CURRICULAR I'), '', '', '', '', '', '', '', '', '', '']
    data_rows.append(ci_row)
    ci_idx = len(data_rows) - 1

    for comp in CAMPOS_INTEGRADORES:
        data_rows.append(['', pcomp(comp)] + [pc('') for _ in SERIES])

    # Rodapé da tabela: CH, Resultado, Ano, Escola, Cidade
    footer_rows = [
        ('CARGA HORÁRIA ANUAL', 'carga_horaria'),
        ('RESULTADO', 'resultado'),
        ('ANO LETIVO', 'ano_letivo'),
        ('ESTABELECIMENTO', 'escola'),
        ('CIDADE / UF', None),
    ]
    footer_indices = {}
    for label, field in footer_rows:
        row = [psmb(label), '']
        for s in SERIES:
            rec = records_map.get(s, {})
            if field:
                val = rec.get(field, '')
                if field == 'resultado':
                    val = str(val).upper() if val else ''
                elif field == 'escola':
                    val = str(val).upper() if val else ''
                row.append(psm(str(val) if val else ''))
            else:
                cidade = rec.get('cidade', '')
                uf = rec.get('uf', '')
                row.append(psm(f"{cidade}/{uf}" if cidade else ''))
        data_rows.append(row)
        footer_indices[label] = len(data_rows) - 1

    # Build table
    main_table = Table(data_rows, colWidths=col_widths, repeatRows=2)

    style_cmds = [
        # Grid suave
        ('GRID', (0, 0), (-1, -1), 0.25, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),

        # Headers
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('BACKGROUND', (0, 1), (-1, 1), HEADER_BG2),
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (4, 0)),   # CICLO I
        ('SPAN', (5, 0), (6, 0)),   # CICLO II
        ('SPAN', (7, 0), (8, 0)),   # CICLO III
        ('SPAN', (9, 0), (10, 0)),  # CICLO IV

        # Parte diversificada
        ('SPAN', (0, div_idx), (1, div_idx)),
        ('BACKGROUND', (0, div_idx), (-1, div_idx), SECTION_BG),

        # Campos integradores
        ('SPAN', (0, ci_idx), (1, ci_idx)),
        ('BACKGROUND', (0, ci_idx), (-1, ci_idx), SECTION_BG),

        # Rounded corners
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]

    # Alternating row colors for BNCC data rows
    for i in range(2, div_idx):
        bg = ROW_ALT if i % 2 == 0 else ROW_WHITE
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))

    # Alternating row colors for diversificada rows (between div_idx and ci_idx)
    for i in range(div_idx + 1, ci_idx):
        bg = ROW_ALT if i % 2 == 0 else ROW_WHITE
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))

    # Alternating row colors for campos integradores rows
    for i in range(ci_idx + 1, ci_idx + 1 + len(CAMPOS_INTEGRADORES)):
        bg = ROW_ALT if i % 2 == 0 else ROW_WHITE
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))

    # Footer rows styling
    for label, idx in footer_indices.items():
        style_cmds.append(('SPAN', (0, idx), (1, idx)))
        style_cmds.append(('BACKGROUND', (0, idx), (1, idx), SECTION_BG))

    # Merge vertical das áreas BNCC
    row_idx = 2
    for area, componentes in COMPONENTES_BNCC.items():
        n = len(componentes)
        if n > 1:
            style_cmds.append(('SPAN', (0, row_idx), (0, row_idx + n - 1)))
        row_idx += n

    main_table.setStyle(TableStyle(style_cmds))
    elements.append(main_table)
    elements.append(Spacer(1, 3 * mm))

    # ===== OBSERVAÇÕES (caixa arredondada) =====
    obs_text = history.get('observations', '')
    media_aprov = history.get('media_aprovacao', 6.0)

    obs_lines = [
        Paragraph(f"<b>OBSERVAÇÕES</b>", make_style('obs_title', 7, bold=True, color=PRIMARY)),
        Spacer(1, 1.5 * mm),
        Paragraph(f"Média de Aprovação: <b>{media_aprov}</b>  |  APV = Aprovado  |  REP = Reprovado  |  DIS = Dispensado  |  E = Em andamento", s_obs),
        Paragraph("C = Consolidado (7,1-10,0)  |  ED = Em Desenvolvimento (3,1-7,0)  |  ND = Não Desenvolvido (0-3,0)", s_obs),
        Paragraph("LDBN N° 9394/96, RESOLUÇÃO CEE-PA nº 001/2010.", s_obs),
    ]
    if obs_text:
        obs_lines.append(Spacer(1, 1 * mm))
        obs_lines.append(Paragraph(obs_text, s_obs))

    obs_data = [[obs_lines]]
    obs_table = Table(obs_data, colWidths=[uw])
    obs_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ('BACKGROUND', (0, 0), (-1, -1), colors.Color(0.98, 0.98, 1.0)),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    elements.append(obs_table)
    elements.append(Spacer(1, 6 * mm))

    # ===== DATA E LOCAL =====
    mant_city = mantenedora.get('municipio', mantenedora.get('cidade', mantenedora.get('city', '')))
    mant_uf = mantenedora.get('estado', mantenedora.get('uf', mantenedora.get('state', 'PA')))

    from datetime import datetime
    now = datetime.now()
    meses = ['', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    data_extenso = f"{mant_city} - {mant_uf}, {now.day} de {meses[now.month]} de {now.year}."
    elements.append(Paragraph(data_extenso, s_footer))
    elements.append(Spacer(1, 10 * mm))

    # ===== ASSINATURAS =====
    line_w = uw * 0.38
    sig_data = [
        [
            Paragraph('_' * 42, make_style('line1', 7, align=TA_CENTER, color=BORDER_COLOR)),
            '',
            Paragraph('_' * 42, make_style('line2', 7, align=TA_CENTER, color=BORDER_COLOR)),
        ],
        [
            Paragraph('Secretário(a) Escolar', make_style('s1', 6.5, align=TA_CENTER, color=TEXT_MED)),
            '',
            Paragraph('Diretor(a)', make_style('s2', 6.5, align=TA_CENTER, color=TEXT_MED)),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[uw * 0.4, uw * 0.2, uw * 0.4])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
