"""Módulo PDF - Livro de Promoção
Estrutura vertical: cada aluno é um bloco com tabela de disciplinas em linhas.
Largura fixa, altura variável. Nunca estoura a página.
"""
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf.utils import ordenar_componentes_por_nivel

PAGE_W, PAGE_H = landscape(A4)
MX = 0.8 * cm
USABLE_W = PAGE_W - 2 * MX

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
        return '-'
    try:
        if isinstance(v, (int, float)):
            return f"{v:.1f}".replace('.', ',')
    except (ValueError, TypeError):
        return '-'
    return str(v) if v else '-'

def _safe(v, mx=40):
    if v is None:
        return ''
    return str(v)[:mx]


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
        courses_ord = courses or []

    # Variável para total de páginas
    page_info = {'total': 0}

    def _header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        pn = doc_obj.page
        tp = page_info['total'] if page_info['total'] > 0 else pn

        # ── CABEÇALHO ──
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
        pag_str = f'PÁGINA: {pn:02d}'
        canvas_obj.drawRightString(PAGE_W - MX - 3, by1 + 3, pag_str)

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

        # ── RODAPÉ desenhado por pós-processamento ──

        canvas_obj.restoreState()
        # Nota: rodapé é desenhado na última página pelo pós-processamento

    # ── Estilos ──────────────────────────────────────────────
    st_aluno_nome = ParagraphStyle('AlunoNome', fontSize=9, fontName='Helvetica-Bold', leading=12)
    st_aluno_info = ParagraphStyle('AlunoInfo', fontSize=7, fontName='Helvetica', leading=9, textColor=colors.HexColor('#444444'))
    st_resultado_ok = ParagraphStyle('ResOk', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#1b5e20'), alignment=TA_CENTER)
    st_resultado_rep = ParagraphStyle('ResRep', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#b71c1c'), alignment=TA_CENTER)
    st_resultado_cur = ParagraphStyle('ResCur', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#1565c0'), alignment=TA_CENTER)
    st_resultado_out = ParagraphStyle('ResOut', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#666666'), alignment=TA_CENTER)

    # ── Larguras das colunas da tabela vertical ──────────────
    # COMPONENTE | B1 | B2 | REC1 | B3 | B4 | REC2 | TOTAL | MÉDIA
    col_comp = 5.5 * cm
    col_nota = 1.5 * cm
    col_total = 1.7 * cm
    col_media = 1.7 * cm
    col_widths = [col_comp] + [col_nota] * 6 + [col_total, col_media]

    # ── Montar blocos por aluno ──────────────────────────────
    elements = []

    for idx, student in enumerate(students_data):
        if idx > 0:
            elements.append(Spacer(1, 10))

        nome = _safe(student.get('studentName', ''), 60)
        sexo = 'Masculino' if _safe(student.get('sex', ''), 1).upper() == 'M' else 'Feminino'
        resultado = _safe(student.get('result', 'CURSANDO'), 30)
        grades = student.get('grades') or {}

        # Cabeçalho do aluno
        bloco = []
        bloco.append(Paragraph(f"{idx + 1}. {nome}", st_aluno_nome))
        bloco.append(Paragraph(f"Sexo: {sexo} | Resultado: <b>{resultado}</b>", st_aluno_info))
        bloco.append(Spacer(1, 4))

        # Tabela de notas
        header = ['COMPONENTE', '1º BIM', '2º BIM', 'REC 1ºS', '3º BIM', '4º BIM', 'REC 2ºS', 'TOTAL', 'MÉDIA']
        data = [header]

        total_pontos = 0
        medias_validas = []

        for course in courses_ord:
            cid = course.get('id', '')
            cname = _abrev(course.get('name', ''))
            gi = grades.get(cid, {})
            if not isinstance(gi, dict):
                gi = {}

            b1 = gi.get('b1')
            b2 = gi.get('b2')
            b3 = gi.get('b3')
            b4 = gi.get('b4')
            rec1 = gi.get('rec1')
            rec2 = gi.get('rec2')
            tp = gi.get('totalPoints')
            fa = gi.get('finalAverage')

            if isinstance(fa, (int, float)):
                total_pontos += fa
                medias_validas.append(fa)

            data.append([
                cname,
                _fmt(b1), _fmt(b2), _fmt(rec1),
                _fmt(b3), _fmt(b4), _fmt(rec2),
                _fmt(tp), _fmt(fa)
            ])

        # Linha de totais
        mg = total_pontos / len(medias_validas) if medias_validas else 0
        data.append([
            'TOTAL GERAL', '', '', '', '', '', '',
            _fmt(total_pontos) if total_pontos > 0 else '-',
            _fmt(mg) if mg > 0 else '-'
        ])

        tbl = Table(data, colWidths=col_widths, repeatRows=1)

        style = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Corpo
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            # Grid
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            # Zebra
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f5f5f5')]),
            # Linha de total
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ]

        # Colorir médias abaixo de 6
        for row_idx in range(1, len(data) - 1):
            fa_val = None
            try:
                gi = grades.get(courses_ord[row_idx - 1].get('id', ''), {})
                if isinstance(gi, dict):
                    fa_val = gi.get('finalAverage')
            except (IndexError, AttributeError):
                pass
            if isinstance(fa_val, (int, float)) and fa_val < 6:
                style.append(('TEXTCOLOR', (-1, row_idx), (-1, row_idx), colors.HexColor('#c62828')))
                style.append(('FONTNAME', (-1, row_idx), (-1, row_idx), 'Helvetica-Bold'))

        tbl.setStyle(TableStyle(style))
        bloco.append(tbl)

        # Resultado com cor
        bloco.append(Spacer(1, 3))
        if 'APROVADO' in resultado or 'PROMOVIDO' in resultado:
            bloco.append(Paragraph(f"RESULTADO FINAL: {resultado}", st_resultado_ok))
        elif 'REPROVADO' in resultado:
            bloco.append(Paragraph(f"RESULTADO FINAL: {resultado}", st_resultado_rep))
        elif 'CURSANDO' in resultado:
            bloco.append(Paragraph(f"RESULTADO FINAL: {resultado}", st_resultado_cur))
        else:
            bloco.append(Paragraph(f"RESULTADO FINAL: {resultado}", st_resultado_out))

        # Manter bloco junto se possível, senão quebra naturalmente
        elements.append(KeepTogether(bloco) if len(courses_ord) <= 12 else bloco[0])
        if len(courses_ord) > 12:
            for item in bloco[1:]:
                elements.append(item)

    # ── Build único (robusto, sem 2-pass) ──────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.0 * cm, bottomMargin=4.2 * cm)
    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)

    # Pós-processamento com fitz: adicionar total de páginas e rodapé na última
    try:
        import fitz as pymupdf
        pdf_doc = pymupdf.open(stream=buffer.getvalue(), filetype='pdf')
        total_pages = len(pdf_doc)
        
        for pg_idx, page in enumerate(pdf_doc):
            # Adicionar "/TOTAL" após "PÁGINA: XX"
            quads = page.search_for("PÁGINA:")
            if quads:
                # Encontrar o final do texto "PÁGINA: XX" para inserir "/TOTAL"
                full_quads = page.search_for(f"PÁGINA: {pg_idx+1:02d}")
                if full_quads:
                    r = full_quads[0]
                    page.insert_text(
                        (r.x1 + 1, r.y1 - 2),
                        f"/{total_pages:02d}",
                        fontsize=7, fontname="helv", color=(0, 0, 0)
                    )
            
            # Rodapé só na última página
            if pg_idx == total_pages - 1:
                pw, ph = page.rect.width, page.rect.height
                mid = pw / 2
                # Data/local
                tw_de = pymupdf.get_text_length(data_extenso, fontname="helv", fontsize=9)
                page.insert_text((mid - tw_de/2, ph - 3.8*28.35 + 9), data_extenso, fontsize=9, fontname="helv", color=(0,0,0))
                # Linhas de assinatura
                ly = ph - 2.6*28.35
                cl_x, cr_x = mid - 5*28.35, mid + 5*28.35
                hl = 4*28.35
                page.draw_line((cl_x-hl, ly), (cl_x+hl, ly))
                page.draw_line((cr_x-hl, ly), (cr_x+hl, ly))
                # Rótulos
                tw_s = pymupdf.get_text_length("Secretário(a)", fontname="helv", fontsize=9)
                tw_d = pymupdf.get_text_length("Diretor(a)", fontname="helv", fontsize=9)
                page.insert_text((cl_x - tw_s/2, ly + 12), "Secretário(a)", fontsize=9, fontname="helv", color=(0,0,0))
                page.insert_text((cr_x - tw_d/2, ly + 12), "Diretor(a)", fontsize=9, fontname="helv", color=(0,0,0))
                # Info de geração
                page.insert_text((MX/28.35*72, ph - 0.6*28.35 + 7), rodape_info, fontsize=7, fontname="helv", color=(0.4,0.4,0.4))
        
        result_buf = BytesIO()
        pdf_doc.save(result_buf)
        pdf_doc.close()
        result_buf.seek(0)
        return result_buf
    except Exception:
        buffer.seek(0)
        return buffer
