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
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf.utils import get_logo_path, is_serie_conceitual_anos_iniciais, valor_para_conceito_fn, calcular_media_conceitual
from grade_calculator import is_educacao_infantil as _is_educacao_infantil

PAGE_W, PAGE_H = landscape(A4)
MX = 0.8 * cm
USABLE_W = PAGE_W - 2 * MX
# Larguras fixas: N° + Nome (mínimo) + Sexo
COL_N_W = 0.55 * cm
COL_NAME_MIN = 3.8 * cm
COL_SEX_W = 0.45 * cm
COL_NOTE_W = 0.62 * cm  # largura estreita - textos dos componentes na vertical
FIXED_W = COL_N_W + COL_NAME_MIN + COL_SEX_W


# ── Flowable: texto vertical para cabeçalhos de componentes ─
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


# ── Estilos de Paragraph ───────────────────────────────────
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
    # Educação Infantil - Campos de Experiência (BNCC)
    'o eu, o outro e nós': 'EU OUT. NÓS',
    'corpo, gestos e movimentos': 'CORP. GEST.',
    'escuta, fala, pensamento e imaginação': 'ESC. FALA.',
    'traço, sons, cores e formas': 'TRAÇ. SONS',
    'espaços, tempos, quantidades, relações e transformações': 'ESP. TEMP.',
    'contação de histórias e iniciação musical': 'CONT. HIST.',
    'higiene e saúde': 'HIG. SAÚDE',
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
    if 'integral' in ap:
        return True
    # Componentes formativos/Tempo Integral — ignorados no Livro de Promoção
    nome = (course.get('name') or '').lower().strip()
    formativos = (
        'arte e cultura',
        'contação de histórias e iniciação musical',
        'higiene e saúde',
        'linguagem recreativa com práticas de esporte e lazer',
        'recreação, esporte e lazer',
        'recreação e lazer',
    )
    return any(nome == f or nome.startswith(f) for f in formativos)


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
    escola_nome = str(school.get('name', ''))
    turma_nome = str(class_info.get('name', ''))
    grade_level = str(class_info.get('grade_level', ''))
    nivel_ensino = str(class_info.get('education_level', '') or class_info.get('nivel_ensino', ''))
    shift_raw = class_info.get('shift', '')
    turno = {'morning':'MATUTINO','afternoon':'VESPERTINO','evening':'NOTURNO',
             'full_time':'INTEGRAL','night':'NOTURNO'}.get(shift_raw, str(shift_raw).upper())

    # Modo de avaliação: conceitual (Ed. Infantil e 1º/2º ano) NÃO tem recuperação
    is_ed_infantil = _is_educacao_infantil(grade_level, nivel_ensino)
    is_anos_iniciais_conc = is_serie_conceitual_anos_iniciais(grade_level)
    usa_conceito = is_ed_infantil or is_anos_iniciais_conc

    # Tipo de Atendimento da turma
    atendimento_raw = (class_info.get('atendimento_programa') or '').lower()
    is_tempo_integral = 'integral' in atendimento_raw
    tipo_atendimento = 'Tempo Integral' if is_tempo_integral else 'Regular'
    book_number_str = str(book_number or '----')

    # Tabela sempre usa apenas componentes regulares
    reg = [c for c in (courses or []) if not is_integral(c)]

    # Se não há nenhum regular (fallback), usar tudo como regular
    if not reg:
        reg = courses or []

    # Estimar total de páginas base (2: semestre 1 e semestre 2 + resultado)
    page_total = [2]

    # ── Canvas callback: apenas cabeçalho (sem rodapé) ─────────
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

        canvas_obj.restoreState()

    # ── Helper: montar tabela combinada de um semestre ─────────
    # bloco = (bim_key, titulo). Keys suportadas: 'b1'/'b2'/'b3'/'b4', 'rec1'/'rec2', 'final_conceito'.
    # Se include_result=True, adiciona MÉDIA + CONCLUSÃO (numérico) ou CONCLUSÃO (conceitual).
    def build_combined_table(blocos, include_result=False):
        """Monta tabela: Nº | Nome | S | [bloco1] | [bloco2] | [bloco3] [| MÉDIA | CONCLUSÃO]
        Componentes de atendimento diferente de 'regular' são ignorados.
        Em turmas conceituais, a coluna MÉDIA é substituída por um bloco 'CONCEITO FINAL' (um por componente).
        """
        n_blocos = len(blocos)
        comps_per_bloco = len(reg)
        # Em conceitual, a "MÉDIA" vira um bloco inteiro (CONCEITO FINAL por componente) e fica fora desse counter
        result_cols_extra = 0
        if include_result:
            result_cols_extra = 1 if usa_conceito else 2  # conceitual: só CONCLUSÃO; numérico: MÉDIA+CONCLUSÃO

        # ── Header 1: títulos spans ──
        h1 = ['N°', 'NOME DO\nALUNO', 'S']
        for _, titulo in blocos:
            h1 += [titulo] + [''] * (comps_per_bloco - 1)
        if include_result:
            if usa_conceito:
                h1 += ['CONCLUSÃO']
            else:
                h1 += ['MÉDIA', 'CONCLUSÃO']

        # ── Header 2: abreviações (texto vertical para economizar largura) ──
        h2 = ['', '', '']
        for _ in blocos:
            h2 += [VerticalText(abrev(c.get('name', ''))) for c in reg]
        if include_result:
            h2 += [''] * result_cols_extra

        # ── Dados ──
        rows = [h1, h2]
        for idx, st in enumerate(students_data, 1):
            nome = str(st.get('studentName', '') or '')
            nome_safe = nome.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            row = [
                str(idx),
                Paragraph(nome_safe, _STYLE_STUDENT_NAME),
                str(st.get('sex', '-') or '-')[:1],
            ]
            gr = st.get('grades') or {}
            for bim_key, _ in blocos:
                for c in reg:
                    gi = gr.get(c.get('id', ''), {})
                    if not isinstance(gi, dict):
                        gi = {}
                    if bim_key == 'final_conceito':
                        # Conceito final do componente = MAIOR conceito dos 4 bimestres
                        bims = [gi.get('b1'), gi.get('b2'), gi.get('b3'), gi.get('b4')]
                        bims_validos = [v for v in bims if v is not None]
                        final_c = max(bims_validos) if bims_validos else None
                        row.append(valor_para_conceito_fn(final_c, grade_level) if final_c is not None else '-')
                        continue
                    valor = gi.get(bim_key)
                    if usa_conceito:
                        # Exibe conceito em vez de número
                        row.append(valor_para_conceito_fn(valor, grade_level) if valor is not None else '-')
                    else:
                        row.append(fmt(valor))

            if include_result:
                if usa_conceito:
                    # Nada a adicionar aqui (CONCEITO FINAL já é um bloco por componente).
                    pass
                else:
                    # Média final = média das finalAverage dos componentes regulares
                    medias = []
                    for c in reg:
                        gi = gr.get(c.get('id', ''), {})
                        if isinstance(gi, dict):
                            fa = gi.get('finalAverage')
                            if isinstance(fa, (int, float)):
                                medias.append(fa)
                    mg = sum(medias) / len(medias) if medias else 0
                    row.append(fmt(mg) if medias else '-')
                result_raw = str(st.get('result', 'CURSANDO') or 'CURSANDO')
                row.append(result_raw[:18])
            rows.append(row)

        # ── Larguras (ajustadas dinamicamente para nunca passar da margem) ──
        media_w = 1.1 * cm
        result_w = 2.6 * cm
        total_note_cols = comps_per_bloco * n_blocos
        if include_result:
            fixed_extra = result_w if usa_conceito else (media_w + result_w)
        else:
            fixed_extra = 0
        available_for_notes = USABLE_W - (COL_N_W + COL_NAME_MIN + COL_SEX_W + fixed_extra)
        if total_note_cols > 0:
            # Cada nota entre 0.45cm (mínimo p/ 10,0 na fonte 7) e 1.0cm (máx confortável)
            note_w = max(0.45 * cm, min(1.0 * cm, available_for_notes / total_note_cols))
        else:
            note_w = 1.0 * cm
        # Sobra vai para a coluna Nome
        name_w = max(
            COL_NAME_MIN,
            USABLE_W - (COL_N_W + COL_SEX_W + total_note_cols * note_w + fixed_extra),
        )
        cw = [COL_N_W, name_w, COL_SEX_W] + [note_w] * total_note_cols
        if include_result:
            cw += ([result_w] if usa_conceito else [media_w, result_w])

        tbl = Table(rows, colWidths=cw, repeatRows=2)

        style = [
            # Cabeçalho principal
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7.5),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Sub-cabeçalho
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
            # Separador grosso depois da coluna Sexo
            ('LINEAFTER', (2, 0), (2, -1), 1.2, colors.black),
        ]

        # Spans e separadores entre blocos
        col_start = 3
        for _, _ in blocos:
            col_end = col_start + comps_per_bloco - 1
            style.append(('SPAN', (col_start, 0), (col_end, 0)))
            style.append(('LINEAFTER', (col_end, 0), (col_end, -1), 1.2, colors.black))
            col_start = col_end + 1

        # Colorir CONCLUSÃO (sempre a última coluna)
        if include_result:
            result_col = 3 + total_note_cols + (0 if usa_conceito else 1)
            for ri, st in enumerate(students_data, 2):  # row 2 é o primeiro aluno (0=h1, 1=h2)
                r = str(st.get('result', '') or '').upper()
                if ('APROVADO' in r and 'DEPEND' not in r) or 'CONCLUIU' in r or 'PROMOVIDO' in r:
                    style.append(('BACKGROUND', (result_col, ri), (result_col, ri), colors.HexColor('#c8e6c9')))
                    style.append(('TEXTCOLOR', (result_col, ri), (result_col, ri), colors.HexColor('#1b5e20')))
                    style.append(('FONTNAME', (result_col, ri), (result_col, ri), 'Helvetica-Bold'))
                elif 'REPROVADO' in r:
                    style.append(('BACKGROUND', (result_col, ri), (result_col, ri), colors.HexColor('#ffcdd2')))
                    style.append(('TEXTCOLOR', (result_col, ri), (result_col, ri), colors.HexColor('#b71c1c')))
                    style.append(('FONTNAME', (result_col, ri), (result_col, ri), 'Helvetica-Bold'))
                elif 'DEPEND' in r:
                    style.append(('BACKGROUND', (result_col, ri), (result_col, ri), colors.HexColor('#fff9c4')))
                    style.append(('FONTNAME', (result_col, ri), (result_col, ri), 'Helvetica-Bold'))

        tbl.setStyle(TableStyle(style))
        return tbl

    # ── Helper: bloco de encerramento (assinaturas + info geração) ─
    def build_closing_block():
        from datetime import datetime as _dt
        gen_time = _dt.now().strftime('%d/%m/%Y às %H:%M')
        total_alunos = len(students_data)

        line_style = ParagraphStyle(
            name='ClosingLine', fontName='Helvetica', fontSize=9, leading=11,
            alignment=TA_CENTER, textColor=colors.black,
        )
        label_style = ParagraphStyle(
            name='ClosingLabel', fontName='Helvetica-Bold', fontSize=8, leading=10,
            alignment=TA_CENTER, textColor=colors.black,
        )
        info_style = ParagraphStyle(
            name='ClosingInfo', fontName='Helvetica-Oblique', fontSize=7, leading=9,
            alignment=TA_CENTER, textColor=colors.HexColor('#555555'),
        )

        # Cidade-UF, Data (data_extenso já contém "Cidade - UF, dd de mês de aaaa")
        city_line = Paragraph(f'<b>{data_extenso}</b>', line_style)

        # Assinaturas (tabela de 2 colunas com linha horizontal)
        sig_row_sep = [
            Paragraph('_' * 45, line_style),
            Paragraph('_' * 45, line_style),
        ]
        sig_row_lbl = [
            Paragraph('Secretário(a)', label_style),
            Paragraph('Diretor(a)', label_style),
        ]
        sig_tbl = Table(
            [sig_row_sep, sig_row_lbl],
            colWidths=[USABLE_W / 2, USABLE_W / 2],
        )
        sig_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        info_line = Paragraph(
            f'Documento gerado em {gen_time} | Total de alunos(as): {total_alunos:02d}',
            info_style,
        )

        return [
            Spacer(1, 0.8 * cm),
            city_line,
            Spacer(1, 1.0 * cm),
            sig_tbl,
            Spacer(1, 0.5 * cm),
            info_line,
        ]

    # ── Montar elementos ─────────────────────────────────────
    elements = []

    if usa_conceito:
        # Educação Infantil e 1º/2º Ano: sem recuperação
        # Página 1: 1º Bim + 2º Bim
        elements.append(build_combined_table(
            [('b1', 'CONCEITOS 1º BIMESTRE'),
             ('b2', 'CONCEITOS 2º BIMESTRE')],
            include_result=False,
        ))
        # Página 2: 3º Bim + 4º Bim + CONCEITO FINAL (por componente) + CONCLUSÃO
        elements.append(PageBreak())
        elements.append(build_combined_table(
            [('b3', 'CONCEITOS 3º BIMESTRE'),
             ('b4', 'CONCEITOS 4º BIMESTRE'),
             ('final_conceito', 'CONCEITO FINAL')],
            include_result=True,
        ))
    else:
        # 3º ao 9º Ano e EJA: com recuperação por semestre
        # Página 1: 1º Bim + 2º Bim + Recuperação 1º Semestre
        elements.append(build_combined_table(
            [('b1', 'NOTAS 1º BIMESTRE'),
             ('b2', 'NOTAS 2º BIMESTRE'),
             ('rec1', 'RECUPERAÇÃO 1º SEMESTRE')],
            include_result=False,
        ))
        # Página 2: 3º Bim + 4º Bim + Recuperação 2º Semestre + MÉDIA + CONCLUSÃO
        elements.append(PageBreak())
        elements.append(build_combined_table(
            [('b3', 'NOTAS 3º BIMESTRE'),
             ('b4', 'NOTAS 4º BIMESTRE'),
             ('rec2', 'RECUPERAÇÃO 2º SEMESTRE')],
            include_result=True,
        ))

    # Legenda de conceitos (apenas quando conceitual)
    if usa_conceito:
        from pdf.utils import criar_legenda_conceitos
        elements.append(Spacer(1, 0.3 * cm))
        for el in criar_legenda_conceitos(is_educacao_infantil=is_ed_infantil, grade_level=grade_level):
            elements.append(el)

    # Citação (última página) quando turma é Tempo Integral
    if is_tempo_integral:
        cit_style = ParagraphStyle(
            name='CitacaoIntegral',
            fontName='Helvetica-Oblique',
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#333333'),
        )
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph(
            'As atividades curriculares complementares de caráter formativo, '
            'referentes ao atendimento em tempo integral, encontram-se registradas '
            'em documento complementar (Adendo), parte integrante deste registro.',
            cit_style,
        ))

    # Encerramento (apenas última página)
    for el in build_closing_block():
        elements.append(el)

    # ── Build ────────────────────────────────────────────────
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=MX, rightMargin=MX, topMargin=3.5 * cm, bottomMargin=1.2 * cm)
    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)

    # Atualizar total de páginas se diferente do estimado
    # (não precisa de 2-pass pois é apenas informativo)
    buffer.seek(0)
    return buffer
