"""
Dossiê Institucional da Unidade Escolar (CTUE) — geração de PDF.

Este documento é APENAS uma representação do CTUE. Não possui lógica/regra/cálculo
próprio: todo o conteúdo vem de (1) dados do cadastro da escola e (2) do resultado do
CTUEConformityService (conformidade, completude, maturidade, atualização).
"""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from pdf.utils import get_logo_image, get_styles

_STATUS_PT = {
    "conforme": "Conforme", "atencao": "Atenção", "critico": "Crítico",
    "nao_conforme": "Não Conforme", "nao_avaliado": "Não avaliado",
}
_STATUS_COLOR = {
    "conforme": colors.HexColor("#16a34a"), "atencao": colors.HexColor("#ca8a04"),
    "critico": colors.HexColor("#ea580c"), "nao_conforme": colors.HexColor("#dc2626"),
    "nao_avaliado": colors.HexColor("#6b7280"),
}
_BLUE = colors.HexColor("#1e40af")
_GRAY = colors.HexColor("#f3f4f6")


def _v(val, none="Não informado"):
    if val is None or val == "":
        return none
    return str(val)


def _bool(val):
    return "Sim" if val else "Não"


def _section_by_key(result, key):
    return next((s for s in result.get("sections", []) if s["key"] == key), None)


def _kv_table(rows, styles, col_widths=(6 * cm, 11 * cm)):
    data = [[Paragraph(f"<b>{k}</b>", styles["Normal"]), Paragraph(_v(val), styles["Normal"])] for k, val in rows]
    t = Table(data, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), _GRAY),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _heading(text, styles):
    return Paragraph(text, styles["DossieH2"])


def generate_dossie_pdf(school: dict, result: dict, mantenedora: dict = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            title=f"Dossiê Institucional - {school.get('name', '')}")
    styles = get_styles()
    if "DossieH2" not in styles:
        styles.add(ParagraphStyle(name="DossieH2", parent=styles["Heading2"], fontSize=12,
                                  textColor=_BLUE, spaceBefore=12, spaceAfter=6, alignment=TA_LEFT))
    if "DossieSmall" not in styles:
        styles.add(ParagraphStyle(name="DossieSmall", parent=styles["Normal"], fontSize=9,
                                  textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER))

    el = []
    logo = get_logo_image(width=2.2 * cm, height=2.2 * cm)
    mant_nome = (mantenedora or {}).get("nome") or (mantenedora or {}).get("name") or "Secretaria Municipal de Educação"

    header_cell = [
        Paragraph(f"<b>{mant_nome}</b>", styles["CenterText"]),
        Paragraph("DOSSIÊ INSTITUCIONAL DA UNIDADE ESCOLAR", styles["MainTitle"]),
        Paragraph(f"<b>{_v(school.get('name'))}</b>", styles["SubTitle"]),
    ]
    if logo:
        head = Table([[logo, header_cell]], colWidths=[2.6 * cm, 14.4 * cm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el.append(head)
    else:
        el.extend(header_cell)
    emitido = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    el.append(Paragraph(f"Documento gerado a partir do Cadastro Técnico da Unidade Escolar (CTUE) — emitido em {emitido} (UTC)", styles["DossieSmall"]))
    el.append(Spacer(1, 0.4 * cm))

    # 1. Identificação
    el.append(_heading("1. Identificação da Unidade", styles))
    el.append(_kv_table([
        ("Nome", school.get("name")),
        ("Código INEP", school.get("inep_code")),
        ("Sigla", school.get("sigla")),
        ("CNPJ", school.get("cnpj")),
        ("Tipo de Unidade", school.get("tipo_unidade")),
        ("Característica", school.get("caracteristica_escolar")),
        ("Zona", "Urbana" if school.get("zona_localizacao") == "urbana" else "Rural" if school.get("zona_localizacao") == "rural" else None),
        ("Situação de Funcionamento", school.get("situacao_funcionamento")),
    ], styles))

    # 2. Dados Administrativos + Gestor
    el.append(_heading("2. Dados Administrativos e Gestão", styles))
    endereco = ", ".join([p for p in [school.get("logradouro"), school.get("numero"), school.get("bairro"),
                                       school.get("municipio"), school.get("estado")] if p]) or None
    el.append(_kv_table([
        ("Endereço", endereco),
        ("CEP", school.get("cep")),
        ("Georreferência", f"{school.get('latitude')}, {school.get('longitude')}" if school.get("latitude") and school.get("longitude") else None),
        ("Dependência Administrativa", school.get("dependencia_administrativa")),
        ("Esfera Administrativa", school.get("esfera_administrativa")),
        ("Órgão Responsável", school.get("orgao_responsavel")),
        ("Ato de Autorização/Reconhecimento", school.get("regulamentacao")),
        ("Gestor(a) Principal", school.get("gestor_principal")),
        ("Cargo do Gestor(a)", school.get("cargo_gestor")),
        ("Secretário(a) Escolar", school.get("secretario_escolar")),
    ], styles))

    # 3. Quadro-resumo de Conformidade + Completude
    el.append(_heading("3. Quadro-resumo de Conformidade e Completude", styles))
    hdr = ["Seção", "Conformidade", "Situação", "Completude", "Itens"]
    data = [hdr]
    style_rows = []
    for i, s in enumerate(result.get("sections", []), start=1):
        avaliada = s.get("avaliada", True)
        status = s.get("status", "nao_avaliado")
        conf = "—" if not avaliada else f"{s.get('conformidade', 0)}%"
        comp = "—" if not avaliada else f"{s.get('completude', 0)}%"
        itens = "—" if not avaliada else f"{s.get('itens_preenchidos', 0)}/{s.get('itens_total', 0)}"
        data.append([s["label"], conf, _STATUS_PT.get(status, status), comp, itens])
        style_rows.append((i, _STATUS_COLOR.get(status, colors.black)))
    tbl = Table(data, colWidths=[6.2 * cm, 2.6 * cm, 3 * cm, 2.6 * cm, 2.6 * cm])
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_idx, color in style_rows:
        ts.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), color))
        ts.append(("FONTNAME", (2, row_idx), (2, row_idx), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(ts))
    el.append(tbl)

    # 4. Infraestrutura
    el.append(_heading("4. Infraestrutura Física e Ambientes", styles))
    ambientes = []
    amb_map = [("possui_biblioteca", "Biblioteca"), ("possui_lab_ciencias", "Lab. Ciências"),
               ("possui_lab_informatica", "Lab. Informática"), ("possui_quadra", "Quadra"),
               ("possui_cozinha", "Cozinha"), ("possui_refeitorio", "Refeitório"),
               ("possui_patio", "Pátio"), ("possui_parque", "Parque"), ("possui_auditorio", "Auditório"),
               ("possui_almoxarifado", "Almoxarifado")]
    for k, lbl in amb_map:
        if school.get(k):
            ambientes.append(lbl)
    el.append(_kv_table([
        ("Nº de Salas de Aula", school.get("numero_salas_aula")),
        ("Capacidade Total de Alunos", school.get("capacidade_total_alunos")),
        ("Nº de Banheiros", school.get("numero_banheiros")),
        ("Sala de Recursos (AEE)", school.get("salas_recursos_multifuncionais")),
        ("Ambientes existentes", ", ".join(ambientes) if ambientes else None),
    ], styles))

    # 5. Acessibilidade
    el.append(_heading("5. Acessibilidade", styles))
    el.append(_kv_table([
        ("Rampas", _bool(school.get("possui_rampas"))),
        ("Corrimão", _bool(school.get("possui_corrimao"))),
        ("Banheiros Acessíveis (qtd)", school.get("banheiros_acessiveis")),
        ("Sinalização Tátil", _bool(school.get("sinalizacao_tatil"))),
    ], styles))

    # 6. Segurança
    el.append(_heading("6. Segurança", styles))
    el.append(_kv_table([
        ("Extintores (qtd)", school.get("qtd_extintores")),
        ("Saídas de Emergência (qtd)", school.get("saidas_emergencia")),
        ("Brigada de Incêndio", _bool(school.get("brigada_incendio"))),
        ("Plano de Evacuação", _bool(school.get("plano_evacuacao"))),
        ("Câmeras de Segurança (qtd)", school.get("qtd_cameras")),
        ("Cercamento/Muro", _bool(school.get("possui_cercamento"))),
    ], styles))

    # 7. Água e Saneamento
    el.append(_heading("7. Água, Saneamento e Energia", styles))
    el.append(_kv_table([
        ("Abastecimento de Água", school.get("abastecimento_agua")),
        ("Energia Elétrica", school.get("energia_eletrica")),
        ("Esgotamento Sanitário", school.get("saneamento")),
        ("Destinação de Resíduos", school.get("coleta_lixo")),
    ], styles))

    # 8. Equipamentos
    el.append(_heading("8. Equipamentos", styles))
    el.append(_kv_table([
        ("Computadores", school.get("qtd_computadores")),
        ("Tablets", school.get("qtd_tablets")),
        ("Projetores", school.get("qtd_projetores")),
        ("Impressoras", school.get("qtd_impressoras")),
        ("Televisores", school.get("qtd_televisores")),
        ("Tamanho do Acervo (biblioteca)", school.get("tamanho_acervo")),
    ], styles))

    # 9. Observações (quando existentes)
    obs = school.get("observacoes_tecnicas")
    if obs:
        el.append(_heading("9. Observações Técnicas", styles))
        el.append(Paragraph(_v(obs), styles["JustifyText"]))

    # Resumo objetivo final
    el.append(Spacer(1, 0.3 * cm))
    el.append(_heading("Resumo Institucional", styles))
    selo = result.get("selo_geral", "nao_avaliado")
    mat = result.get("maturidade", {})
    atual = result.get("atualizacao", {})
    resumo = Table([
        ["Conformidade Geral", f"{result.get('conformidade_geral', 0)}%", "Situação", _STATUS_PT.get(selo, selo)],
        ["Completude Geral", f"{result.get('completude_geral', 0)}%", "Nível de Maturidade", f"Nível {mat.get('nivel', '-')} — {mat.get('nome', '')}"],
        ["Última Atualização", atual.get("label", "—"), "Perfil de Avaliação", result.get("profile", "default")],
    ], colWidths=[4.2 * cm, 4.4 * cm, 4.2 * cm, 4.2 * cm])
    resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _GRAY),
        ("BACKGROUND", (2, 0), (2, -1), _GRAY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (1, 0), _STATUS_COLOR.get(selo, colors.black)),
        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    el.append(resumo)
    el.append(Spacer(1, 0.3 * cm))
    el.append(Paragraph(
        "Documento gerado automaticamente pelo SIGESC a partir do Cadastro Técnico da Unidade Escolar (CTUE). "
        "As informações refletem exclusivamente os dados cadastrados na plataforma.",
        styles["DossieSmall"]))

    doc.build(el)
    return buf.getvalue()
