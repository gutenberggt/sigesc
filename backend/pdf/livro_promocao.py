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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak, Flowable, Spacer, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W, PAGE_H = landscape(A4)
MX = 0.8 * cm
USABLE_W = PAGE_W - 2 * MX
FIXED_W = 0.6 * cm + 3.8 * cm + 0.5 * cm  # N° + Nome + Sexo


# ── Flowable: texto vertical ────────────────────────────────
class VerticalText(Flowable):
    def __init__(self, text, font='Helvetica-Bold', size=6, text_color=colors.white):
        Flowable.__init__(self)
        self.text = str(text or '')
        self.font = font
        self.size = size
        self.text_color = text_color
        self.width = size + 4
        self.height = stringWidth(self.text, font, size) + 6

    def draw(self):
        self.canv.saveState()
        self.canv.setFont(self.font, self.size)
        self.canv.setFillColor(self.text_color)
        self.canv.rotate(90)
        self.canv.drawString(3, -self.size - 1, self.text)
        self.canv.restoreState()


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
def generate_livro_promocao_pdf(school, class_info, students_data, courses, academic_year, mantenedora=None):
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
    data_extenso = f"{mun} - {uf}, {today.day} de {meses[today.month-1]} de {today.year}"
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    escola_nome = str(school.get('name', ''))
    turma_nome = str(class_info.get('name', ''))
    grade_level = str(class_info.get('grade_level', ''))
    shift_raw = class_info.get('shift', '')
    turno = {'morning':'MATUTINO','afternoon':'VESPERTINO','evening':'NOTURNO',
             'full_time':'INTEGRAL','night':'NOTURNO'}.get(shift_raw, str(shift_raw).upper())

    # Separar componentes
    reg = [c for c in (courses or []) if not is_integral(c)]
    intg = [c for c in (courses or []) if is_integral(c)]
    has_integral = len(intg) > 0

    # Se não tem componentes regulares, usar todos como regulares
    if not reg:
        reg = courses or []
        intg = []
        has_integral = False

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

        # Cabeçalho
        y = PAGE_H - 0.6 * cm
        canvas_obj.setFont('Helvetica-Bold', 10)
        canvas_obj.drawString(MX, y, mant_nome.upper())
        y -= 12
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawString(MX, y, secretaria_nome)
        if slogan:
            y -= 10
            canvas_obj.setFont('Helvetica-Oblique', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(MX, y, f'"{slogan}"')
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
        """Cria tabela para um bimestre. Colunas: N° | Nome | S | [reg comps] | [int comps]"""
        show_int = include_integral and has_integral
        all_comps = reg + (intg if show_int else [])
        n = len(all_comps)
        nr = len(reg)

        # Header 1: título com span
        h1 = ['N°', 'NOME DO ALUNO', 'S']
        h1 += [f'NOTAS {title}'] + [''] * (nr - 1)
        if show_int:
            h1 += [f'PARTICIPAÇÃO {title}'] + [''] * (len(intg) - 1)

        # Header 2: nomes dos componentes
        h2 = ['', '', '']
        h2 += [VerticalText(abrev(c.get('name', ''))) for c in reg]
        if show_int:
            h2 += [VerticalText(abrev(c.get('name', ''))) for c in intg]

        # Dados
        rows = [h1, h2]
        for idx, st in enumerate(students_data, 1):
            row = [str(idx), str(st.get('studentName', '') or '')[:30], str(st.get('sex', '-') or '-')[:1]]
            gr = st.get('grades') or {}
            for c in all_comps:
                gi = gr.get(c.get('id', ''), {})
                if not isinstance(gi, dict):
                    gi = {}
                row.append(fmt(gi.get(bim_key)))
            rows.append(row)

        # Larguras
        note_w = (USABLE_W - FIXED_W) / n if n > 0 else 1 * cm
        cw = [0.6 * cm, 3.8 * cm, 0.5 * cm] + [note_w] * n

        tbl = Table(rows, colWidths=cw, repeatRows=2)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
            ('FONTSIZE', (0, 1), (-1, 1), 6),
            ('FONTSIZE', (0, 2), (-1, -1), 6),
            ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
            ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 2), (1, -1), 'LEFT'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),
            # Span do título NOTAS
            ('SPAN', (3, 0), (3 + nr - 1, 0)),
            ('LINEAFTER', (3 + nr - 1, 0), (3 + nr - 1, -1), 1.5, colors.black),
        ]

        if show_int:
            col_int_start = 3 + nr
            col_int_end = col_int_start + len(intg) - 1
            style.append(('SPAN', (col_int_start, 0), (col_int_end, 0)))
            style.append(('BACKGROUND', (col_int_start, 0), (col_int_end, 0), colors.HexColor('#4a148c')))
            style.append(('BACKGROUND', (col_int_start, 1), (col_int_end, 1), colors.HexColor('#7b1fa2')))

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
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
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

    # ── Build ────────────────────────────────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.0 * cm, bottomMargin=4.2 * cm)
    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)

    # Atualizar total de páginas se diferente do estimado
    # (não precisa de 2-pass pois é apenas informativo)
    buffer.seek(0)
    return buffer
