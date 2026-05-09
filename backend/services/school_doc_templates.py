"""Templates PDF oficiais de declarações escolares (G1.7 — Fev/2026).

Design institucional com brasão placeholder, cabeçalho da secretaria,
identificação do município, corpo declaratório, validade explícita e
selo de verificação (QR + código).

LGPD: apenas dados mínimos no PDF (nome, data nasc., escola, turma, ano).
CPF/RG não incluídos nesta versão do MVP.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, date
from typing import Literal, Optional

import segno
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

FrontendURL = os.environ.get("APP_FRONTEND_URL", "https://sigesc.app").rstrip("/")

DocType = Literal["matricula", "frequencia", "escolaridade"]

DOC_TITLES = {
    "matricula": "DECLARAÇÃO DE MATRÍCULA",
    "frequencia": "DECLARAÇÃO DE FREQUÊNCIA",
    "escolaridade": "DECLARAÇÃO DE ESCOLARIDADE",
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(
        "DocTitle", parent=s["Heading1"], fontSize=16, leading=20,
        alignment=TA_CENTER, textColor=colors.HexColor("#1F2937"),
        spaceAfter=6, fontName="Helvetica-Bold",
    ))
    s.add(ParagraphStyle(
        "InstitutionalHeader", parent=s["BodyText"], fontSize=11,
        leading=14, alignment=TA_CENTER,
        textColor=colors.HexColor("#374151"), fontName="Helvetica-Bold",
    ))
    s.add(ParagraphStyle(
        "InstitutionalSub", parent=s["BodyText"], fontSize=9,
        leading=12, alignment=TA_CENTER,
        textColor=colors.HexColor("#6B7280"),
    ))
    s.add(ParagraphStyle(
        "DeclarBody", parent=s["BodyText"], fontSize=12, leading=18,
        alignment=TA_JUSTIFY, firstLineIndent=1.5 * cm, spaceAfter=12,
    ))
    s.add(ParagraphStyle(
        "SignatureLabel", parent=s["BodyText"], fontSize=10,
        alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"),
    ))
    s.add(ParagraphStyle(
        "Footer", parent=s["BodyText"], fontSize=8, leading=11,
        textColor=colors.HexColor("#6B7280"),
    ))
    s.add(ParagraphStyle(
        "FooterBold", parent=s["BodyText"], fontSize=9, leading=12,
        textColor=colors.HexColor("#1F2937"), fontName="Helvetica-Bold",
    ))
    s.add(ParagraphStyle(
        "MonoSmall", parent=s["BodyText"], fontSize=7, leading=10,
        fontName="Courier", textColor=colors.HexColor("#374151"),
    ))
    return s


def _qr_image(url: str, size_cm: float = 2.8) -> Optional[Image]:
    try:
        qr = segno.make(url, error="H")
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=6, border=1)
        buf.seek(0)
        return Image(buf, width=size_cm * cm, height=size_cm * cm)
    except Exception:
        return None


def _format_br_date(iso_or_br: Optional[str]) -> str:
    if not iso_or_br:
        return "—"
    s = iso_or_br.strip()
    # Já em DD/MM/YYYY
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return s
    # ISO YYYY-MM-DD
    try:
        d = date.fromisoformat(s[:10])
        return d.strftime("%d/%m/%Y")
    except Exception:
        return s


def _format_today() -> str:
    now = datetime.now()
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return f"{now.day} de {meses[now.month - 1]} de {now.year}"


def _institutional_header(context: dict, styles) -> list:
    """Cabeçalho oficial: secretaria + município + escola."""
    secretariat = context.get("secretariat_name") or "Secretaria Municipal de Educação"
    city = context.get("city") or "—"
    state = context.get("state") or "—"
    school = context.get("school_name") or "—"

    # Placeholder de brasão (caso não tenha logo custom)
    brasao_placeholder = Table(
        [[Paragraph(
            '<para alignment="center">'
            '<font color="#3730A3" size="24"><b>⬢</b></font><br/>'
            '<font color="#6B7280" size="7">BRASÃO</font>'
            '</para>',
            styles["BodyText"],
        )]],
        colWidths=[2 * cm],
    )
    brasao_placeholder.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    header_info = [
        Paragraph(
            f'<b>{secretariat}</b>'.upper(),
            styles["InstitutionalHeader"],
        ),
        Paragraph(
            f"{city.upper()} · {state.upper()}",
            styles["InstitutionalSub"],
        ),
        Spacer(1, 3),
        Paragraph(
            f'<b>{school.upper()}</b>',
            styles["InstitutionalSub"],
        ),
    ]

    header_table = Table(
        [[brasao_placeholder, header_info]],
        colWidths=[2.5 * cm, 14 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [
        header_table,
        Spacer(1, 6),
        Table(
            [[""]],
            colWidths=[16.5 * cm], rowHeights=[1],
            style=TableStyle([
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#6366F1")),
            ]),
        ),
        Spacer(1, 18),
    ]


def _declaration_body(doc_type: DocType, context: dict, styles) -> list:
    """Corpo declaratório (texto formal) por tipo."""
    student_name = (context.get("student_name") or "—").upper()
    birth_date = _format_br_date(context.get("student_birth_date"))
    school = context.get("school_name") or "—"
    class_name = context.get("class_name") or "—"
    academic_year = context.get("academic_year") or "—"
    grade = context.get("grade_level") or "—"
    shift = context.get("shift") or ""
    purpose = context.get("purpose") or ""
    frequencia = context.get("frequencia_pct")
    bimestre = context.get("bimestre")
    serie_concluida = context.get("serie_concluida")

    purpose_text = f" para fins de <b>{purpose}</b>" if purpose else ""

    if doc_type == "matricula":
        body = (
            f"Declaramos, para os devidos fins, que <b>{student_name}</b>, "
            f"nascido(a) em <b>{birth_date}</b>, encontra-se regularmente "
            f"<b>matriculado(a)</b> nesta unidade de ensino "
            f"<b>{school}</b>, cursando a <b>{grade}</b> "
            f"na turma <b>{class_name}</b>"
            + (f" ({shift})" if shift else "")
            + f" no ano letivo de <b>{academic_year}</b>{purpose_text}."
        )
    elif doc_type == "frequencia":
        freq_txt = f"{frequencia}%" if frequencia is not None else "—"
        bim_txt = f" referente ao <b>{bimestre}</b>" if bimestre else ""
        body = (
            f"Declaramos, para os devidos fins, que <b>{student_name}</b>, "
            f"nascido(a) em <b>{birth_date}</b>, matriculado(a) na "
            f"<b>{grade}</b> (turma <b>{class_name}</b>) "
            f"desta unidade de ensino <b>{school}</b>, "
            f"apresenta <b>frequência escolar de {freq_txt}</b> no ano "
            f"letivo de <b>{academic_year}</b>{bim_txt}{purpose_text}."
        )
    else:  # escolaridade
        serie_txt = serie_concluida or grade
        body = (
            f"Declaramos, para os devidos fins, que <b>{student_name}</b>, "
            f"nascido(a) em <b>{birth_date}</b>, "
            f"<b>concluiu/cursa</b> o nível <b>{serie_txt}</b> "
            f"nesta unidade de ensino <b>{school}</b>, "
            f"no ano letivo de <b>{academic_year}</b>{purpose_text}."
        )

    return [
        Paragraph(body, styles["DeclarBody"]),
        Spacer(1, 30),
        Paragraph(
            f"{(context.get('city') or '—')}, {_format_today()}.",
            styles["SignatureLabel"],
        ),
        Spacer(1, 40),
        Table(
            [[""]], colWidths=[9 * cm], rowHeights=[1],
            style=TableStyle([
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#374151")),
            ]),
            hAlign="CENTER",
        ),
        Paragraph(
            f'<b>{(context.get("issuer_name") or "Secretaria da Escola").upper()}</b>',
            styles["SignatureLabel"],
        ),
        Paragraph(
            f'{context.get("issuer_role") or "Secretário(a) Escolar"}',
            styles["SignatureLabel"],
        ),
    ]


def _validity_footer(context: dict, styles) -> list:
    """Rodapé obrigatório: código, validade, QR, instrução."""
    code = context.get("code") or "—"
    valid_until = context.get("valid_until")
    verification_token = context.get("verification_token")
    portal_url = f"{FrontendURL}/verificar"
    if verification_token and code != "—":
        # URL curta /v/{token} — carregada apenas no QR (owner spec Fev/2026).
        qr_url = f"{FrontendURL}/v/{verification_token}"
    else:
        qr_url = f"{portal_url}/{code}" if code != "—" else portal_url
    qr = _qr_image(qr_url)

    valid_str = _format_br_date(valid_until) if valid_until else "—"

    left_cell = [
        Paragraph("<b>Verificação de Autenticidade</b>", styles["FooterBold"]),
        Spacer(1, 3),
        Paragraph(
            "Este documento pode ser validado publicamente sem login:",
            styles["Footer"],
        ),
        Spacer(1, 2),
        Paragraph("<b>Código:</b>", styles["Footer"]),
        Paragraph(
            f'<font name="Courier-Bold" size="11" color="#3730A3">{code}</font>',
            styles["Footer"],
        ),
        Spacer(1, 3),
        Paragraph(
            f'<b>Portal:</b> <font name="Courier">{portal_url}</font>',
            styles["Footer"],
        ),
        Spacer(1, 3),
        Paragraph(
            f'<font color="#DC2626"><b>Válido até:</b> {valid_str}</font>',
            styles["Footer"],
        ),
        Spacer(1, 3),
        Paragraph(
            "Escaneie o QR Code ou digite o código no portal para "
            "confirmar a autenticidade e integridade deste documento.",
            styles["Footer"],
        ),
    ]
    box = Table(
        [[left_cell, qr or Paragraph("—", styles["Footer"])]],
        colWidths=[12 * cm, 4.5 * cm],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6366F1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [Spacer(1, 16), box]


def build_school_document_pdf(doc_type: DocType, context: dict) -> bytes:
    """Gera o PDF de uma declaração escolar. Espera o context já preenchido
    com todos os dados necessários (ver `school_docs_service.build_context`).
    """
    styles = _styles()
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=DOC_TITLES.get(doc_type, "Declaração Escolar"),
    )

    story = []
    story.extend(_institutional_header(context, styles))
    story.append(Paragraph(DOC_TITLES.get(doc_type, "DECLARAÇÃO"), styles["DocTitle"]))
    story.append(Spacer(1, 20))
    story.extend(_declaration_body(doc_type, context, styles))
    story.extend(_validity_footer(context, styles))
    pdf.build(story)
    return buf.getvalue()
