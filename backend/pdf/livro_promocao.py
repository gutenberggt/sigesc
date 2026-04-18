"""Módulo PDF - Livro de Promoção
Paginação horizontal por componentes com separação NOTAS/PARTICIPAÇÃO para integrais.
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
MAX_REG_PER_PAGE = 8


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
    'oficina de leitura': 'OF. LEIT.',
    'contação de histórias e iniciação musical': 'CONT. HIST.',
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
    return str(v)[:mx] if v else ''

def _chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def _is_integral_course(course):
    ap = (course.get('atendimento_programa') or '').lower().strip()
    return ap in ('atendimento_integral', 'integral')

def _base_style():
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
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]


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
    all_courses = ordenar_componentes_por_nivel(courses, nivel) or courses or []

    # Separar regulares e integrais
    reg_courses = [c for c in all_courses if not _is_integral_course(c)]
    int_courses = [c for c in all_courses if _is_integral_course(c)]
    has_integral = len(int_courses) > 0

    # Se não integral, tudo é regular
    if not has_integral:
        reg_courses = all_courses

    reg_names = [_abrev(c.get('name', '')) for c in reg_courses]
    int_names = [_abrev(c.get('name', '')) for c in int_courses]

    # Chunks de regulares
    reg_chunks = list(_chunk(reg_courses, MAX_REG_PER_PAGE)) if reg_courses else [[]]
    reg_name_chunks = list(_chunk(reg_names, MAX_REG_PER_PAGE)) if reg_names else [[]]

    # Estimar total de páginas
    ppt = 1 if len(students_data) <= 18 else 2 if len(students_data) <= 36 else 3
    total_est = len(reg_chunks) * 2 * ppt
    page_total = [total_est]

    # ── Header/Footer ────────────────────────────────────────
    def _hf(canvas_obj, doc_obj):
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

    # ── Helper: construir header row 1 e 2, data rows, col_widths ──
    def _vt(name):
        return VerticalText(name)

    def _build_sem1_table(reg_chunk, reg_chunk_names):
        """Semestre 1: NOTAS 1ºBIM [+ PART 1ºBIM] | NOTAS 2ºBIM [+ PART 2ºBIM] | REC 1ºSEM (só reg)"""
        nr = len(reg_chunk)
        ni = len(int_courses)

        # Header row 1
        h1 = ['N°', 'NOME DO ALUNO', 'S']
        for bim_label in ['NOTAS 1º BIMESTRE', 'NOTAS 2º BIMESTRE']:
            h1 += [bim_label] + [''] * (nr - 1)
            if has_integral:
                part_label = bim_label.replace('NOTAS', 'PARTICIPAÇÃO')
                h1 += [part_label] + [''] * (ni - 1)
        h1 += ['RECUPERAÇÃO 1º SEMESTRE'] + [''] * (nr - 1)

        # Header row 2
        h2 = ['', '', '']
        for _ in range(2):  # 2 bimestres
            h2 += [_vt(n) for n in reg_chunk_names]
            if has_integral:
                h2 += [_vt(n) for n in int_names]
        h2 += [_vt(n) for n in reg_chunk_names]  # rec só regular

        # Data rows
        data = [h1, h2]
        for idx, st in enumerate(students_data, 1):
            row = [str(idx), _safe(st.get('studentName', ''), 30), _safe(st.get('sex', '-'), 1)]
            gr = st.get('grades') or {}
            for bim in ('b1', 'b2'):
                for c in reg_chunk:
                    gi = gr.get(c.get('id', ''), {})
                    row.append(_fmt(gi.get(bim) if isinstance(gi, dict) else None))
                if has_integral:
                    for c in int_courses:
                        gi = gr.get(c.get('id', ''), {})
                        row.append(_fmt(gi.get(bim) if isinstance(gi, dict) else None))
            # Rec 1º sem - só regular
            for c in reg_chunk:
                gi = gr.get(c.get('id', ''), {})
                row.append(_fmt(gi.get('rec1') if isinstance(gi, dict) else None))
            data.append(row)

        # Col widths
        fixed = 0.6 * cm + 4.0 * cm + 0.5 * cm
        total_note_cols = nr * 3 + (ni * 2 if has_integral else 0)
        nw = (USABLE_W - fixed) / total_note_cols
        cw = [0.6 * cm, 4.0 * cm, 0.5 * cm] + [nw] * total_note_cols

        # Style
        style = _base_style()
        # Separadores e spans
        col = 3
        for b in range(2):  # 2 bimestres
            style.append(('SPAN', (col, 0), (col + nr - 1, 0)))
            style.append(('LINEAFTER', (col + nr - 1, 0), (col + nr - 1, -1), 1.5, colors.black))
            col += nr
            if has_integral:
                style.append(('SPAN', (col, 0), (col + ni - 1, 0)))
                # Cor diferente para PARTICIPAÇÃO
                style.append(('BACKGROUND', (col, 0), (col + ni - 1, 0), colors.HexColor('#4a148c')))
                style.append(('BACKGROUND', (col, 1), (col + ni - 1, 1), colors.HexColor('#7b1fa2')))
                style.append(('LINEAFTER', (col + ni - 1, 0), (col + ni - 1, -1), 1.5, colors.black))
                col += ni
        # Rec
        style.append(('SPAN', (col, 0), (col + nr - 1, 0)))
        style.append(('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black))

        tbl = Table(data, colWidths=cw, repeatRows=2)
        tbl.setStyle(TableStyle(style))
        return tbl

    def _build_sem2_table(reg_chunk, reg_chunk_names, is_last_chunk):
        """Semestre 2: NOTAS 3ºBIM [+ PART 3ºBIM] | NOTAS 4ºBIM [+ PART 4ºBIM] | REC 2ºSEM (só reg) [+ TOTAL/MÉDIA/RES]"""
        nr = len(reg_chunk)
        ni = len(int_courses)

        h1 = ['N°', 'NOME DO ALUNO', 'S']
        for bim_label in ['NOTAS 3º BIMESTRE', 'NOTAS 4º BIMESTRE']:
            h1 += [bim_label] + [''] * (nr - 1)
            if has_integral:
                part_label = bim_label.replace('NOTAS', 'PARTICIPAÇÃO')
                h1 += [part_label] + [''] * (ni - 1)
        h1 += ['RECUPERAÇÃO 2º SEMESTRE'] + [''] * (nr - 1)
        if is_last_chunk:
            h1 += ['TOTAL', 'MÉDIA', 'RESULTADO']

        h2 = ['', '', '']
        for _ in range(2):
            h2 += [_vt(n) for n in reg_chunk_names]
            if has_integral:
                h2 += [_vt(n) for n in int_names]
        h2 += [_vt(n) for n in reg_chunk_names]
        if is_last_chunk:
            h2 += ['PTS', 'FINAL', '']

        data = [h1, h2]
        for idx, st in enumerate(students_data, 1):
            row = [str(idx), _safe(st.get('studentName', ''), 30), _safe(st.get('sex', '-'), 1)]
            gr = st.get('grades') or {}
            for bim in ('b3', 'b4'):
                for c in reg_chunk:
                    gi = gr.get(c.get('id', ''), {})
                    row.append(_fmt(gi.get(bim) if isinstance(gi, dict) else None))
                if has_integral:
                    for c in int_courses:
                        gi = gr.get(c.get('id', ''), {})
                        row.append(_fmt(gi.get(bim) if isinstance(gi, dict) else None))
            for c in reg_chunk:
                gi = gr.get(c.get('id', ''), {})
                row.append(_fmt(gi.get('rec2') if isinstance(gi, dict) else None))

            if is_last_chunk:
                tp_val, medias = 0, []
                for c in all_courses:
                    gi = gr.get(c.get('id', ''), {})
                    if isinstance(gi, dict):
                        fa = gi.get('finalAverage')
                        if isinstance(fa, (int, float)):
                            tp_val += fa
                            medias.append(fa)
                mg = tp_val / len(medias) if medias else 0
                row.append(f"{tp_val:.1f}".replace('.', ',') if tp_val > 0 else '-')
                row.append(f"{mg:.1f}".replace('.', ',') if mg > 0 else '-')
                row.append(_safe(st.get('result', 'CURSANDO'), 12))

            data.append(row)

        fixed = 0.6 * cm + 4.0 * cm + 0.5 * cm
        extra_w = (0.9 * cm + 0.9 * cm + 1.5 * cm) if is_last_chunk else 0
        total_note_cols = nr * 3 + (ni * 2 if has_integral else 0)
        nw = (USABLE_W - fixed - extra_w) / total_note_cols
        cw = [0.6 * cm, 4.0 * cm, 0.5 * cm] + [nw] * total_note_cols
        if is_last_chunk:
            cw += [0.9 * cm, 0.9 * cm, 1.5 * cm]

        style = _base_style()
        col = 3
        for b in range(2):
            style.append(('SPAN', (col, 0), (col + nr - 1, 0)))
            style.append(('LINEAFTER', (col + nr - 1, 0), (col + nr - 1, -1), 1.5, colors.black))
            col += nr
            if has_integral:
                style.append(('SPAN', (col, 0), (col + ni - 1, 0)))
                style.append(('BACKGROUND', (col, 0), (col + ni - 1, 0), colors.HexColor('#4a148c')))
                style.append(('BACKGROUND', (col, 1), (col + ni - 1, 1), colors.HexColor('#7b1fa2')))
                style.append(('LINEAFTER', (col + ni - 1, 0), (col + ni - 1, -1), 1.5, colors.black))
                col += ni
        # Rec
        style.append(('SPAN', (col, 0), (col + nr - 1, 0)))
        style.append(('LINEAFTER', (col + nr - 1, 0), (col + nr - 1, -1), 1.5, colors.black))
        style.append(('LINEAFTER', (2, 0), (2, -1), 1.5, colors.black))

        if is_last_chunk:
            col_res = len(cw) - 1
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

        tbl = Table(data, colWidths=cw, repeatRows=2)
        tbl.setStyle(TableStyle(style))
        return tbl

    # ── Montar elementos ─────────────────────────────────────
    elements = []

    # Sem1 para cada chunk de regulares
    for ci, (rc, rn) in enumerate(zip(reg_chunks, reg_name_chunks)):
        if ci > 0:
            elements.append(PageBreak())
        elements.append(_build_sem1_table(rc, rn))

    # Sem2 para cada chunk de regulares
    for ci, (rc, rn) in enumerate(zip(reg_chunks, reg_name_chunks)):
        elements.append(PageBreak())
        is_last = (ci == len(reg_chunks) - 1)
        elements.append(_build_sem2_table(rc, rn, is_last))

    # ── Build ────────────────────────────────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.0 * cm, bottomMargin=4.2 * cm)
    doc.build(elements, onFirstPage=_hf, onLaterPages=_hf)
    buffer.seek(0)
    return buffer
