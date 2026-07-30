"""
Dossiê Institucional da Rede Municipal de Ensino (CTUE) — geração de PDF consolidado.

Representação da REDE. Não possui lógica/regra/cálculo próprio: todo o conteúdo vem do
CTUEConformityService (build_network_dossie), que por sua vez deriva do SSoT
(build_network_panel + evaluate por escola). O PDF apenas representa.
"""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, ListFlowable, ListItem)

from pdf.utils import get_logo_image, get_styles

_STATUS_PT = {
    "conforme": "Adequado", "atencao": "Em Adequação", "critico": "Necessita Adequação",
    "nao_conforme": "Não Adequado", "nao_avaliado": "Não avaliado",
}
_BLUE = colors.HexColor("#1e40af")
_GRAY = colors.HexColor("#f3f4f6")
_HEAD_GRID = colors.HexColor("#e5e7eb")

_CELL = ParagraphStyle("RedeCell", fontName="Helvetica", fontSize=8.5, leading=10.5, alignment=TA_LEFT)
_CELL_H = ParagraphStyle("RedeCellH", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5,
                         alignment=TA_LEFT, textColor=colors.white)


def _v(val, none="Não informado"):
    if val is None or val == "":
        return none
    return str(val)


def _h2(text, styles):
    return Paragraph(text, styles["RedeH2"])


def _c(text, header=False):
    return Paragraph(str(text) if header else _v(text, "—"), _CELL_H if header else _CELL)


def _bar_table(rows, header, col_widths):
    data = [[_c(h, header=True) for h in header]] + [[_c(v) for v in r] for r in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("GRID", (0, 0), (-1, -1), 0.4, _HEAD_GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _bullets(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(_v(i), styles["Normal"]), leftIndent=10) for i in items],
        bulletType="bullet", start="•", leftIndent=12,
    )


def generate_network_dossie_pdf(data: dict, mantenedora: dict = None, exercicio: str = None) -> bytes:
    buf = BytesIO()
    styles = get_styles()
    if "RedeH2" not in styles:
        styles.add(ParagraphStyle(name="RedeH2", parent=styles["Heading2"], fontSize=13,
                                  textColor=_BLUE, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT))
    if "RedeSmall" not in styles:
        styles.add(ParagraphStyle(name="RedeSmall", parent=styles["Normal"], fontSize=9,
                                  textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER))
    if "RedeCover" not in styles:
        styles.add(ParagraphStyle(name="RedeCover", parent=styles["Heading1"], fontSize=24,
                                  textColor=_BLUE, alignment=TA_CENTER, spaceBefore=10, spaceAfter=10, leading=28))

    m = mantenedora or {}
    prefeitura = m.get("nome") or "Prefeitura Municipal"
    secretaria = m.get("secretaria") or "Secretaria Municipal de Educação"
    municipio = m.get("municipio")
    exercicio = exercicio or str(datetime.now(timezone.utc).year)
    emitido = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    rodape_titulo = "Dossiê Institucional da Rede Municipal de Ensino"

    # Brasão do município (identificação da mantenedora); fallback: logotipo → logo padrão
    brasao_url = m.get("brasao_url") or m.get("logotipo_url") or None

    def _footer(canvas, doc):
        canvas.saveState()
        w, _ = A4
        if doc.page > 1:  # capa sem rodapé
            canvas.setStrokeColor(_HEAD_GRID)
            canvas.setLineWidth(0.5)
            canvas.line(1.8 * cm, 1.2 * cm, w - 1.8 * cm, 1.2 * cm)
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(colors.HexColor("#6b7280"))
            canvas.drawString(1.8 * cm, 0.8 * cm, f"{rodape_titulo} · {prefeitura}")
            canvas.drawRightString(w - 1.8 * cm, 0.8 * cm, f"Página {doc.page}")
            canvas.drawCentredString(w / 2.0, 0.8 * cm, "SIGESC · gerado a partir do CTUE (SSoT)")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.8 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            title="Dossiê Institucional da Rede Municipal de Ensino")

    el = []

    # ===== 1. Capa Institucional =====
    el.append(Spacer(1, 2.0 * cm))
    logo = get_logo_image(width=3.4 * cm, height=3.4 * cm, logo_url=brasao_url)
    if logo:
        lt = Table([[logo]], colWidths=[3.4 * cm]); lt.hAlign = "CENTER"
        el.append(lt); el.append(Spacer(1, 0.6 * cm))
    el.append(Paragraph(f"<b>{prefeitura}</b>", styles["SubTitle"]))
    el.append(Paragraph(f"<b>{secretaria}</b>", styles["CenterText"]))
    if municipio:
        el.append(Paragraph(municipio, styles["RedeSmall"]))
    el.append(Spacer(1, 1.3 * cm))
    el.append(Paragraph("DOSSIÊ INSTITUCIONAL DA REDE MUNICIPAL DE ENSINO", styles["RedeCover"]))
    el.append(Spacer(1, 0.5 * cm))
    el.append(Paragraph(f"Exercício {exercicio}", styles["SubTitle"]))
    el.append(Spacer(1, 3.2 * cm))
    el.append(Paragraph(f"Emitido em {emitido} (UTC) · Perfil de avaliação: "
                        f"{data.get('profile_label', data.get('profile'))}", styles["RedeSmall"]))
    el.append(PageBreak())

    # ===== Sumário =====
    el.append(_h2("Sumário", styles))
    sumario = [
        "1. Capa Institucional", "2. Apresentação", "3. Panorama Geral",
        "4. Distribuição da Rede", "5. Ranking de Conformidade", "6. Ranking de Prioridades",
        "7. Infraestrutura da Rede", "8. Obras e Intervenções", "9. Documentação",
        "10. Diagnóstico Executivo", "11. Plano de Ação Sugerido", "12. Conclusão",
    ]
    el.append(ListFlowable([ListItem(Paragraph(s, styles["Normal"]), leftIndent=8) for s in sumario],
                           bulletType="bullet", start="", leftIndent=6))
    el.append(Paragraph("<i>Observação: a partir do item 4, os indicadores consideram apenas as "
                        "escolas ativas da rede.</i>", styles["RedeSmall"]))
    el.append(PageBreak())

    # ===== 2. Apresentação =====
    el.append(_h2("2. Apresentação", styles))
    el.append(Paragraph(
        "Este Dossiê consolida, em documento único, a fotografia institucional da Rede Municipal de "
        "Ensino a partir do Cadastro Técnico da Unidade Escolar (CTUE). Todas as informações são "
        "geradas automaticamente pelo SIGESC, sem consolidação manual, respeitando rigorosamente o "
        "princípio de fonte única de dados (Single Source of Truth). O documento destina-se à alta "
        "gestão e pode subsidiar prestação de contas, planejamento estratégico, planos de ação da "
        "Secretaria e o atendimento a órgãos de controle (Ministério Público, Tribunal de Contas, "
        "FNDE), à Câmara Municipal e ao Conselho Municipal de Educação.",
        styles["JustifyText"]))

    # ===== 3. Panorama Geral (TODA a rede) =====
    ex = data["executive"]
    el.append(_h2("3. Panorama Geral", styles))
    pg = [
        ["Total de escolas", str(ex["total"]), "Conformidade média", f"{ex['conformidade_media']}%"],
        ["Escolas ativas", str(ex["ativas"]), "Completude média", f"{ex['completude_media']}%"],
        ["Escolas inativas", str(ex["inativas"]),
         "Atualização média", f"{ex['atualizacao_media_dias']} dias" if ex.get("atualizacao_media_dias") is not None else "—"],
        ["Cadastros nunca atualizados", str(ex.get("cadastros_nunca_atualizados", 0)),
         "Maturidade média", f"Nível {ex.get('maturidade_media', 1)}"],
    ]
    t = Table([[_c(a), _c(b), _c(cc), _c(d)] for a, b, cc, d in pg],
              colWidths=[4.6 * cm, 4.0 * cm, 4.6 * cm, 4.0 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _GRAY), ("BACKGROUND", (2, 0), (2, -1), _GRAY),
        ("GRID", (0, 0), (-1, -1), 0.4, _HEAD_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(t)

    # ===== 4. Distribuição da Rede (apenas ativas) =====
    el.append(_h2("4. Distribuição da Rede", styles))
    el.append(Paragraph("Considera apenas escolas ativas.", styles["RedeSmall"]))
    comp = data["comparativos"]
    for key, titulo in [("zona", "Urbana × Rural"), ("etapas", "Etapas de Ensino"),
                        ("porte", "Porte das Escolas"), ("distrito", "Distritos / Polos")]:
        linhas = comp.get(key, [])
        if not linhas:
            continue
        el.append(Paragraph(f"<b>{titulo}</b>", styles["Normal"]))
        rows = [[g["grupo"], str(g["escolas"]), f"{g['conformidade_media']}%", f"{g['completude_media']}%"] for g in linhas]
        el.append(_bar_table(rows, ["Grupo", "Escolas", "Conf. média", "Compl. média"],
                             [8.0 * cm, 3.0 * cm, 3.1 * cm, 3.1 * cm]))
        el.append(Spacer(1, 0.25 * cm))

    # ===== 5. Ranking de Conformidade =====
    el.append(PageBreak())
    el.append(_h2("5. Ranking de Conformidade", styles))
    el.append(Paragraph("Escolas ativas, da maior para a menor conformidade.", styles["RedeSmall"]))
    rows = [[str(i), r["name"], f"{r['conformidade']}%", f"{r['completude']}%", r["atualizacao"],
             f"N{r['maturidade_nivel']}", _STATUS_PT.get(r["status"], r["status"])]
            for i, r in enumerate(data["ranking"], start=1)]
    el.append(_bar_table(rows, ["#", "Escola", "Conf.", "Compl.", "Atualização", "Mat.", "Situação"],
                         [0.9 * cm, 5.4 * cm, 1.5 * cm, 1.6 * cm, 3.2 * cm, 1.2 * cm, 3.4 * cm]))

    # ===== 6. Ranking de Prioridades =====
    el.append(PageBreak())
    el.append(_h2("6. Ranking de Prioridades", styles))
    el.append(Paragraph("Fila de Ações Prioritárias — mesma lógica do Painel Gerencial da Rede.", styles["RedeSmall"]))
    prio = data["priorities"]
    if prio:
        rows = [[str(p.get("ordem", i + 1)), p.get("school_name"), p.get("acao")] for i, p in enumerate(prio[:30])]
        el.append(_bar_table(rows, ["#", "Unidade", "Ação recomendada"], [1.0 * cm, 5.0 * cm, 11.2 * cm]))
    else:
        el.append(Paragraph("Nenhuma ação prioritária no momento.", styles["RedeSmall"]))

    # ===== 7. Infraestrutura da Rede =====
    el.append(PageBreak())
    el.append(_h2("7. Infraestrutura da Rede", styles))
    rows = [[x["indicador"], str(x["com"]), str(x["sem"]), f"{x['pct_com']}%"] for x in data["infraestrutura"]]
    el.append(_bar_table(rows, ["Indicador", "Com", "Sem", "% Com"],
                         [9.0 * cm, 2.7 * cm, 2.7 * cm, 2.8 * cm]))

    # ===== 8. Obras e Intervenções =====
    el.append(_h2("8. Obras e Intervenções", styles))
    ob = data["obras"]
    el.append(Paragraph(f"Total de {ob['total_intervencoes']} intervenção(ões) em "
                        f"{ob['escolas_com_obras']} unidade(s).", styles["Normal"]))
    if ob["por_situacao"]:
        el.append(Spacer(1, 0.15 * cm)); el.append(Paragraph("<b>Por situação</b>", styles["Normal"]))
        el.append(_bar_table([[g["grupo"], str(g["qtd"])] for g in ob["por_situacao"]],
                             ["Situação", "Qtd."], [13.0 * cm, 4.2 * cm]))
    if ob["por_tipo"]:
        el.append(Spacer(1, 0.15 * cm)); el.append(Paragraph("<b>Por tipo de intervenção</b>", styles["Normal"]))
        el.append(_bar_table([[g["grupo"], str(g["qtd"])] for g in ob["por_tipo"]],
                             ["Tipo", "Qtd."], [13.0 * cm, 4.2 * cm]))
    if not ob["por_situacao"] and not ob["por_tipo"]:
        el.append(Paragraph("Nenhuma obra ou intervenção cadastrada na rede.", styles["RedeSmall"]))

    # ===== 9. Documentação =====
    el.append(_h2("9. Documentação", styles))
    rows = [[x["documento"], str(x["com"]), str(x["sem"]), f"{x['pct_com']}%"] for x in data["documentacao"]]
    el.append(_bar_table(rows, ["Documento", "Possuem", "Não possuem", "% Possuem"],
                         [9.0 * cm, 2.7 * cm, 2.7 * cm, 2.8 * cm]))

    # ===== 10. Diagnóstico Executivo =====
    el.append(PageBreak())
    el.append(_h2("10. Diagnóstico Executivo", styles))
    diag = data["diagnostico"]
    el.append(Paragraph("<b>Principais pontos fortes</b>", styles["Normal"]))
    el.append(_bullets(diag["pontos_fortes"], styles))
    el.append(Spacer(1, 0.2 * cm))
    el.append(Paragraph("<b>Principais fragilidades</b>", styles["Normal"]))
    el.append(_bullets(diag["fragilidades"], styles))
    el.append(Spacer(1, 0.2 * cm))
    el.append(Paragraph("<b>Áreas prioritárias para atuação da Secretaria</b>", styles["Normal"]))
    el.append(_bullets(diag["areas_prioritarias"], styles))

    # ===== 11. Plano de Ação Sugerido =====
    el.append(_h2("11. Plano de Ação Sugerido", styles))
    el.append(Paragraph("Recomendações consolidadas a partir da Fila de Prioridades do sistema.", styles["RedeSmall"]))
    plano = data["plano_acao"]
    if plano:
        rows = []
        for i, p in enumerate(plano, start=1):
            exemplos = ", ".join(p.get("exemplos", []))
            if p.get("escolas", 0) > len(p.get("exemplos", [])):
                exemplos += ", …"
            rows.append([str(i), p["recomendacao"], str(p["escolas"]), exemplos or "—"])
        el.append(_bar_table(rows, ["#", "Recomendação", "Unid.", "Exemplos"],
                             [0.9 * cm, 8.2 * cm, 1.5 * cm, 6.6 * cm]))
    else:
        el.append(Paragraph("Sem recomendações no momento — rede em situação regular.", styles["RedeSmall"]))

    # ===== 12. Conclusão =====
    el.append(_h2("12. Conclusão", styles))
    el.append(Paragraph(
        f"Este documento representa a fotografia da Rede Municipal de Ensino na data de sua emissão "
        f"({emitido} UTC) e foi gerado automaticamente pelo SIGESC a partir do Cadastro Técnico da "
        f"Unidade Escolar (CTUE). As informações refletem exclusivamente os dados cadastrados na "
        f"plataforma, consolidados sob o princípio de fonte única de dados (Single Source of Truth). "
        f"A evolução dos indicadores dependerá da atualização contínua dos cadastros pelas unidades "
        f"escolares e pela Secretaria Municipal de Educação.",
        styles["JustifyText"]))

    doc.build(el, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
