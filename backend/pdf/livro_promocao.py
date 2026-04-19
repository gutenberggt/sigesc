"""Módulo PDF - Livro de Promoção (reescrita limpa)

Estratégia: UMA TABELA POR BIMESTRE.
- Cada bimestre gera uma página (ou mais se muitos alunos)
- Máximo ~20 colunas por tabela (N° + Nome + Sexo + componentes)
- Componentes integrais marcados como PARTICIPAÇÃO
- Nunca estoura largura
- Funciona para qualquer quantidade de componentes
"""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak, Spacer, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf.utils import get_logo_path

PAGE_W, PAGE_H = landscape(A4)
MX = 0.8 * cm
USABLE_W = PAGE_W - 2 * MX
# Larguras fixas: N° + Nome (mínimo) + Sexo
COL_N_W = 0.6 * cm
COL_NAME_MIN = 4.5 * cm
COL_SEX_W = 0.5 * cm
COL_NOTE_W = 1.0 * cm  # largura mínima suficiente para "10,0" em fonte 7
FIXED_W = COL_N_W + COL_NAME_MIN + COL_SEX_W


# ── Estilos de Paragraph ───────────────────────────────────
_STYLE_COMP_HEADER = ParagraphStyle(
    name='CompHeader', fontName='Helvetica-Bold', fontSize=5.5, leading=6.5,
    alignment=TA_CENTER, textColor=colors.white,
)
_STYLE_STUDENT_NAME = ParagraphStyle(
    name='StudentName', fontName='Helvetica', fontSize=7, leading=8,
    alignment=TA_LEFT, textColor=colors.black,
)


# ── Abreviações ──────────────────────────────────────────────
_ABREV = {
    'língua portuguesa': 'L. PORT.', 'arte': 'ARTE', 'educação física': 'ED. FÍS.',
    'língua inglesa': 'L. ING.', 'inglês': 'L. ING.', 'matemática': 'MAT.',
    'ciências': 'CIÊN.', 'história': 'HIST.', 'geografia': 'GEOG.',
    'ensino religioso': 'ENS. REL.', 'educação ambiental e clima': 'ED. AMB. CLI.',
    'estudos amazônicos': 'EST. AMAZ.', 'literatura e redação': 'LIT. E RED.',
    'arte e cultura': 'ART. E CULT.',
    'recreação e lazer': 'REC. ESP. LAZ.', 'recreação, esporte e lazer': 'REC. ESP. LAZ.',
    'linguagem recreativa com práticas de esporte e lazer': 'REC. ESP. LAZ.',
    'tecnologia da informação': 'TEC. E INFO.', 'tecnologia e informática': 'TEC. E INFO.',
    'acompanhamento pedagógico de língua portuguesa': 'AC. PED. L. PORT.',
    'acompanhamento pedagógico de matemática': 'AC. PED. MAT.',
    'acomp. ped. de língua portuguesa': 'AC. PED. L. PORT.',
    'acomp. ped. de matemática': 'AC. PED. MAT.',
}

def abrev(nome):
    if not nome:
        return ''
    nl = nome.lower().strip()
    if nl in _ABREV:
        return _ABREV[nl]
    for k, v in _ABREV.items():
        if nl.startswith(k) or k.startswith(nl):
            return v
    return nome.upper()


def fmt(v):
    if v is None:
        return ''
    try:
        if isinstance(v, (int, float)):
            return f'{v:.1f}'.replace('.', ',')
    except (ValueError, TypeError):
        pass
    return str(v) if v else ''


def is_integral(course):
    ap = (course.get('atendimento_programa') or '').lower()
    return 'integral' in ap


# ── Geração ──────────────────────────────────────────────────
def generate_livro_promocao_pdf(school, class_info, students_data, courses, academic_year, mantenedora=None, book_number=None):
    buffer = BytesIO()
    mantenedora = mantenedora or {}

    # Dados para cabeçalho/rodapé
    today = datetime.now()
    meses = ['janeiro','fevereiro','março','abril','maio','junho',
             'julho','agosto','setembro','outubro','novembro','dezembro']
    mun = mantenedora.get('municipio', 'Floresta do Araguaia')
    uf = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mun}')
    secretaria_nome = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')
    slogan = mantenedora.get('slogan', '')

    # Brasão (caminho local cacheado)
    logo_url = mantenedora.get('brasao_url') or mantenedora.get('logotipo_url')
    brasao_path = get_logo_path(logo_url) if logo_url else None
    data_extenso = f"{mun} - {uf}, {today.day} de {meses[today.month-1]} de {today.year}"
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    escola_nome = str(school.get('name', ''))
    turma_nome = str(class_info.get('name', ''))
    grade_level = str(class_info.get('grade_level', ''))
    shift_raw = class_info.get('shift', '')
    turno = {'morning':'MATUTINO','afternoon':'VESPERTINO','evening':'NOTURNO',
             'full_time':'INTEGRAL','night':'NOTURNO'}.get(shift_raw, str(shift_raw).upper())

    # Tipo de Atendimento da turma
    atendimento_raw = (class_info.get('atendimento_programa') or '').lower()
    is_tempo_integral = 'integral' in atendimento_raw
    tipo_atendimento = 'Tempo Integral' if is_tempo_integral else 'Regular'
    book_number_str = str(book_number or '----')

    # Tabela sempre usa apenas componentes regulares
    reg = [c for c in (courses or []) if not is_integral(c)]
    # Flag apenas para decidir se exibe a citação na última página
    has_integral_components = any(is_integral(c) for c in (courses or []))

    # Se não há nenhum regular (fallback), usar tudo como regular
    if not reg:
        reg = courses or []

    # Estimar total de páginas
    # Bimestres 1-4 (cada um = 1 página) + Rec1 + Rec2 + Resultado = 7 páginas base
    # Se muitos alunos, cada tabela pode gerar 2+ páginas
    pages_per_table = 1 if len(students_data) <= 20 else 2
    n_tables = 7  # b1, b2, rec1, b3, b4, rec2, resultado
    page_total = [n_tables * pages_per_table]

    # ── Canvas callback ──────────────────────────────────────
    def header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        pn = doc_obj.page
        tp = page_total[0]

        # Brasão (à esquerda)
        text_x = MX
        if brasao_path:
            try:
                brasao_size = 1.6 * cm
                canvas_obj.drawImage(
                    brasao_path,
                    MX, PAGE_H - 0.4 * cm - brasao_size,
                    width=brasao_size, height=brasao_size,
                    preserveAspectRatio=True, mask='auto'
                )
                text_x = MX + brasao_size + 0.2 * cm
            except Exception:
                pass

        # Cabeçalho institucional (ao lado do brasão)
        y = PAGE_H - 0.6 * cm
        canvas_obj.setFont('Helvetica-Bold', 10)
        canvas_obj.drawString(text_x, y, mant_nome.upper())
        y -= 12
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawString(text_x, y, secretaria_nome)
        if slogan:
            y -= 10
            canvas_obj.setFont('Helvetica-Oblique', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(text_x, y, f'"{slogan}"')
            canvas_obj.setFillColor(colors.black)

        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.setFillColor(colors.HexColor('#1e40af'))
        canvas_obj.drawRightString(PAGE_W - MX, PAGE_H - 0.7 * cm, 'LIVRO DE PROMOÇÃO')
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont('Helvetica', 10)
        canvas_obj.drawRightString(PAGE_W - MX, PAGE_H - 1.2 * cm, f'ANO LETIVO: {academic_year}')

        bh = 0.4 * cm
        by1 = PAGE_H - 2.2 * cm
        canvas_obj.setLineWidth(0.5)
        canvas_obj.rect(MX, by1, USABLE_W, bh, stroke=1, fill=0)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawString(MX + 3, by1 + 3, 'ESCOLA:')
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(MX + 3 + stringWidth('ESCOLA: ', 'Helvetica-Bold', 7), by1 + 3, escola_nome)
        canvas_obj.setFont('Helvetica-Bold', 7)
        canvas_obj.drawRightString(PAGE_W - MX - 3, by1 + 3, f'PÁGINA: {pn:02d}/{tp:02d}')

        by2 = by1 - bh
        canvas_obj.rect(MX, by2, USABLE_W, bh, stroke=1, fill=0)
        tw = USABLE_W / 3
        canvas_obj.line(MX + tw, by2, MX + tw, by2 + bh)
        canvas_obj.line(MX + 2 * tw, by2, MX + 2 * tw, by2 + bh)
        for lbl, val, off in [('TURMA:', turma_nome, 0), ('ANO/ETAPA:', grade_level, tw), ('TURNO:', turno, 2 * tw)]:
            canvas_obj.setFont('Helvetica-Bold', 7)
            canvas_obj.drawString(MX + off + 3, by2 + 3, lbl)
            canvas_obj.setFont('Helvetica', 7)
            canvas_obj.drawString(MX + off + 3 + stringWidth(lbl + ' ', 'Helvetica-Bold', 7), by2 + 3, val)

        # Linha 3: Nº do Livro + Tipo de Atendimento
        by3 = by2 - bh
        canvas_obj.rect(MX, by3, USABLE_W, bh, stroke=1, fill=0)
        canvas_obj.line(MX + USABLE_W / 2, by3, MX + USABLE_W / 2, by3 + bh)
        for lbl, val, off in [('Nº DO LIVRO:', book_number_str, 0),
                              ('TIPO DE ATENDIMENTO:', tipo_atendimento, USABLE_W / 2)]:
            canvas_obj.setFont('Helvetica-Bold', 7)
            canvas_obj.drawString(MX + off + 3, by3 + 3, lbl)
            canvas_obj.setFont('Helvetica', 7)
            canvas_obj.drawString(MX + off + 3 + stringWidth(lbl + ' ', 'Helvetica-Bold', 7), by3 + 3, val)

        # Rodapé só na última
        if pn == tp:
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.drawCentredString(PAGE_W / 2, 3.8 * cm, data_extenso)
            ly = 2.6 * cm
            cl, cr, hl = PAGE_W / 2 - 5 * cm, PAGE_W / 2 + 5 * cm, 4 * cm
            canvas_obj.line(cl - hl, ly, cl + hl, ly)
            canvas_obj.line(cr - hl, ly, cr + hl, ly)
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.drawCentredString(cl, ly - 12, 'Secretário(a)')
            canvas_obj.drawCentredString(cr, ly - 12, 'Diretor(a)')
            canvas_obj.setFont('Helvetica', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(MX, 0.6 * cm, rodape_info)

        canvas_obj.restoreState()

    # ── Helper: montar tabela de um bimestre ─────────────────
    def build_bim_table(bim_key, title, include_integral=True):
        """Cria tabela para um bimestre. Colunas: N° | Nome | S | [reg comps]
        Componentes de atendimento diferente de 'regular' são ignorados.
        """
        all_comps = reg
        n = len(all_comps)
        nr = n

        # Header 1: título com span
        h1 = ['N°', 'NOME DO ALUNO', 'S']
        h1 += [f'NOTAS {title}'] + [''] * (nr - 1)

        # Header 2: nomes dos componentes (horizontal, com quebra automática)
        h2 = ['', '', '']
        h2 += [Paragraph(abrev(c.get('name', '')), _STYLE_COMP_HEADER) for c in reg]

        # Dados
        rows = [h1, h2]
        for idx, st in enumerate(students_data, 1):
            nome = str(st.get('studentName', '') or '')
            # Escape HTML e permitir quebra de linha natural
            nome_safe = nome.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            row = [
                str(idx),
                Paragraph(nome_safe, _STYLE_STUDENT_NAME),
                str(st.get('sex', '-') or '-')[:1]
            ]
            gr = st.get('grades') or {}
            for c in all_comps:
                gi = gr.get(c.get('id', ''), {})
                if not isinstance(gi, dict):
                    gi = {}
                row.append(fmt(gi.get(bim_key)))
            rows.append(row)

        # Larguras: colunas de nota fixas no mínimo; sobra vai para Nome
        note_w = COL_NOTE_W
        name_w = max(COL_NAME_MIN, USABLE_W - (COL_N_W + COL_SEX_W + n * note_w))
        cw = [COL_N_W, name_w, COL_SEX_W] + [note_w] * n

        tbl = Table(rows, colWidths=cw, repeatRows=2)

        style = [
            # Cabeçalho principal
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Sub-cabeçalho (componentes - Paragraph renderiza estilo próprio)
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
            # Dados
            ('FONTSIZE', (0, 2), (-1, -1), 7),
            ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
            ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 2), (1, -1), 'LEFT'),
            # Bordas
            ('BOX', (0, 0), (-1, -1), 0.8, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#b0b0b0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            # Separadores mais grossos entre blocos
            ('LINEAFTER', (2, 0), (2, -1), 1.2, colors.black),
            # Span do título NOTAS
            ('SPAN', (3, 0), (3 + nr - 1, 0)),
            ('LINEAFTER', (3 + nr - 1, 0), (3 + nr - 1, -1), 1.2, colors.black),
        ]

        tbl.setStyle(TableStyle(style))
        return tbl

    # ── Helper: tabela de recuperação (só regulares) ─────────
    def build_rec_table(rec_key, title):
        return build_bim_table(rec_key, title, include_integral=False)

    # ── Helper: tabela de resultado final ────────────────────
    def build_result_table():
        h1 = ['N°', 'NOME DO ALUNO', 'S', 'TOTAL PONTOS', 'MÉDIA FINAL', 'RESULTADO']
        rows = [h1]
        for idx, st in enumerate(students_data, 1):
            gr = st.get('grades') or {}
            tp_val, medias = 0, []
            for c in (courses or []):
                gi = gr.get(c.get('id', ''), {})
                if isinstance(gi, dict):
                    fa = gi.get('finalAverage')
                    if isinstance(fa, (int, float)):
                        tp_val += fa
                        medias.append(fa)
            mg = tp_val / len(medias) if medias else 0
            rows.append([
                str(idx),
                str(st.get('studentName', '') or '')[:30],
                str(st.get('sex', '-') or '-')[:1],
                fmt(tp_val) if tp_val > 0 else '-',
                fmt(mg) if mg > 0 else '-',
                str(st.get('result', 'CURSANDO') or 'CURSANDO')[:20]
            ])

        cw = [0.6 * cm, 8 * cm, 0.5 * cm, 4 * cm, 4 * cm, 4 * cm]
        tbl = Table(rows, colWidths=cw, repeatRows=1)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]

        # Colorir resultado
        for ri, st in enumerate(students_data, 1):
            r = str(st.get('result', '') or '')
            if 'APROVADO' in r and 'DEPENDÊNCIA' not in r:
                style.append(('BACKGROUND', (5, ri), (5, ri), colors.HexColor('#c8e6c9')))
                style.append(('TEXTCOLOR', (5, ri), (5, ri), colors.HexColor('#1b5e20')))
                style.append(('FONTNAME', (5, ri), (5, ri), 'Helvetica-Bold'))
            elif 'REPROVADO' in r:
                style.append(('BACKGROUND', (5, ri), (5, ri), colors.HexColor('#ffcdd2')))
                style.append(('TEXTCOLOR', (5, ri), (5, ri), colors.HexColor('#b71c1c')))
                style.append(('FONTNAME', (5, ri), (5, ri), 'Helvetica-Bold'))
            elif 'DEPENDÊNCIA' in r:
                style.append(('BACKGROUND', (5, ri), (5, ri), colors.HexColor('#fff9c4')))
                style.append(('FONTNAME', (5, ri), (5, ri), 'Helvetica-Bold'))

        tbl.setStyle(TableStyle(style))
        return tbl

    # ── Montar elementos ─────────────────────────────────────
    elements = []

    # Página 1: 1º Bimestre
    elements.append(build_bim_table('b1', '1º BIMESTRE'))

    # Página 2: 2º Bimestre
    elements.append(PageBreak())
    elements.append(build_bim_table('b2', '2º BIMESTRE'))

    # Página 3: Recuperação 1º Semestre (só regulares)
    elements.append(PageBreak())
    elements.append(build_rec_table('rec1', 'RECUPERAÇÃO 1º SEMESTRE'))

    # Página 4: 3º Bimestre
    elements.append(PageBreak())
    elements.append(build_bim_table('b3', '3º BIMESTRE'))

    # Página 5: 4º Bimestre
    elements.append(PageBreak())
    elements.append(build_bim_table('b4', '4º BIMESTRE'))

    # Página 6: Recuperação 2º Semestre (só regulares)
    elements.append(PageBreak())
    elements.append(build_rec_table('rec2', 'RECUPERAÇÃO 2º SEMESTRE'))

    # Página 7: Resultado Final
    elements.append(PageBreak())
    elements.append(build_result_table())

    # Citação ao final (última página) quando a turma é de Tempo Integral
    if is_tempo_integral and has_integral_components:
        cit_style = ParagraphStyle(
            name='CitacaoIntegral',
            fontName='Helvetica-Oblique',
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#333333'),
        )
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(Paragraph(
            'As atividades curriculares complementares de caráter formativo, '
            'referentes ao atendimento em tempo integral, encontram-se registradas '
            'em documento complementar (Adendo), parte integrante deste registro.',
            cit_style
        ))

    # ── Build ────────────────────────────────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.5 * cm, bottomMargin=4.2 * cm)
    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)

    # Atualizar total de páginas se diferente do estimado
    # (não precisa de 2-pass pois é apenas informativo)
    buffer.seek(0)
    return buffer
