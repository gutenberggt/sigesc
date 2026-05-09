"""Rodapé de Verificação Pública para PDFs SIGESC.

Centraliza o componente "Código + QR + URL do portal + Validade" para
ser injetado em qualquer PDF gerado pelo SIGESC (Histórico, Certificado,
Boletim, etc.).

Existem 2 modos:
  • Modo Platypus (SimpleDocTemplate / Story):
        from pdf.verification_footer import build_verification_flowables
        story.extend(build_verification_flowables(code, valid_until))

  • Modo Canvas (canvas.Canvas direto, ex.: certificado em landscape):
        from pdf.verification_footer import draw_verification_footer_on_canvas
        draw_verification_footer_on_canvas(c, x, y, code, valid_until, width=...)
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

import segno
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage, Paragraph, Spacer, Table, TableStyle,
)

logger = logging.getLogger(__name__)

# URL do portal público (pode ser sobrescrita por env var)
DEFAULT_PORTAL_URL = (
    os.environ.get("PUBLIC_PORTAL_URL")
    or os.environ.get("FRONTEND_URL", "https://app.sigesc.com.br").rstrip("/")
    + "/verificar"
)


def _portal_url() -> str:
    """URL base do portal de verificação por código humano (`/verificar/{code}`).

    Mantida para fallback quando não há `verification_token`.
    """
    env = os.environ.get("PUBLIC_PORTAL_URL")
    if env:
        return env.rstrip("/") + ("" if env.rstrip("/").endswith("/verificar") else "/verificar")
    fe = os.environ.get("FRONTEND_URL", "https://app.sigesc.com.br").rstrip("/")
    return f"{fe}/verificar"


def _short_verify_url(token: Optional[str]) -> Optional[str]:
    """URL curta `/v/{token}` quando há `verification_token` opaco.

    Owner spec (Fev/2026): QR carrega APENAS este link, nunca dados.
    """
    if not token:
        return None
    fe = os.environ.get("FRONTEND_URL", "https://app.sigesc.com.br").rstrip("/")
    return f"{fe}/v/{token}"


def _qr_png_bytes(url: str) -> bytes:
    """Gera PNG do QR Code apontando para `url` (capacidade alta)."""
    qr = segno.make(url, error="H")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=6, border=1)
    return buf.getvalue()


def _format_br_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        from datetime import datetime
        s = iso[:10] if "T" in iso else iso
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except Exception:
        return iso


# ============================================================
# MODO PLATYPUS (SimpleDocTemplate / Story)
# ============================================================
def build_verification_flowables(
    code: Optional[str],
    valid_until: Optional[str] = None,
    *,
    label: str = "Verificação de Autenticidade",
    verification_token: Optional[str] = None,
) -> list:
    """Constrói flowables (Spacer + Table) a serem appendados ao story.

    `code` pode ser None: nesse caso retorna lista vazia (não desenha rodapé).
    Quando `verification_token` é fornecido, o QR carrega a URL curta
    `/v/{token}` (recomendado — owner spec Fev/2026). O `code` humano
    permanece visível no rodapé para digitação manual.
    """
    if not code:
        return []

    portal = _portal_url()
    short_url = _short_verify_url(verification_token)
    qr_url = short_url or f"{portal}/{code}"

    style_bold = ParagraphStyle(
        "VerifFooterBold", fontName="Helvetica-Bold", fontSize=8,
        textColor=colors.HexColor("#3730A3"), leading=10,
    )
    style_body = ParagraphStyle(
        "VerifFooter", fontName="Helvetica", fontSize=7,
        textColor=colors.HexColor("#374151"), leading=10,
    )

    try:
        png = _qr_png_bytes(qr_url)
        qr_img = RLImage(io.BytesIO(png), width=2.6 * cm, height=2.6 * cm)
    except Exception as e:
        logger.warning("Falha ao gerar QR para %s: %s", code, e)
        qr_img = Paragraph("—", style_body)

    valid_str = _format_br_date(valid_until) if valid_until else None

    left_cell = [
        Paragraph(f"<b>{label}</b>", style_bold),
        Spacer(1, 2),
        Paragraph(
            "Este documento pode ser validado publicamente sem login:",
            style_body,
        ),
        Spacer(1, 2),
        Paragraph(
            f'<b>Código:</b> '
            f'<font name="Courier-Bold" size="9" color="#3730A3">{code}</font>',
            style_body,
        ),
        Paragraph(
            f'<b>Portal:</b> <font name="Courier">{portal}</font>',
            style_body,
        ),
    ]
    if valid_str:
        left_cell.append(
            Paragraph(
                f'<font color="#DC2626"><b>Válido até:</b> {valid_str}</font>',
                style_body,
            )
        )
    left_cell.append(
        Paragraph(
            "Escaneie o QR Code ou digite o código no portal para "
            "confirmar a autenticidade e integridade deste documento.",
            style_body,
        )
    )

    box = Table(
        [[left_cell, qr_img]],
        colWidths=[12 * cm, 3.2 * cm],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6366F1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 10), box]


# ============================================================
# MODO CANVAS (canvas.Canvas direto)
# ============================================================
def draw_verification_footer_on_canvas(
    c,
    x: float,
    y: float,
    code: Optional[str],
    valid_until: Optional[str] = None,
    *,
    width: float = 17 * cm,
    height: float = 2.8 * cm,
    verification_token: Optional[str] = None,
):
    """Desenha o rodapé de verificação direto em um canvas (modo certificado).

    `(x, y)` é o canto INFERIOR-ESQUERDO do bloco.
    `width`/`height` definem o tamanho do bloco.
    `code` é o código curto. Se None, não desenha nada.
    Se `verification_token` for fornecido, QR carrega URL curta `/v/{token}`.
    """
    if not code:
        return

    portal = _portal_url()
    short_url = _short_verify_url(verification_token)
    qr_url = short_url or f"{portal}/{code}"

    # Caixa de fundo
    c.saveState()
    c.setFillColorRGB(0.92, 0.94, 1.0)  # #EEF2FF
    c.setStrokeColor(colors.HexColor("#6366F1"))
    c.setLineWidth(0.5)
    c.rect(x, y, width, height, fill=1, stroke=1)

    # QR à direita
    qr_size = height - 0.4 * cm
    qr_x = x + width - qr_size - 0.2 * cm
    qr_y = y + (height - qr_size) / 2

    try:
        png = _qr_png_bytes(qr_url)
        from reportlab.lib.utils import ImageReader
        c.drawImage(
            ImageReader(io.BytesIO(png)), qr_x, qr_y,
            width=qr_size, height=qr_size, mask='auto',
        )
    except Exception as e:
        logger.warning("Falha QR canvas %s: %s", code, e)

    # Texto à esquerda
    text_x = x + 0.3 * cm
    text_top_y = y + height - 0.4 * cm

    c.setFillColor(colors.HexColor("#3730A3"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(text_x, text_top_y, "Verificação de Autenticidade")

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 7)
    c.drawString(
        text_x, text_top_y - 11,
        "Validável publicamente sem login. Use o código ou QR Code:",
    )

    c.setFillColor(colors.HexColor("#3730A3"))
    c.setFont("Courier-Bold", 9)
    c.drawString(text_x, text_top_y - 24, f"Código: {code}")

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 7)
    c.drawString(text_x, text_top_y - 35, f"Portal: {portal}")

    if valid_until:
        c.setFillColor(colors.HexColor("#DC2626"))
        c.setFont("Helvetica-Bold", 7)
        c.drawString(
            text_x, text_top_y - 46,
            f"Válido até: {_format_br_date(valid_until)}",
        )

    c.restoreState()
