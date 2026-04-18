"""Módulo PDF - Livro de Promoção
Paginação horizontal por componentes: divide em blocos de MAX_COMPONENTS_PER_PAGE.
Compatível com turmas regulares e integrais sem risco de estouro de largura.
"""
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak, Flowable
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf.utils import ordenar_componentes_por_nivel

PAGE_W, PAGE_H = landscape(A4)
MX = 0.8 * cm
USABLE_W = PAGE_W - 2 * MX
MAX_COMPONENTS_PER_PAGE = 8


class VerticalText(Flowable):
    def __init__(self, text, font='Helvetica-Bold', size=6, text_color=colors.white):
        Flowable.__init__(self)
        self.text = text or ''
        self.font = font
        self.size = size
        self.text_color = text_color
        self.width = size + 4
        self.height = stringWidth(self.text, font, size) + 6

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(self.font, self.size)
        c.setFillColor(self.text_color)
        c.rotate(90)
        c.drawString(3, -self.size - 1, self.text)
        c.restoreState()


# ── Abreviações ──────────────────────────────────────────────
ABREV = {
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

def _abrev(nome):
    if not nome:
        return ''
    nl = nome.lower().strip()
    if nl in ABREV:
        return ABREV[nl]
    for k, v in ABREV.items():
        if nl.startswith(k) or k.startswith(nl):
            return v
    return nome.upper()

def _fmt(v):
    if v is None:
        return ''
    try:
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
    except (ValueError, TypeError):
        return ''
    return str(v) if v else ''

def _safe(v, mx=30):
    if v is None:
        return ''
    return str(v)[:mx]

def _chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def generate_livro_promocao_pdf(
    school: Dict[str, Any],
    class_info: Dict[str, Any],
    students_data: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    academic_year: int,
    mantenedora: Dict[str, Any] = None
) -> BytesIO:

    buffer = BytesIO()
    mantenedora = mantenedora or {}

    # Dados do cabeçalho/rodapé
    today = datetime.now()
    meses = ['janeiro','fevereiro','março','abril','maio','junho',
             'julho','agosto','setembro','outubro','novembro','dezembro']
    mun = mantenedora.get('municipio', 'Floresta do Araguaia')
    uf = mantenedora.get('estado', 'PA')
    mant_nome = mantenedora.get('nome', f'Prefeitura Municipal de {mun}')
    secretaria = mantenedora.get('secretaria', 'Secretaria Municipal de Educação')
    slogan = mantenedora.get('slogan', '')
    data_extenso = f"{mun} - {uf}, {today.day} de {meses[today.month-1]} de {today.year}"
    rodape_info = f"Documento gerado em {today.strftime('%d/%m/%Y às %H:%M')} | Total de alunos: {len(students_data)}"
    escola_nome = school.get('name', '')
    turma_nome = class_info.get('name', '')
    grade_level = class_info.get('grade_level', '')
    shift_raw = class_info.get('shift', '')
    TURNOS = {'morning':'MATUTINO','afternoon':'VESPERTINO','evening':'NOTURNO','full_time':'INTEGRAL','night':'NOTURNO'}
    turno = TURNOS.get(shift_raw, shift_raw.upper() if shift_raw else '')

    nivel = class_info.get('education_level', '')
    courses_ord = ordenar_componentes_por_nivel(courses, nivel)
    if not courses_ord:
        courses_ord = courses or [{'id': '_', 'name': 'Componente'}]

    # Dividir componentes em chunks
    component_chunks = list(_chunk(courses_ord, MAX_COMPONENTS_PER_PAGE))
    # Estimar páginas: cada chunk gera 2 tabelas (sem1+sem2), cada tabela pode ocupar ~2 páginas com muitos alunos
    pages_per_table = 1 if len(students_data) <= 18 else 2 if len(students_data) <= 36 else 3
    total_pages_estimate = len(component_chunks) * 2 * pages_per_table

    # ── Header/Footer callback ───────────────────────────────
    page_total = [total_pages_estimate]

    def _header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        pn = doc_obj.page
        tp = page_total[0]

        y = PAGE_H - 0.6 * cm
        canvas_obj.setFont('Helvetica-Bold', 10)
        canvas_obj.drawString(MX, y, mant_nome.upper())
        y -= 12
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawString(MX, y, secretaria)
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

        # Rodapé só na última página
        if pn == tp:
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.drawCentredString(PAGE_W / 2, 3.8 * cm, data_extenso)
            ly = 2.6 * cm
            cl, cr, hl = PAGE_W / 2 - 5 * cm, PAGE_W / 2 + 5 * cm, 4 * cm
            canvas_obj.setLineWidth(0.5)
            canvas_obj.line(cl - hl, ly, cl + hl, ly)
            canvas_obj.line(cr - hl, ly, cr + hl, ly)
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.drawCentredString(cl, ly - 12, 'Secretário(a)')
            canvas_obj.drawCentredString(cr, ly - 12, 'Diretor(a)')
            canvas_obj.setFont('Helvetica', 7)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawString(MX, 0.6 * cm, rodape_info)

        canvas_obj.restoreState()

    # ── Estilos base da tabela ───────────────────────────────
    def _base_style(n_comp):
        return [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#3b5998')),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 6),
            ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
            ('FONTSIZE', (0, 2), (-1, -1), 6),
            ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
            ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 2), (1, -1), 'LEFT'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black),
            ('LINEAFTER', (2 + n_comp, 0), (2 + n_comp, -1), 1.5, colors.black),
            ('LINEAFTER', (2 + n_comp * 2, 0), (2 + n_comp * 2, -1), 1.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('SPAN', (3, 0), (3 + n_comp - 1, 0)),
            ('SPAN', (3 + n_comp, 0), (3 + n_comp * 2 - 1, 0)),
            ('SPAN', (3 + n_comp * 2, 0), (3 + n_comp * 3 - 1, 0)),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]

    # ── Montar elementos ─────────────────────────────────────
    elements = []

    # ===== SEMESTRE 1 (B1, B2, REC1) - para cada chunk =====
    for chunk_idx, chunk in enumerate(component_chunks):
        if chunk_idx > 0:
            elements.append(PageBreak())

        n_comp = len(chunk)
        names = [_abrev(c.get('name', '')) for c in chunk]

        header1 = ['N°', 'NOME DO ALUNO', 'S']
        header1 += ['NOTAS 1º BIMESTRE'] + [''] * (n_comp - 1)
        header1 += ['NOTAS 2º BIMESTRE'] + [''] * (n_comp - 1)
        header1 += ['RECUPERAÇÃO 1º SEMESTRE'] + [''] * (n_comp - 1)

        header2 = ['', '', '']
        for _ in range(3):
            header2 += [VerticalText(n) for n in names]

        data = [header1, header2]
        for idx, st in enumerate(students_data, 1):
            row = [str(idx), _safe(st.get('studentName', ''), 30), _safe(st.get('sex', '-'), 1)]
            gr = st.get('grades') or {}
            for bim in ('b1', 'b2', 'rec1'):
                for c in chunk:
                    gi = gr.get(c.get('id', ''), {})
                    if not isinstance(gi, dict):
                        gi = {}
                    row.append(_fmt(gi.get(bim)))
            data.append(row)

        total_cols = n_comp * 3
        fixed_w = 0.6 * cm + 4.0 * cm + 0.5 * cm
        note_w = (USABLE_W - fixed_w) / total_cols
        col_widths = [0.6 * cm, 4.0 * cm, 0.5 * cm] + [note_w] * total_cols

        tbl = Table(data, colWidths=col_widths, repeatRows=2)
        tbl.setStyle(TableStyle(_base_style(n_comp)))
        elements.append(tbl)

    # ===== SEMESTRE 2 (B3, B4, REC2 + resultado) - para cada chunk =====
    for chunk_idx, chunk in enumerate(component_chunks):
        elements.append(PageBreak())

        n_comp = len(chunk)
        names = [_abrev(c.get('name', '')) for c in chunk]
        is_last = (chunk_idx == len(component_chunks) - 1)

        header1 = ['N°', 'NOME DO ALUNO', 'S']
        header1 += ['NOTAS 3º BIMESTRE'] + [''] * (n_comp - 1)
        header1 += ['NOTAS 4º BIMESTRE'] + [''] * (n_comp - 1)
        header1 += ['RECUPERAÇÃO 2º SEMESTRE'] + [''] * (n_comp - 1)
        if is_last:
            header1 += ['TOTAL', 'MÉDIA', 'RESULTADO']

        header2 = ['', '', '']
        for _ in range(3):
            header2 += [VerticalText(n) for n in names]
        if is_last:
            header2 += ['PTS', 'FINAL', '']

        data = [header1, header2]
        for idx, st in enumerate(students_data, 1):
            row = [str(idx), _safe(st.get('studentName', ''), 30), _safe(st.get('sex', '-'), 1)]
            gr = st.get('grades') or {}
            for bim in ('b3', 'b4', 'rec2'):
                for c in chunk:
                    gi = gr.get(c.get('id', ''), {})
                    if not isinstance(gi, dict):
                        gi = {}
                    row.append(_fmt(gi.get(bim)))

            if is_last:
                # Total e média usando TODOS os componentes
                tp_val = 0
                medias = []
                for c in courses_ord:
                    gi = gr.get(c.get('id', ''), {})
                    if not isinstance(gi, dict):
                        gi = {}
                    fa = gi.get('finalAverage')
                    if isinstance(fa, (int, float)):
                        tp_val += fa
                        medias.append(fa)
                mg = tp_val / len(medias) if medias else 0
                row.append(f"{tp_val:.1f}".replace('.', ',') if tp_val > 0 else '-')
                row.append(f"{mg:.1f}".replace('.', ',') if mg > 0 else '-')
                row.append(_safe(st.get('result', 'CURSANDO'), 12))

            data.append(row)

        total_cols = n_comp * 3
        fixed_w = 0.6 * cm + 4.0 * cm + 0.5 * cm
        if is_last:
            extra_w = 0.9 * cm + 0.9 * cm + 1.5 * cm
            note_w = (USABLE_W - fixed_w - extra_w) / total_cols
            col_widths = [0.6 * cm, 4.0 * cm, 0.5 * cm] + [note_w] * total_cols + [0.9 * cm, 0.9 * cm, 1.5 * cm]
        else:
            note_w = (USABLE_W - fixed_w) / total_cols
            col_widths = [0.6 * cm, 4.0 * cm, 0.5 * cm] + [note_w] * total_cols

        tbl = Table(data, colWidths=col_widths, repeatRows=2)
        style = _base_style(n_comp)

        # Separadores extras na P2
        if is_last:
            style.append(('LINEAFTER', (2 + n_comp * 3, 0), (2 + n_comp * 3, -1), 1.5, colors.black))
            style.append(('LINEAFTER', (2 + n_comp * 3 + 1, 0), (2 + n_comp * 3 + 1, -1), 1.5, colors.black))
            # Colorir resultado
            col_res = len(col_widths) - 1
            for ri, st in enumerate(students_data, 2):
                r = _safe(st.get('result', ''), 12)
                if 'APROVADO' in r or 'PROMOVIDO' in r:
                    style.append(('BACKGROUND', (col_res, ri), (col_res, ri), colors.HexColor('#c8e6c9')))
                    style.append(('TEXTCOLOR', (col_res, ri), (col_res, ri), colors.HexColor('#1b5e20')))
                    style.append(('FONTNAME', (col_res, ri), (col_res, ri), 'Helvetica-Bold'))
                elif 'REPROVADO' in r:
                    style.append(('BACKGROUND', (col_res, ri), (col_res, ri), colors.HexColor('#ffcdd2')))
                    style.append(('TEXTCOLOR', (col_res, ri), (col_res, ri), colors.HexColor('#b71c1c')))
                    style.append(('FONTNAME', (col_res, ri), (col_res, ri), 'Helvetica-Bold'))
                elif 'DESISTENTE' in r:
                    style.append(('BACKGROUND', (col_res, ri), (col_res, ri), colors.HexColor('#e0e0e0')))
                elif 'TRANSFERIDO' in r:
                    style.append(('BACKGROUND', (col_res, ri), (col_res, ri), colors.HexColor('#fff9c4')))

        tbl.setStyle(TableStyle(style))
        elements.append(tbl)

    # ── Build ────────────────────────────────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.0 * cm, bottomMargin=4.2 * cm)
    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer
